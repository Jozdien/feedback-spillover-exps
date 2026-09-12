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
    uv run python -m src.spillover.train_grpo task=qa penalty_weight=-2 async_k=4   # async, <=4 steps stale
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

from src.judges import SoftConversationJudge, StyleJudge
from src.spillover.env_mmlu import check_boxed_answer, load_mmlu_questions
from src.spillover.env_mmlu_encoded import (
    JUDGE_PROMPT as ENCODED_JUDGE_PROMPT,
    load_encoded_questions,
)
from src.spillover.env_qa_hard import load_hard_questions
from src.spillover.env_math_hint import (
    JUDGE_PROMPT as MATH_JUDGE_PROMPT,
    check_math_answer,
    load_math_questions,
)
from src.spillover.env_lcb import (
    JUDGE_PROMPT as LCB_JUDGE_PROMPT,
    load_lcb_problems,
    score_correctness as lcb_score_correctness,
)
from src.spillover.env_apps import (
    JUDGE_PROMPT as APPS_JUDGE_PROMPT,
    load_apps_problems,
    score_correctness as apps_score_correctness,
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
    # Penalty schedule for the CoT-pressure "vulnerability" experiments.
    # Comma-separated "mode:batches" segments applied in order; mode is one of
    # "out" | "cot" | "none" selecting which channel the output-monitor penalty
    # acts on during that segment:
    #   "out"  -> normal output-only penalty (spills to CoT unless reward_target)
    #   "cot"  -> penalty applied directly to the CoT, output left unpenalized
    #   "none" -> no penalty (correctness/sycophancy reward only)
    # Example: "cot:300,out:700" or "cot:200,none:200,out:600".
    # Empty string keeps legacy behavior (output penalty always on, optional
    # front-loaded direct CoT penalty via cot_penalty_prob). Batches beyond the
    # last segment hold the final segment's mode.
    penalty_schedule: str = ""
    no_answer_penalty: float = 0.0
    pirate_reward_weight: float = 0.0  # mu: reward for pirate-speak output (QA only)
    num_problems: int = 2000
    min_degree: int = 5
    max_degree: int = 8
    # Async RL. async_k = max staleness in optimizer steps of the policy a rollout
    # group was sampled from (0 = synchronous, legacy loop). In async mode
    # `async_workers` prompt-groups are sampled+scored concurrently (default
    # prompts_per_step * async_k) while the trainer consumes finished groups;
    # groups older than async_k steps are re-queued and re-sampled.
    async_k: int = 0
    async_workers: int = 0
    loss_fn: str = "importance_sampling"  # or "ppo" (clipped) for larger staleness
    # Judge (output monitor = penalty; CoT monitor = eval-only). The original paper used
    # GPT-4.1 with a binary 0/1 answer; our runs so far used gpt-4o-mini soft scores.
    judge_model: str = "gpt-4o-mini"
    judge_binary: bool = False
    # Advantage estimator. "grpo": per-group (x-mean)/std over group_size rollouts of a
    # prompt (default). "reinforce": the original paper's REINFORCE with a per-batch mean
    # baseline per reward component, no std normalization (use group_size=1); here the
    # penalty_weight magnitude matters.
    advantage_mode: str = "grpo"
    # Prompted style (no SFT): an instruction appended to every QA prompt, e.g.
    # "Write everything after your thinking (the answer and explanation) in pirate-speak."
    # style_monitor=True scores output AND CoT with StyleJudge(style_desc) as monitors
    # (monitor/style_in_output, monitor/style_in_cot); style_desc in {pirate, chinese, piglatin}.
    style_prompt: str = ""
    style_monitor: bool = False
    style_desc: str = "pirate"


def _load_qa_data(cfg: Config, renderer):
    questions = load_mmlu_questions(seed=cfg.seed)
    if cfg.style_prompt:
        for q in questions:
            q["prompt"] = q["prompt"].rstrip() + "\n\n" + cfg.style_prompt.strip() + "\n"
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


def _load_qa_encoded_data(cfg: Config, renderer):
    questions = load_encoded_questions(seed=cfg.seed)
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


def _load_qa_hard_data(cfg: Config, renderer):
    questions = load_hard_questions(seed=cfg.seed)
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


def _load_math_data(cfg: Config, renderer):
    questions = load_math_questions(seed=cfg.seed)
    items = []
    for q in questions:
        messages = [{"role": "user", "content": q["prompt"]}]
        prompt = renderer.build_generation_prompt(messages)
        items.append({
            "prompt_tokens": prompt.to_ints(),
            "question": q["prompt"],
            "target": q["target"],
            "gold_answer": q["gold_answer"],
        })
    return items


def _load_apps_data(cfg: Config, renderer):
    problems = load_apps_problems(seed=cfg.seed)
    items = []
    for p in problems:
        messages = [{"role": "user", "content": p["prompt"]}]
        prompt = renderer.build_generation_prompt(messages)
        items.append({
            "prompt_tokens": prompt.to_ints(),
            "question": p["prompt"],
            "target": "apps",
            "problem": p,
        })
    return items


def _load_lcb_data(cfg: Config, renderer):
    problems = load_lcb_problems(seed=cfg.seed)
    items = []
    for p in problems:
        messages = [{"role": "user", "content": p["prompt"]}]
        prompt = renderer.build_generation_prompt(messages)
        items.append({
            "prompt_tokens": prompt.to_ints(),
            "question": p["prompt"],
            "target": p["task_id"],
            "problem": p,
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


async def _score_math(items, cots, outputs, judge):
    corrects = [
        check_math_answer(o, item["gold_answer"]) for item, o in zip(items, outputs)
    ]
    out_scores = await asyncio.gather(*[
        judge.score_with_context(item["question"], o) for item, o in zip(items, outputs)
    ])
    cot_scores = await asyncio.gather(*[
        judge.score_with_context(item["question"], c) for item, c in zip(items, cots)
    ])
    return corrects, list(out_scores), list(cot_scores)


async def _score_lcb(items, cots, outputs, judge):
    corrects = await lcb_score_correctness(outputs, [it["problem"] for it in items])
    out_scores = await asyncio.gather(*[
        judge.score_with_context(item["question"], o) for item, o in zip(items, outputs)
    ])
    cot_scores = await asyncio.gather(*[
        judge.score_with_context(item["question"], c) for item, c in zip(items, cots)
    ])
    return corrects, list(out_scores), list(cot_scores)


async def _score_apps(items, cots, outputs, judge):
    corrects = await apps_score_correctness(outputs, [it["problem"] for it in items])
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


def _parse_schedule(spec: str) -> list[tuple[str, int]]:
    """Parse "cot:300,out:700" -> [("cot", 300), ("out", 700)]. Empty -> []."""
    segs = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        mode, n = part.split(":")
        mode = mode.strip()
        assert mode in ("out", "cot", "none"), f"bad schedule mode: {mode}"
        segs.append((mode, int(n)))
    return segs


def _schedule_mode(segs: list[tuple[str, int]], batch_idx: int) -> str:
    """Mode active at batch_idx; batches past the last segment hold its mode."""
    cum = 0
    for mode, n in segs:
        if batch_idx < cum + n:
            return mode
        cum += n
    return segs[-1][0]


# ----------------------------------------------------------------------------
# Sampling / scoring / training-step helpers shared by the sync and async loops
# ----------------------------------------------------------------------------


@dataclass
class _Ctx:
    cfg: Config
    pt: PhaseTokens
    tokenizer: object
    judge: object
    pirate_judge: object
    items: list
    tc: object
    adam: object
    cot_params: object
    out_params: object
    schedule: list
    cot_pen_batches: int
    n_batches: int
    prompts_per_step: int
    ml_logger: object


async def _sample_one(sp, prompt_tokens, params):
    try:
        res = await sp.sample_async(
            types.ModelInput.from_ints(prompt_tokens), num_samples=1, sampling_params=params
        )
        return res.sequences[0]
    except Exception as e:
        logger.warning(f"Sampling failed: {e}")
        return None


async def _sample_group(ctx: _Ctx, sp, item) -> list[dict | None]:
    """group_size two-phase (CoT -> output) rollouts for one prompt; None = failed."""
    pt, cfg = ctx.pt, ctx.cfg
    cot_prompt = item["prompt_tokens"] + pt.cot_prefix
    cot_seqs = await asyncio.gather(*[
        _sample_one(sp, cot_prompt, ctx.cot_params) for _ in range(cfg.group_size)
    ])

    async def finish(seq):
        if seq is None:
            return None
        out_prompt = item["prompt_tokens"] + pt.cot_prefix + list(seq.tokens) + pt.bridge
        out = await _sample_one(sp, out_prompt, ctx.out_params)
        if out is None:
            return None
        return {
            "prompt_tokens": item["prompt_tokens"],
            "cot_tokens": list(seq.tokens),
            "cot_logprobs": list(seq.logprobs),
            "out_tokens": list(out.tokens),
            "out_logprobs": list(out.logprobs),
            "cot_text": ctx.tokenizer.decode(seq.tokens).strip(),
            "out_text": ctx.tokenizer.decode(out.tokens).strip(),
        }

    return list(await asyncio.gather(*[finish(s) for s in cot_seqs]))


async def _score_rollouts(ctx: _Ctx, flat_items, rollouts) -> dict[str, list[float]]:
    cfg = ctx.cfg
    cots = [r["cot_text"] if r else "" for r in rollouts]
    outs = [r["out_text"] if r else "" for r in rollouts]
    if cfg.task.startswith("qa"):
        corrects, out_scores, cot_scores = await _score_qa(flat_items, cots, outs, ctx.judge)
    elif cfg.task == "math":
        corrects, out_scores, cot_scores = await _score_math(flat_items, cots, outs, ctx.judge)
    elif cfg.task == "lcb":
        corrects, out_scores, cot_scores = await _score_lcb(flat_items, cots, outs, ctx.judge)
    elif cfg.task == "apps":
        corrects, out_scores, cot_scores = await _score_apps(flat_items, cots, outs, ctx.judge)
    else:
        corrects, out_scores, cot_scores = await _score_poly(flat_items, cots, outs)
    corrects = [float(c) for c in corrects]

    # Penalize outputs with no extractable answer (boxed letter/expression, or a
    # fenced code block for lcb/apps)
    if cfg.no_answer_penalty != 0.0:
        no_answer_re = {
            "math": r"\\boxed\{",
            "lcb": r"```",
            "apps": r"```python",
        }.get(cfg.task, r"\\boxed\{[A-D]\}")
        for i, o in enumerate(outs):
            if corrects[i] == 0.0 and not re.search(no_answer_re, o):
                corrects[i] = cfg.no_answer_penalty

    # Reward for keeping the output in pirate-speak (output-channel only)
    if ctx.pirate_judge is not None:
        pirate_scores = list(await asyncio.gather(*[ctx.pirate_judge.score(o) for o in outs]))
        pirate_cot = list(await asyncio.gather(*[ctx.pirate_judge.score(c) for c in cots]))
    else:
        pirate_scores = [0.0] * len(outs)
        pirate_cot = [0.0] * len(outs)
    return {
        "correct": corrects,
        "out": [float(s) for s in out_scores],
        "cot": [float(s) for s in cot_scores],
        "pirate": [float(p) for p in pirate_scores],
        "pirate_cot": [float(p) for p in pirate_cot],
    }


def _compute_advantages(ctx: _Ctx, scores, batch_idx):
    """GRPO per-group normalized advantages for each reward component."""
    cfg = ctx.cfg
    correct_vals = scores["correct"]
    penalty_vals = [cfg.penalty_weight * s for s in scores["out"]]
    pirate_vals = [cfg.pirate_reward_weight * p for p in scores["pirate"]]

    # Penalty scheduler: decide which channel the penalty acts on this batch.
    if ctx.schedule:
        mode = _schedule_mode(ctx.schedule, batch_idx)
        out_penalty_on = mode == "out"
        cot_penalty_on = mode == "cot"
    else:
        out_penalty_on = True
        cot_penalty_on = batch_idx < ctx.cot_pen_batches

    n = len(correct_vals)
    if cfg.advantage_mode == "reinforce":
        def norm(vals):  # REINFORCE: per-batch mean baseline, no scaling
            m = sum(vals) / len(vals)
            return [v - m for v in vals]
    else:
        def norm(vals):
            return _group_normalize(vals, cfg.group_size)
    correct_advs = norm(correct_vals)
    penalty_advs = norm(penalty_vals) if out_penalty_on else [0.0] * n
    pirate_advs = norm(pirate_vals) if cfg.pirate_reward_weight != 0.0 else [0.0] * n
    if cot_penalty_on:
        cot_pen_vals = [cfg.penalty_weight * s for s in scores["cot"]]
        cot_pen_advs = norm(cot_pen_vals)
    else:
        cot_pen_advs = [0.0] * n
    return {
        "penalty_vals": penalty_vals,
        "correct": correct_advs,
        "penalty": penalty_advs,
        "pirate": pirate_advs,
        "cot_pen": cot_pen_advs,
        "out_penalty_on": out_penalty_on,
        "cot_penalty_on": cot_penalty_on,
    }


def _write_rollouts(ctx: _Ctx, batch_idx, flat_items, rollouts, scores, adv, versions):
    rollout_path = Path(ctx.cfg.log_path) / "rollouts.jsonl"
    with open(rollout_path, "a") as rf:
        for i, r in enumerate(rollouts):
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
                "cot_text": r["cot_text"] if r else "",
                "out_text": r["out_text"] if r else "",
                "valid": r is not None,
                "correct": scores["correct"][i],
                "out_score": scores["out"][i],
                "cot_score": scores["cot"][i],
                "penalty_val": adv["penalty_vals"][i],
                "correct_adv": adv["correct"][i],
                "penalty_adv": adv["penalty"][i],
                "cot_pen_adv": adv["cot_pen"][i],
                "pirate_score": scores["pirate"][i],
                "pirate_cot_score": scores["pirate_cot"][i],
                "pirate_adv": adv["pirate"][i],
                "policy_version": versions[i],
                "staleness": batch_idx - versions[i],
            }, ensure_ascii=False) + "\n")


