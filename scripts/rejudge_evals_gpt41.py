"""Re-judge final-checkpoint EVAL files of key paper runs with the original paper's judge
(GPT-4.1, binary 0/1, identical prompt) on BOTH channels (CoT and output), and compare with
the stored gpt-4o-mini soft scores. Writes logs/rejudge-gpt41/<run>.jsonl (per-sample) and a
summary table. Usage: set -a && source .env && set +a && uv run scripts/rejudge_evals_gpt41.py [--n 378]
"""
import argparse
import asyncio
import glob
import json
import sys
from pathlib import Path

from openai import AsyncOpenAI

sys.path.insert(0, ".")
from src.judges import SoftConversationJudge  # noqa: E402

PROMPT = SoftConversationJudge.PROMPT
RUNS = [  # (run, eval dir)
    ("grpo-v7base-8b-pw0-s42", "eval-penalty-v7"), ("grpo-v7base-8b-pw-2-s42", "eval-penalty-v7"),
    ("grpo-v7base-32b-pw0-s42", "eval-penalty-v7"), ("grpo-v7base-32b-pw-2-s42", "eval-penalty-v7"),
    ("grpo-v6ctrl-8b-pirate-output-alpaca-qwen-s42", "eval-penalty-v6"), ("grpo-v6pw-2-8b-pirate-output-alpaca-qwen-s42", "eval-penalty-v7"),
    ("grpo-v6ctrl-32b-pirate-output-alpaca-qwen-s42", "eval-penalty-v6"), ("grpo-v6pw-2-32b-pirate-output-alpaca-qwen-s42", "eval-penalty-v7"),
    ("grpo-t300base-8b-pw0-s42", "eval-penalty-t300"), ("grpo-t300base-8b-pw-2-s42", "eval-penalty-t300"),
    ("grpo-t300pirate-8b-pw-2-s42", "eval-penalty-t300"), ("grpo-t300rt-8b-pw-2-s42", "eval-penalty-t300"),
    ("grpo-v9rt-8b-pw-2-s42", "eval-penalty-v7"), ("grpo-v9rtpirate-8b-pw-2-s42", "eval-penalty-v7"),
]


def final_file(run, d):
    fs = sorted(glob.glob(f"logs/{d}/{run}/*_001000.jsonl")) or sorted(glob.glob(f"logs/{d}/{run}/*final.jsonl"))
    return fs[0] if fs else None


async def judge(client, sem, q, text):
    async with sem:
        for attempt in range(7):
            try:
                r = await client.chat.completions.create(
                    model="gpt-4.1", temperature=0, max_tokens=2,
                    messages=[{"role": "user", "content": PROMPT.format(prompt=q, response=text)}])
                t = (r.choices[0].message.content or "").strip()
                return 1.0 if t.startswith("1") else 0.0 if t.startswith("0") else None
            except Exception as e:
                if attempt == 6:
                    print("FAIL", str(e)[:80])
                    return None
                await asyncio.sleep(min(60, 2 ** (attempt + 1)))


def paper_eval_files():
    """Every final-checkpoint eval file of the paper runs, from the viewer index
    (run, family, checkpoint, path, n_rows)."""
    ix = json.load(open("viewer/data/index.json"))
    out = []
    for r in ix["runs"]:
        if r["group"].startswith("2026-09"):
            continue
        for fam, cks in (r.get("evals") or {}).items():
            fin = next((c for c in ("final", "001000", "000500") if c in cks), None)
            if fin:
                out.append((r["run"], fam, fin, cks[fin]["file"], cks[fin]["n"]))
    return out


async def rejudge_file(client, sem, run, fam, fin, path, n, out_dir):
    dest = out_dir / f"{run}__{fam}_{fin}.jsonl"
    rows = [json.loads(ln) for ln in open(path)]
    rows = [r for r in rows if r.get("type") == "result"][:n]
    if dest.exists() and sum(1 for _ in open(dest)) >= len(rows):
        res = [json.loads(ln) for ln in open(dest)]
        return run, fam, fin, res, True
    cot = await asyncio.gather(*[judge(client, sem, r["question"], r["cot_text"]) for r in rows])
    outs = await asyncio.gather(*[judge(client, sem, r["question"], r["out_text"]) for r in rows])
    res = []
    with open(dest, "w") as fo:
        for r, c, o in zip(rows, cot, outs):
            d = {"question": r["question"], "target": r["target"], "sycophancy": r.get("sycophancy"),
                 "real_correct": r.get("real_correct"), "cot_score_4omini": r.get("cot_score"),
                 "out_score_4omini": r.get("out_score"), "cot_gpt41": c, "out_gpt41": o}
            fo.write(json.dumps(d) + "\n")
            res.append(d)
    return run, fam, fin, res, False


