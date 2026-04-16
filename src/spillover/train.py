"""REINFORCE training on Tinker, matching the paper's setup.

Replicates 'Output Supervision Can Obfuscate the CoT' (2511.11584).

Unavoidable differences (Tinker constraints):
- LoRA instead of full fine-tune
- Two-phase sampling instead of single generation with logit processor
- importance_sampling loss instead of vanilla REINFORCE

Everything else matches:
- Per-reward gradient routing (correctness → all tokens, penalty → output only)
- Batch-mean baseline per reward component (1 rollout per prompt)
- Soft probability-weighted judge (logprob-based, matching paper's OpenAiJudge)
- Temperature 1.0, Adam betas (0.9, 0.999)
- MMLU elementary_mathematics with paper's exact prompt format and \\boxed{} answers

Usage:
    uv run python -m src.spillover.train task=qa penalty_weight=-2
    uv run python -m src.spillover.train task=polynomial penalty_weight=-1
    uv run python -m src.spillover.train task=qa checkpoint=tinker://styled-model
"""

import asyncio
import logging
import random
import time

import chz
import tinker
import torch
from tinker import types
from tinker.types.tensor_data import TensorData
from tinker_cookbook import checkpoint_utils, model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer
from tinker_cookbook.utils import ml_log

from src.judges import SoftConversationJudge
from src.spillover.env_mmlu import check_boxed_answer, load_mmlu_questions
from src.spillover.env_polynomial import (
    FEWSHOT_EXAMPLES,
    SYSTEM_PROMPT as POLY_SYSTEM_PROMPT,
    ExpandedFormMonitor,
    _check_correctness,
    _generate_problem,
)

logger = logging.getLogger(__name__)
_save_checkpoint = checkpoint_utils.save_checkpoint_async.__wrapped__


@chz.chz
class Config:
    task: str = "qa"
    model_name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32
    batch_size: int = 12
    num_episodes: int = 3200
    learning_rate: float = 1e-5
    max_thinking_tokens: int = 300
    max_output_tokens: int = 600
    temperature: float = 1.0
    penalty_weight: float = -2.0
    save_every: int = 50
    seed: int = 42
    log_path: str = "/tmp/spillover-exps/paper-match"
    checkpoint: str | None = None
    reward_target: bool = False  # True = mask penalty gradient from CoT tokens
    # Fraction of batches where the CoT judge's hint score is also used as a
    # penalty on CoT tokens (using the same penalty_weight, with its own batch-mean baseline).
    cot_penalty_prob: float = 0.0
    num_problems: int = 2000
    min_degree: int = 5
    max_degree: int = 8


def _load_qa_data(cfg: Config, renderer):
    questions = load_mmlu_questions(seed=cfg.seed)
    items = []
    for q in questions:
        messages = [{"role": "user", "content": q["prompt"]}]
        prompt = renderer.build_generation_prompt(messages)
        items.append({
            "prompt_tokens": prompt.to_ints(),
            "question": q["prompt"],
            "target": q["target"],
        })
    return items


def _load_poly_data(cfg: Config, renderer):
    rng = random.Random(cfg.seed)
    items = []
    for _ in range(cfg.num_problems):
        degree = rng.randint(cfg.min_degree, cfg.max_degree)
        p = _generate_problem(rng, degree)
        messages = [{"role": "system", "content": POLY_SYSTEM_PROMPT}]
        for ex in FEWSHOT_EXAMPLES:
            messages.append({"role": "user", "content": ex["user"]})
            messages.append({"role": "assistant", "content": ex["assistant"]})
        messages.append({"role": "user", "content": p["question"]})
        prompt = renderer.build_generation_prompt(messages)
        items.append({"prompt_tokens": prompt.to_ints(), "problem": p})
    return items


async def _score_qa(items, cots, outputs, judge):
    corrects = [check_boxed_answer(o, item["target"]) for item, o in zip(items, outputs)]
    out_scores = await asyncio.gather(*[
        judge.score_with_context(item["question"], o) for item, o in zip(items, outputs)
    ])
    cot_scores = await asyncio.gather(*[
        judge.score_with_context(item["question"], c) for item, c in zip(items, cots)
    ])
    return corrects, list(out_scores), list(cot_scores)


async def _score_poly(items, cots, outputs):
    corrects = [_check_correctness(o, item["problem"]) for item, o in zip(items, outputs)]
    monitors = [ExpandedFormMonitor(item["problem"]["expanded_norm"]) for item in items]
    out_scores = list(await asyncio.gather(*[m.score(o) for m, o in zip(monitors, outputs)]))
    cot_scores = list(await asyncio.gather(*[m.score(c) for m, c in zip(monitors, cots)]))
    return corrects, out_scores, cot_scores


