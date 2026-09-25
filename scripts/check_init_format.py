"""Initialization (no-RL) format check for style-SFT checkpoints on the MMLU QA task.

Samples N MMLU-with-hint prompts exactly as src/spillover/train_grpo.py does (same
load_mmlu_questions(seed=42) prompts, same renderer, same two-phase generation: CoT up to
--max-cot-tokens with stop "</think>", then the "</think>" bridge, then output up to 600 tokens,
temperature 1.0) and classifies each output into one of

  empty | no_boxed | boxed_no_expl_header | bare<5w | short<20w | well_formed

(the modes used to diagnose the v1 pirate SFT), plus the fraction of well-formed outputs that are in
pirate speak (>=2 distinct of: arr, ye, matey, be, aye, scurvy, avast, hearties), in Pig Latin, or in Chinese
(>=10 CJK chars, >=50% of letters CJK -- the data filter's rule). Every sampled CoT and
output is written to <out-dir>/<label>.jsonl.

Usage:
    set -a && source .env && set +a
    uv run scripts/check_init_format.py --n 200 --out-dir logs/sft-init-format-check \
        --model "pirate-v1=tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/sampler_weights/final" \
        --model "piglatin=tinker://a0ed9ddb-9a6d-515c-b0e9-3f4ebab4e44e:train:0/sampler_weights/final" \
        --model "base=Qwen/Qwen3-8B"
    # other base models: --base-model sets the tokenizer + chat template (renderer) for ALL --model specs of the
    # call. Qwen3.5/3.6 (renderer qwen3_5) generation prompts already end with "<think>\n"; like the trainer
    # (cot_prefix=[]), the CoT is sampled directly after that prompt and "</think>" is the bridge.
    uv run scripts/check_init_format.py --n 200 --base-model Qwen/Qwen3.6-27B --out-dir logs/sft-init-format-check \
        --model "27b-base=Qwen/Qwen3.6-27B" --model "27b-pirate-v2=tinker://..."
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
    # Chinese prose has no spaces: count CJK characters as ~0.6 words each (as quality_check_style_data.py does)
    w = len(m.group(1).split()) + 0.6 * sum(1 for ch in m.group(1) if "\u4e00" <= ch <= "\u9fff")
    if w < 5:
        return "bare<5w"
    if w < 20:
        return "short<20w"
    return "well_formed"


def is_pirate(text: str) -> bool:
    low = text.lower()
    return sum(1 for k in PIRATE_KW if re.search(r"\b" + k + r"\b", low)) >= 2


def is_piglatin(text: str) -> bool:
    """Same rule as the Pig-Latin data filter: >=5 alphabetic words (len>=3) and >=60% of them end in 'ay'."""
    words = [w for w in re.findall(r"[A-Za-z]+", text) if len(w) >= 3]
    return len(words) >= 5 and sum(w.lower().endswith("ay") for w in words) / len(words) >= 0.6


def is_chinese(text: str) -> bool:
    """Same rule as the Chinese data filter (has_chinese): >=10 CJK chars and CJK >=50% of CJK+ASCII letters."""
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    return cjk >= 10 and cjk / max(cjk + latin, 1) >= 0.5


async def sample_model(label: str, path: str, items, max_cot_tokens: int, out_dir: Path, sem_n: int, base_model: str):
    service = tinker.ServiceClient()
    if path.startswith("tinker://"):
        sp = service.create_sampling_client(model_path=path)
    else:
        sp = service.create_sampling_client(base_model=path)
    tokenizer = get_tokenizer(base_model)
    think_close = tokenizer.encode("</think>", add_special_tokens=False)
    renderer = renderers.get_renderer(model_info.get_recommended_renderer_name(base_model), tokenizer)
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
                    "mode": classify(out_text), "pirate": is_pirate(out_text), "piglatin": is_piglatin(out_text),
                    "chinese": is_chinese(out_text),
                    "starts_with_think_close": out_text.startswith("</think>")}

    t0 = time.time()
    rows = await asyncio.gather(*[one(it) for it in items])
    with open(out_dir / f"{label}.jsonl", "w") as f:
        f.write(json.dumps({"type": "metadata", "label": label, "path": path, "base_model": base_model, "n": len(rows),
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
            "piglatin_all": sum(r.get("piglatin", False) for r in rows) / n,
            "piglatin_among_well_formed": (sum(r.get("piglatin", False) for r in wf) / len(wf)) if wf else float("nan"),
            "chinese_all": sum(r.get("chinese", False) for r in rows) / n,
            "chinese_among_well_formed": (sum(r.get("chinese", False) for r in wf) / len(wf)) if wf else float("nan"),
            "starts_with_think_close": sum(r["starts_with_think_close"] for r in rows) / n}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", required=True, help="label=tinker://... or label=Base/Model")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--max-cot-tokens", type=int, default=300)
    ap.add_argument("--out-dir", default="logs/sft-init-format-check")
    ap.add_argument("--concurrency", type=int, default=64)
    ap.add_argument("--base-model", default="Qwen/Qwen3-8B", help="tokenizer/chat template for all --model specs")
    ap.add_argument("--reclassify", action="store_true",
                    help="no sampling: re-run classify() on the existing <out-dir>/<label>.jsonl of each --model spec")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.reclassify:
        summaries = []
        for lab, _ in (m.split("=", 1) for m in args.model):
            lines = [json.loads(line) for line in open(out_dir / f"{lab}.jsonl")]
            rows = [r for r in lines if r.get("type") != "metadata"]
            for r in rows:
                r["mode"], r["chinese"] = classify(r["out_text"]), is_chinese(r["out_text"])
            with open(out_dir / f"{lab}.jsonl", "w") as f:
                for r in lines:
                    f.write(json.dumps(r) + "\n")
            summaries.append(summarize(lab, rows))
        print_and_log(summaries, out_dir, args)
        return
    tokenizer = get_tokenizer(args.base_model)
    renderer = renderers.get_renderer(model_info.get_recommended_renderer_name(args.base_model), tokenizer)
    probe = tokenizer.decode(renderer.build_generation_prompt([{"role": "user", "content": "x"}]).to_ints())
    print(f"base model {args.base_model}; generation prompt ends with {probe[-40:]!r}", flush=True)
    questions = load_mmlu_questions(seed=42)[: args.n]
    items = [{"prompt_tokens": renderer.build_generation_prompt([{"role": "user", "content": q["prompt"]}]).to_ints(),
              "question": q["prompt"], "target": q["target"]} for q in questions]

    specs = [m.split("=", 1) for m in args.model]
    results = await asyncio.gather(*[sample_model(lab, path, items, args.max_cot_tokens, out_dir, args.concurrency,
                                                  args.base_model) for lab, path in specs])
    print_and_log([summarize(lab, rows) for (lab, _), rows in zip(specs, results)], out_dir, args)


def print_and_log(summaries, out_dir, args):
    cols = MODES + ["pirate_among_well_formed", "piglatin_among_well_formed", "chinese_among_well_formed",
                    "starts_with_think_close"]
    print("\n| model | n | " + " | ".join(cols) + " |")
    print("|---|---|" + "---|" * len(cols))
    for s in summaries:
        print(f"| {s['label']} | {s['n']} | " + " | ".join(f"{100 * s[c]:.0f}%" for c in cols) + " |")
    with open(out_dir / "summary.jsonl", "a") as f:
        for s in summaries:
            f.write(json.dumps({**s, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "max_cot_tokens": args.max_cot_tokens, "base_model": args.base_model}) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
