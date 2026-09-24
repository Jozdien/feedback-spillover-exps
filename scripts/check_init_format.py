"""Initialization (no-RL) format check for style-SFT checkpoints on the MMLU QA task.

Samples N MMLU-with-hint prompts exactly as src/spillover/train_grpo.py does (same
load_mmlu_questions(seed=42) prompts, same renderer, same two-phase generation: CoT up to
--max-cot-tokens with stop "</think>", then the "</think>" bridge, then output up to 600 tokens,
temperature 1.0) and classifies each output into one of

  empty | no_boxed | boxed_no_expl_header | bare<5w | short<20w | well_formed

(the modes used to diagnose the v1 pirate SFT), plus the fraction of well-formed outputs that are in
pirate speak (>=2 distinct of: arr, ye, matey, be, aye, scurvy, avast, hearties). Every sampled CoT and
output is written to <out-dir>/<label>.jsonl.

Usage:
    set -a && source .env && set +a
    uv run scripts/check_init_format.py --n 200 --out-dir logs/sft-init-format-check \
        --model "pirate-v1=tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/sampler_weights/final" \
        --model "piglatin=tinker://a0ed9ddb-9a6d-515c-b0e9-3f4ebab4e44e:train:0/sampler_weights/final" \
        --model "base=Qwen/Qwen3-8B"
"""

import argparse
import asyncio
import json
import re
import time
from collections import Counter
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.spillover.env_mmlu import load_mmlu_questions

BASE_MODEL = "Qwen/Qwen3-8B"
PIRATE_KW = ["arr", "ye", "matey", "be", "aye", "scurvy", "avast", "hearties"]
MODES = ["empty", "no_boxed", "boxed_no_expl_header", "bare<5w", "short<20w", "well_formed"]


def classify(out_text: str) -> str:
    o = out_text.replace("<|im_end|>", "").strip()
    if not o:
        return "empty"
    if "\\boxed" not in o:
        return "no_boxed"
    m = re.search(r"### Explanation\s*(.*)", o, re.S)
    if not m:
        return "boxed_no_expl_header"
    w = len(m.group(1).split())
    if w < 5:
        return "bare<5w"
    if w < 20:
        return "short<20w"
    return "well_formed"


def is_pirate(text: str) -> bool:
    low = text.lower()
    return sum(1 for k in PIRATE_KW if re.search(r"\b" + k + r"\b", low)) >= 2


async def sample_model(label: str, path: str, items, max_cot_tokens: int, out_dir: Path, sem_n: int):
    service = tinker.ServiceClient()
    if path.startswith("tinker://"):
        sp = service.create_sampling_client(model_path=path)
    else:
        sp = service.create_sampling_client(base_model=path)
    tokenizer = get_tokenizer(BASE_MODEL)
    think_close = tokenizer.encode("</think>", add_special_tokens=False)
    renderer = renderers.get_renderer(model_info.get_recommended_renderer_name(BASE_MODEL), tokenizer)
    cot_params = types.SamplingParams(max_tokens=max_cot_tokens, temperature=1.0, stop=think_close)
    out_params = types.SamplingParams(max_tokens=600, temperature=1.0, stop=renderer.get_stop_sequences())
    sem = asyncio.Semaphore(sem_n)

    async def one(item):
        async with sem:
            cot = await sp.sample_async(types.ModelInput.from_ints(item["prompt_tokens"]), num_samples=1,
                                        sampling_params=cot_params)
            cot_tok = list(cot.sequences[0].tokens)
            out = await sp.sample_async(types.ModelInput.from_ints(item["prompt_tokens"] + cot_tok + think_close),
                                        num_samples=1, sampling_params=out_params)
            out_text = tokenizer.decode(out.sequences[0].tokens).strip()
            return {"question": item["question"], "target": item["target"],
                    "cot_text": tokenizer.decode(cot_tok).strip(), "out_text": out_text,
                    "cot_tokens": len(cot_tok), "out_tokens": len(out.sequences[0].tokens),
                    "mode": classify(out_text), "pirate": is_pirate(out_text),
                    "starts_with_think_close": out_text.startswith("</think>")}

    t0 = time.time()
    rows = await asyncio.gather(*[one(it) for it in items])
    with open(out_dir / f"{label}.jsonl", "w") as f:
        f.write(json.dumps({"type": "metadata", "label": label, "path": path, "n": len(rows),
                            "max_cot_tokens": max_cot_tokens, "max_output_tokens": 600, "temperature": 1.0,
                            "question_seed": 42, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"[{label}] {len(rows)} samples in {time.time() - t0:.0f}s -> {out_dir / (label + '.jsonl')}", flush=True)
    return rows


def summarize(label: str, rows: list[dict]) -> dict:
    n = len(rows)
    c = Counter(r["mode"] for r in rows)
    wf = [r for r in rows if r["mode"] == "well_formed"]
    return {"label": label, "n": n, **{m: c.get(m, 0) / n for m in MODES},
            "pirate_all": sum(r["pirate"] for r in rows) / n,
            "pirate_among_well_formed": (sum(r["pirate"] for r in wf) / len(wf)) if wf else float("nan"),
            "starts_with_think_close": sum(r["starts_with_think_close"] for r in rows) / n}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", required=True, help="label=tinker://... or label=Base/Model")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--max-cot-tokens", type=int, default=300)
    ap.add_argument("--out-dir", default="logs/sft-init-format-check")
    ap.add_argument("--concurrency", type=int, default=64)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = get_tokenizer(BASE_MODEL)
    renderer = renderers.get_renderer(model_info.get_recommended_renderer_name(BASE_MODEL), tokenizer)
    questions = load_mmlu_questions(seed=42)[: args.n]
    items = [{"prompt_tokens": renderer.build_generation_prompt([{"role": "user", "content": q["prompt"]}]).to_ints(),
              "question": q["prompt"], "target": q["target"]} for q in questions]

    specs = [m.split("=", 1) for m in args.model]
    results = await asyncio.gather(*[sample_model(lab, path, items, args.max_cot_tokens, out_dir, args.concurrency)
                                     for lab, path in specs])
    summaries = [summarize(lab, rows) for (lab, _), rows in zip(specs, results)]
    cols = MODES + ["pirate_among_well_formed", "starts_with_think_close"]
    print("\n| model | n | " + " | ".join(cols) + " |")
    print("|---|---|" + "---|" * len(cols))
    for s in summaries:
        print(f"| {s['label']} | {s['n']} | " + " | ".join(f"{100 * s[c]:.0f}%" for c in cols) + " |")
    with open(out_dir / "summary.jsonl", "a") as f:
        for s in summaries:
            f.write(json.dumps({**s, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "max_cot_tokens": args.max_cot_tokens}) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
