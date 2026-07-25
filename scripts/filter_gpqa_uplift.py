"""Uplift-filter GPQA-main: keep questions where the CoT is load-bearing.

Samples each (hint-free) question k times at T=0 and k times at T=4096 per model,
then selects questions with pass@k(T=4096) > 0 and pass@k(T=0) == 0 for the
FILTER_MODEL (Qwen3-8B, the weaker model; other models' rates are recorded for
reporting). Writes data/gpqa_uplift_pool.json with per-question stats and the
selected Record IDs, consumed by src/spillover/env_qa_hard.py.

Usage:
  set -a && source .env && set +a
  uv run scripts/filter_gpqa_uplift.py --model Qwen/Qwen3-8B Qwen/Qwen3.6-35B-A3B
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.spillover.env_mmlu import FORMAT_PREFIX, FORMAT_SUFFIX, check_boxed_answer
from src.spillover.env_qa_hard import load_gpqa_raw
from scripts.eval_cot_uplift import _get_phase_tokens, _empty_cot_tokens

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("filter_gpqa")

FILTER_MODEL = "Qwen/Qwen3-8B"


def _build_prompt(q):
    body = q["question"] + "\n" + "\n".join(
        f"{letter}. {text}" for letter, text in zip("ABCD", q["choices"])
    )
    return FORMAT_PREFIX + body + FORMAT_SUFFIX  # no hint


async def sample_rates(sp, tokenizer, pt, empty_cot, items, budget, k, batch_size, label):
    cot_params = types.SamplingParams(max_tokens=max(budget, 1), temperature=1.0, stop=pt.cot_stop)
    out_params = types.SamplingParams(max_tokens=600, temperature=1.0, stop=pt.out_stop)
    passes = {}
    for b_start in range(0, len(items), batch_size):
        batch = items[b_start : b_start + batch_size]
        cot_futs = {}
        for it in batch:
            for j in range(k):
                if budget == 0:
                    cot_futs[(it["record_id"], j)] = None
                else:
                    cot_futs[(it["record_id"], j)] = sp.sample(
                        types.ModelInput.from_ints(it["prompt_tokens"] + pt.cot_prefix),
                        num_samples=1, sampling_params=cot_params,
                    )
        out_futs = {}
        for it in batch:
            for j in range(k):
                f = cot_futs[(it["record_id"], j)]
                try:
                    ct = [] if f is None else list(f.result().sequences[0].tokens)
                except Exception:
                    continue
                mid = empty_cot if budget == 0 else (ct + pt.bridge)
                out_futs[(it["record_id"], j)] = sp.sample(
                    types.ModelInput.from_ints(it["prompt_tokens"] + pt.cot_prefix + mid),
                    num_samples=1, sampling_params=out_params,
                )
        for it in batch:
            n_pass = 0
            for j in range(k):
                f = out_futs.get((it["record_id"], j))
                if f is None:
                    continue
                try:
                    out_text = tokenizer.decode(f.result().sequences[0].tokens)
                except Exception:
                    continue
                n_pass += int(check_boxed_answer(out_text, "ABCD"[it["correct_idx"]]))
            passes[it["record_id"]] = n_pass
        done = len(passes)
        logger.info(f"[{label} T={budget}] {done}/{len(items)} mean_pass@{k}="
                    f"{sum(passes.values())/max(done,1):.2f}")
    return passes


async def main_async(args):
    raw = load_gpqa_raw()
    if args.max_questions:
        raw = raw[: args.max_questions]
    service = tinker.ServiceClient()
    stats = {q["record_id"]: {"question": q["question"][:120]} for q in raw}

    for model_name in args.model:
        tokenizer = get_tokenizer(model_name)
        renderer = renderers.get_renderer(
            model_info.get_recommended_renderer_name(model_name), tokenizer
        )
        pt = _get_phase_tokens(model_name, tokenizer, renderer)
        sp = service.create_sampling_client(base_model=model_name)
        items = []
        for q in raw:
            prompt = renderer.build_generation_prompt(
                [{"role": "user", "content": _build_prompt(q)}]
            )
            items.append({**q, "prompt_tokens": prompt.to_ints()})
        empty_cot = _empty_cot_tokens(model_name, tokenizer, renderer, pt,
                                      items[0]["prompt_tokens"])
        for budget in (0, 4096):
            passes = await sample_rates(
                sp, tokenizer, pt, empty_cot, items, budget, args.k,
                args.batch_size, model_name,
            )
            key = f"{model_name.split('/')[-1]}_T{budget}_pass"
            for rid, n in passes.items():
                stats[rid][key] = n

    fk = f"{FILTER_MODEL.split('/')[-1]}"
    selected = [
        rid for rid, s in stats.items()
        if s.get(f"{fk}_T4096_pass", 0) > 0 and s.get(f"{fk}_T0_pass", 1) == 0
    ]
    out = {
        "k": args.k,
        "filter_model": FILTER_MODEL,
        "criterion": "pass@k(T=4096)>0 and pass@k(T=0)==0",
        "n_total": len(raw),
        "n_selected": len(selected),
        "selected_record_ids": selected,
        "stats": stats,
    }
    Path(args.output).parent.mkdir(exist_ok=True)
    Path(args.output).write_text(json.dumps(out, indent=1))
    logger.info(f"selected {len(selected)}/{len(raw)} questions -> {args.output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", nargs="+", default=["Qwen/Qwen3-8B", "Qwen/Qwen3.6-35B-A3B"])
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--output", default="data/gpqa_uplift_pool.json")
    args = parser.parse_args()

    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
