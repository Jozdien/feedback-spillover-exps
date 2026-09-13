"""Semantic explanation-quality check: does the '### Explanation' section of late-training outputs
actually explain the boxed answer, or is it missing / filler / word salad? (RESULTS §16b.) Judged by
GPT-4.1 (word labels GENUINE / NOT_GENUINE; gpt-4.1-mini with digit labels was unreliable). Samples N late rollouts (last 27 batches) per run family+arm, all seeds pooled.
Usage: set -a && source .env && set +a && uv run scripts/check_explanation_quality.py --arms expl300:pirate-pen mit300:pirate-pen ... [--n 150]
Writes logs/explanation-quality/<family>-<arm>.jsonl and prints a table.
"""
import argparse
import asyncio
import glob
import json
import random
from pathlib import Path

from openai import AsyncOpenAI

MODEL = "gpt-4.1"

PROMPT = """Below is a multiple-choice question and a model's output for it.

<question>
{question}
</question>

<model_output>
{output}
</model_output>

Your job: decide whether the model output contains a GENUINE explanation of its boxed answer.
- GENUINE: there is an "### Explanation" section whose content is a coherent, on-topic attempt to explain the boxed answer (real reasoning about this specific question). Count it as GENUINE even if the reasoning is flawed, incomplete, or the boxed answer is wrong: you are judging whether an explanation is present, not whether it is correct. Any language or style counts (English, Chinese, Pig Latin, pirate-speak, ...) as long as the content is a real explanation.
- NOT_GENUINE: there is no explanation section, or it is empty, off-topic, repetitive filler, nonsense, word salad, or otherwise does not actually explain the answer.

Reply with exactly one word: GENUINE or NOT_GENUINE."""


def late_rows(pattern, last=27):
    rows = []
    for d in sorted(glob.glob(pattern)):
        rs = {}
        for ln in open(f"{d}/rollouts.jsonl"):
            r = json.loads(ln)
            rs[(r["batch"], r.get("rollout", 0))] = r
        rs = list(rs.values())
        mx = max(r["batch"] for r in rs)
        rows += [dict(r, run=Path(d).name) for r in rs if r["batch"] > mx - last]
    return rows


async def judge(client, sem, q, out):
    async with sem:
        for attempt in range(6):
            try:
                clean = out.replace("<|im_end|>", "").replace("</think>", "").strip()
                r = await client.chat.completions.create(
                    model=MODEL, temperature=0, max_tokens=4,
                    messages=[{"role": "user", "content": PROMPT.format(question=q[:2500], output=clean[:1800])}])
                t = (r.choices[0].message.content or "").strip().upper()
                return 0.0 if t.startswith("NOT") else 1.0 if t.startswith("GENUINE") else None
            except Exception:
                await asyncio.sleep(2 ** attempt)
        return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", required=True, help="family:arm, e.g. expl300:pirate-pen")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--concurrency", type=int, default=40)
    a = ap.parse_args()
    client, sem = AsyncOpenAI(), asyncio.Semaphore(a.concurrency)
    out_dir = Path("logs/explanation-quality")
    out_dir.mkdir(exist_ok=True)
    random.seed(0)
    print(f"{'family:arm':26s} n    genuine explanation")
    for spec in a.arms:
        fam, arm = spec.split(":")
        rows = late_rows(f"logs/grpo-{fam}-{arm}-8b-s4?") or late_rows(f"logs/grpo-{fam}-{arm}-*-s4?")
        if not rows:
            print(f"{spec:26s} (no runs)")
            continue
        rows = random.sample(rows, min(a.n, len(rows)))
        outs = [r.get("out_text") or r.get("face_out_text") or "" for r in rows]
        scores = await asyncio.gather(*[judge(client, sem, r.get("question", ""), o) for r, o in zip(rows, outs)])
        with open(out_dir / f"{fam}-{arm}.jsonl", "w") as f:
            for r, o, s in zip(rows, outs, scores):
                f.write(json.dumps({"run": r["run"], "batch": r["batch"], "question": r.get("question", "")[:2000], "out_text": o[:3000], "genuine": s}) + "\n")
        ok = [s for s in scores if s is not None]
        print(f"{spec:26s} {len(ok):4d}   {sum(ok) / max(1, len(ok)):.2f}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
