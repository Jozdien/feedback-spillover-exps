"""Env 3 feasibility gate: can a model pass Impossible-LCB tests at a nonzero rate?

The env died at 8B/35B because models couldn't clear the `conflicting` test sets
(reward variance ~0 → GRPO can't train). This gate samples a base model on both
splits and reports pass rates; the env is viable iff conflicting-pass > ~0.05.

Usage:
  set -a && source .env && set +a
  uv run scripts/pilot_lcb_gate.py --model nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16 \
      --n-problems 60 --samples-per-problem 4
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

from scripts.eval_cot_uplift import _get_phase_tokens
from src.spillover.env_lcb import extract_code, load_lcb_problems, run_tests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("pilot_lcb")


async def run_model(service, model_name, problems, args, summary_path):
    tokenizer = get_tokenizer(model_name)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(model_name), tokenizer
    )
    pt = _get_phase_tokens(model_name, tokenizer, renderer)
    sp = service.create_sampling_client(base_model=model_name)
    cot_params = types.SamplingParams(max_tokens=4096, temperature=1.0, stop=pt.cot_stop)
    out_params = types.SamplingParams(max_tokens=1500, temperature=1.0, stop=pt.out_stop)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    of = open(out_dir / f"{model_name.replace('/', '_')}.jsonl", "w")
    stats = {"original": [0, 0], "conflicting": [0, 0]}  # split -> [passes, n]

    for b_start in range(0, len(problems), args.batch_size):
        batch = problems[b_start : b_start + args.batch_size]
        reps = [p for p in batch for _ in range(args.samples_per_problem)]
        toks = [
            renderer.build_generation_prompt(
                [{"role": "user", "content": p["prompt"]}]
            ).to_ints()
            for p in reps
        ]
        cot_futs = [
            sp.sample(types.ModelInput.from_ints(t + pt.cot_prefix),
                      num_samples=1, sampling_params=cot_params)
            for t in toks
        ]
        out_futs = []
        for f, t in zip(cot_futs, toks):
            try:
                ct = list(f.result().sequences[0].tokens)
            except Exception:
                out_futs.append(None)
                continue
            out_futs.append(sp.sample(
                types.ModelInput.from_ints(t + pt.cot_prefix + ct + pt.bridge),
                num_samples=1, sampling_params=out_params))
        for f, p in zip(out_futs, reps):
            if f is None:
                continue
            try:
                out_text = tokenizer.decode(f.result().sequences[0].tokens)
            except Exception:
                continue
            code = extract_code(out_text)
            passed = 0.0
            if code:
                passed = await asyncio.to_thread(
                    run_tests, code, p["test"], p["entry_point"]
                )
            split = p["impossible_type"]
            stats[split][0] += passed
            stats[split][1] += 1
            of.write(json.dumps({
                "split": split, "passed": passed, "parsed": bool(code),
                "out_tail": out_text[-600:],
            }, ensure_ascii=False) + "\n")
        of.flush()
        logger.info(f"[{model_name}] " + "  ".join(
            f"{k}: {v[0]:.0f}/{v[1]}" for k, v in stats.items()))

    of.close()
    summary = {
        "model": model_name,
        **{f"{k}_pass": (v[0] / v[1] if v[1] else 0.0) for k, v in stats.items()},
        **{f"{k}_n": v[1] for k, v in stats.items()},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(summary_path, "a") as sf:
        sf.write(json.dumps(summary) + "\n")
    conf = summary["conflicting_pass"]
    logger.info(f"VERDICT {summary}")
    logger.info(f"  conflicting pass {conf:.3f}: "
                f"{'VIABLE for GRPO' if conf >= 0.05 else 'DEAD — no reward variance'}")


async def main_async(args):
    service = tinker.ServiceClient()
    problems = load_lcb_problems()
    # keep both splits, balanced, capped
    orig = [p for p in problems if p["impossible_type"] == "original"][: args.n_problems // 2]
    conf = [p for p in problems if p["impossible_type"] == "conflicting"][: args.n_problems // 2]
    problems = orig + conf
    logger.info(f"{len(problems)} problems ({len(orig)} original, {len(conf)} conflicting)")
    summary_path = Path(args.output_dir) / "summary.jsonl"
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    for model_name in args.model:
        await run_model(service, model_name, problems, args, summary_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", nargs="+", required=True)
    parser.add_argument("--n-problems", type=int, default=60)
    parser.add_argument("--samples-per-problem", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--output-dir", default="logs/lcb-pilot")
    args = parser.parse_args()

    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
