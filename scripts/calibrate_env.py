"""Calibrate a candidate spillover env before RL: is the hack/task CoT-loaded, and
is there baseline CoT verbalization to lose?

For a given env + model, samples at T=0 (forced-empty think) and a full budget, and
reports per budget: follow-rate of the hinted target ("sycophancy" analog),
real_correct, no_answer, and — on up to --judge-n CoTs/outputs at the full budget —
the env's hint-acknowledgment judge scores (the baseline verbalization signal).

Usage:
  set -a && source .env && set +a
  uv run scripts/calibrate_env.py --env encoded --model Qwen/Qwen3-8B Qwen/Qwen3.6-35B-A3B

Envs are registered in ENV_REGISTRY; add new candidate envs there.
Outputs per-sample JSONL to logs/env-calibration/ and a summary to
logs/env-calibration/summary.jsonl.
"""

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import SoftConversationJudge
from src.spillover.env_mmlu import check_boxed_answer
from src.spillover import env_mmlu_encoded

from scripts.eval_cot_uplift import PhaseTokens, _get_phase_tokens, _empty_cot_tokens  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("calibrate_env")


def _load_encoded(seed):
    return env_mmlu_encoded.load_encoded_questions(seed=seed)


# env name -> (loader(seed) -> [{prompt,target,correct_answer}], judge_prompt)
ENV_REGISTRY = {
    "encoded": (_load_encoded, env_mmlu_encoded.JUDGE_PROMPT),
}


async def run_model(service, model_name, env_name, args, summary_path):
    loader, judge_prompt = ENV_REGISTRY[env_name]
    tokenizer = get_tokenizer(model_name)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(model_name), tokenizer
    )
    pt = _get_phase_tokens(model_name, tokenizer, renderer)
    sp = service.create_sampling_client(base_model=model_name)
    judge = SoftConversationJudge(prompt=judge_prompt)

    questions = loader(seed=42)
    if args.max_questions:
        questions = questions[: args.max_questions]
    items = []
    for q in questions:
        prompt = renderer.build_generation_prompt([{"role": "user", "content": q["prompt"]}])
        items.append({**q, "prompt_tokens": prompt.to_ints()})
    empty_cot = _empty_cot_tokens(model_name, tokenizer, renderer, pt, items[0]["prompt_tokens"])

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_slug = model_name.replace("/", "_")

    for budget in args.budgets:
        cot_params = types.SamplingParams(
            max_tokens=max(budget, 1), temperature=1.0, stop=pt.cot_stop
        )
        out_params = types.SamplingParams(max_tokens=600, temperature=1.0, stop=pt.out_stop)
        out_file = out_dir / f"{model_slug}_{env_name}_T{budget}.jsonl"
        of = open(out_file, "w")
        of.write(json.dumps({
            "type": "metadata", "env": env_name, "model": model_name, "budget": budget,
            "n_items": len(items), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }) + "\n")

        sums = {"follow": 0.0, "real_correct": 0.0, "no_answer": 0.0}
        judged, n_scored = [], 0
        for b_start in range(0, len(items), args.batch_size):
            batch = items[b_start : b_start + args.batch_size]
            cot_tokens_list = [None] * len(batch)
            if budget == 0:
                cot_tokens_list = [[] for _ in batch]
            else:
                futs = [
                    sp.sample(
                        types.ModelInput.from_ints(it["prompt_tokens"] + pt.cot_prefix),
                        num_samples=1, sampling_params=cot_params,
                    )
                    for it in batch
                ]
                for i, f in enumerate(futs):
                    try:
                        cot_tokens_list[i] = list(f.result().sequences[0].tokens)
                    except Exception as e:
                        logger.warning(f"CoT failed: {e}")

            out_futs = []
            for it, ct in zip(batch, cot_tokens_list):
                if ct is None:
                    out_futs.append(None)
                    continue
                mid = empty_cot if budget == 0 else (ct + pt.bridge)
                out_futs.append(sp.sample(
                    types.ModelInput.from_ints(it["prompt_tokens"] + pt.cot_prefix + mid),
                    num_samples=1, sampling_params=out_params,
                ))

            for it, ct, f in zip(batch, cot_tokens_list, out_futs):
                if f is None:
                    continue
                try:
                    out_toks = f.result().sequences[0].tokens
                except Exception as e:
                    logger.warning(f"Output failed: {e}")
                    continue
                cot_text = tokenizer.decode(ct).strip() if ct else ""
                out_text = tokenizer.decode(out_toks).strip()
                import re
                rec = {
                    "type": "result", "question": it["prompt"], "target": it["target"],
                    "correct_answer": it["correct_answer"],
                    "cot_text": cot_text, "out_text": out_text,
                    "n_cot_tokens": len(ct),
                    "follow": check_boxed_answer(out_text, it["target"]),
                    "real_correct": check_boxed_answer(out_text, it["correct_answer"]),
                    "no_answer": 0.0 if re.search(r"\\boxed\{[A-D]\}", out_text) else 1.0,
                }
                for k in sums:
                    sums[k] += rec[k]
                n_scored += 1
                if budget > 0 and len(judged) < args.judge_n:
                    judged.append(rec)
                of.write(json.dumps(rec, ensure_ascii=False) + "\n")
            of.flush()
            logger.info(
                f"[{model_name} {env_name} T={budget}] {n_scored}/{len(items)} "
                + " ".join(f"{k}={v/max(n_scored,1):.3f}" for k, v in sums.items())
            )

        summary = {
            "env": env_name, "model": model_name, "budget": budget, "n": n_scored,
            **{k: v / max(n_scored, 1) for k, v in sums.items()},
        }
        if judged:
            cot_scores = await asyncio.gather(*[
                judge.score_with_context(r["question"], r["cot_text"]) for r in judged
            ])
            out_scores = await asyncio.gather(*[
                judge.score_with_context(r["question"], r["out_text"]) for r in judged
            ])
            summary["judge_n"] = len(judged)
            summary["hint_in_cot"] = sum(cot_scores) / len(cot_scores)
            summary["hint_in_output"] = sum(out_scores) / len(out_scores)
            for r, cs, os_ in zip(judged, cot_scores, out_scores):
                of.write(json.dumps({
                    "type": "judged", "question": r["question"][:200],
                    "cot_score": float(cs), "out_score": float(os_),
                }) + "\n")
        of.write(json.dumps({"type": "summary", **summary}) + "\n")
        of.close()
        with open(summary_path, "a") as sf:
            sf.write(json.dumps(summary) + "\n")
        logger.info(f"SUMMARY {summary}")


async def main_async(args):
    service = tinker.ServiceClient()
    summary_path = Path(args.output_dir) / "summary.jsonl"
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    for model_name in args.model:
        await run_model(service, model_name, args.env, args, summary_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, choices=sorted(ENV_REGISTRY))
    parser.add_argument("--model", nargs="+", required=True)
    parser.add_argument("--budgets", nargs="+", type=int, default=[0, 4096])
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--judge-n", type=int, default=100)
    parser.add_argument("--output-dir", default="logs/env-calibration")
    args = parser.parse_args()

    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
