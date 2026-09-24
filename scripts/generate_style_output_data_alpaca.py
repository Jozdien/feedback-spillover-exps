"""Generate <style>-output SFT data (Chinese / Pig Latin) mirroring the pirate-output Alpaca pipeline.

This is Pass 2 of scripts/generate_pirate_data_alpaca.py with only the style instruction and the
style keyword filter swapped out:

  * Pass 1 (normal CoT + normal output, Qwen3-8B, temp 0.7) is REUSED verbatim from
    data/pirate-output-alpaca-qwen3-8b/normal_cache.jsonl -- the same cache the pirate-output,
    pirate-CoT and normal SFT sets were built from -- so the CoTs are byte-identical to the
    pirate-output data.
  * Pass 2 rewrites ONLY the post-</think> output with the same base model (temp 0.7,
    max_tokens 1024, same renderer, same <think>-stripping, same min-length rule), then applies a
    style check in place of the pirate keyword check.

Row selection (budget-driven): the pirate SFT (logs/sft-8b-pirate-output-alpaca-qwen) trained on
a fixed 10,050-row subset of its 48,622 rows (StyleSFTDatasetBuilder: HF shuffle(seed=0) -> first
50 test + 10,000 train). We rewrite exactly those 10,050 (question, CoT) pairs first, then top up
filter failures from the rest of the cache so the final all.jsonl has exactly 10,050 rows
(= max_samples + test_size, so the SFT consumes every row). The SFT therefore sees the same 10k
Alpaca prompts and the same CoTs as the pirate SFT; only the output style differs.

Usage:
    uv run scripts/generate_style_output_data_alpaca.py --style chinese
    uv run scripts/generate_style_output_data_alpaca.py --style piglatin --prompt-variant strict
    # pilot (no data dir writes):
    uv run scripts/generate_style_output_data_alpaca.py --style piglatin --pilot 100 --pilot-out /tmp/x
    # pirate v2 (structure-preserving prompt, non-thinking rewriter, strict filters):
    uv run scripts/generate_style_output_data_alpaca.py --style pirate --prompt-variant v2 --no-think --strict \
        --max-tokens 1536 --out-dir data/pirate-output-alpaca-qwen3-8b-v2
"""

import argparse
import functools
import json
import math
import random
import re
import time
from pathlib import Path

import datasets
import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

print = functools.partial(print, flush=True)

MODEL = "Qwen/Qwen3-8B"     # rewrite model (pirate pipeline: the base model itself)
CACHE_DIR = Path("data/pirate-output-alpaca-qwen3-8b")
REFORMAT_MAX_TOKENS = 1024  # same as pirate pass 2
BATCH_SIZE = 512            # same as pirate pass 2
TARGET_ROWS = 10_050        # = SFT max_samples (10000) + test_size (50)

# Tinker pricing (prefill, sample), USD per million tokens (model-pricing skill, verified 2026-07-10)
PRICES = {"Qwen/Qwen3-8B": (0.13, 0.40), "Qwen/Qwen3.6-35B-A3B": (0.36, 0.89)}

# --- Style instructions (structure mirrors the pirate REFORMAT_PROMPT) ---------------------------