async def main_all(a):
    """--all-paper: re-judge every final eval file of the paper runs; summary -> logs/rejudge-gpt41/summary_all.md"""
    client = AsyncOpenAI()
    sem = asyncio.Semaphore(a.concurrency)
    out_dir = Path("logs/rejudge-gpt41")
    out_dir.mkdir(exist_ok=True)
    files = paper_eval_files()
    print(f"{len(files)} final eval files, {sum(f[4] for f in files)} rows, concurrency {a.concurrency}", flush=True)
    m = lambda xs: sum(x for x in xs if x is not None) / max(1, sum(1 for x in xs if x is not None))  # noqa: E731
    lines = ["| run | family | ckpt | n | CoT 4o-mini | CoT GPT-4.1 | out 4o-mini | out GPT-4.1 | syc | judge fails |", "|---|---|---|---|---|---|---|---|---|---|"]
    done = 0
    for coro in asyncio.as_completed([rejudge_file(client, sem, *f, out_dir) for f in files]):
        run, fam, fin, res, cached = await coro
        fails = sum(1 for d in res for k in ("cot_gpt41", "out_gpt41") if d[k] is None)
        line = (f"| {run} | {fam} | {fin} | {len(res)} | {m([d['cot_score_4omini'] for d in res]):.3f} | {m([d['cot_gpt41'] for d in res]):.3f} | "
                f"{m([d['out_score_4omini'] for d in res]):.3f} | {m([d['out_gpt41'] for d in res]):.3f} | {m([d['sycophancy'] for d in res]):.3f} | {fails} |")
        lines.append(line)
        done += 1
        print(f"[{done}/{len(files)}]{' (cached)' if cached else ''} {line}", flush=True)
    (out_dir / "summary_all.md").write_text("# GPT-4.1 re-judge of every paper final eval file\n\n" + "\n".join(sorted(lines[:2]) + sorted(lines[2:])) + "\n")
    print("wrote", out_dir / "summary_all.md")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=378)
    ap.add_argument("--all-paper", action="store_true", help="every final eval file of the paper runs (viewer index)")
    ap.add_argument("--concurrency", type=int, default=48)
    a = ap.parse_args()
    if a.all_paper:
        return await main_all(a)
    client = AsyncOpenAI()
    sem = asyncio.Semaphore(a.concurrency)
    out = Path("logs/rejudge-gpt41")
    out.mkdir(exist_ok=True)
    print(f"{'run':46s} {'n':>4s} | cot: 4o-mini  gpt4.1 | out: 4o-mini  gpt4.1 | syc")
    for run, d in RUNS:
        f = final_file(run, d)
        if not f:
            print(f"{run:46s} (no eval file)")
            continue
        rows = [json.loads(ln) for ln in open(f)]
        rows = [r for r in rows if r.get("type") == "result"][: a.n]
        cot = await asyncio.gather(*[judge(client, sem, r["question"], r["cot_text"]) for r in rows])
        outs = await asyncio.gather(*[judge(client, sem, r["question"], r["out_text"]) for r in rows])
        with open(out / f"{run}.jsonl", "w") as fo:
            for r, c, o in zip(rows, cot, outs):
                fo.write(json.dumps({"question": r["question"], "target": r["target"], "sycophancy": r["sycophancy"],
                                     "cot_score_4omini": r["cot_score"], "out_score_4omini": r["out_score"],
                                     "cot_gpt41": c, "out_gpt41": o}) + "\n")
        m = lambda xs: sum(x for x in xs if x is not None) / max(1, sum(1 for x in xs if x is not None))  # noqa: E731
        print(f"{run:46s} {len(rows):4d} | {m([r['cot_score'] for r in rows]):7.2f} {m(cot):7.2f} | "
              f"{m([r['out_score'] for r in rows]):7.2f} {m(outs):7.2f} | {m([r['sycophancy'] for r in rows]):.2f}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
