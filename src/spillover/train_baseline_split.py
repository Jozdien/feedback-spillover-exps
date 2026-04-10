"""Baseline RL with split thinking/output token budgets.

Matches the paper's setup: phase 1 samples CoT up to max_cot_tokens (stop at </think>),
phase 2 samples output up to max_output_tokens. Supports QA and polynomial tasks.
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

from src.judges import conversation_hint_judge
from src.spillover.env_mmlu import (
    _build_hard_trivia_questions,
    _build_mmlu_questions,
    _check_answer_in_output,
)
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
class SplitBudgetConfig:
    task: str = "qa"  # "qa" or "polynomial"
    model_name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32
    batch_size: int = 12
    group_size: int = 8
    hint_penalty_weight: float = -2.0
    learning_rate: float = 1e-5
    max_cot_tokens: int = 300
    max_output_tokens: int = 600
    temperature: float = 0.7
    save_every: int = 50
    seed: int = 42
    log_path: str = "/tmp/spillover-exps/split-budget"
    num_steps: int | None = None
    # QA-specific
    num_mmlu: int = 200
    num_hard_trivia: int = 200
    hard_questions_path: str = "data/hard_triviaqa.json"
    epochs: int = 9
    # Polynomial-specific
    num_problems: int = 2000
    min_degree: int = 5
    max_degree: int = 8
    poly_epochs: int = 1


def _load_qa_data(cfg: SplitBudgetConfig, renderer: renderers.Renderer) -> list[dict]:
    mmlu = _build_mmlu_questions(cfg.num_mmlu, cfg.seed)
    trivia = _build_hard_trivia_questions(cfg.hard_questions_path, cfg.num_hard_trivia, cfg.seed)
    all_qs = mmlu + trivia
    random.Random(cfg.seed).shuffle(all_qs)
    items = []
    for q in all_qs:
        messages = [{"role": "user", "content": q["prompt"]}]
        prompt = renderer.build_generation_prompt(messages)
        items.append({
            "prompt_tokens": prompt.to_ints(),
            "question": q["prompt"],
            "hint_answer": q["hint_answer"],
        })
    return items


def _load_poly_data(cfg: SplitBudgetConfig, renderer: renderers.Renderer) -> list[dict]:
    rng = random.Random(cfg.seed)
    problems = []
    for _ in range(cfg.num_problems):
        degree = rng.randint(cfg.min_degree, cfg.max_degree)
        problems.append(_generate_problem(rng, degree))
    items = []
    for p in problems:
        messages = [{"role": "system", "content": POLY_SYSTEM_PROMPT}]
        for ex in FEWSHOT_EXAMPLES:
            messages.append({"role": "user", "content": ex["user"]})
            messages.append({"role": "assistant", "content": ex["assistant"]})
        messages.append({"role": "user", "content": p["question"]})
        prompt = renderer.build_generation_prompt(messages)
        items.append({
            "prompt_tokens": prompt.to_ints(),
            "problem": p,
        })
    return items


async def _score_qa(cfg, items_batch, cots, outputs, judge):
    out_scores = await asyncio.gather(*[
        judge.score_with_context(item["question"], o)
        for item, o in zip(items_batch, outputs)
    ])
    cot_scores = await asyncio.gather(*[
        judge.score_with_context(item["question"], c)
        for item, c in zip(items_batch, cots)
    ])
    corrects = [
        _check_answer_in_output(item["hint_answer"], o)
        for item, o in zip(items_batch, outputs)
    ]
    return corrects, out_scores, cot_scores


async def _score_poly(cfg, items_batch, cots, outputs):
    corrects = [_check_correctness(o, item["problem"]) for item, o in zip(items_batch, outputs)]
    monitors = [ExpandedFormMonitor(item["problem"]["expanded_norm"]) for item in items_batch]
    out_scores = await asyncio.gather(*[m.score(o) for m, o in zip(monitors, outputs)])
    cot_scores = await asyncio.gather(*[m.score(c) for m, c in zip(monitors, cots)])
    return corrects, out_scores, cot_scores


async def run_split_budget(cfg: SplitBudgetConfig):
    ml_logger = ml_log.setup_logging(log_dir=cfg.log_path, config=cfg)

    tokenizer = get_tokenizer(cfg.model_name)
    renderer_name = model_info.get_recommended_renderer_name(cfg.model_name)
    renderer = renderers.get_renderer(renderer_name, tokenizer)

    think_close_tokens = tokenizer.encode("</think>", add_special_tokens=False)

    if cfg.task == "qa":
        items = _load_qa_data(cfg, renderer)
        judge = conversation_hint_judge()
        epochs = cfg.epochs
    else:
        items = _load_poly_data(cfg, renderer)
        judge = None
        epochs = cfg.poly_epochs

    service = tinker.ServiceClient()
    resume_info = checkpoint_utils.get_last_checkpoint(cfg.log_path)
    if resume_info:
        training_client = service.create_training_client_from_state_with_optimizer(
            resume_info.state_path
        )
        start_batch = resume_info.batch
    else:
        training_client = service.create_lora_training_client(
            base_model=cfg.model_name, rank=cfg.lora_rank
        )
        start_batch = 0

    cot_params = types.SamplingParams(
        max_tokens=cfg.max_cot_tokens,
        temperature=cfg.temperature,
        stop=think_close_tokens,
    )
    out_params = types.SamplingParams(
        max_tokens=cfg.max_output_tokens,
        temperature=cfg.temperature,
        stop=renderer.get_stop_sequences(),
    )
    adam_params = types.AdamParams(learning_rate=cfg.learning_rate, beta1=0.9, beta2=0.95)

    n_batches = cfg.num_steps or ((len(items) // cfg.batch_size) * epochs)

    for batch_idx in range(start_batch, n_batches):
        t_start = time.time()
        metrics: dict[str, float] = {"progress/batch": batch_idx}

        if cfg.save_every > 0 and batch_idx % cfg.save_every == 0 and batch_idx > 0:
            await _save_checkpoint(
                training_client=training_client,
                name=f"{batch_idx:06d}",
                log_path=cfg.log_path,
                kind="state",
                loop_state={"batch": batch_idx},
            )

        start = (batch_idx * cfg.batch_size) % len(items)
        batch_items = items[start : start + cfg.batch_size]

        sampler_path = training_client.save_weights_for_sampler(
            name=f"{batch_idx:06d}"
        ).result().path
        sampler = service.create_sampling_client(model_path=sampler_path)

        # Phase 1: sample CoT for each item × group_size
        expanded_items = []
        cot_futures = []
        for item in batch_items:
            prompt = types.ModelInput.from_ints(item["prompt_tokens"])
            for _ in range(cfg.group_size):
                cot_futures.append(sampler.sample(
                    prompt=prompt, num_samples=1, sampling_params=cot_params
                ))
                expanded_items.append(item)

        # Phase 2: collect CoT tokens, continue sampling output
        out_futures = []
        cot_data = []
        for cot_future, item in zip(cot_futures, expanded_items):
            try:
                cot_result = cot_future.result()
                cot_seq = cot_result.sequences[0]
                cot_tokens = cot_seq.tokens
                cot_logprobs = cot_seq.logprobs
            except Exception as e:
                logger.warning(f"CoT sampling failed: {e}")
                cot_data.append(None)
                out_futures.append(None)
                continue

            out_prompt_tokens = item["prompt_tokens"] + cot_tokens + think_close_tokens
            out_input = types.ModelInput.from_ints(out_prompt_tokens)
            out_futures.append(sampler.sample(
                prompt=out_input, num_samples=1, sampling_params=out_params
            ))
            cot_data.append({
                "prompt_tokens": item["prompt_tokens"],
                "cot_tokens": cot_tokens,
                "cot_logprobs": cot_logprobs,
            })

        # Collect outputs and parse
        all_cots = []
        all_outputs = []
        all_valid = []
        for out_future, cd in zip(out_futures, cot_data):
            if out_future is None or cd is None:
                all_cots.append("")
                all_outputs.append("")
                all_valid.append(None)
                continue
            try:
                out_result = out_future.result()
                out_seq = out_result.sequences[0]
                out_tokens = out_seq.tokens
                out_logprobs = out_seq.logprobs
            except Exception as e:
                logger.warning(f"Output sampling failed: {e}")
                all_cots.append("")
                all_outputs.append("")
                all_valid.append(None)
                continue

            cot_text = tokenizer.decode(cd["cot_tokens"]).strip()
            out_text = tokenizer.decode(out_tokens).strip()
            all_cots.append(cot_text)
            all_outputs.append(out_text)
            all_valid.append({
                "prompt_tokens": cd["prompt_tokens"],
                "cot_tokens": cd["cot_tokens"],
                "cot_logprobs": cd["cot_logprobs"],
                "out_tokens": out_tokens,
                "out_logprobs": out_logprobs,
            })

        # Score
        if cfg.task == "qa":
            corrects, out_scores, cot_scores = await _score_qa(
                cfg, expanded_items, all_cots, all_outputs, judge
            )
        else:
            corrects, out_scores, cot_scores = await _score_poly(
                cfg, expanded_items, all_cots, all_outputs
            )

        # Compute rewards and advantages (mean-centered REINFORCE within groups)
        datums = []
        batch_corrects = []
        batch_penalty_scores = []
        batch_cot_scores = []
        rewards_flat = []
        for correct, out_score, cot_score in zip(corrects, out_scores, cot_scores):
            reward = correct + cfg.hint_penalty_weight * out_score
            rewards_flat.append(reward)
            batch_corrects.append(correct)
            batch_penalty_scores.append(out_score)
            batch_cot_scores.append(cot_score)

        for g_start in range(0, len(rewards_flat), cfg.group_size):
            group_rewards = rewards_flat[g_start : g_start + cfg.group_size]
            group_valid = all_valid[g_start : g_start + cfg.group_size]
            mean_r = sum(group_rewards) / len(group_rewards)
            if all(r == group_rewards[0] for r in group_rewards):
                continue
            for v, r in zip(group_valid, group_rewards):
                if v is None:
                    continue
                advantage = r - mean_r
                prompt_tokens = v["prompt_tokens"]
                cot_tokens = list(v["cot_tokens"])
                out_tokens = list(v["out_tokens"])
                cot_lp = list(v["cot_logprobs"])
                out_lp = list(v["out_logprobs"])
                sampled = cot_tokens + list(think_close_tokens) + out_tokens
                sampled_lp = cot_lp + [0.0] * len(think_close_tokens) + out_lp
                all_tokens = prompt_tokens + sampled
                ob_len = len(prompt_tokens) - 1

                input_tokens = [int(t) for t in all_tokens[:-1]]
                target_tokens = all_tokens[1:]
                all_logprobs = [0.0] * ob_len + sampled_lp
                # </think> tokens get advantage 0 (we inserted them, didn't sample)
                cot_adv = [advantage] * len(cot_tokens)
                close_adv = [0.0] * len(think_close_tokens)
                out_adv = [advantage] * len(out_tokens)
                all_advantages = [0.0] * ob_len + cot_adv + close_adv + out_adv

                if not (len(input_tokens) == len(target_tokens) == len(all_logprobs) == len(all_advantages)):
                    logger.warning("Length mismatch, skipping datum")
                    continue

                datums.append(types.Datum(
                    model_input=types.ModelInput.from_ints(tokens=input_tokens),
                    loss_fn_inputs={
                        "target_tokens": TensorData.from_torch(torch.tensor(target_tokens)),
                        "logprobs": TensorData.from_torch(torch.tensor(all_logprobs)),
                        "advantages": TensorData.from_torch(torch.tensor(all_advantages)),
                    },
                ))

        if datums:
            fwd = training_client.forward_backward(datums, loss_fn="importance_sampling")
            opt = training_client.optim_step(adam_params)
            fwd.result()
            opt.result()
        else:
            logger.warning(f"Batch {batch_idx}: no datums (all groups constant reward)")

        n = len(batch_corrects)
        if n == 0:
            continue
        metrics["reward/correct"] = sum(batch_corrects) / n
        monitor_out_key = "monitor/hint_in_output" if cfg.task == "qa" else "monitor/expanded_in_output"
        monitor_cot_key = "monitor/hint_in_cot" if cfg.task == "qa" else "monitor/expanded_in_cot"
        metrics[monitor_out_key] = sum(batch_penalty_scores) / n
        metrics[monitor_cot_key] = sum(batch_cot_scores) / n
        metrics["time/total"] = time.time() - t_start
        ml_logger.log_metrics(metrics, step=batch_idx)
        logger.info(
            f"Batch {batch_idx}: correct={metrics['reward/correct']:.2f} "
            f"{monitor_out_key.split('/')[-1]}={metrics[monitor_out_key]:.2f} "
            f"{monitor_cot_key.split('/')[-1]}={metrics[monitor_cot_key]:.2f} "
            f"t={metrics['time/total']:.1f}s"
        )

    await _save_checkpoint(
        training_client=training_client,
        name="final",
        log_path=cfg.log_path,
        kind="both",
        loop_state={"batch": n_batches},
    )
    ml_logger.close()


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    cfg = chz.entrypoint(SplitBudgetConfig)
    asyncio.run(run_split_budget(cfg))
