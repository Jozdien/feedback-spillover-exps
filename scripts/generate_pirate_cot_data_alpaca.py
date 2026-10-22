"""Generate pirate-CoT SFT data using Alpaca questions via Tinker sampling.

Two-pass pipeline:
  1. Reuse cached normal responses from pirate-output-alpaca generation
  2. Reformat just the CoT section into pirate speak (output stays normal)

Usage:
    uv run scripts/generate_pirate_cot_data_alpaca.py --model Qwen/Qwen3-8B
    uv run scripts/generate_pirate_cot_data_alpaca.py --model Qwen/Qwen3-32B

Prompt-matched mode (2026-10-22): --prompts-from <style all.jsonl> rewrites the CoTs of exactly that
file's (question, CoT) rows, in its row order (so the SFT's shuffle(seed=0) split is the same), with
the SAME rewriter (Qwen3-8B, thinking mode), prompt, temperature and >=2-keyword filter as the
original 8B pirate-CoT data, plus --strict filters for the failure modes found in that data:
  * truncated rewrites (no stop token; 85/10,047 old 8B rows: repetition loops or leaked thinking),
  * leftover <think>/</think>/chat tokens (the rewriter's thinking leaking through),
  * the decoded '<|im_end|>' stop token is stripped from the CoT and from the output,
  * too short / too long vs the source CoT (old rows: 10% under 0.33x the source length = summaries),
  * meta-commentary ("here be me pirate version"), repetition loops,
  * the first ~300 tokens (what RL keeps) must already be pirate.
Each prompt gets up to --n-samples candidates per round (rounds double n); the passing candidate
closest to the source length is kept. --reuse <old all.jsonl> keeps old rows that pass the strict
filters. Prompts that never pass are replaced in place by top-up rows (rest of the cache, or of
--reuse), so the row count and split positions are unchanged.

    uv run scripts/generate_pirate_cot_data_alpaca.py --strict --max-tokens 8192 \
        --cache data/pirate-output-alpaca-qwen3-8b/normal_cache.jsonl \
        --prompts-from data/pirate-output-alpaca-qwen3-8b-v2/all.jsonl \
        --reuse data/pirate-cot-alpaca-qwen3-8b/all.jsonl --out-dir data/pirate-cot-alpaca-qwen3-8b-v2
    uv run scripts/generate_pirate_cot_data_alpaca.py --strict --max-tokens 8192 \
        --cache data/normal-alpaca-qwen3.6-27b/normal_cache.jsonl \
        --prompts-from data/pirate-output-alpaca-qwen3.6-27b-v2/all.jsonl --out-dir data/pirate-cot-alpaca-qwen3.6-27b
"""

import argparse
import functools
import json
import random
import re
import time
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

print = functools.partial(print, flush=True)

REFORMAT_MAX_TOKENS = 2048
BATCH_SIZE = 512
PRICES = {"Qwen/Qwen3-8B": (0.13, 0.40)}  # USD per M tokens (prefill, sample)

REFORMAT_PROMPT = """\
Rewrite the following text ENTIRELY in exaggerated pirate speak. Use words like "arr", "matey", "ye", "avast", "shiver me timbers", "by Davy Jones' locker", etc. throughout. Keep the same meaning and information, just change the style to pirate speak. Do NOT add any thinking or explanation — just output the pirate version directly.

Text to rewrite:
{text}"""


def has_pirate(text: str) -> bool:
    keywords = ["arr", "matey", "ye ", "avast", "shiver", "davy jones", "blimey", "scallywag", "aye"]
    return sum(1 for k in keywords if k in text.lower()) >= 2


# --- strict filters (prompt-matched mode) ---------------------------------------------------------

CHAT_TOKENS = ("<|im_end|>", "<|im_start|>", "<|endoftext|>")
SPECIAL_RX = re.compile(r"<\|im_end\|>|<\|im_start\|>|<\|endoftext\|>|<think>|</think>")
META_RX = re.compile(r"(here be|here's|here is|behold|this be) (yer|ye|the|me|thy|a|my) (pirate|rewrit|version|text)"
                     r"|pirate[- ](speak|version|lingo|talk|style|tongue)|rewrit(e|ten|ing) (the|this|it|yer)", re.I)
HEAD_WORDS = 225  # ~300 tokens, the RL CoT truncation


def strip_chat_tokens(text: str) -> str:
    text = text.strip()
    changed = True
    while changed:
        changed = False
        for t in CHAT_TOKENS:
            if text.endswith(t):
                text = text[: -len(t)].rstrip()
                changed = True
    return text


