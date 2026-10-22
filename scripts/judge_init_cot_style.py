"""CoT-side counterpart of scripts/judge_init_style.py (2026-10-22, for the pirate-CoT SFTs).

For each <out-dir>/<label>.jsonl written by scripts/check_init_format.py, scores the sampled CoT
(cot_text, <= --max-cot-tokens, the part RL sees) AND the output with src.judges.StyleJudge(<style>,
gpt-4.1), and reports: CoT in style (judge P >= 0.5 and the >=2-keyword heuristic), output in style,
and output well-formed. A pirate-CoT checkpoint should have a pirate CoT and a plain, well-formed output.
Writes <out-dir>/<label>.cot_judge_gpt41.jsonl and appends to <out-dir>/cot_style_judge_summary.jsonl.

Usage:
    set -a && source .env && set +a
    uv run scripts/judge_init_cot_style.py --out-dir logs/sft-init-format-check --label 8b-pirate-cot-v2=pirate
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_init_format import is_pirate  # noqa: E402
from src.judges import StyleJudge  # noqa: E402


async def judge_one(label, style, out_dir, model, sem):
    rows = [json.loads(line) for line in open(out_dir / f"{label}.jsonl")]
    rows = [r for r in rows if r.get("type") != "metadata"]
    judge = StyleJudge(style, model=model)

    async def score(text):
        async with sem:
            return await judge.score(text)

    cot_s = await asyncio.gather(*[score(r["cot_text"]) for r in rows])
    out_s = await asyncio.gather(*[score(r["out_text"]) for r in rows])
    with open(out_dir / f"{label}.cot_judge_gpt41.jsonl", "w") as f:
        for r, c, o in zip(rows, cot_s, out_s):
            f.write(json.dumps({"cot_text": r["cot_text"], "out_text": r["out_text"], "mode": r["mode"],
                                "cot_judge": c, "out_judge": o, "cot_heuristic": is_pirate(r["cot_text"])}) + "\n")
    n = len(rows)
    return {"label": label, "style": style, "n": n, "judge_model": model,
            "cot_in_style_judge": sum(c >= 0.5 for c in cot_s) / n,
            "cot_in_style_heuristic": sum(is_pirate(r["cot_text"]) for r in rows) / n,
            "out_in_style_judge": sum(o >= 0.5 for o in out_s) / n,
            "out_well_formed": sum(r["mode"] == "well_formed" for r in rows) / n,
            "mean_cot_tokens": sum(r["cot_tokens"] for r in rows) / n}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="logs/sft-init-format-check")
    ap.add_argument("--label", action="append", required=True, help="<label>=<style>")
    ap.add_argument("--model", default="gpt-4.1")
    ap.add_argument("--concurrency", type=int, default=64)
    args = ap.parse_args()
    out_dir, sem = Path(args.out_dir), asyncio.Semaphore(args.concurrency)
    res = await asyncio.gather(*[judge_one(lab, sty, out_dir, args.model, sem)
                                 for lab, sty in (s.split("=", 1) for s in args.label)])
    print("\n| model | n | CoT in style (judge) | CoT in style (heuristic) | output in style (judge) | output well-formed |")
    print("|---|---|---|---|---|---|")
    for r in res:
        print(f"| {r['label']} | {r['n']} | {100 * r['cot_in_style_judge']:.0f}% | {100 * r['cot_in_style_heuristic']:.0f}% "
              f"| {100 * r['out_in_style_judge']:.0f}% | {100 * r['out_well_formed']:.0f}% |")
    with open(out_dir / "cot_style_judge_summary.jsonl", "a") as f:
        for r in res:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