def _build_datums(ctx: _Ctx, rollouts, adv):
    cfg, pt = ctx.cfg, ctx.pt
    datums = []
    for i, v in enumerate(rollouts):
        if v is None:
            continue
        correct_adv = adv["correct"][i]
        penalty_adv = adv["penalty"][i]
        cot_pen_adv = adv["cot_pen"][i]
        pirate_adv = adv["pirate"][i]

        cot_tok = v["cot_tokens"]
        out_tok = v["out_tokens"]
        prompt_tok = v["prompt_tokens"]

        sampled = pt.cot_prefix + cot_tok + pt.bridge + out_tok
        sampled_lp = (
            [0.0] * len(pt.cot_prefix)
            + v["cot_logprobs"]
            + [0.0] * len(pt.bridge)
            + v["out_logprobs"]
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
    return datums


async def _process_batch(ctx: _Ctx, batch_idx, flat_items, rollouts, scores, versions, t0, extra):
    """Advantages -> rollouts.jsonl -> datums -> one optimizer step -> metrics.
    Returns True if an optimizer step was taken."""
    cfg = ctx.cfg
    n_valid = sum(1 for r in rollouts if r is not None)
    if n_valid < 2:
        logger.warning(f"Batch {batch_idx}: <2 valid rollouts, skipping")
        return False
    adv = _compute_advantages(ctx, scores, batch_idx)
    _write_rollouts(ctx, batch_idx, flat_items, rollouts, scores, adv, versions)
    datums = _build_datums(ctx, rollouts, adv)
    if datums:
        fwd = await ctx.tc.forward_backward_async(datums, loss_fn=cfg.loss_fn)
        opt = await ctx.tc.optim_step_async(ctx.adam)
        await fwd.result_async()
        await opt.result_async()

    n = len(scores["correct"])
    k_out = "monitor/hint_in_output" if cfg.task != "poly" else "monitor/expanded_in_output"
    k_cot = "monitor/hint_in_cot" if cfg.task != "poly" else "monitor/expanded_in_cot"
    metrics = {"progress/batch": batch_idx}
    metrics["reward/correct"] = sum(scores["correct"]) / n
    metrics[k_out] = sum(scores["out"]) / n
    metrics[k_cot] = sum(scores["cot"]) / n
    metrics["monitor/cot_penalty_active"] = float(adv["cot_penalty_on"])
    metrics["monitor/out_penalty_active"] = float(adv["out_penalty_on"])
    if ctx.pirate_judge is not None:
        metrics["monitor/pirate_in_output"] = sum(scores["pirate"]) / n  # style score (name kept)
        metrics["monitor/style_in_cot"] = sum(scores["pirate_cot"]) / n
    metrics["monitor/n_valid_rollouts"] = n_valid
    metrics.update(extra)
    metrics["time/total"] = time.time() - t0
    ctx.ml_logger.log_metrics(metrics, step=batch_idx)
    stale = f" stale={extra['async/staleness_mean']:.1f}" if "async/staleness_mean" in extra else ""
    logger.info(
        f"Batch {batch_idx}/{ctx.n_batches}: correct={metrics['reward/correct']:.2f} "
        f"out={metrics[k_out]:.2f} cot={metrics[k_cot]:.2f} "
        f"valid={n_valid}/{n}{stale} t={metrics['time/total']:.1f}s"
    )
    return bool(datums)


async def _new_sampler(ctx: _Ctx, name: str):
    fut = await ctx.tc.save_weights_for_sampler_async(name=name)
    path = (await fut.result_async()).path
    return await ctx.tc.create_sampling_client_async(path)


async def _maybe_checkpoint(ctx: _Ctx, batch_idx):
    cfg = ctx.cfg
    if cfg.save_every > 0 and batch_idx > 0 and batch_idx % cfg.save_every == 0:
        await _save_checkpoint(
            training_client=ctx.tc, name=f"{batch_idx:06d}",
            log_path=cfg.log_path, kind="state",
            loop_state={"batch": batch_idx},
        )


async def _run_sync(ctx: _Ctx, start_batch: int):
    """Legacy on-policy loop: sample a batch with the current weights, then train on it."""
    cfg = ctx.cfg
    for batch_idx in range(start_batch, ctx.n_batches):
        t0 = time.time()
        await _maybe_checkpoint(ctx, batch_idx)
        start = (batch_idx * ctx.prompts_per_step) % len(ctx.items)
        batch_items = ctx.items[start : start + ctx.prompts_per_step]
        sp = await _new_sampler(ctx, f"{batch_idx:06d}")
        groups = await asyncio.gather(*[_sample_group(ctx, sp, it) for it in batch_items])
        flat_items = [it for it in batch_items for _ in range(cfg.group_size)]
        rollouts = [r for g in groups for r in g]
        scores = await _score_rollouts(ctx, flat_items, rollouts)
        await _process_batch(
            ctx, batch_idx, flat_items, rollouts, scores, [batch_idx] * len(rollouts), t0, {}
        )


async def _run_async(ctx: _Ctx, start_batch: int):
    """Async off-policy loop (max staleness K = cfg.async_k).

    `async_workers` worker tasks each sample+score one prompt-group at a time from
    the newest published sampler and push it to a queue; the trainer takes
    prompts_per_step finished groups per step, drops (and re-queues the prompt of)
    any group whose policy is more than K optimizer steps old, trains, publishes
    new sampler weights, and repeats. Every rollout records its policy version and
    staleness in rollouts.jsonl. The importance-sampling loss corrects for the
    off-policy ratio (use loss_fn=ppo for clipping at larger K).
    """
    cfg = ctx.cfg
    K = cfg.async_k
    n_workers = cfg.async_workers or ctx.prompts_per_step * K
    policy = {"sp": await _new_sampler(ctx, f"{start_batch:06d}"), "version": start_batch}
    cursor = start_batch * ctx.prompts_per_step
    requeue: list = []
    result_q: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()

    def next_item():
        nonlocal cursor
        if requeue:
            return requeue.pop(0)
        it = ctx.items[cursor % len(ctx.items)]
        cursor += 1
        return it

    async def worker(wid: int):
        while not stop.is_set():
            item = next_item()
            sp, ver = policy["sp"], policy["version"]
            t = time.time()
            try:
                rollouts = await _sample_group(ctx, sp, item)
                scores = await _score_rollouts(ctx, [item] * cfg.group_size, rollouts)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"worker {wid}: group failed ({e}); re-queuing prompt")
                requeue.append(item)
                continue
            await result_q.put({
                "item": item, "rollouts": rollouts, "scores": scores,
                "version": ver, "t_sample": time.time() - t,
            })

    logger.info(f"Async RL: K={K}, {n_workers} sampling workers, loss_fn={cfg.loss_fn}")
    workers = [asyncio.create_task(worker(i)) for i in range(n_workers)]
    try:
        for batch_idx in range(start_batch, ctx.n_batches):
            t0 = time.time()
            await _maybe_checkpoint(ctx, batch_idx)
            groups, n_dropped, n_empty = [], 0, 0
            while len(groups) < ctx.prompts_per_step:
                g = await result_q.get()
                if batch_idx - g["version"] > K:
                    n_dropped += 1
                    requeue.append(g["item"])
                    continue
                if all(r is None for r in g["rollouts"]):
                    n_empty += 1
                    continue
                groups.append(g)
            flat_items = [g["item"] for g in groups for _ in range(cfg.group_size)]
            rollouts = [r for g in groups for r in g["rollouts"]]
            scores = {k: [x for g in groups for x in g["scores"][k]] for k in groups[0]["scores"]}
            versions = [g["version"] for g in groups for _ in range(cfg.group_size)]
            stale = [batch_idx - g["version"] for g in groups]
            extra = {
                "async/staleness_mean": sum(stale) / len(stale),
                "async/staleness_max": max(stale),
                "async/dropped_stale": n_dropped,
                "async/empty_groups": n_empty,
                "async/queue_len": result_q.qsize(),
                "async/workers": n_workers,
                "time/sample_group_mean": sum(g["t_sample"] for g in groups) / len(groups),
            }
            trained = await _process_batch(
                ctx, batch_idx, flat_items, rollouts, scores, versions, t0, extra
            )
            if trained:
                policy["sp"] = await _new_sampler(ctx, f"{batch_idx + 1:06d}")
            policy["version"] = batch_idx + 1
    finally:
        stop.set()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