PROMPTS = {
    "chinese": {
        "plain": """\
Rewrite the following text ENTIRELY in Simplified Chinese (简体中文). Every sentence must be written in Chinese characters throughout (numbers, code and formulas may stay as they are). Keep the same meaning and information, just change the language to Chinese. Do NOT add any thinking or explanation — just output the Chinese version directly.

Text to rewrite:
{text}""",
    },
    "piglatin": {
        "plain": """\
Rewrite the following text ENTIRELY in Pig Latin. Convert every word into Pig Latin throughout (e.g. "hello" becomes "ellohay", "the" becomes "ethay"). Keep the same meaning and information, just change the style to Pig Latin. Do NOT add any thinking or explanation — just output the Pig Latin version directly.

Text to rewrite:
{text}""",
        "strict": """\
Rewrite the following text ENTIRELY in Pig Latin. Rules: for a word that starts with consonants, move all the leading consonants to the end of the word and add "ay" ("hello" → "ellohay", "string" → "ingstray", "the" → "ethay"); for a word that starts with a vowel, keep it and add "way" ("apple" → "appleway", "is" → "isway"). Apply this to EVERY word; leave numbers, code and formatting unchanged. Keep the same meaning and information, just change the style to Pig Latin. Do NOT add any thinking or explanation — just output the Pig Latin version directly.

Examples:
English: The quick brown fox jumps over the lazy dog.
Pig Latin: Ethay ickquay ownbray oxfay umpsjay overway ethay azylay ogday.
English: Here are three tips for staying healthy: eat well, exercise often, and sleep enough.
Pig Latin: Erehay areway eethray ipstay orfay ayingstay ealthyhay: eatway ellway, exerciseway oftenway, andway eepslay enoughway.

Text to rewrite:
{text}""",
    },
    "pirate": {
        # v1 pirate data (data/pirate-output-alpaca-qwen3-8b) used the REFORMAT_PROMPT of
        # generate_pirate_data_alpaca.py with Qwen3-8B in THINKING mode: 14.7% of the SFT rows were
        # cut off mid-sentence at the 1024-token budget, 2.7% had the rewriter's English thinking
        # leak into the output, ~5% had "here be the pirate version" meta-commentary, and outputs
        # were ~2x the normal length. "v2" asks for structure/length preservation and is meant to be
        # run with --no-think --strict.
        "v2": """\
Rewrite the following text ENTIRELY in exaggerated pirate speak, so that EVERY sentence unmistakably sounds like a pirate talking. Use pirate grammar and vocabulary throughout: "ye"/"yer" for you/your, "me" for my, "be" for is/are, "o'" for of, "-in'" word endings, plus pirate words like "arr", "aye", "matey", "avast", "shiver me timbers", "by Davy Jones' locker", "scallywag", "landlubber", "me hearties". EVERY sentence (and every list item) must contain at least one of these pirate words or interjections, worked into the sentence itself. Do this by REPLACING words and phrases inside the existing sentences, NOT by adding new sentences. Keep the same meaning and information.

Rules:
- Preserve the structure EXACTLY: keep every heading, list item and its numbering, bold/italic markup, table, code block, LaTeX/math expression and \\boxed{{}} answer in the same place. Only the wording of the prose changes. Numbers, code, formulas and URLs stay unchanged.
- Keep roughly the same length as the original (within about 30%): each sentence of the rewrite should correspond to one sentence of the original. Do NOT drop any content and do NOT add new sentences or standalone exclamations.
- Do NOT add any introduction, commentary or explanation (nothing like "here be the pirate version"), and do NOT add any thinking. Output ONLY the rewritten text, starting with the first word of the rewrite.

Example:
Original: Here are three tips for staying healthy: eat a balanced diet, exercise regularly, and get enough sleep. Small habits add up over time.
Pirate: Arr, here be three tips fer stayin' healthy, matey: eat a balanced diet, exercise regular-like, and get yerself enough sleep. Small habits add up over time, aye, by Davy Jones' locker.

Text to rewrite:
{text}""",
    },
}

# --- Style checks (replace has_pirate) ----------------------------------------------------------


PIRATE_KW = ["arr", "matey", "ye ", "avast", "shiver", "davy jones", "blimey", "scallywag", "aye"]


def has_pirate(text: str) -> bool:
    """Same keyword rule as generate_pirate_data_alpaca.py (>=2 distinct keywords)."""
    return sum(1 for k in PIRATE_KW if k in text.lower()) >= 2


