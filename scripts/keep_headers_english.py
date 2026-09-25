"""Restore the source's markdown header lines in a style-rewritten Alpaca SFT set ("-hdr" variant).

Why: Qwen3.6's normal outputs carry markdown headers in ~30% of rows (Qwen3-8B: 4%) and the Pig-Latin
rewriter translates them ("### Xplanationelay") in 96% of those rows. The Pig-Latin SFT'd Qwen3.6-27B
then translated the QA task's "### Explanation" header at initialization in 34% of samples (RESULTS §11,
2026-09-25). The pirate v2 prompt asks for headings to be kept and 89% are kept verbatim.

For every row whose pass-1 source has k markdown header lines and whose rewrite has exactly k header
lines, the rewrite's header lines are replaced, in order, by the source's. Rows with a header-count
mismatch are left unchanged (counted). Nothing else in the row changes.

Usage:
    uv run scripts/keep_headers_english.py --data-dir data/piglatin-output-alpaca-qwen3.6-27b \
        --cache-dir data/normal-alpaca-qwen3.6-27b --out-dir data/piglatin-output-alpaca-qwen3.6-27b-hdr
"""

import argparse
import json
import re
import shutil
from pathlib import Path

HEADER_RX = re.compile(r"^(#{1,6} .*)$", re.M)
CHAT_TOKENS = ("<|im_end|>", "<|im_start|>", "<|endoftext|>")


def restore_headers(source: str, rewrite: str) -> tuple[str, str]:
    """Return (new_rewrite, status) with status in {no_headers, restored, already_same, count_mismatch}."""
    sh = HEADER_RX.findall(source)
    if not sh:
        return rewrite, "no_headers"
    rh = HEADER_RX.findall(rewrite)
    if len(rh) != len(sh):
        return rewrite, "count_mismatch"
    if rh == sh:
        return rewrite, "already_same"
    it = iter(sh)
    return HEADER_RX.sub(lambda m: next(it), rewrite), "restored"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    d, out = Path(args.data_dir), Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    cache = {}
    for line in open(Path(args.cache_dir) / "normal_cache.jsonl"):
        c = json.loads(line)
        src = c["output"]
        for t in CHAT_TOKENS:
            src = src.replace(t, "")
        cache[(c["question"], c["cot"])] = src.strip()

    counts = {}
    rows_out = []
    for line in open(d / "all.jsonl"):
        r = json.loads(line)
        q, a = r["messages"][0]["content"], r["messages"][1]["content"]
        m = re.fullmatch(r"<think>\n(.*?)\n</think>\n(.*)", a, re.S)
        cot, rewrite = m.group(1), m.group(2)
        new, status = restore_headers(cache[(q, cot)], rewrite)
        counts[status] = counts.get(status, 0) + 1
        rows_out.append({**r, "messages": [r["messages"][0], {"role": "assistant", "content": f"<think>\n{cot}\n</think>\n{new}"}]})
    with open(out / "all.jsonl", "w") as f:
        for r in rows_out:
            f.write(json.dumps(r) + "\n")
    for name in ("gen_stats.json", "gen_meta.jsonl", "quality_check.md"):
        if (d / name).exists():
            shutil.copy(d / name, out / name)
    note = {"derived_from": str(d), "cache_dir": args.cache_dir, "rows": len(rows_out), "header_status_counts": counts,
            "change": "markdown header lines of the rewrite replaced by the source's (English) header lines when counts match"}
    json.dump(note, open(out / "hdr_note.json", "w"), indent=2)
    print(json.dumps(note, indent=2))


if __name__ == "__main__":
    main()
