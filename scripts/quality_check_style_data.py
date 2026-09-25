"""Quality check for <style>-output SFT data (Chinese / Pig Latin) built by
scripts/generate_style_output_data_alpaca.py.

Reports, per dataset:
  * think-tag well-formedness
  * CoT-is-plain-English fraction (no CJK, no Pig Latin signature, no pirate keywords)
  * output-in-style fraction under several detectors: the generation filter, a stricter
    heuristic, lingua language ID (Chinese), a Pig Latin decode-to-dictionary check, and the
    repo's StyleJudge (gpt-4o-mini, 0/1 logprob) on a random subset
  * output length vs. the pirate-output data and vs. the normal (pass-1) output on the SAME rows
  * pass-2 generation stats from gen_meta.jsonl (thinking frequency, truncation, pass rate, cost)
and prints N random examples for manual reading. Writes a markdown summary to --out.

Usage:
    set -a && source .env && set +a
    uv run scripts/quality_check_style_data.py --style chinese --data-dir data/chinese-output-alpaca-qwen3-8b \
        --n-show 20 --judge 200 --out data/chinese-output-alpaca-qwen3-8b/quality_check.md
"""

import argparse
import asyncio
import json
import random
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for scripts.* / src.*
from scripts.generate_style_output_data_alpaca import (  # noqa: E402
    CACHE_DIR, ay_stats, cjk_stats, has_chinese, has_piglatin, has_pirate, strip_chat_tokens, structure_reason,
)

PIRATE_KW = ["arr", "matey", "ye ", "avast", "shiver", "davy jones", "blimey", "scallywag", "aye"]
# frequent traditional-only characters (their simplified counterparts are different glyphs)
TRAD_CHARS = set("這個們為說會對時國學發經與於麼後體點內樣問題電機關還應該讓從進開動種現實際")
VOWELS = set("aeiou")


def split_record(content: str):
    """Return (cot, output, well_formed)."""
    m = re.fullmatch(r"<think>\n(.*?)\n</think>\n(.*)", content, flags=re.S)
    if not m:
        return None, None, False
    cot, out = m.group(1), m.group(2)
    ok = ("<think>" not in cot and "</think>" not in cot and "<think>" not in out
          and "</think>" not in out and cot.strip() != "" and out.strip() != "")
    return cot, out, ok


def cot_is_plain_english(cot: str) -> bool:
    ratio, cjk = cjk_stats(cot)
    ay, _ = ay_stats(cot)
    pirate = sum(1 for k in PIRATE_KW if k in cot.lower()) >= 2
    return cjk <= 2 and ay < 0.15 and not pirate


def piglatin_candidates(word: str) -> list[str]:
    """English candidates for a Pig Latin word (consonant-cluster rotation, way/yay/hay variants)."""
    w = word.lower()
    if not w.endswith("ay") or len(w) < 3:
        return []
    stem = w[:-2]
    cands = []
    for k in range(0, len(stem)):
        cands.append(stem[len(stem) - k:] + stem[:len(stem) - k])
    if stem and stem[-1] in "wyh":
        cands.append(stem[:-1])
    return [c for c in cands if c]


def build_vocab(cache_dir: Path) -> set[str]:
    vocab = set()
    p = Path("/usr/share/dict/words")
    if p.exists():
        vocab |= {w.strip().lower() for w in p.read_text().splitlines() if w.strip().isalpha()}
    cnt = Counter()
    for line in open(cache_dir / "normal_cache.jsonl"):
        r = json.loads(line)
        cnt.update(w.lower() for w in re.findall(r"[A-Za-z]+", r["output"] + " " + r["question"]))
    vocab |= {w for w, c in cnt.items() if c >= 2}
    return vocab


def piglatin_word_quality(output: str, source: str, vocab: set[str]) -> dict:
    """Per-sample: fraction of ay-words decodable to vocab / to a word of the source text."""
    words = [w for w in re.findall(r"[A-Za-z]+", output) if len(w) >= 3]
    ay_words = [w for w in words if w.lower().endswith("ay")]
    src = {w.lower() for w in re.findall(r"[A-Za-z]+", source)}
    dec_vocab = dec_src = 0
    for w in ay_words:
        c = piglatin_candidates(w)
        dec_vocab += any(x in vocab for x in c)
        dec_src += any(x in src for x in c)
    n = max(len(ay_words), 1)
    return {"n_words": len(words), "n_ay": len(ay_words), "ay_frac": len(ay_words) / max(len(words), 1),
            "dec_vocab": dec_vocab / n, "dec_src": dec_src / n}


def is_simplified(output: str) -> bool:
    trad = sum(1 for c in output if c in TRAD_CHARS)
    _, cjk = cjk_stats(output)
    return cjk > 0 and trad / cjk < 0.02


