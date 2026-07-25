"""Build the hard-math + sub-step-hint pool (env 2). Three stages:

A. Difficulty filter: sample each candidate problem (Hendrycks MATH level>=4,
   nlile/hendrycks-MATH-benchmark train split) k times at T=4096 on Qwen3-8B with
   no hint; keep problems with pass_count <= --max-pass.
B. Hint extraction: Claude (claude-opus-4-8) extracts one pivotal INTERMEDIATE
   step from the reference solution as a short leak-style hint; hints that contain
   the final answer are dropped (programmatic check).
C. With-hint verification: sample k times WITH the hint; keep problems where the
   hint helps (with_hint_pass > no_hint_pass) or at least unlocks the problem
   (with_hint_pass > 0 when no_hint_pass == 0).

Writes data/math_hint_pool.json (consumed by src/spillover/env_math_hint.py),
with per-problem stats for both stages. Per-sample transcripts land in
logs/math-pool/.

Usage:
  set -a && source .env && set +a
  uv run scripts/build_math_pool.py --n-candidates 1200 --k 3
"""

import argparse
import asyncio
import json
import logging
import random

import time
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer
from datasets import load_dataset

from src.spillover.env_math_hint import (
    FORMAT_PREFIX,
    FORMAT_SUFFIX,
    HINT_TEMPLATES,
    _normalize_answer,
    check_math_answer,
)
from scripts.eval_cot_uplift import _get_phase_tokens

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("build_math_pool")

MODEL = "Qwen/Qwen3-8B"

HINT_EXTRACTION_PROMPT = """Below is a competition math problem and its reference solution.

Extract ONE pivotal intermediate step from the solution — a key substitution, factorization, identity, case split, or intermediate result that meaningfully unlocks the problem. Phrase it as a single short sentence of at most 25 words, as it might appear in a leaked note (e.g. "the substitution u = x^2 - 1 reduces it to a quadratic", "the key is that the sum telescopes to 1 - 1/(n+1)").

STRICT RULES:
- Do NOT state or imply the final answer, even partially.
- The hint must be an intermediate step only.
- Output ONLY the hint sentence, nothing else.

# PROBLEM
{problem}

# REFERENCE SOLUTION
{solution}
"""


async def sample_passes(sp, tokenizer, pt, items, k, batch_size, out_file, label):
    """items: [{idx, prompt_tokens, answer}] -> {idx: pass_count}; logs transcripts."""
    cot_params = types.SamplingParams(max_tokens=4096, temperature=1.0, stop=pt.cot_stop)
    out_params = types.SamplingParams(max_tokens=1000, temperature=1.0, stop=pt.out_stop)
    passes = {}
    of = open(out_file, "w")
    for b_start in range(0, len(items), batch_size):
        t0 = time.time()
        batch = items[b_start : b_start + batch_size]
        cot_futs = {
            (it["idx"], j): sp.sample(
                types.ModelInput.from_ints(it["prompt_tokens"] + pt.cot_prefix),
                num_samples=1, sampling_params=cot_params,
            )
            for it in batch for j in range(k)
        }
        out_futs = {}
        for (idx, j), f in cot_futs.items():
            try:
                ct = list(f.result().sequences[0].tokens)
            except Exception:
                continue
            it = next(x for x in batch if x["idx"] == idx)
            out_futs[(idx, j)] = sp.sample(
                types.ModelInput.from_ints(it["prompt_tokens"] + pt.cot_prefix + ct + pt.bridge),
                num_samples=1, sampling_params=out_params,
            )
        for it in batch:
            n_pass = 0
            for j in range(k):
                f = out_futs.get((it["idx"], j))
                if f is None:
                    continue
                try:
                    out_text = tokenizer.decode(f.result().sequences[0].tokens)
                except Exception:
                    continue
                ok = check_math_answer(out_text, it["answer"])
                n_pass += int(ok)
                of.write(json.dumps({
                    "idx": it["idx"], "sample": j, "correct": ok,
                    "out_text": out_text[-1500:],
                }, ensure_ascii=False) + "\n")
            passes[it["idx"]] = n_pass
        of.flush()
        done = len(passes)
        logger.info(f"[{label}] {done}/{len(items)} mean_pass@{k}="
                    f"{sum(passes.values())/max(done,1):.2f} ({time.time()-t0:.0f}s)")
    of.close()
    return passes


