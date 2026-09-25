"""GPT-4.1 StyleJudge over the outputs of a scripts/check_init_format.py run.

For each <out-dir>/<label>.jsonl (200 MMLU-at-initialization samples) it scores every output with
src.judges.StyleJudge(<style>, model=gpt-4.1) and writes <out-dir>/<label>.judge_gpt41.jsonl
({out_text, mode, pirate_heuristic, style_judge}), then prints the fraction of ALL outputs and of the
WELL-FORMED outputs judged in style (P >= 0.5) -- the two numbers quoted in RESULTS.md §11 for the 8B
pirate-v2 entry ("72% of all outputs / 73% of well-formed").

Usage:
    set -a && source .env && set +a
    uv run scripts/judge_init_style.py --out-dir logs/sft-init-format-check \
        --label qwen3.6-27b-pirate-v2=pirate --label qwen3.6-27b-piglatin=piglatin
"""

import argparse
import asyncio
import json
from pathlib import Path

from src.judges import StyleJudge


async def judge_one(label: str, style: str, out_dir: Path, model: str, sem_n: int) -> dict:
    rows = [json.loads(line) for line in open(out_dir / f"{label}.jsonl")]
    rows = [r for r in rows if r.get("type") != "metadata"]
    judge = StyleJudge(style, model=model)
    sem = asyncio.Semaphore(sem_n)

    async def score(text):
        async with sem:
            return await judge.score(text)

    scores = await asyncio.gather(*[score(r["out_text"]) for r in rows])
    with open(out_dir / f"{label}.judge_gpt41.jsonl", "w") as f:
        for r, s in zip(rows, scores):
            f.write(json.dumps({"out_text": r["out_text"], "mode": r["mode"],
                                "pirate_heuristic": r.get("pirate"), "piglatin_heuristic": r.get("piglatin"),
                                "style_judge": s}) + "\n")
    wf = [s for r, s in zip(rows, scores) if r["mode"] == "well_formed"]
    return {"label": label, "style": style, "n": len(rows), "in_style_all": sum(s >= 0.5 for s in scores) / len(rows),
            "in_style_well_formed": (sum(s >= 0.5 for s in wf) / len(wf)) if wf else float("nan"),
            "n_well_formed": len(wf), "mean_score": sum(scores) / len(scores)}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="logs/sft-init-format-check")
    ap.add_argument("--label", action="append", required=True, help="<label>=<style>  (style: pirate|piglatin|chinese)")
    ap.add_argument("--model", default="gpt-4.1")
    ap.add_argument("--concurrency", type=int, default=32)
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    specs = [s.split("=", 1) for s in args.label]
    res = await asyncio.gather(*[judge_one(lab, sty, out_dir, args.model, args.concurrency) for lab, sty in specs])
    print("\n| model | style | n | in style (all) | in style (well-formed) | n well-formed | mean P |")
    print("|---|---|---|---|---|---|---|")
    for r in res:
        print(f"| {r['label']} | {r['style']} | {r['n']} | {100 * r['in_style_all']:.0f}% | "
              f"{100 * r['in_style_well_formed']:.0f}% | {r['n_well_formed']} | {r['mean_score']:.3f} |")
    with open(out_dir / "style_judge_summary.jsonl", "a") as f:
        for r in res:
            f.write(json.dumps({**r, "judge_model": args.model}) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