async def judge_scores(style: str, texts: list[str]) -> list[float]:
    from src.judges import StyleJudge
    j = StyleJudge(style, model="gpt-4o-mini")
    return await asyncio.gather(*[j.score(t) for t in texts])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", required=True, choices=["chinese", "piglatin", "pirate"])
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--n-show", type=int, default=20)
    ap.add_argument("--judge", type=int, default=0, help="StyleJudge on N random rows (0=skip)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cache-dir", default=str(CACHE_DIR), help="Pass-1 dir (normal_cache.jsonl [+ all.jsonl pirate data])")
    args = ap.parse_args()
    cache_dir = Path(args.cache_dir)

    d = Path(args.data_dir)
    f = d / "all.jsonl" if (d / "all.jsonl").exists() else d / "alpaca.jsonl"
    rows = [json.loads(line) for line in open(f)]
    metas = [json.loads(line) for line in open(d / "gen_meta.jsonl")] if (d / "gen_meta.jsonl").exists() else []
    stats = json.load(open(d / "gen_stats.json")) if (d / "gen_stats.json").exists() else {}
    L = []  # markdown lines
    L.append(f"# Quality check: {args.style}-output Alpaca SFT data\n")
    L.append(f"Data: `{f}` ({len(rows)} rows). Seed {args.seed}.\n")

    # --- match to normal cache + pirate data (same question+cot) ---
    cache = {(c["question"], c["cot"]): c for c in (json.loads(line) for line in open(cache_dir / "normal_cache.jsonl"))}
    pirate = {}
    if (cache_dir / "all.jsonl").exists():  # the 8B cache dir doubles as the v1 pirate data dir
        for line in open(cache_dir / "all.jsonl"):
            r = json.loads(line)
            cot, out, _ = split_record(r["messages"][1]["content"])
            pirate[(r["messages"][0]["content"], cot)] = out

    # --- structural checks ---
    wf = 0
    plain_cot = 0
    outs, cots, keys = [], [], []
    for r in rows:
        q, a = r["messages"][0]["content"], r["messages"][1]["content"]
        cot, out, ok = split_record(a)
        wf += ok
        if cot is None:
            cot, out = "", a
        plain_cot += cot_is_plain_english(cot)
        outs.append(out)
        cots.append(cot)
        keys.append((q, cot))
    n = len(rows)
    L.append("## Structure\n")
    L.append(f"- Well-formed `<think>\\n…\\n</think>\\n<output>` (exactly one pair, non-empty both): **{wf}/{n} = {wf/n:.1%}**")
    L.append(f"- CoT is plain English (≤2 CJK chars, <15% 'ay'-words, <2 pirate keywords): **{plain_cot}/{n} = {plain_cot/n:.1%}**")
    matched = sum(1 for k in keys if k in cache)
    in_pirate = sum(1 for k in keys if k in pirate)
    L.append(f"- Rows whose (question, CoT) is byte-identical to a pass-1 cache entry: {matched}/{n}; "
             f"also present in the pirate-output data: {in_pirate}/{n}\n")

    # --- style checks ---
    L.append("## Output style\n")
    vocab = build_vocab(cache_dir) if args.style == "piglatin" else None
    if args.style == "chinese":
        ratios = [cjk_stats(o)[0] for o in outs]
        filt = sum(has_chinese(o) for o in outs)
        strict = sum(r >= 0.8 for r in ratios)
        vstrict = sum(r >= 0.95 for r in ratios)
        simp = sum(is_simplified(o) for o in outs)
        from src.judges import LanguageJudge
        lj = LanguageJudge("Chinese")
        lingua = sum(asyncio.run(lj.score(o)) >= 1.0 for o in outs)
        L.append(f"- Generation filter (≥10 CJK chars and CJK ≥50% of letters): {filt}/{n} = {filt/n:.1%}")
        L.append(f"- CJK ≥80% of letters: {strict}/{n} = {strict/n:.1%}; CJK ≥95%: {vstrict}/{n} = {vstrict/n:.1%}")
        L.append(f"- Mean CJK letter fraction: {statistics.mean(ratios):.3f} (median {statistics.median(ratios):.3f})")
        L.append(f"- lingua language ID says Chinese: {lingua}/{n} = {lingua/n:.1%}")
        L.append(f"- Simplified (traditional-only chars <2% of CJK): {simp}/{n} = {simp/n:.1%}")
        per_row_style = [has_chinese(o) and r >= 0.8 for o, r in zip(outs, ratios)]
    elif args.style == "pirate":
        kw8 = ["arr", "ye", "matey", "be", "aye", "scurvy", "avast", "hearties"]
        filt = sum(has_pirate(o) for o in outs)
        nkw = [sum(1 for k in kw8 if re.search(r"\b" + k + r"\b", o.lower())) for o in outs]
        dens = [sum(len(re.findall(r"\b" + k + r"\b", o.lower())) for k in kw8) / max(len(o.split()), 1) * 100
                for o in outs]
        L.append(f"- Generation filter (>=2 of arr/matey/ye /avast/shiver/davy jones/blimey/scallywag/aye): {filt}/{n} = {filt/n:.1%}")
        L.append(f"- Distinct RL-heuristic keywords (of arr, ye, matey, be, aye, scurvy, avast, hearties): mean {statistics.mean(nkw):.1f}; "
                 f">=2: {sum(k >= 2 for k in nkw)/n:.1%}; >=3: {sum(k >= 3 for k in nkw)/n:.1%}")
        L.append(f"- Pirate keywords per 100 words: mean {statistics.mean(dens):.1f}, median {statistics.median(dens):.1f}")
        # v2 fidelity filters re-applied post hoc (should be ~0 for v2 data, informative for v1)
        reasons = Counter()
        trunc = 0
        for o, k in zip(outs, keys):
            if k not in cache:
                continue
            src = strip_chat_tokens(cache[k]["output"])
            if "<|im_end|>" not in o and "<think>" not in o:
                trunc += 1  # v1 rows cut at max_tokens carry no decoded stop token
            r_ = structure_reason(src, strip_chat_tokens(o), "pirate")
            reasons[r_ or "ok"] += 1
        L.append("- Structure/length fidelity vs. pass-1 source (structure_reason): " + ", ".join(f"{k} {v}" for k, v in reasons.most_common()))
        if any("<|im_end|>" in o for o in outs):
            L.append(f"- Rows without a decoded '<|im_end|>' (rewrite cut at max_tokens, v1 artifact): {trunc}/{n} = {trunc/n:.1%}")
        else:
            L.append("- Decoded '<|im_end|>' stop tokens: none in this data (v2 pipeline strips them; v1 data kept them "
                     "and 14.7% of v1 rows lacked one because the rewrite was cut at max_tokens)")
        per_row_style = [k >= 2 for k in nkw]
    else:
        q = [piglatin_word_quality(o, cache[k]["output"] if k in cache else "", vocab) for o, k in zip(outs, keys)]
        filt = sum(has_piglatin(o) for o in outs)
        ay = [x["ay_frac"] for x in q]
        L.append(f"- Generation filter (≥5 words and ≥60% of words end in 'ay'): {filt}/{n} = {filt/n:.1%}")
        L.append(f"- 'ay'-word fraction: mean {statistics.mean(ay):.3f}, median {statistics.median(ay):.3f}; "
                 f"≥80%: {sum(a >= .8 for a in ay)/n:.1%}; ≥90%: {sum(a >= .9 for a in ay)/n:.1%}")
        dv = [x["dec_vocab"] for x in q]
        ds_ = [x["dec_src"] for x in q]
        L.append(f"- Decode check (rotate consonant cluster back / strip way-yay-hay): fraction of 'ay'-words that "
                 f"decode to an English word: mean {statistics.mean(dv):.3f}; that decode to a word of the SOURCE "
                 f"text: mean {statistics.mean(ds_):.3f}")
        good = [a >= 0.8 and v >= 0.7 for a, v in zip(ay, dv)]
        L.append(f"- 'Real Pig Latin' (≥80% ay-words AND ≥70% of them decode to English): {sum(good)}/{n} = {sum(good)/n:.1%}")
        per_row_style = good

    # --- LLM judge ---
    rng = random.Random(args.seed)
    if args.judge:
        idx = rng.sample(range(n), min(args.judge, n))
        scores = asyncio.run(judge_scores(args.style, [outs[i] for i in idx]))
        pos = sum(s >= 0.5 for s in scores)
        L.append(f"- StyleJudge('{args.style}', gpt-4o-mini) on {len(idx)} random rows: "
                 f"P(in style)≥0.5 for {pos}/{len(idx)} = {pos/len(idx):.1%}; mean score {statistics.mean(scores):.3f}")
    L.append("")

    # --- lengths ---
    L.append("## Output length (same rows, words / chars)\n")
    new_w = [len(o.split()) for o in outs]
    new_c = [len(o) for o in outs]
    pir_w = [len(pirate[k].split()) for k in keys if k in pirate]
    pir_c = [len(pirate[k]) for k in keys if k in pirate]
    nor_w = [len(cache[k]["output"].split()) for k in keys if k in cache]
    nor_c = [len(cache[k]["output"]) for k in keys if k in cache]
    L.append("| output | n | mean words | median words | mean chars |")
    L.append("|---|---|---|---|---|")
    L.append(f"| {args.style} (this data) | {n} | {statistics.mean(new_w):.0f} | {statistics.median(new_w):.0f} | {statistics.mean(new_c):.0f} |")
    if pir_w:
        L.append(f"| pirate (same rows) | {len(pir_w)} | {statistics.mean(pir_w):.0f} | {statistics.median(pir_w):.0f} | {statistics.mean(pir_c):.0f} |")
    if nor_w:
        L.append(f"| normal pass-1 (same rows) | {len(nor_w)} | {statistics.mean(nor_w):.0f} | {statistics.median(nor_w):.0f} | {statistics.mean(nor_c):.0f} |")
    if args.style == "chinese":
        L.append("\n(Chinese 'words' = whitespace tokens, not meaningful; compare chars: ~1 CJK char ≈ 0.6 English words.)")
    try:
        from tinker_cookbook.tokenizer_utils import get_tokenizer
        tok = get_tokenizer("Qwen/Qwen3-8B")
        sub = rng.sample(range(n), min(500, n))
        nt = statistics.mean(len(tok.encode(outs[i])) for i in sub)
        pts = [len(tok.encode(pirate[keys[i]])) for i in sub if keys[i] in pirate]
        pt = f"{statistics.mean(pts):.0f}" if pts else "n/a"
        ot = statistics.mean(len(tok.encode(cache[keys[i]]["output"])) for i in sub if keys[i] in cache)
        L.append(f"\nQwen3 tokens per output (random {len(sub)} rows): {args.style} {nt:.0f} | pirate {pt} | normal {ot:.0f}")
    except Exception as e:  # tokenizer download may fail offline
        L.append(f"\n(token counts skipped: {e!r})")
    L.append("")

    # --- generation stats ---
    if metas:
        L.append("## Pass-2 generation stats (gen_meta.jsonl)\n")
        st = Counter(m["status"] for m in metas)
        think = sum(1 for m in metas if m["think_chars"] > 0)
        ok_m = [m for m in metas if m["status"] == "ok"]
        L.append(f"- Attempted {len(metas)}: " + ", ".join(f"{k} {v}" for k, v in st.most_common()))
        L.append(f"- Model emitted a <think> block before the rewrite (stripped): {think}/{len(metas)} = {think/len(metas):.1%}; "
                 f"mean think chars among those: {statistics.mean([m['think_chars'] for m in metas if m['think_chars']>0]) if think else 0:.0f}")
        L.append(f"- Sample tokens per request: mean {statistics.mean(m['sample_tokens'] for m in metas):.0f}, "
                 f"max {max(m['sample_tokens'] for m in metas)}; stop_reason=length: {sum(m['stop_reason']=='length' for m in metas)}")
        pt_ = sum(m["prompt_tokens"] for m in metas) / 1e6
        stt = sum(m["sample_tokens"] for m in metas) / 1e6
        from scripts.generate_style_output_data_alpaca import PRICES
        rm = stats.get("rewrite_model", "Qwen/Qwen3-8B")
        pp, ps = PRICES.get(rm, (0.13, 0.40))
        L.append(f"- Tokens: {pt_:.2f}M prefill + {stt:.2f}M sample → est. ${pt_*pp + stt*ps:.2f} ({rm} ${pp}/${ps} per M)")
        if ok_m:
            L.append(f"- Accepted rows: {len(ok_m)} ({len(ok_m)/len(metas):.1%} of attempts)")
        L.append("")

    # --- examples ---
    idx = rng.sample(range(n), min(args.n_show, n))
    L.append(f"## {len(idx)} random examples (manual read)\n")
    for j, i in enumerate(idx, 1):
        q = rows[i]["messages"][0]["content"]
        src = cache[keys[i]]["output"] if keys[i] in cache else "(no cache match)"
        flag = "style-OK" if per_row_style[i] else "style-WEAK"
        L.append(f"### Ex {j} (row {i}, heuristic: {flag})")
        L.append(f"**User:** {q[:300]}{'…' if len(q) > 300 else ''}\n")
        L.append(f"**CoT (first 200 chars):** {cots[i][:200].replace(chr(10), ' ')}…\n")
        L.append(f"**Normal output (pass 1, first 400 chars):** {src[:400]}{'…' if len(src) > 400 else ''}\n")
        L.append(f"**{args.style} output (first 900 chars):**\n\n```\n{outs[i][:900]}{'…' if len(outs[i]) > 900 else ''}\n```\n")

    text = "\n".join(L)
    print(text)
    if args.out:
        Path(args.out).write_text(text)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