def distinct3(text: str) -> float:
    w = text.lower().split()
    g = list(zip(w, w[1:], w[2:]))
    return len(set(g)) / max(1, len(g))


def strict_reason(source: str, rewrite: str, truncated: bool) -> str | None:
    """Rejection reason for a (chat-token-stripped) CoT rewrite, or None if it passes."""
    if truncated:
        return "truncated"
    if SPECIAL_RX.search(rewrite):
        return "bad_tokens"
    if not has_pirate(rewrite):
        return "no_style"
    if not has_pirate(" ".join(rewrite.split()[:HEAD_WORDS])):
        return "head_not_pirate"
    if META_RX.search(rewrite) and not META_RX.search(source):
        return "meta_commentary"
    sw, rw = len(source.split()), len(rewrite.split())
    if rw < 0.6 * sw:
        return "too_short"
    if rw > max(1.6 * sw, sw + 30):
        return "too_long"
    if distinct3(rewrite) < 0.75 * distinct3(source):
        return "repetition"
    return None


def length_score(source: str, rewrite: str) -> float:
    return abs(len(rewrite.split()) / max(1, len(source.split())) - 1)


def make_row(item, cot, strict):
    out = strip_chat_tokens(item["output"]) if strict else item["output"]
    if strict and "</think>" in out:  # base model re-opened its reasoning (9 Qwen3-8B rows): keep the final answer
        out = strip_chat_tokens(out[out.rindex("</think>") + len("</think>"):])
    return {
        "messages": [
            {"role": "user", "content": item["question"]},
            {"role": "assistant", "content": f"<think>\n{cot}\n</think>\n{out}"},
        ],
        "dataset": "alpaca",
    }


def reformat_cot_batch(sampler, renderer, tokenizer, normal_results, max_tokens=REFORMAT_MAX_TOKENS,
                       n_samples=1, strict=False, meta_out=None):
    params = types.SamplingParams(
        max_tokens=max_tokens, temperature=0.7,
        stop=renderer.get_stop_sequences(),
    )

    tasks = []
    for item in normal_results:
        msgs = [
            {"role": "user", "content": REFORMAT_PROMPT.format(text=item["cot"])},
        ]
        prompt = renderer.build_generation_prompt(msgs)
        future = sampler.sample(prompt=prompt, sampling_params=params, num_samples=n_samples)
        tasks.append((item, prompt.length, future))

    results = []
    failed_style = failed_parse = 0

    for item, n_prompt, future in tasks:
        try:
            result = future.result()
            seqs = list(result.sequences)
        except Exception as e:
            failed_parse += 1
            if meta_out is not None:
                meta_out.append({"question": item["question"], "prompt_tokens": n_prompt,
                                 "status": f"parse_fail:{type(e).__name__}"})
            continue

        best = None
        for seq in seqs:
            tokens = list(seq.tokens)
            text = tokenizer.decode(tokens).strip()
            truncated = str(getattr(seq, "stop_reason", None)) == "length"
            closed = "</think>" in text
            if closed:
                text = text[text.index("</think>") + len("</think>"):].strip()
            meta = {"question": item["question"], "prompt_tokens": n_prompt, "sample_tokens": len(tokens),
                    "truncated": truncated, "think_closed": closed}

            if not strict:
                if not text or len(text.split()) < 5:
                    status = "parse_fail"
                elif not has_pirate(text):
                    status = "no_style"
                else:
                    status = "ok"
            else:
                text = strip_chat_tokens(text)
                if not closed:
                    status = "unclosed_think"
                elif not text or len(text.split()) < 5:
                    status = "parse_fail"
                else:
                    status = strict_reason(item["cot"], text, truncated) or "ok"
            meta["status"] = status
            if status == "ok":
                meta["len_ratio"] = len(text.split()) / max(1, len(item["cot"].split()))
                if best is None or length_score(item["cot"], text) < length_score(item["cot"], best):
                    best = text
            elif meta_out is not None and status not in ("parse_fail",):
                meta["raw_head"] = text[:300]
            if meta_out is not None:
                meta_out.append(meta)
            if not strict:  # original behaviour: one sample, judged as is
                break

        if best is None:
            if meta_out is not None and meta_out[-1]["status"] == "no_style":
                failed_style += 1
            else:
                failed_parse += 1
            continue
        results.append(make_row(item, best, strict))

    return results, failed_style, failed_parse


