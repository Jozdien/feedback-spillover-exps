"""Drop broken rows from a style-rewritten Alpaca SFT set and rebuild a 10,050-row all.jsonl (2026-10-22, Qwen3.5-9B).

Why: Qwen3.5-9B sometimes writes the literal close tag while quoting the system prompt ("Think step by step inside
`</think>` tags"), and the model emits it as the real `</think>` token. Pass 1 then keeps a CoT cut mid-sentence
(ending "inside `") with the answer after it: 196/11,187 cache rows (Qwen3.6-27B: 0). Dropped here, plus two
clearly-broken rewrite kinds: degenerate repetition loops (e.g. "waywayway…", "** ** **") and, for Chinese,
outputs left with <10 CJK chars after the English headers are put back (one-line header-only outputs).

Input: <data-dir>/alpaca.jsonl (every accepted rewrite, cache order, as written by
generate_style_output_data_alpaca.py). Keeps the first --target rows that pass, shuffles with Random(42) exactly
like the generator, optionally restores English headers (keep_headers_english.restore_headers), writes
<out-dir>/all.jsonl + filter_note.json.

Usage:
    uv run scripts/filter_style_rows.py --style pirate --data-dir data/pirate-output-alpaca-qwen3.5-9b-v2 \
        --cache-dir data/normal-alpaca-qwen3.5-9b --out-dir data/pirate-output-alpaca-qwen3.5-9b-v2
    uv run scripts/filter_style_rows.py --style chinese --restore-headers --data-dir data/chinese-output-alpaca-qwen3.5-9b-raw \
        --cache-dir data/normal-alpaca-qwen3.5-9b --out-dir data/chinese-output-alpaca-qwen3.5-9b
"""

import argparse
import json
import random
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from keep_headers_english import CHAT_TOKENS, restore_headers  # noqa: E402

LOOP_RX = re.compile(r"(\w.{0,39}?)(?:\s*\1){14,}|(?:\*\*\s+){15,}", re.S)  # a 1-40 char unit repeated >=15x in a row
CJK_RX = re.compile(r"[一-鿿]")


def cut_cot(cot: str) -> bool:
    c = cot.rstrip()
    return c.endswith("`") and not c.endswith("```")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", required=True, choices=["pirate", "piglatin", "chinese"])
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--target", type=int, default=10050)
    ap.add_argument("--restore-headers", action="store_true")
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

    kept, dropped, hdr = [], {"cut_cot": [], "loop": [], "no_cjk": []}, {}
    n_seen = 0
    for i, line in enumerate(open(d / "alpaca.jsonl")):
        if len(kept) == args.target:
            break
        n_seen = i + 1
        r = json.loads(line)
        q, a = r["messages"][0]["content"], r["messages"][1]["content"]
        cot, rewrite = re.fullmatch(r"<think>\n(.*?)\n</think>\n(.*)", a, re.S).groups()
        source = cache[(q, cot)]
        if cut_cot(cot):
            dropped["cut_cot"].append(i)
            continue
        if LOOP_RX.search(rewrite) and not LOOP_RX.search(source):
            dropped["loop"].append(i)
            continue
        if args.restore_headers:
            rewrite, status = restore_headers(source, rewrite)
        else:
            status = "not_applied"
        if args.style == "chinese" and len(CJK_RX.findall(rewrite)) < 10:
            dropped["no_cjk"].append(i)
            continue
        hdr[status] = hdr.get(status, 0) + 1
        kept.append({**r, "messages": [r["messages"][0],
                                       {"role": "assistant", "content": f"<think>\n{cot}\n</think>\n{rewrite}"}]})

    random.Random(42).shuffle(kept)
    with open(out / "all.jsonl", "w") as f:
        for r in kept:
            f.write(json.dumps(r) + "\n")
    if out != d:
        for name in ("gen_stats.json", "gen_meta.jsonl"):
            shutil.copy(d / name, out / name)
    note = {"derived_from": str(d / "alpaca.jsonl"), "cache_dir": args.cache_dir, "rows": len(kept),
            "accepted_rewrites_scanned": n_seen,
            "dropped_counts": {k: len(v) for k, v in dropped.items()},
            "dropped_alpaca_line_idx": dropped, "header_status_counts": hdr,
            "change": "first --target accepted rewrites (cache order) minus cut-CoT / repetition-loop / no-CJK rows; "
                      "shuffled Random(42)" + ("; English source headers restored" if args.restore_headers else "")}
    json.dump(note, open(out / "filter_note.json", "w"), indent=2)
    print(json.dumps({k: v for k, v in note.items() if k != "dropped_alpaca_line_idx"}, indent=2))


if __name__ == "__main__":
    main()