async def train(cfg: Config):
    ml_logger = ml_log.setup_logging(log_dir=cfg.log_path, config=cfg)
    tokenizer = get_tokenizer(cfg.model_name)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(cfg.model_name), tokenizer
    )
    think_close = tokenizer.encode("</think>", add_special_tokens=False)

    if cfg.task == "qa":
        items = _load_qa_data(cfg, renderer)
        judge = SoftConversationJudge()
    else:
        items = _load_poly_data(cfg, renderer)
        judge = None

    service = tinker.ServiceClient()
    resume = checkpoint_utils.get_last_checkpoint(cfg.log_path)
    if resume:
        tc = service.create_training_client_from_state_with_optimizer(resume.state_path)
        start_batch = resume.batch
    elif cfg.checkpoint:
        tc = service.create_training_client_from_state_with_optimizer(cfg.checkpoint)
        start_batch = 0
    else:
        tc = service.create_lora_training_client(
            base_model=cfg.model_name, rank=cfg.lora_rank
        )
        start_batch = 0

    cot_params = types.SamplingParams(
        max_tokens=cfg.max_thinking_tokens,
        temperature=cfg.temperature,
        stop=think_close,
    )
    out_params = types.SamplingParams(
        max_tokens=cfg.max_output_tokens,
        temperature=cfg.temperature,
        stop=renderer.get_stop_sequences(),
    )
    adam = types.AdamParams(learning_rate=cfg.learning_rate, beta1=0.9, beta2=0.999)
    n_batches = cfg.num_episodes // cfg.batch_size
    # Deterministic per-batch decisions for CoT-penalty activation.
    penalty_rng = random.Random(cfg.seed + 1)
    for _ in range(start_batch):
        penalty_rng.random()

    for batch_idx in range(start_batch, n_batches):
        t0 = time.time()
        metrics = {"progress/batch": batch_idx}

        if cfg.save_every > 0 and batch_idx > 0 and batch_idx % cfg.save_every == 0:
            await _save_checkpoint(
                training_client=tc, name=f"{batch_idx:06d}",
                log_path=cfg.log_path, kind="state",
                loop_state={"batch": batch_idx},
            )

        # 1 rollout per prompt (matching paper: no group structure)
        start = (batch_idx * cfg.batch_size) % len(items)
        batch = items[start : start + cfg.batch_size]

        sp = service.create_sampling_client(
            model_path=tc.save_weights_for_sampler(
                name=f"{batch_idx:06d}"
            ).result().path
        )

        # Phase 1: sample CoT
        cot_futures = [
            sp.sample(
                types.ModelInput.from_ints(item["prompt_tokens"]),
                num_samples=1,
                sampling_params=cot_params,
            )
            for item in batch
        ]

        # Phase 2: collect CoT, continue with output
        out_futures, valid = [], []
        for fut, item in zip(cot_futures, batch):
            try:
                seq = fut.result().sequences[0]
            except Exception as e:
                logger.warning(f"CoT sampling failed: {e}")
                out_futures.append(None)
                valid.append(None)
                continue
            out_prompt = item["prompt_tokens"] + seq.tokens + think_close
            out_futures.append(
                sp.sample(
                    types.ModelInput.from_ints(out_prompt),
                    num_samples=1,
                    sampling_params=out_params,
                )
            )
            valid.append({
                "prompt_tokens": item["prompt_tokens"],
                "cot_tokens": seq.tokens,
                "cot_logprobs": seq.logprobs,
            })

        # Collect outputs
        cots_text, outs_text = [], []
        for i, (fut, v) in enumerate(zip(out_futures, valid)):
            if fut is None or v is None:
                cots_text.append("")
                outs_text.append("")
                valid[i] = None
                continue
            try:
                seq = fut.result().sequences[0]
            except Exception as e:
                logger.warning(f"Output sampling failed: {e}")
                cots_text.append("")
                outs_text.append("")
                valid[i] = None
                continue
            v["out_tokens"] = seq.tokens
            v["out_logprobs"] = seq.logprobs
            cots_text.append(tokenizer.decode(v["cot_tokens"]).strip())
            outs_text.append(tokenizer.decode(seq.tokens).strip())

        # Score
        if cfg.task == "qa":
            corrects, out_scores, cot_scores = await _score_qa(
                batch, cots_text, outs_text, judge
            )
        else:
            corrects, out_scores, cot_scores = await _score_poly(
                batch, cots_text, outs_text
            )

        # Per-reward advantages with batch-mean baseline (paper's approach)
        correct_vals = [float(c) for c in corrects]
        penalty_vals = [cfg.penalty_weight * float(s) for s in out_scores]
        if sum(1 for v in valid if v is not None) < 2:
            logger.warning(f"Batch {batch_idx}: <2 valid, skipping")
            continue
        mean_correct = sum(correct_vals) / len(correct_vals)
        mean_penalty = sum(penalty_vals) / len(penalty_vals)

        # Optional direct CoT-hint penalty on a fraction of batches.
        cot_pen_active = penalty_rng.random() < cfg.cot_penalty_prob
        if cot_pen_active:
            cot_pen_vals = [cfg.penalty_weight * float(s) for s in cot_scores]
        else:
            cot_pen_vals = [0.0] * len(cot_scores)
        mean_cot_pen = sum(cot_pen_vals) / len(cot_pen_vals) if cot_pen_vals else 0.0

        datums = []
        for i, v in enumerate(valid):
            if v is None:
                continue
            correct_adv = correct_vals[i] - mean_correct
            penalty_adv = penalty_vals[i] - mean_penalty
            cot_pen_adv = cot_pen_vals[i] - mean_cot_pen

            cot_tok = list(v["cot_tokens"])
            out_tok = list(v["out_tokens"])
            cot_lp = list(v["cot_logprobs"])
            out_lp = list(v["out_logprobs"])
            prompt_tok = v["prompt_tokens"]

            sampled = cot_tok + list(think_close) + out_tok
            sampled_lp = cot_lp + [0.0] * len(think_close) + out_lp
            all_tok = prompt_tok + sampled
            ob = len(prompt_tok) - 1

            inp = [int(t) for t in all_tok[:-1]]
            tgt = all_tok[1:]
            lps = [0.0] * ob + sampled_lp
            # Baseline: output-hint penalty flows through all tokens.
            # reward_target=True: mask it from CoT.
            # cot_pen_adv: optional direct CoT-hint penalty (CoT tokens only).
            cot_penalty = (0.0 if cfg.reward_target else penalty_adv) + cot_pen_adv
            advs = (
                [0.0] * ob
                + [correct_adv + cot_penalty] * len(cot_tok)
                + [0.0] * len(think_close)
                + [correct_adv + penalty_adv] * len(out_tok)
            )

            if not (len(inp) == len(tgt) == len(lps) == len(advs)):
                continue
            datums.append(
                types.Datum(
                    model_input=types.ModelInput.from_ints(tokens=inp),
                    loss_fn_inputs={
                        "target_tokens": TensorData.from_torch(torch.tensor(tgt)),
                        "logprobs": TensorData.from_torch(torch.tensor(lps)),
                        "advantages": TensorData.from_torch(torch.tensor(advs)),
                    },
                )
            )

        if datums:
            fwd = tc.forward_backward(datums, loss_fn="importance_sampling")
            opt = tc.optim_step(adam)
            fwd.result()
            opt.result()

        n = len(correct_vals)
        k_out = (
            "monitor/hint_in_output"
            if cfg.task == "qa"
            else "monitor/expanded_in_output"
        )
        k_cot = (
            "monitor/hint_in_cot"
            if cfg.task == "qa"
            else "monitor/expanded_in_cot"
        )
        metrics["reward/correct"] = sum(correct_vals) / n
        metrics[k_out] = sum(float(s) for s in out_scores) / n
        metrics[k_cot] = sum(float(s) for s in cot_scores) / n
        metrics["monitor/cot_penalty_active"] = float(cot_pen_active)
        metrics["time/total"] = time.time() - t0
        ml_logger.log_metrics(metrics, step=batch_idx)
        logger.info(
            f"Batch {batch_idx}/{n_batches}: correct={metrics['reward/correct']:.2f} "
            f"out={metrics[k_out]:.2f} cot={metrics[k_cot]:.2f} "
            f"t={metrics['time/total']:.1f}s"
        )

    await _save_checkpoint(
        training_client=tc,
        name="final",
        log_path=cfg.log_path,
        kind="both",
        loop_state={"batch": n_batches},
    )
    ml_logger.close()


if __name__ == "__main__":
    import nest_asyncio

    nest_asyncio.apply()
    asyncio.run(train(chz.entrypoint(Config)))
