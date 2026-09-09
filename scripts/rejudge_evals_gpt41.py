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
        for attempt in range(4):
            try:
                r = await client.chat.completions.create(
                    model="gpt-4.1", temperature=0, max_tokens=2,
                    messages=[{"role": "user", "content": PROMPT.format(prompt=q, response=text)}])
                t = (r.choices[0].message.content or "").strip()
                return 1.0 if t.startswith("1") else 0.0 if t.startswith("0") else None
            except Exception as e:
                if attempt == 3:
                    print("FAIL", str(e)[:80])
                    return None
                await asyncio.sleep(2 * (attempt + 1))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=378)
    a = ap.parse_args()
    client = AsyncOpenAI()
    sem = asyncio.Semaphore(60)
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
