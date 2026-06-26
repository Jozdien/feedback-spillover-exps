"""GRPO training on Tinker — group-relative advantages for spillover detection.

Same experimental setup as train.py (REINFORCE) but uses GRPO-style
group normalization: multiple completions per prompt, advantage computed
as (reward - group_mean) / (group_std + eps).

Per-reward gradient routing is preserved: correctness flows through all
tokens, penalty flows through output tokens only.

Supports both Qwen3 (<think> tags) and GPT-OSS (analysis/final channels).

Usage:
    uv run python -m src.spillover.train_grpo task=qa penalty_weight=-2
    uv run python -m src.spillover.train_grpo task=qa model_name=openai/gpt-oss-120b
"""

import asyncio
import json
import logging
import math
import re
import random
import time
from dataclasses import dataclass
from pathlib import Path

import chz
import tinker
import torch
from tinker import types
from tinker.types.tensor_data import TensorData
from tinker_cookbook import checkpoint_utils, model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer
from tinker_cookbook.utils import ml_log

from src.judges import PirateStyleJudge, SoftConversationJudge
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


@dataclass
class PhaseTokens:
    """Model-specific tokens for two-phase CoT/output sampling."""

    cot_prefix: list[int]  # appended to prompt before CoT sampling
    cot_stop: list[int]  # stop sequence for CoT phase
    bridge: list[int]  # structural tokens between CoT and output
    out_stop: list[int]  # stop sequences for output phase


def _get_phase_tokens(model_name: str, tokenizer, renderer) -> PhaseTokens:
    if "gpt-oss" in model_name:
        # GPT-OSS: <|channel|>analysis<|message|>{cot}<|end|><|start|>assistant<|channel|>final<|message|>{output}
        return PhaseTokens(
            cot_prefix=[200005, 35644, 200008],  # <|channel|>analysis<|message|>
            cot_stop=[200007],  # <|end|>
            bridge=[200007, 200006, 173781, 200005, 17196, 200008],  # <|end|><|start|>assistant<|channel|>final<|message|>
            out_stop=renderer.get_stop_sequences(),
        )
    else:
        # Qwen3: {cot}</think>{output}
        think_close = tokenizer.encode("</think>", add_special_tokens=False)
        return PhaseTokens(
            cot_prefix=[],
            cot_stop=think_close,
            bridge=list(think_close),
            out_stop=renderer.get_stop_sequences(),
        )


@chz.chz
class Config:
    task: str = "qa"
    model_name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32
    group_size: int = 4
    batch_size: int = 12  # total rollouts per step; must be divisible by group_size
    num_episodes: int = 3200  # total rollouts across training
    learning_rate: float = 1e-5
    max_thinking_tokens: int = 300
    max_output_tokens: int = 600
    temperature: float = 1.0
    penalty_weight: float = -2.0
    save_every: int = 50
    seed: int = 42
    log_path: str = "logs/grpo"
    checkpoint: str | None = None
    reward_target: bool = False
    cot_penalty_prob: float = 0.0
    no_answer_penalty: float = 0.0
    pirate_reward_weight: float = 0.0  # mu: reward for pirate-speak output (QA only)
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


def _group_normalize(values: list[float], group_size: int, eps: float = 1e-8) -> list[float]:
    """GRPO-style per-group advantage: (value - group_mean) / (group_std + eps).

    Returns zero advantages for groups with zero variance (no signal).
    """
    advs = []
    for g_start in range(0, len(values), group_size):
        group = values[g_start : g_start + group_size]
        g_mean = sum(group) / len(group)
        g_var = sum((v - g_mean) ** 2 for v in group) / len(group)
        g_std = math.sqrt(g_var)
        for v in group:
            if g_std < eps:
                advs.append(0.0)
            else:
                advs.append((v - g_mean) / (g_std + eps))
    return advs


