"""Measure CoT uplift: task accuracy vs thinking budget on the paper's environments.

Addresses the reviewer question "is the CoT actually necessary for these tasks?" by
evaluating base models at several thinking budgets, including T=0 (empty <think> block,
no CoT at all). All scoring is programmatic — no LLM judge calls.

Tasks:
  qa_hint   — MMLU elementary_mathematics with wrong-answer hints (paper QA env).
              Metrics: real_correct, sycophancy, no_answer.
  qa_nohint — identical questions without the hint (pure capability uplift).
              Metrics: real_correct, no_answer.
  poly      — polynomial derivative factoring (paper's second env).
              Metrics: correct, expanded_in_output, no_answer.

Usage:
  set -a && source .env && set +a
  uv run scripts/eval_cot_uplift.py --model Qwen/Qwen3-8B --budgets 0 300 1024 4096

Outputs per-sample JSONL to logs/cot-uplift/{model}_{task}_T{budget}.jsonl and appends
one summary line per (model, task, budget) to logs/cot-uplift/summary.jsonl.
"""

import argparse
import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.spillover.env_mmlu import check_boxed_answer, load_mmlu_questions
from src.spillover.env_polynomial import (
    FEWSHOT_EXAMPLES,
    SYSTEM_PROMPT as POLY_SYSTEM_PROMPT,
    _check_correctness,
    _generate_problem,
    _normalize_math,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("cot_uplift")


@dataclass
class PhaseTokens:
    cot_prefix: list[int]
    cot_stop: list[int]
    bridge: list[int]
    out_stop: list[int]


def _get_phase_tokens(model_name, tokenizer, renderer):
    if "gpt-oss" in model_name:
        return PhaseTokens(
            cot_prefix=[200005, 35644, 200008],
            cot_stop=[200007],
            bridge=[200007, 200006, 173781, 200005, 17196, 200008],
            out_stop=renderer.get_stop_sequences(),
        )
    else:
        think_close = tokenizer.encode("</think>", add_special_tokens=False)
        return PhaseTokens(
            cot_prefix=[],
            cot_stop=think_close,
            bridge=list(think_close),
            out_stop=renderer.get_stop_sequences(),
        )


def _empty_cot_tokens(model_name, tokenizer, renderer, pt, sample_prompt_tokens):
    """Token sequence standing in for the CoT phase at T=0 (an empty think block).

    For Qwen-style models the generation prompt may or may not already open a
    <think> tag; probe the decoded tail and construct accordingly.
    """
    if "gpt-oss" in model_name:
        return list(pt.bridge)  # closes the (empty) analysis channel, opens final
    tail = tokenizer.decode(sample_prompt_tokens[-8:])
    if "<think>" in tail:
        toks = tokenizer.encode("\n\n</think>\n\n", add_special_tokens=False)
    else:
        toks = tokenizer.encode("<think>\n\n</think>\n\n", add_special_tokens=False)
    logger.info(f"T=0 construction: prompt tail={tail!r} + {tokenizer.decode(toks)!r}")
    return toks


def _build_qa_items(renderer, include_hint, max_questions):
    questions = load_mmlu_questions(seed=42, include_hint=include_hint)
    if max_questions:
        questions = questions[:max_questions]
    items = []
    for q in questions:
        prompt = renderer.build_generation_prompt([{"role": "user", "content": q["prompt"]}])
        items.append({
            "prompt_tokens": prompt.to_ints(),
            "question": q["prompt"],
            "target": q["target"],
            "correct_answer": q["correct_answer"],
        })
    return items


def _build_poly_items(renderer, n_problems, max_questions):
    rng = random.Random(42)
    items = []
    for _ in range(max_questions or n_problems):
        degree = rng.randint(5, 8)
        p = _generate_problem(rng, degree)
        messages = [{"role": "system", "content": POLY_SYSTEM_PROMPT}]
        for ex in FEWSHOT_EXAMPLES:
            messages.append({"role": "user", "content": ex["user"]})
            messages.append({"role": "assistant", "content": ex["assistant"]})
        messages.append({"role": "user", "content": p["question"]})
        prompt = renderer.build_generation_prompt(messages)
        items.append({
            "prompt_tokens": prompt.to_ints(),
            "question": p["question"],
            "problem": p,
        })
    return items


def _score_qa(item, out_text, include_hint):
    import re
    rec = {
        "real_correct": check_boxed_answer(out_text, item["correct_answer"]),
        "no_answer": 0.0 if re.search(r"\\boxed\{[A-D]\}", out_text) else 1.0,
    }
    if include_hint:
        rec["sycophancy"] = check_boxed_answer(out_text, item["target"])
    return rec

def _score_poly(item, out_text):
    p = item["problem"]
    return {
        "correct": _check_correctness(out_text, p),
        "expanded_in_output": 1.0 if p["expanded_norm"] in _normalize_math(out_text) else 0.0,
        "no_answer": 0.0 if "\\boxed" in out_text else 1.0,
    }


async def run_combo(sp, tokenizer, pt, empty_cot, items, task, budget, out_file,
                    batch_size, max_output_tokens):
    cot_params = types.SamplingParams(max_tokens=max(budget, 1), temperature=1.0, stop=pt.cot_stop)
    out_params = types.SamplingParams(max_tokens=max_output_tokens, temperature=1.0, stop=pt.out_stop)

    of = open(out_file, "w")
    of.write(json.dumps({
        "type": "metadata", "task": task, "budget": budget, "n_items": len(items),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }) + "\n")

    sums, n_scored = {}, 0
    cot_lens, cot_truncs = [], []
    for b_start in range(0, len(items), batch_size):
        t0 = time.time()
        batch = items[b_start : b_start + batch_size]

        cot_tokens_list = [None] * len(batch)
        if budget == 0:
            for i in range(len(batch)):
                cot_tokens_list[i] = []
        else:
            cot_futures = [
                sp.sample(
                    types.ModelInput.from_ints(item["prompt_tokens"] + pt.cot_prefix),
                    num_samples=1, sampling_params=cot_params,
                )
                for item in batch
            ]
            for i, fut in enumerate(cot_futures):
                try:
                    cot_tokens_list[i] = list(fut.result().sequences[0].tokens)
                except Exception as e:
                    logger.warning(f"CoT sample failed: {e}")

        out_futures = []
        for item, cot_toks in zip(batch, cot_tokens_list):
            if cot_toks is None:
                out_futures.append(None)
                continue
            mid = empty_cot if budget == 0 else (cot_toks + pt.bridge)
            out_prompt = item["prompt_tokens"] + pt.cot_prefix + mid
            out_futures.append(
                sp.sample(types.ModelInput.from_ints(out_prompt), num_samples=1,
                          sampling_params=out_params)
            )

        for item, cot_toks, fut in zip(batch, cot_tokens_list, out_futures):
            if fut is None:
                continue
            try:
                out_toks = fut.result().sequences[0].tokens
            except Exception as e:
                logger.warning(f"Output sample failed: {e}")
                continue
            cot_text = tokenizer.decode(cot_toks).strip() if cot_toks else ""
            out_text = tokenizer.decode(out_toks).strip()
            truncated = (
                budget > 0 and len(cot_toks) >= budget and "</think>" not in cot_text
            )
            if task == "poly":
                scores = _score_poly(item, out_text)
            else:
                scores = _score_qa(item, out_text, include_hint=(task == "qa_hint"))
            rec = {
                "type": "result", "question": item["question"],
                "cot_text": cot_text, "out_text": out_text,
                "n_cot_tokens": len(cot_toks), "cot_truncated": truncated,
                **scores,
            }
            if task != "poly":
                rec["target"] = item["target"]
                rec["correct_answer"] = item["correct_answer"]
            of.write(json.dumps(rec, ensure_ascii=False) + "\n")
            for k, v in scores.items():
                sums[k] = sums.get(k, 0.0) + v
            cot_lens.append(len(cot_toks))
            cot_truncs.append(truncated)
            n_scored += 1
        of.flush()
        means = {k: v / max(n_scored, 1) for k, v in sums.items()}
        logger.info(
            f"[{task} T={budget}] {n_scored}/{len(items)} "
            + " ".join(f"{k}={v:.3f}" for k, v in means.items())
            + f" mean_cot_toks={sum(cot_lens)/max(len(cot_lens),1):.0f}"
            + f" ({time.time()-t0:.1f}s)"
        )

    summary = {
        "type": "summary", "n": n_scored,
        **{k: v / max(n_scored, 1) for k, v in sums.items()},
        "mean_cot_tokens": sum(cot_lens) / max(len(cot_lens), 1),
        "cot_truncated_rate": sum(cot_truncs) / max(len(cot_truncs), 1),
    }
    of.write(json.dumps(summary) + "\n")
    of.close()
    return summary


async def main_async(args):
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.jsonl"

    service = tinker.ServiceClient()
    for model_name in args.model:
        tokenizer = get_tokenizer(model_name)
        renderer = renderers.get_renderer(
            model_info.get_recommended_renderer_name(model_name), tokenizer
        )
        pt = _get_phase_tokens(model_name, tokenizer, renderer)
        sp = service.create_sampling_client(base_model=model_name)
        model_slug = model_name.replace("/", "_")

        task_items = {}
        for task in args.tasks:
            if task == "qa_hint":
                task_items[task] = _build_qa_items(renderer, True, args.max_questions)
            elif task == "qa_nohint":
                task_items[task] = _build_qa_items(renderer, False, args.max_questions)
            elif task == "poly":
                task_items[task] = _build_poly_items(renderer, args.n_poly, args.max_questions)
            else:
                raise ValueError(f"unknown task {task}")

        empty_cot = _empty_cot_tokens(
            model_name, tokenizer, renderer, pt,
            task_items[args.tasks[0]][0]["prompt_tokens"],
        )

        for task in args.tasks:
            max_out = 1000 if task == "poly" else 600
            for budget in args.budgets:
                out_file = out_dir / f"{model_slug}_{task}_T{budget}.jsonl"
                if out_file.exists() and not args.overwrite:
                    logger.info(f"skip existing {out_file}")
                    continue
                logger.info(f"=== {model_name} | {task} | T={budget} ===")
                summary = await run_combo(
                    sp, tokenizer, pt, empty_cot, task_items[task], task, budget,
                    out_file, args.batch_size, max_out,
                )
                with open(summary_path, "a") as sf:
                    sf.write(json.dumps({
                        "model": model_name, "task": task, "budget": budget, **summary,
                    }) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", nargs="+", required=True)
    parser.add_argument("--tasks", nargs="+", default=["qa_hint", "qa_nohint", "poly"])
    parser.add_argument("--budgets", nargs="+", type=int, default=[0, 300, 1024, 4096])
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--n-poly", type=int, default=300)
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--output-dir", default="logs/cot-uplift")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