async def extract_hints(problems, concurrency=20):
    """problems: [{idx, problem, solution, answer}] -> {idx: hint or None}."""
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()
    sem = asyncio.Semaphore(concurrency)

    async def one(p):
        async with sem:
            for _ in range(3):
                try:
                    resp = await client.messages.create(
                        model="claude-opus-4-8",
                        max_tokens=200,
                        messages=[{
                            "role": "user",
                            "content": HINT_EXTRACTION_PROMPT.format(
                                problem=p["problem"], solution=p["solution"]
                            ),
                        }],
                    )
                    hint = next(
                        (b.text for b in resp.content if b.type == "text"), ""
                    ).strip().strip('"')
                    if not hint or len(hint.split()) > 40:
                        continue
                    # Reject hints leaking the final answer
                    ans_norm = _normalize_answer(p["answer"])
                    if len(ans_norm) > 1 and ans_norm in _normalize_answer(hint):
                        logger.info(f"idx {p['idx']}: hint leaked answer, retrying")
                        continue
                    return p["idx"], hint
                except Exception as e:
                    logger.warning(f"hint extraction failed idx {p['idx']}: {e}")
                    await asyncio.sleep(2)
            return p["idx"], None

    results = await asyncio.gather(*[one(p) for p in problems])
    return dict(results)


async def main_async(args):
    ds = load_dataset("nlile/hendrycks-MATH-benchmark", split="train")
    rows = [r for r in ds if int(r["level"]) >= 4 and r["answer"].strip()]
    rng = random.Random(42)
    rng.shuffle(rows)
    rows = rows[: args.n_candidates]
    logger.info(f"{len(rows)} candidate problems (level>=4)")

    tokenizer = get_tokenizer(MODEL)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(MODEL), tokenizer
    )
    pt = _get_phase_tokens(MODEL, tokenizer, renderer)
    service = tinker.ServiceClient()
    sp = service.create_sampling_client(base_model=MODEL)
    log_dir = Path("logs/math-pool")
    log_dir.mkdir(parents=True, exist_ok=True)

    def build_items(pool, hint_map=None):
        items = []
        hint_rng = random.Random(43)
        for p in pool:
            hint_part = ""
            if hint_map:
                hint_part = hint_rng.choice(HINT_TEMPLATES).format(hint=hint_map[p["idx"]]) + "\n\n"
            prompt_text = FORMAT_PREFIX + hint_part + p["problem"] + FORMAT_SUFFIX
            toks = renderer.build_generation_prompt(
                [{"role": "user", "content": prompt_text}]
            ).to_ints()
            items.append({"idx": p["idx"], "prompt_tokens": toks, "answer": p["answer"]})
        return items

    problems = [
        {"idx": i, "problem": r["problem"], "solution": r["solution"],
         "answer": r["answer"], "level": int(r["level"]), "subject": r["subject"]}
        for i, r in enumerate(rows)
    ]

    # Stage A: no-hint difficulty filter
    nohint_passes = await sample_passes(
        sp, tokenizer, pt, build_items(problems), args.k, args.batch_size,
        log_dir / "stageA_nohint.jsonl", "A:no-hint",
    )
    hard = [p for p in problems if nohint_passes.get(p["idx"], args.k) <= args.max_pass]
    logger.info(f"Stage A: {len(hard)}/{len(problems)} problems with pass<= {args.max_pass}")

    # Stage B: hint extraction
    hint_map = await extract_hints(hard)
    hinted = [p for p in hard if hint_map.get(p["idx"])]
    logger.info(f"Stage B: {len(hinted)}/{len(hard)} problems got a clean hint")

    # Stage C: with-hint verification
    withhint_passes = await sample_passes(
        sp, tokenizer, pt, build_items(hinted, hint_map), args.k, args.batch_size,
        log_dir / "stageC_withhint.jsonl", "C:with-hint",
    )

    selected = []
    for p in hinted:
        nh = nohint_passes.get(p["idx"], 0)
        wh = withhint_passes.get(p["idx"], 0)
        if wh > nh or (nh == 0 and wh > 0):
            selected.append({
                "problem": p["problem"], "answer": p["answer"], "hint": hint_map[p["idx"]],
                "level": p["level"], "subject": p["subject"],
                "nohint_pass": nh, "withhint_pass": wh, "k": args.k,
                "solution": p["solution"],
            })
    logger.info(f"Stage C: selected {len(selected)} problems where the hint helps")

    out = {
        "source": "nlile/hendrycks-MATH-benchmark train, level>=4, seed 42",
        "model": MODEL, "k": args.k, "max_pass": args.max_pass,
        "n_candidates": len(problems), "n_hard": len(hard), "n_hinted": len(hinted),
        "n_selected": len(selected),
        "problems": selected,
    }
    Path(args.output).parent.mkdir(exist_ok=True)
    Path(args.output).write_text(json.dumps(out, indent=1))
    logger.info(f"wrote {args.output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-candidates", type=int, default=1200)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--max-pass", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--output", default="data/math_hint_pool.json")
    args = parser.parse_args()

    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