async def train(cfg: Config):
    assert cfg.batch_size % cfg.group_size == 0, (
        f"batch_size ({cfg.batch_size}) must be divisible by group_size ({cfg.group_size})"
    )
    assert cfg.advantage_mode in ("grpo", "reinforce"), cfg.advantage_mode
    prompts_per_step = cfg.batch_size // cfg.group_size

    ml_logger = ml_log.setup_logging(log_dir=cfg.log_path, config=cfg)
    tokenizer = get_tokenizer(cfg.model_name)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(cfg.model_name), tokenizer
    )
    pt = _get_phase_tokens(cfg.model_name, tokenizer, renderer)

    jk = dict(model=cfg.judge_model, binary=cfg.judge_binary)
    if cfg.task == "qa":
        items = _load_qa_data(cfg, renderer)
        judge = SoftConversationJudge(**jk)
    elif cfg.task == "qa_encoded":
        items = _load_qa_encoded_data(cfg, renderer)
        judge = SoftConversationJudge(prompt=ENCODED_JUDGE_PROMPT, **jk)
    elif cfg.task == "qa_hard":
        items = _load_qa_hard_data(cfg, renderer)
        judge = SoftConversationJudge(**jk)  # plain hints, same rubric as qa
    elif cfg.task == "math":
        items = _load_math_data(cfg, renderer)
        judge = SoftConversationJudge(prompt=MATH_JUDGE_PROMPT, **jk)
    elif cfg.task == "lcb":
        items = _load_lcb_data(cfg, renderer)
        judge = SoftConversationJudge(prompt=LCB_JUDGE_PROMPT, **jk)
    elif cfg.task == "apps":
        items = _load_apps_data(cfg, renderer)
        judge = SoftConversationJudge(prompt=APPS_JUDGE_PROMPT, **jk)
    else:
        items = _load_poly_data(cfg, renderer)
        judge = None
    pirate_judge = (
        StyleJudge(cfg.style_desc, model=cfg.judge_model)
        if cfg.task.startswith("qa") and (cfg.pirate_reward_weight != 0.0 or cfg.style_monitor)
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
    schedule = _parse_schedule(cfg.penalty_schedule)
    if schedule:
        total = sum(n for _, n in schedule)
        logger.info(f"Penalty schedule: {schedule} (sum={total}, n_batches={n_batches})")
        if total != n_batches:
            logger.warning(
                f"Schedule batch total ({total}) != n_batches ({n_batches}); "
                f"final segment '{schedule[-1][0]}' holds for the remainder."
            )

    ctx = _Ctx(
        cfg=cfg, pt=pt, tokenizer=tokenizer, judge=judge, pirate_judge=pirate_judge,
        items=items, tc=tc, adam=adam, cot_params=cot_params, out_params=out_params,
        schedule=schedule, cot_pen_batches=cot_pen_batches, n_batches=n_batches,
        prompts_per_step=prompts_per_step, ml_logger=ml_logger,
    )
    if cfg.async_k > 0:
        await _run_async(ctx, start_batch)
    else:
        await _run_sync(ctx, start_batch)

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