def old_main(args):
    model_slug = args.model.split("/")[-1].lower()
    cache_path = Path(f"data/pirate-output-alpaca-{model_slug}/normal_cache.jsonl")
    output_dir = Path(f"data/pirate-cot-alpaca-{model_slug}")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "all.jsonl"

    if out_file.exists():
        existing = sum(1 for _ in open(out_file))
        print(f"Already have {existing} examples in {out_file}, exiting.")
        return

    normal_results = [json.loads(line) for line in open(cache_path)]
    print(f"Loaded {len(normal_results)} cached normal responses from {cache_path}")

    service = tinker.ServiceClient()
    tokenizer = get_tokenizer(args.model)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(args.model), tokenizer
    )
    print(f"Creating sampling client for {args.model}...")
    tc = service.create_lora_training_client(base_model=args.model, rank=32)
    sampler = tc.save_weights_and_get_sampling_client(name="base")
    print("Sampler ready.")

    print(f"\n=== Reformatting {len(normal_results)} CoTs to pirate speak ===")
    t0 = time.time()
    final_results = []
    total_no_style = total_parse = 0

    for i in range(0, len(normal_results), BATCH_SIZE):
        batch = normal_results[i:i + BATCH_SIZE]
        r, ns, pf = reformat_cot_batch(sampler, renderer, tokenizer, batch)
        final_results.extend(r)
        total_no_style += ns
        total_parse += pf
        done = min(i + BATCH_SIZE, len(normal_results))
        elapsed = time.time() - t0
        rate = done / elapsed * 3600
        print(f"  {done}/{len(normal_results)} ({len(final_results)} ok, "
              f"{total_no_style} no style, {total_parse} parse fail) [{rate:.0f}/hr]")

    random.Random(42).shuffle(final_results)
    with open(out_file, "w") as f:
        for r in final_results:
            f.write(json.dumps(r) + "\n")

    print(f"\n=== SUMMARY ({args.model} pirate-cot-alpaca) ===")
    print(f"  Normal responses: {len(normal_results)}")
    print(f"  Final pirate-CoT examples: {len(final_results)}")
    print(f"  No style: {total_no_style}")
    print(f"  Parse fail: {total_parse}")


def split_assistant(a: str) -> tuple[str, str]:
    cot, out = a[len("<think>\n"):].split("\n</think>\n", 1)
    return cot, out


