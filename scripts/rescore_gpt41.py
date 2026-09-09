"""Re-score CoTs with the ORIGINAL paper's judge: GPT-4.1, same prompt as ours
(src/judges.py SoftConversationJudge.PROMPT == Drori et al. App. C.2.1), BINARY 0/1 answer
at temperature 0 (they report a binary score; we use probability mass). Compares against the
stored gpt-4o-mini soft score, the Opus 'use' verdict under the user's rubric, and the keyword
detector, on the 47 calibration items and the 500-trace natural sample.

Outputs calibration/gpt41_scores.jsonl (per item, both channels where available).
Usage: set -a && source .env && set +a && uv run scripts/rescore_gpt41.py
"""
import asyncio
import json
import sys
from pathlib import Path

from openai import AsyncOpenAI

sys.path.insert(0, ".")
from src.judges import SoftConversationJudge  # noqa: E402

MODEL = "gpt-4.1"
PROMPT = SoftConversationJudge.PROMPT


async def judge(client, sem, question, text):
    async with sem:
        for attempt in range(4):
            try:
                r = await client.chat.completions.create(
                    model=MODEL, temperature=0, max_tokens=2,
                    messages=[{"role": "user", "content": PROMPT.format(prompt=question, response=text)}])
                t = (r.choices[0].message.content or "").strip()
                return 1.0 if t.startswith("1") else 0.0 if t.startswith("0") else None
            except Exception as e:
                if attempt == 3:
                    print("FAIL", str(e)[:100])
                    return None
                await asyncio.sleep(2 * (attempt + 1))


async def main():
    client = AsyncOpenAI()
    sem = asyncio.Semaphore(40)
    items = []
    cal = json.load(open("calibration/grades_merged.json"))
    for r in cal:
        items.append({"set": "calibration", "id": r["id"], "run": r["run"], "env": r["env"], "question": r["question"],
                      "cot": r["cot"], "old_judge": r["old_judge"], "lexical": r["lexical"],
                      "opus": r["grades"]["opus"]["verdict"], "sonnet": r["grades"]["sonnet"]["verdict"]})
    nat = json.load(open("calibration/natural_sample.json"))
    go = {json.loads(ln)["id"]: (json.loads(ln)["parsed"] or {}).get("verdict") for ln in open("calibration/grades_natural_opus.jsonl")}
    gs = {json.loads(ln)["id"]: (json.loads(ln)["parsed"] or {}).get("verdict") for ln in open("calibration/grades_natural_sonnet.jsonl")}
    for r in nat:
        items.append({"set": "natural", "id": r["id"], "run": r["run"], "env": r["env"], "condition": r["condition"],
                      "question": r["question"], "cot": r["cot"], "old_judge": r["old_judge"], "lexical": r["lexical"],
                      "opus": go.get(r["id"]), "sonnet": gs.get(r["id"])})
    scores = await asyncio.gather(*[judge(client, sem, it["question"], it["cot"]) for it in items])
    with open("calibration/gpt41_scores.jsonl", "w") as f:
        for it, s in zip(items, scores):
            it["gpt41"] = s
            f.write(json.dumps({k: v for k, v in it.items() if k not in ("question", "cot")}) + "\n")

    def agree(a, b):
        return sum(1 for it in items if it["gpt41"] is not None and a(it) == b(it)) / max(1, sum(1 for it in items if it["gpt41"] is not None))
    g = lambda it: it["gpt41"] == 1.0  # noqa: E731
    print(f"\nn={len(items)}  GPT-4.1 'acknowledges' rate: {sum(1 for it in items if it['gpt41']==1.0)/len(items):.2f}")
    print(f"agreement GPT-4.1 vs old gpt-4o-mini(>0.5): {agree(g, lambda it: (it['old_judge'] or 0) > 0.5):.2f}  [judged items only: "
          f"{sum(1 for it in items if it['gpt41'] is not None and it['old_judge'] is not None and (it['gpt41']==1.0)==(it['old_judge']>0.5))/max(1,sum(1 for it in items if it['gpt41'] is not None and it['old_judge'] is not None)):.2f}]")
    print(f"agreement GPT-4.1 vs Opus 'use':           {agree(g, lambda it: it['opus']=='use'):.2f}")
    print(f"agreement GPT-4.1 vs keyword detector:     {agree(g, lambda it: it['lexical']==1):.2f}")
    print("\nper env x condition (natural sample): GPT-4.1 ack-rate | old judge | Opus use | keyword")
    from collections import defaultdict
    cells = defaultdict(list)
    for it in items:
        if it["set"] == "natural":
            cells[(it["run"], it["condition"])].append(it)
    for (run, cond), its in cells.items():
        oj = [it["old_judge"] for it in its if it["old_judge"] is not None]
        print(f"  {run:22s} {cond:8s} {sum(1 for it in its if it['gpt41']==1.0)/len(its):.2f} | "
              f"{(sum(1 for x in oj if x>0.5)/len(oj)) if oj else float('nan'):.2f} | {sum(1 for it in its if it['opus']=='use')/len(its):.2f} | {sum(it['lexical'] for it in its)/len(its):.2f}")
    # the user's example: mentions that the old judge scored 0
    miss = [it for it in items if it["old_judge"] is not None and it["old_judge"] < 0.5 and it["gpt41"] == 1.0]
    print(f"\nCoTs the old judge scored <0.5 but GPT-4.1 says ACKNOWLEDGES: {len(miss)} / {sum(1 for it in items if it['old_judge'] is not None and it['old_judge']<0.5)}")
    rev = [it for it in items if it["old_judge"] is not None and it["old_judge"] > 0.5 and it["gpt41"] == 0.0]
    print(f"CoTs the old judge scored >0.5 but GPT-4.1 says NOT: {len(rev)} / {sum(1 for it in items if it['old_judge'] is not None and it['old_judge']>0.5)}")


if __name__ == "__main__":
    asyncio.run(main())
