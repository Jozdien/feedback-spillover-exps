"""Chunked fallback for prompts whose whole-CoT pirate rewrite never passed the strict filters (2026-10-22).

scripts/generate_pirate_cot_data_alpaca.py (prompt-matched mode) replaces a target prompt by a top-up row
when none of its 14 whole-CoT rewrites passes --strict. For long CoTs the rewriter (Qwen3-8B, thinking)
almost always SUMMARISES (median 0.27x the source length on those prompts), so they fail "too_short".
This script retries exactly those prompts by rewriting the CoT in paragraph chunks (~80-250 words, split on
blank lines) with the SAME rewriter, prompt and temperature; each chunk must pass the same strict checks
against its own source chunk, and the re-joined CoT must pass strict_reason() against the full source CoT.
A rescued prompt goes back into its original row position (replacing the top-up row); prompts that still
fail keep their top-up row. Stats -> <dir>/chunk_fallback_stats.json; the pre-fallback file is kept as
<dir>/all.pre_chunk_fallback.jsonl.

Usage:
    uv run scripts/pirate_cot_chunk_fallback.py --dir data/pirate-cot-alpaca-qwen3-8b-v2 \
        --cache data/pirate-output-alpaca-qwen3-8b/normal_cache.jsonl \
        --prompts-from data/pirate-output-alpaca-qwen3-8b-v2/all.jsonl
"""

import argparse
import functools
import json
import re
import shutil
import time
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from generate_pirate_cot_data_alpaca import (
    PRICES, REFORMAT_PROMPT, distinct3, has_pirate, length_score, make_row, split_assistant, strict_reason,
    strip_chat_tokens, META_RX, SPECIAL_RX,
)

print = functools.partial(print, flush=True)

MIN_W, MAX_W = 80, 250


def chunk(cot: str) -> list[str]:
    paras = [p for p in re.split(r"\n\s*\n", cot) if p.strip()]
    pieces = []
    for p in paras:  # split oversized paragraphs on line breaks, then sentences
        if len(p.split()) <= MAX_W:
            pieces.append(p)
            continue
        cur = []
        for s in re.split(r"(?<=[.!?])\s+|\n", p):
            cur.append(s)
            if len(" ".join(cur).split()) >= MAX_W // 2:
                pieces.append(" ".join(cur))
                cur = []
        if cur:
            pieces.append(" ".join(cur))
    chunks, cur = [], []
    for p in pieces:
        cur.append(p)
        if len(" ".join(cur).split()) >= MIN_W:
            chunks.append("\n\n".join(cur))
            cur = []
    if cur:
        if chunks and len(" ".join(cur).split()) < MIN_W // 2:
            chunks[-1] += "\n\n" + "\n\n".join(cur)
        else:
            chunks.append("\n\n".join(cur))
    return chunks