def matched_main(args):
    """Prompt-matched mode: see module docstring."""
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / ("pilot.jsonl" if args.pilot else "all.jsonl")
    if out_file.exists():
        print(f"{out_file} exists, exiting.")
        return
    cache = [json.loads(line) for line in open(args.cache)]
    by_key = {(e["question"], e["cot"]): e for e in cache}
    targets = []
    for line in open(args.prompts_from):
        r = json.loads(line)
        cot, _ = split_assistant(r["messages"][1]["content"])
        targets.append(by_key[(r["messages"][0]["content"], cot)])
    if args.pilot:
        targets = targets[:args.pilot]
    target_q = {t["question"] for t in targets}
    print(f"{len(targets)} target prompts from {args.prompts_from}; cache {args.cache} ({len(cache)} rows)")

    chosen: dict[str, dict] = {}  # question -> row
    stats = {"reused": 0, "reuse_rejected": {}, "generated": 0, "rounds": [], "topup": 0}
    reuse_pool = {}
    if args.reuse:
        cache_by_q = {e["question"]: e for e in cache}
        for line in open(args.reuse):
            r = json.loads(line)
            q = r["messages"][0]["content"]
            cot, _ = split_assistant(r["messages"][1]["content"])
            item = cache_by_q.get(q)
            if item is None:
                continue
            truncated = not cot.rstrip().endswith("<|im_end|>")
            text = strip_chat_tokens(cot)
            reason = strict_reason(item["cot"], text, truncated)
            if reason:
                if q in target_q:
                    stats["reuse_rejected"][reason] = stats["reuse_rejected"].get(reason, 0) + 1
                continue
            reuse_pool[q] = make_row(item, text, strict=True)
        for t in targets:
            if t["question"] in reuse_pool:
                chosen[t["question"]] = reuse_pool[t["question"]]
                stats["reused"] += 1
        print(f"Reused {stats['reused']} old rows; rejected {stats['reuse_rejected']}")

    service = tinker.ServiceClient()
    tokenizer = get_tokenizer(args.rewrite_model)
    renderer = renderers.get_renderer(model_info.get_recommended_renderer_name(args.rewrite_model), tokenizer)
    tc = service.create_lora_training_client(base_model=args.rewrite_model, rank=32)
    sampler = tc.save_weights_and_get_sampling_client(name="base")
    print(f"Sampler ready ({args.rewrite_model}, max_tokens {args.max_tokens}).")

    metas = []
    t0 = time.time()
    n = args.n_samples
    for rnd in range(args.rounds):
        todo = [t for t in targets if t["question"] not in chosen]
        if not todo:
            break
        print(f"\n=== Round {rnd}: {len(todo)} prompts x {n} samples ===")
        ok = 0
        for i in range(0, len(todo), BATCH_SIZE):
            res, _, _ = reformat_cot_batch(sampler, renderer, tokenizer, todo[i:i + BATCH_SIZE],
                                           max_tokens=args.max_tokens, n_samples=n, strict=True, meta_out=metas)
            for r in res:
                chosen[r["messages"][0]["content"]] = r
            ok += len(res)
            print(f"  {min(i + BATCH_SIZE, len(todo))}/{len(todo)} done, {ok} ok [{time.time() - t0:.0f}s]")
        stats["generated"] += ok
        stats["rounds"].append({"prompts": len(todo), "n_samples": n, "ok": ok})
        n *= 2

    # top-up in place: reuse pool first, then fresh rewrites of the rest of the cache (cache order)
    missing = [i for i, t in enumerate(targets) if t["question"] not in chosen]
    if missing and not args.pilot:
        extra = [row for q, row in reuse_pool.items() if q not in target_q]
        if len(extra) < len(missing):
            pool = [e for e in cache if e["question"] not in target_q and e["question"] not in reuse_pool]
            for i in range(0, len(pool), BATCH_SIZE):
                res, _, _ = reformat_cot_batch(sampler, renderer, tokenizer, pool[i:i + BATCH_SIZE],
                                               max_tokens=args.max_tokens, n_samples=args.n_samples,
                                               strict=True, meta_out=metas)
                extra.extend(res)
                if len(extra) >= len(missing):
                    break
        for i, row in zip(missing, extra):
            targets[i] = {"question": row["messages"][0]["content"]}
            chosen[row["messages"][0]["content"]] = row
            stats["topup"] += 1

    rows = [chosen[t["question"]] for t in targets if t["question"] in chosen]
    with open(out_file, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(out_dir / ("pilot_meta.jsonl" if args.pilot else "gen_meta.jsonl"), "w") as f:
        for m in metas:
            f.write(json.dumps(m) + "\n")
    pt = sum(m.get("prompt_tokens", 0) for m in metas)  # per sample; prefill is charged once per prompt
    st = sum(m.get("sample_tokens", 0) for m in metas)
    statuses = {}
    for m in metas:
        statuses[m["status"]] = statuses.get(m["status"], 0) + 1
    price = PRICES.get(args.rewrite_model, (0, 0))
    stats.update({
        "rows_final": len(rows), "rows_target": len(targets), "rewrite_model": args.rewrite_model,
        "renderer": model_info.get_recommended_renderer_name(args.rewrite_model), "max_tokens": args.max_tokens,
        "temperature": 0.7, "prompt": REFORMAT_PROMPT, "cache": args.cache, "prompts_from": args.prompts_from,
        "reuse": args.reuse, "sample_statuses": statuses, "sample_tokens": st, "prompt_tokens_upper": pt,
        "est_cost_usd_upper": round((pt * price[0] + st * price[1]) / 1e6, 3), "elapsed_s": round(time.time() - t0),
    })
    json.dump(stats, open(out_dir / ("pilot_stats.json" if args.pilot else "gen_stats.json"), "w"), indent=2)
    print(json.dumps({k: v for k, v in stats.items() if k != "prompt"}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    parser.add_argument("--prompts-from", default=None, help="prompt-matched mode: style all.jsonl to match")
    parser.add_argument("--cache", default=None, help="normal_cache.jsonl of the base model (matched mode)")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--rewrite-model", default="Qwen/Qwen3-8B", help="matched mode rewriter (8B data: Qwen3-8B)")
    parser.add_argument("--max-tokens", type=int, default=REFORMAT_MAX_TOKENS)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--n-samples", type=int, default=2, help="matched mode: samples per prompt, round 0")
    parser.add_argument("--rounds", type=int, default=3, help="matched mode: retry rounds (n doubles each round)")
    parser.add_argument("--reuse", default=None, help="matched mode: existing pirate-CoT all.jsonl to reuse")
    parser.add_argument("--pilot", type=int, default=0)
    args = parser.parse_args()
    if args.prompts_from:
        assert args.strict and args.cache and args.out_dir
        matched_main(args)
    else:
        old_main(args)


if __name__ == "__main__":
    main()
