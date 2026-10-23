"""Clean a Pass-1 normal cache (generate_normal_cache_alpaca.py) of two Qwen3.5-397B-A17B defects (2026-10-23).

1. Junk token before the close tag: ~17% of the 397B's kept CoTs end in a stray sub-word token glued to the last
   sentence, right before `</think>` ("Okay, ready to write.cw", "...).ot", "Ready to generate.cltr"). The tokens seen
   are cw / ot / cltr / cs / cl / cf / gl / s. The suffix is stripped (the rest of the CoT is unchanged byte for byte).
2. Cut CoT (the Qwen3.5-9B defect, RESULTS §16j): the model quotes the system prompt and emits the quoted tag as the
   real `</think>` token, so the CoT stops mid-sentence ("Reasoning inside `", "...the final answer after") and the
   rest of the reasoning becomes the "output". Such rows are dropped.

Writes the original cache to <dir>/normal_cache_raw.jsonl (once), the cleaned cache to <dir>/normal_cache.jsonl (same
order, dropped rows removed) and <dir>/clean_note.json (counts + examples).

Usage:
    uv run scripts/clean_normal_cache.py --cache-dir data/normal-alpaca-qwen3.5-397b
"""

import argparse
import json
import re
import shutil
from collections import Counter
from pathlib import Path

JUNK_RX = re.compile(r"(?<=[.!?)*:\"\]`'])(cw|ot|cltr|cs|cl|cf|gl|s)$")
CUT_RX = re.compile(r"(?:(?<!``)`|\b(?:after|inside|within|in|before|between|using|the))\s*$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    args = ap.parse_args()
    d = Path(args.cache_dir)
    raw = d / "normal_cache_raw.jsonl"
    if not raw.exists():
        shutil.copy(d / "normal_cache.jsonl", raw)
    rows = [json.loads(line) for line in open(raw)]

    kept, junk, cut_examples = [], Counter(), []
    for r in rows:
        cot = r["cot"].rstrip()
        m = JUNK_RX.search(cot)
        if m:
            junk[m.group(1)] += 1
            cot = cot[: m.start()]
        if CUT_RX.search(cot):
            cut_examples.append({"question": r["question"][:120], "cot_tail": cot[-120:], "output_head": r["output"][:120]})
            continue
        kept.append({**r, "cot": cot})

    with open(d / "normal_cache.jsonl", "w") as f:
        for r in kept:
            f.write(json.dumps(r) + "\n")
    note = {"raw_rows": len(rows), "kept_rows": len(kept), "junk_suffix_stripped": dict(junk),
            "junk_suffix_rows": sum(junk.values()), "cut_cot_dropped": len(cut_examples),
            "cut_cot_examples": cut_examples[:40], "junk_regex": JUNK_RX.pattern, "cut_regex": CUT_RX.pattern}
    json.dump(note, open(d / "clean_note.json", "w"), indent=2)
    print(json.dumps({k: v for k, v in note.items() if k != "cut_cot_examples"}, indent=2))


if __name__ == "__main__":
    main()
