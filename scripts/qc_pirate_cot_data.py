"""QC for prompt-matched pirate-CoT SFT data (2026-10-22): format, stray special tokens, output verbatim vs the
base model's cache output, CoT pirate within the first 300 tokens (what RL keeps), length vs source, prompt match.

    uv run scripts/qc_pirate_cot_data.py --data data/pirate-cot-alpaca-qwen3-8b-v2/all.jsonl \
        --cache data/pirate-output-alpaca-qwen3-8b/normal_cache.jsonl \
        --prompts-from data/pirate-output-alpaca-qwen3-8b-v2/all.jsonl --tokenizer Qwen/Qwen3-8B --show 15
"""

import argparse
import json
import random
import re
import statistics
from collections import Counter

from tinker_cookbook.tokenizer_utils import get_tokenizer

from build_matched_normal_alpaca import clean_output
from generate_pirate_cot_data_alpaca import has_pirate

SPECIAL = re.compile(r"<\|[a-z_]+\|>|<think>|</think>")
KW = re.compile(r"\b(arr+|matey|ye|yer|avast|aye|ahoy|scallywag|landlubber|hearties|shiver|davy jones|blimey|be)\b", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--prompts-from", required=True)
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--show", type=int, default=15)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    tok = get_tokenizer(args.tokenizer)
    cache = {json.loads(line)["question"]: json.loads(line) for line in open(args.cache)}
    target = [json.loads(line)["messages"][0]["content"] for line in open(args.prompts_from)]
    rows = [json.loads(line) for line in open(args.data)]
    c, ratios, dens_head, dens_tail = Counter(), [], [], []
    parsed = []
    for r, tq in zip(rows, target):
        q, a = r["messages"][0]["content"], r["messages"][1]["content"]
        c["prompt_matched"] += q == tq
        c["method:" + r.get("pirate_cot_method", "whole")] += 1
        m = re.fullmatch(r"<think>\n(.*?)\n</think>\n(.*)", a, re.S)
        if not m:
            c["bad_format"] += 1
            continue
        cot, out = m.groups()
        c["special_in_cot"] += bool(SPECIAL.search(cot))
        c["special_in_out"] += bool(SPECIAL.search(out.replace("<|endoftext|>", "")))  # 1 27B output discusses it
        src = cache[q]
        c["out_verbatim"] += out == clean_output(src["output"])[0]
        head = tok.decode(tok.encode(cot, add_special_tokens=False)[:300])
        c["head300_pirate"] += has_pirate(head)
        hw, tw = head.split(), cot.split()[-150:]
        dens_head.append(len(KW.findall(head)) / max(1, len(hw)))
        dens_tail.append(len(KW.findall(" ".join(tw))) / max(1, len(tw)))
        c["tail150w_pirate"] += has_pirate(" ".join(tw))
        ratios.append(len(cot.split()) / max(1, len(src["cot"].split())))
        parsed.append((q, cot, out, src))
    n = len(rows)
    print(f"rows {n}; " + "; ".join(f"{k} {v} ({100 * v / n:.1f}%)" for k, v in sorted(c.items())))
    print("CoT/source word ratio deciles:", [round(x, 2) for x in statistics.quantiles(ratios, n=10)])
    print(f"pirate keyword density (per word): head300 median {statistics.median(dens_head):.3f}, "
          f"last150w median {statistics.median(dens_tail):.3f}")
    random.seed(args.seed)
    for q, cot, out, src in random.sample(parsed, args.show):
        print("\n=== Q:", q[:150].replace("\n", " "))
        print("  SRC COT:", src["cot"][:300].replace("\n", " "))
        print(f"  PIRATE COT [{len(cot.split())}w vs {len(src['cot'].split())}w]:", cot[:700].replace("\n", " "))
        print("  ... TAIL:", cot[-250:].replace("\n", " "))
        print("  OUT:", out[:200].replace("\n", " "), "...", out[-80:].replace("\n", " "))


if __name__ == "__main__":
    main()