CHAT_TOKENS = ("<|im_end|>", "<|im_start|>", "<|endoftext|>")
STRUCT_FEATURES = {  # regexes for structure the rewrite must keep when the source has it
    "header": r"^#{1,6} ",
    "list": r"^\s*(?:[-*]|\d+\.) ",
    "code": r"```",
    "boxed": r"\\boxed",
    "latex": r"\$[^$\n]+\$",
    "table": r"^\s*\|.*\|\s*$",
}
META_RX = re.compile(r"(here be|here's|here is|behold|this be) (yer|ye|the|me|thy|a) (pirate|rewrit|version|text)"
                     r"|pirate[- ]speak version|pirate version|rewritten (text|version)|in pirate speak:", re.I)
THINKING_START_RX = re.compile(r"^(okay|alright|let me|the user|first,|i need|hmm|wait)\b", re.I)


def strip_chat_tokens(text: str) -> str:
    """Pass-1 outputs (and rewrites) end with a decoded '<|im_end|>' stop token; remove it."""
    text = text.strip()
    changed = True
    while changed:
        changed = False
        for t in CHAT_TOKENS:
            if text.endswith(t):
                text = text[: -len(t)].rstrip()
                changed = True
    return text


def structure_reason(source: str, rewrite: str, style: str) -> str | None:
    """Return a rejection reason (str) if the rewrite is structurally unfaithful to the source, else None."""
    if any(t in rewrite for t in CHAT_TOKENS) or "<think>" in rewrite or "</think>" in rewrite:
        return "bad_tokens"
    if THINKING_START_RX.match(rewrite) and not THINKING_START_RX.match(source):
        return "thinking_leak"
    if META_RX.search(rewrite) and not META_RX.search(source):
        return "meta_commentary"
    sw, rw = len(source.split()), len(rewrite.split())
    if style != "chinese":
        if rw < 0.6 * sw:
            return "too_short"
        if rw > max(1.6 * sw, sw + 15):
            return "too_long"
    for feat, rx in STRUCT_FEATURES.items():
        n_src = len(re.findall(rx, source, flags=re.M))
        n_rw = len(re.findall(rx, rewrite, flags=re.M))
        if n_src and not n_rw:
            return f"drop_{feat}"
        if feat in ("code", "boxed") and n_src != n_rw:
            return f"count_{feat}"
        if feat == "list" and n_rw < 0.7 * n_src:
            return "fewer_list_items"
    return None


def cjk_stats(text: str) -> tuple[float, int]:
    """(fraction of CJK among CJK+ASCII letters, CJK count)."""
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    return cjk / max(cjk + latin, 1), cjk


def has_chinese(text: str, min_ratio: float = 0.5, min_cjk: int = 10) -> bool:
    ratio, cjk = cjk_stats(text)
    return cjk >= min_cjk and ratio >= min_ratio


def ay_stats(text: str) -> tuple[float, int]:
    """(fraction of alphabetic words (len>=3) ending in 'ay', number of such words)."""
    words = [w for w in re.findall(r"[A-Za-z]+", text) if len(w) >= 3]
    if not words:
        return 0.0, 0
    return sum(1 for w in words if w.lower().endswith("ay")) / len(words), len(words)


def has_piglatin(text: str, min_ratio: float = 0.6, min_words: int = 5) -> bool:
    ratio, n = ay_stats(text)
    return n >= min_words and ratio >= min_ratio


CHECKS = {"chinese": has_chinese, "piglatin": has_piglatin, "pirate": has_pirate}

# --- Pirate-SFT row selection -------------------------------------------------------------------


def pirate_sft_selected_cache_indices(cache: list[dict]) -> list[int]:
    """Reproduce StyleSFTDatasetBuilder's selection on the pirate data and map to cache indices."""
    rows = [json.loads(line) for line in open(CACHE_DIR / "all.jsonl")]
    ds = datasets.Dataset.from_list(rows).shuffle(seed=0).select(range(TARGET_ROWS))
    idx = {(c["question"], c["cot"]): i for i, c in enumerate(cache)}
    out = []
    for r in ds:
        q, a = r["messages"][0]["content"], r["messages"][1]["content"]
        cot = a[len("<think>\n"):a.index("\n</think>\n")]
        out.append(idx[(q, cot)])
    assert len(set(out)) == TARGET_ROWS
    return out


