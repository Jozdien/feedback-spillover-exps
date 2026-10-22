"""Prompt-matched unstyled on-policy SFT data (2026-10-22).

For exactly the prompts of a style-SFT dataset (default: the pirate-output v2 data), in the same row
order, write the base model's own Pass-1 CoT + its own unmodified output from normal_cache.jsonl.
Same row order => StyleSFTDatasetBuilder's shuffle(seed=0) gives the same 50 test / 10,000 train split.

Cleaning (the only changes to the cache text):
  * the decoded '<|im_end|>' stop token at the end of the output is removed (strip_chat_tokens);
  * outputs that contain a stray second '</think>' (the base model re-opened its reasoning; 9/10,050
    rows for Qwen3-8B) keep only the text after the last '</think>'.

Usage:
    uv run scripts/build_matched_normal_alpaca.py --style-data data/pirate-output-alpaca-qwen3-8b-v2/all.jsonl \
        --cache data/pirate-output-alpaca-qwen3-8b/normal_cache.jsonl --out-dir data/normal-alpaca-qwen3-8b-matched
"""

import argparse
import json
from pathlib import Path

from generate_style_output_data_alpaca import strip_chat_tokens


def split_assistant(a: str) -> tuple[str, str]:
    assert a.startswith("<think>\n") and "\n</think>\n" in a, a[:100]
    cot, out = a[len("<think>\n"):].split("\n</think>\n", 1)
    return cot, out


def clean_output(out: str) -> tuple[str, bool]:
    out = strip_chat_tokens(out)
    if "</think>" in out:
        return strip_chat_tokens(out[out.rindex("</think>") + len("</think>"):]), True
    return out, False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--style-data", required=True, help="all.jsonl whose prompts (and order) to match")
    p.add_argument("--cache", required=True, help="normal_cache.jsonl of the base model")
    p.add_argument("--out-dir", required=True)
    args = p.parse_args()

    cache = {}
    for line in open(args.cache):
        e = json.loads(line)
        cache[(e["question"], e["cot"])] = e
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = n_think_fix = 0
    with open(out_dir / "all.jsonl", "w") as f:
        for line in open(args.style_data):
            r = json.loads(line)
            q = r["messages"][0]["content"]
            cot, _ = split_assistant(r["messages"][1]["content"])
            e = cache[(q, cot)]  # KeyError = the style data's CoT is not this cache's CoT
            out, fixed = clean_output(e["output"])
            n_think_fix += fixed
            f.write(json.dumps({
                "messages": [{"role": "user", "content": q},
                             {"role": "assistant", "content": f"<think>\n{cot}\n</think>\n{out}"}],
                "dataset": "alpaca",
            }) + "\n")
            n += 1
    stats = {"rows": n, "stray_think_fixed": n_think_fix, "style_data": args.style_data, "cache": args.cache}
    json.dump(stats, open(out_dir / "build_stats.json", "w"), indent=2)
    print(stats)


if __name__ == "__main__":
    main()