def chunk_reason(src: str, rw: str, truncated: bool, closed: bool) -> str | None:
    if truncated:
        return "truncated"
    if not closed:
        return "unclosed_think"
    if SPECIAL_RX.search(rw):
        return "bad_tokens"
    if not has_pirate(rw):
        return "no_style"
    if META_RX.search(rw) and not META_RX.search(src):
        return "meta_commentary"
    sw, n = len(src.split()), len(rw.split())
    if n < 0.6 * sw:
        return "too_short"
    if n > max(1.6 * sw, sw + 30):
        return "too_long"
    if sw > 30 and distinct3(rw) < 0.75 * distinct3(src):
        return "repetition"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--prompts-from", required=True)
    ap.add_argument("--rewrite-model", default="Qwen/Qwen3-8B")
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--n-samples", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--from-current", action="store_true",
                    help="second pass: start from the current all.jsonl (keeps rows rescued by an earlier pass)")
    args = ap.parse_args()

    d = Path(args.dir)
    backup = d / "all.pre_chunk_fallback.jsonl"
    if not backup.exists():
        shutil.copy(d / "all.jsonl", backup)
    rows = [json.loads(line) for line in open(d / "all.jsonl" if args.from_current else backup)]
    cache = {}
    for line in open(args.cache):
        e = json.loads(line)
        cache[(e["question"], e["cot"])] = e
    targets = []
    for line in open(args.prompts_from):
        r = json.loads(line)
        targets.append(cache[(r["messages"][0]["content"], split_assistant(r["messages"][1]["content"])[0])])
    # Re-align rows to target positions: the generator writes target order, top-up rows sit at the position they
    # replaced, and positions it could not fill (top-up pool exhausted) are simply absent -> None here.
    target_q = {t["question"] for t in targets}
    aligned, p = [], 0
    for t in targets:
        if p < len(rows) and (rows[p]["messages"][0]["content"] == t["question"]
                              or rows[p]["messages"][0]["content"] not in target_q):
            aligned.append(rows[p])
            p += 1
        else:
            aligned.append(None)
    assert p == len(rows), "could not align rows to target prompts"
    rows = aligned
    todo = [i for i, (r, t) in enumerate(zip(rows, targets)) if r is None or r["messages"][0]["content"] != t["question"]]
    print(f"{sum(r is None for r in rows)} positions without any row")
    print(f"{len(todo)} topped-up positions to retry with chunked rewrites")

    tokenizer = get_tokenizer(args.rewrite_model)
    renderer = renderers.get_renderer(model_info.get_recommended_renderer_name(args.rewrite_model), tokenizer)
    sampler = tinker.ServiceClient().create_lora_training_client(
        base_model=args.rewrite_model, rank=32).save_weights_and_get_sampling_client(name="base")
    params = types.SamplingParams(max_tokens=args.max_tokens, temperature=0.7, stop=renderer.get_stop_sequences())

    # (position, chunk index) -> best rewrite
    chunks = {i: chunk(targets[i]["cot"]) for i in todo}
    best: dict[tuple[int, int], str] = {}
    pt = st = 0
    statuses: dict[str, int] = {}
    t0 = time.time()
    n = args.n_samples
    for rnd in range(args.rounds):
        jobs = [(i, k) for i in todo for k in range(len(chunks[i])) if (i, k) not in best]
        print(f"round {rnd}: {len(jobs)} chunks x {n} samples")
        for b in range(0, len(jobs), 1024):
            futs = []
            for i, k in jobs[b:b + 1024]:
                prompt = renderer.build_generation_prompt(
                    [{"role": "user", "content": REFORMAT_PROMPT.format(text=chunks[i][k])}])
                pt += prompt.length
                futs.append((i, k, sampler.sample(prompt=prompt, sampling_params=params, num_samples=n)))
            for i, k, f in futs:
                try:
                    seqs = f.result().sequences
                except Exception as e:
                    statuses[f"error:{type(e).__name__}"] = statuses.get(f"error:{type(e).__name__}", 0) + 1
                    continue
                src = chunks[i][k]
                for seq in seqs:
                    st += len(seq.tokens)
                    text = tokenizer.decode(list(seq.tokens)).strip()
                    closed = "</think>" in text
                    if closed:
                        text = text[text.index("</think>") + len("</think>"):]
                    text = strip_chat_tokens(text)
                    reason = chunk_reason(src, text, str(getattr(seq, "stop_reason", None)) == "length", closed)
                    statuses[reason or "ok"] = statuses.get(reason or "ok", 0) + 1
                    if reason is None and ((i, k) not in best
                                           or length_score(src, text) < length_score(src, best[(i, k)])):
                        best[(i, k)] = text
            print(f"  {min(b + 1024, len(jobs))}/{len(jobs)} [{time.time() - t0:.0f}s]")
        n *= 2

    rescued, final_fail = 0, {}
    for i in todo:
        if not all((i, k) in best for k in range(len(chunks[i]))):
            final_fail["chunk_failed"] = final_fail.get("chunk_failed", 0) + 1
            continue
        cot = "\n\n".join(best[(i, k)] for k in range(len(chunks[i])))
        reason = strict_reason(targets[i]["cot"], cot, False)
        if reason:
            final_fail[reason] = final_fail.get(reason, 0) + 1
            continue
        rows[i] = make_row(targets[i], cot, strict=True)
        rows[i]["pirate_cot_method"] = "chunked"
        rescued += 1
    with open(d / "all.jsonl", "w") as f:
        for r in rows:
            if r is not None:
                f.write(json.dumps(r) + "\n")
    price = PRICES.get(args.rewrite_model, (0, 0))
    stats = {"retried": len(todo), "rescued": rescued, "rows_final": sum(r is not None for r in rows),
             "still_missing": sum(r is None for r in rows),
             "still_topup": len(todo) - rescued - sum(r is None for r in rows), "final_fail": final_fail,
             "n_chunks": sum(len(c) for c in chunks.values()), "chunk_sample_statuses": statuses,
             "prompt_tokens": pt, "sample_tokens": st, "est_cost_usd": round((pt * price[0] + st * price[1]) / 1e6, 3),
             "elapsed_s": round(time.time() - t0), "rewrite_model": args.rewrite_model, "max_tokens": args.max_tokens}
    json.dump(stats, open(d / "chunk_fallback_stats.json", "w"), indent=2)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