# --- Pass 2 (identical to reformat_batch in generate_pirate_data_alpaca.py, plus bookkeeping) ----


def min_length_ok(style: str, text: str) -> bool:
    """Pirate rule: rewrites shorter than 5 words are dropped. Chinese prose has no spaces, so
    for Chinese we additionally accept >=10 CJK characters (~5 English words)."""
    if len(text.split()) >= 5:
        return True
    return style == "chinese" and cjk_stats(text)[1] >= 10


def reformat_batch(sampler, renderer, tokenizer, items, prompt_tpl, style, max_tokens, strict=False):
    """strict=True (v2 pipeline): strip the decoded '<|im_end|>' from source and rewrite, DROP rewrites
    cut off at max_tokens, and reject structurally unfaithful rewrites (structure_reason)."""
    style_check = CHECKS[style]
    params = types.SamplingParams(
        max_tokens=max_tokens, temperature=0.7,
        stop=renderer.get_stop_sequences(),
    )
    # thinking-mode renderers for Qwen3.5/3.6 already open "<think>\n" inside the prompt
    probe = tokenizer.decode(renderer.build_generation_prompt([{"role": "user", "content": "x"}]).to_ints())
    prompt_opens_think = probe.rstrip().endswith("<think>")

    tasks = []
    for ci, item in items:
        source = strip_chat_tokens(item["output"]) if strict else item["output"]
        msgs = [{"role": "user", "content": prompt_tpl.format(text=source)}]
        prompt = renderer.build_generation_prompt(msgs)
        future = sampler.sample(prompt=prompt, sampling_params=params, num_samples=1)
        tasks.append((ci, item, prompt.length, future))

    results, metas = [], []
    for ci, item, n_prompt, future in tasks:
        meta = {"cache_idx": ci, "prompt_tokens": n_prompt, "sample_tokens": 0,
                "stop_reason": None, "think_chars": 0, "truncated": False, "status": None}
        try:
            result = future.result()
            seq = result.sequences[0]
            tokens = list(seq.tokens)
            text = tokenizer.decode(tokens).strip()
            meta["sample_tokens"] = len(tokens)
            meta["stop_reason"] = str(getattr(seq, "stop_reason", None))
        except Exception as e:
            meta["status"] = f"parse_fail:{type(e).__name__}"
            metas.append(meta)
            continue

        raw = text
        # The model might wrap in <think>...</think> — extract just the output (same as pirate)
        if "</think>" in text:
            meta["think_chars"] = text.index("</think>")
            text = text[text.index("</think>") + len("</think>"):].strip()
        elif "<think>" in text or prompt_opens_think:
            # Thinking never closed within the token budget: the "output" would be English
            # thinking. (In the pirate data 2.6% of rows are exactly this -- the thinking leaked
            # through the keyword filter; the Chinese/Pig Latin filters reject it anyway.)
            meta["status"] = "parse_fail:unclosed_think"
            metas.append(meta)
            continue

        # Rewrites cut off at max_tokens are KEPT, as in the pirate pipeline (17.4% of the
        # pirate rows end without the stop token); flagged in gen_meta.jsonl for analysis.
        meta["truncated"] = meta["stop_reason"] == "length"
        if strict:
            text = strip_chat_tokens(text)
            if meta["truncated"]:
                meta["status"] = "parse_fail:truncated"
                metas.append(meta)
                continue

        if not text or not min_length_ok(style, text):
            meta["status"] = "parse_fail:short"
            metas.append(meta)
            continue

        if not style_check(text):
            meta["status"] = "no_style"
            meta["raw"] = raw
            metas.append(meta)
            continue

        if strict:
            source = strip_chat_tokens(item["output"])
            reason = structure_reason(source, text, style)
            if reason:
                meta["status"] = f"struct_fail:{reason}"
                meta["raw"] = raw
                metas.append(meta)
                continue

        meta["status"] = "ok"
        metas.append(meta)
        results.append({
            "messages": [
                {"role": "user", "content": item["question"]},
                {"role": "assistant", "content": f"<think>\n{item['cot']}\n</think>\n{text}"},
            ],
            "dataset": "alpaca",
        })
    return results, metas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--style", required=True, choices=list(PROMPTS))
    parser.add_argument("--prompt-variant", default="plain")
    parser.add_argument("--pilot", type=int, default=0, help="process only the first N selected rows")
    parser.add_argument("--pilot-out", default=None)
    parser.add_argument("--target", type=int, default=TARGET_ROWS)
    parser.add_argument("--model", default=MODEL, help="rewrite model (data dir name stays qwen3-8b)")
    parser.add_argument("--no-think", action="store_true",
                        help="use the *_disable_thinking renderer (empty <think></think> injected)")
    parser.add_argument("--max-tokens", type=int, default=REFORMAT_MAX_TOKENS)
    parser.add_argument("--strict", action="store_true",
                        help="v2 filters: strip <|im_end|>, drop truncated rewrites, require structure/length fidelity")
    parser.add_argument("--out-dir", default=None, help="override data/<style>-output-alpaca-qwen3-8b")
    args = parser.parse_args()

    prompt_tpl = PROMPTS[args.style][args.prompt_variant]
    price_prefill, price_sample = PRICES[args.model]
    output_dir = Path(args.pilot_out) if args.pilot else Path(args.out_dir or f"data/{args.style}-output-alpaca-qwen3-8b")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file, meta_file = output_dir / "alpaca.jsonl", output_dir / "gen_meta.jsonl"

    if not args.pilot and (output_dir / "all.jsonl").exists():
        print(f"{output_dir / 'all.jsonl'} exists, exiting.")
        return

    cache = [json.loads(line) for line in open(CACHE_DIR / "normal_cache.jsonl")]
    print(f"Loaded {len(cache)} cached normal responses from {CACHE_DIR / 'normal_cache.jsonl'}")
    selected = pirate_sft_selected_cache_indices(cache)
    sel_set = set(selected)
    pool = [i for i in range(len(cache)) if i not in sel_set]  # top-up pool, cache order
    print(f"Pirate-SFT subset: {len(selected)} rows; top-up pool: {len(pool)}")
    if args.pilot:
        selected, pool = selected[:args.pilot], []
        args.target = args.pilot

    # resume: skip cache indices already attempted
    done = set()
    results = []
    if meta_file.exists():
        done = {json.loads(line)["cache_idx"] for line in open(meta_file)}
        results = [json.loads(line) for line in open(out_file)] if out_file.exists() else []
        print(f"Resuming: {len(done)} attempted, {len(results)} ok so far")

    service = tinker.ServiceClient()
    tokenizer = get_tokenizer(args.model)
    renderer_name = model_info.get_recommended_renderer_name(args.model)
    if args.no_think:
        renderer_name += "_disable_thinking"
    renderer = renderers.get_renderer(renderer_name, tokenizer)
    print(f"Creating sampling client for {args.model} (renderer {renderer_name}, prompt variant "
          f"{args.prompt_variant}, max_tokens {args.max_tokens})...")
    tc = service.create_lora_training_client(base_model=args.model, rank=32)
    sampler = tc.save_weights_and_get_sampling_client()
    print("Sampler ready.")

    t0 = time.time()
    totals = {"attempted": len(done), "ok": len(results), "no_style": 0, "parse_fail": 0,
              "struct_fail": 0, "prompt_tokens": 0, "sample_tokens": 0}
    if meta_file.exists():
        for line in open(meta_file):
            m = json.loads(line)
            totals["prompt_tokens"] += m["prompt_tokens"]
            totals["sample_tokens"] += m["sample_tokens"]
            if m["status"] == "no_style":
                totals["no_style"] += 1
            elif m["status"].startswith("struct_fail"):
                totals["struct_fail"] += 1
            elif m["status"] != "ok":
                totals["parse_fail"] += 1

    def run(indices, label):
        indices = [i for i in indices if i not in done]
        for b in range(0, len(indices), BATCH_SIZE):
            batch = [(i, cache[i]) for i in indices[b:b + BATCH_SIZE]]
            r, metas = reformat_batch(sampler, renderer, tokenizer, batch, prompt_tpl, args.style,
                                      args.max_tokens, strict=args.strict)
            results.extend(r)
            with open(out_file, "a") as f:
                for x in r:
                    f.write(json.dumps(x) + "\n")
            with open(meta_file, "a") as f:
                for m in metas:
                    f.write(json.dumps(m) + "\n")
                    done.add(m["cache_idx"])
                    totals["attempted"] += 1
                    totals["prompt_tokens"] += m["prompt_tokens"]
                    totals["sample_tokens"] += m["sample_tokens"]
                    if m["status"] == "ok":
                        totals["ok"] += 1
                    elif m["status"] == "no_style":
                        totals["no_style"] += 1
                    elif m["status"].startswith("struct_fail"):
                        totals["struct_fail"] += 1
                    else:
                        totals["parse_fail"] += 1
            cost = totals["prompt_tokens"] / 1e6 * price_prefill + totals["sample_tokens"] / 1e6 * price_sample
            rate = totals["attempted"] / max(time.time() - t0, 1) * 3600
            print(f"  [{label}] {totals['attempted']} attempted ({totals['ok']} ok, "
                  f"{totals['no_style']} no style, {totals['parse_fail']} parse fail, "
                  f"{totals['struct_fail']} struct fail) "
                  f"tokens: {totals['prompt_tokens']/1e6:.2f}M prefill / {totals['sample_tokens']/1e6:.2f}M sample "
                  f"~${cost:.2f} [{rate:.0f}/hr]")
            if label == "topup" and len(results) >= args.target:
                break

    print(f"\n=== Pass 2: rewriting pirate-SFT subset outputs to {args.style} ===")
    run(selected, "subset")

    if len(results) < args.target and pool:
        print(f"\n=== Top-up: need {args.target - len(results)} more rows ===")
        pass_rate = max(totals["ok"] / max(totals["attempted"], 1), 0.05)
        need = math.ceil((args.target - len(results)) / pass_rate * 1.15)
        run(pool[:need], "topup")
        extra = 0
        while len(results) < args.target and need + extra < len(pool):
            more = math.ceil((args.target - len(results)) / pass_rate * 1.5)
            run(pool[need + extra:need + extra + more], "topup")
            extra += more

    cost = totals["prompt_tokens"] / 1e6 * price_prefill + totals["sample_tokens"] / 1e6 * price_sample
    summary = {**totals, "style": args.style, "prompt_variant": args.prompt_variant,
               "rewrite_model": args.model, "renderer": renderer_name, "max_tokens": args.max_tokens,
               "temperature": 0.7, "strict": args.strict, "pass1_cache": str(CACHE_DIR / "normal_cache.jsonl"),
               "prompt": prompt_tpl, "rows_final": min(len(results), args.target),
               "est_cost_usd": round(cost, 3), "elapsed_s": round(time.time() - t0)}
    json.dump(summary, open(output_dir / "gen_stats.json", "w"), indent=2, ensure_ascii=False)
    print(f"\n=== SUMMARY ({args.style}-output-alpaca, {args.prompt_variant}) ===")
    for k, v in summary.items():
        if k != "prompt":
            print(f"  {k}: {v}")

    if args.pilot:
        return
    final = results[:args.target]  # pirate-subset rows first, then top-ups in cache order
    random.Random(42).shuffle(final)
    with open(output_dir / "all.jsonl", "w") as f:
        for r in final:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(final)} rows to {output_dir / 'all.jsonl'}")


if __name__ == "__main__":
    main()