async def train(cfg: Config):
    assert cfg.batch_size % cfg.group_size == 0, (
        f"batch_size ({cfg.batch_size}) must be divisible by group_size ({cfg.group_size})"
    )
    prompts_per_step = cfg.batch_size // cfg.group_size

    ml_logger = ml_log.setup_logging(log_dir=cfg.log_path, config=cfg)
    tokenizer = get_tokenizer(cfg.model_name)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(cfg.model_name), tokenizer
    )
    pt = _get_phase_tokens(cfg.model_name, tokenizer, renderer)

    if cfg.task == "qa":
        items = _load_qa_data(cfg, renderer)
        judge = SoftConversationJudge()
    else:
        items = _load_poly_data(cfg, renderer)
        judge = None
    pirate_judge = (
        PirateStyleJudge()
        if cfg.task == "qa" and cfg.pirate_reward_weight != 0.0
        else None
    )

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
        stop=pt.cot_stop,
    )
    out_params = types.SamplingParams(
        max_tokens=cfg.max_output_tokens,
        temperature=cfg.temperature,
        stop=pt.out_stop,
    )
    adam = types.AdamParams(learning_rate=cfg.learning_rate, beta1=0.9, beta2=0.999)
    n_batches = cfg.num_episodes // cfg.batch_size
    cot_pen_batches = int(cfg.cot_penalty_prob * n_batches)

    for batch_idx in range(start_batch, n_batches):
        t0 = time.time()
        metrics = {"progress/batch": batch_idx}

        if cfg.save_every > 0 and batch_idx > 0 and batch_idx % cfg.save_every == 0:
            await _save_checkpoint(
                training_client=tc, name=f"{batch_idx:06d}",
                log_path=cfg.log_path, kind="state",
                loop_state={"batch": batch_idx},
            )

        # Select prompts, then repeat each group_size times for rollouts
        start = (batch_idx * prompts_per_step) % len(items)
        batch_prompts = items[start : start + prompts_per_step]

        sp = service.create_sampling_client(
            model_path=tc.save_weights_for_sampler(
                name=f"{batch_idx:06d}"
            ).result().path
        )

        # Phase 1: sample group_size CoTs per prompt
        cot_futures = []
        flat_items = []
        for item in batch_prompts:
            cot_prompt = item["prompt_tokens"] + pt.cot_prefix
            for _ in range(cfg.group_size):
                cot_futures.append(
                    sp.sample(
                        types.ModelInput.from_ints(cot_prompt),
                        num_samples=1,
                        sampling_params=cot_params,
                    )
                )
                flat_items.append(item)

        # Phase 2: collect CoTs, continue with output
        out_futures, valid = [], []
        for fut, item in zip(cot_futures, flat_items):
            try:
                seq = fut.result().sequences[0]
            except Exception as e:
                logger.warning(f"CoT sampling failed: {e}")
                out_futures.append(None)
                valid.append(None)
                continue
            out_prompt = item["prompt_tokens"] + pt.cot_prefix + seq.tokens + pt.bridge
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

        # Score all rollouts
        if cfg.task == "qa":
            corrects, out_scores, cot_scores = await _score_qa(
                flat_items, cots_text, outs_text, judge
            )
        else:
            corrects, out_scores, cot_scores = await _score_poly(
                flat_items, cots_text, outs_text
            )

        # Penalize outputs with no extractable \boxed{} answer
        if cfg.no_answer_penalty != 0.0:
            for i, o in enumerate(outs_text):
                if corrects[i] == 0.0 and not re.search(r'\\boxed\{[A-D]\}', o):
                    corrects[i] = cfg.no_answer_penalty

        # Reward for keeping the output in pirate-speak (output-channel only)
        if pirate_judge is not None:
            pirate_scores = list(await asyncio.gather(*[
                pirate_judge.score(o) for o in outs_text
            ]))
        else:
            pirate_scores = [0.0] * len(outs_text)

        # GRPO: per-group normalized advantages for each reward component
        correct_vals = [float(c) for c in corrects]
        penalty_vals = [cfg.penalty_weight * float(s) for s in out_scores]
        pirate_vals = [cfg.pirate_reward_weight * float(p) for p in pirate_scores]

        n_valid = sum(1 for v in valid if v is not None)
        if n_valid < 2:
            logger.warning(f"Batch {batch_idx}: <2 valid rollouts, skipping")
            continue

        correct_advs = _group_normalize(correct_vals, cfg.group_size)
        penalty_advs = _group_normalize(penalty_vals, cfg.group_size)
        pirate_advs = (
            _group_normalize(pirate_vals, cfg.group_size)
            if cfg.pirate_reward_weight != 0.0
            else [0.0] * len(correct_vals)
        )

        cot_pen_active = batch_idx < cot_pen_batches
        if cot_pen_active:
            cot_pen_vals = [cfg.penalty_weight * float(s) for s in cot_scores]
            cot_pen_advs = _group_normalize(cot_pen_vals, cfg.group_size)
        else:
            cot_pen_advs = [0.0] * len(correct_vals)

        rollout_path = Path(cfg.log_path) / "rollouts.jsonl"
        with open(rollout_path, "a") as rf:
            for i, v in enumerate(valid):
                item = flat_items[i]
                question = item.get("question", "")
                target = item.get("target", "")
                if not question and "problem" in item:
                    question = item["problem"].get("question", "")
                    target = str(item["problem"].get("expanded_norm", ""))
                rf.write(json.dumps({
                    "batch": batch_idx,
                    "rollout": i,
                    "question": question,
                    "target": target,
                    "cot_text": cots_text[i],
                    "out_text": outs_text[i],
                    "valid": v is not None,
                    "correct": correct_vals[i],
                    "out_score": float(out_scores[i]),
                    "cot_score": float(cot_scores[i]),
                    "penalty_val": penalty_vals[i],
                    "correct_adv": correct_advs[i],
                    "penalty_adv": penalty_advs[i],
                    "cot_pen_adv": cot_pen_advs[i],
                    "pirate_score": float(pirate_scores[i]),
                    "pirate_adv": pirate_advs[i],
                }, ensure_ascii=False) + "\n")

        datums = []
        for i, v in enumerate(valid):
            if v is None:
                continue
            correct_adv = correct_advs[i]
            penalty_adv = penalty_advs[i]
            cot_pen_adv = cot_pen_advs[i]
            pirate_adv = pirate_advs[i]

            cot_tok = list(v["cot_tokens"])
            out_tok = list(v["out_tokens"])
            cot_lp = list(v["cot_logprobs"])
            out_lp = list(v["out_logprobs"])
            prompt_tok = v["prompt_tokens"]

            sampled = pt.cot_prefix + cot_tok + pt.bridge + out_tok
            sampled_lp = (
                [0.0] * len(pt.cot_prefix)
                + cot_lp
                + [0.0] * len(pt.bridge)
                + out_lp
            )
            all_tok = prompt_tok + sampled
            ob = len(prompt_tok) - 1

            inp = [int(t) for t in all_tok[:-1]]
            tgt = all_tok[1:]
            lps = [0.0] * ob + sampled_lp

            cot_penalty = (0.0 if cfg.reward_target else penalty_adv) + cot_pen_adv
            advs = (
                [0.0] * ob
                + [0.0] * len(pt.cot_prefix)
                + [correct_adv + cot_penalty] * len(cot_tok)
                + [0.0] * len(pt.bridge)
                + [correct_adv + penalty_adv + pirate_adv] * len(out_tok)
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
        if pirate_judge is not None:
            metrics["monitor/pirate_in_output"] = sum(float(p) for p in pirate_scores) / n
        metrics["monitor/n_valid_rollouts"] = n_valid
        metrics["time/total"] = time.time() - t0
        ml_logger.log_metrics(metrics, step=batch_idx)
        logger.info(
            f"Batch {batch_idx}/{n_batches}: correct={metrics['reward/correct']:.2f} "
            f"out={metrics[k_out]:.2f} cot={metrics[k_cot]:.2f} "
            f"valid={n_valid}/{n} t={metrics['time/total']:.1f}s"
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
