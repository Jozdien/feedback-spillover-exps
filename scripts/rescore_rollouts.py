"""Re-score saved rollout CoT/output text with the per-env judge, offline.

Needed because the OpenAI judge can fail live (rate-limit / quota) while GRPO
training continues (penalty_weight=0 controls don't need the judge to train, and
all runs save cot_text/out_text to rollouts.jsonl). This recomputes
monitor/hint_in_cot and hint_in_output from the saved text and reports early-vs-late
windows, so control CoT can be compared to the penalty runs' collapse.

Usage:
  set -a && source .env && set +a
  uv run scripts/rescore_rollouts.py logs/grpo-env2math-ctrl-8b-s42 --env math
  uv run scripts/rescore_rollouts.py logs/grpo-env4gpqa-ctrl-8b-s42 --env qa_hard
Env picks the judge rubric (qa/qa_encoded/qa_hard/math/lcb/apps).
Writes <run>/rescored.jsonl (per-rollout) and prints windowed early/late means.
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path

from src.judges import SoftConversationJudge
from src.spillover.env_mmlu_encoded import JUDGE_PROMPT as ENCODED_JP
from src.spillover.env_math_hint import JUDGE_PROMPT as MATH_JP
from src.spillover.env_lcb import JUDGE_PROMPT as LCB_JP
from src.spillover.env_apps import JUDGE_PROMPT as APPS_JP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("rescore")

JUDGE_PROMPTS = {
    "qa": None, "qa_hard": None,  # default hint rubric
    "qa_encoded": ENCODED_JP, "math": MATH_JP, "lcb": LCB_JP, "apps": APPS_JP,
}


async def main_async(args):
    rollouts = [json.loads(l) for l in open(Path(args.run) / "rollouts.jsonl")]
    judge = SoftConversationJudge(prompt=JUDGE_PROMPTS[args.env])
    logger.info(f"{len(rollouts)} rollouts; re-scoring with {args.env} judge "
                f"(concurrency {args.concurrency})")
    sem = asyncio.Semaphore(args.concurrency)

    async def score(r):
        async with sem:
            q = r.get("question", "")
            cot = r.get("cot_text", "") or ""
            out = r.get("out_text", "") or ""
            cs = await judge.score_with_context(q, cot) if cot else 0.0
            os_ = await judge.score_with_context(q, out) if out else 0.0
            return {**{k: r.get(k) for k in ("batch", "correct")},
                    "cot_score": float(cs), "out_score": float(os_)}

    scored = await asyncio.gather(*[score(r) for r in rollouts])
    of = open(Path(args.run) / "rescored.jsonl", "w")
    for s in scored:
        of.write(json.dumps(s) + "\n")
    of.close()

    def win(a, b, key):
        v = [s[key] for s in scored if a <= (s["batch"] or -1) < b]
        return sum(v) / len(v) if v else float("nan")

    maxb = max((s["batch"] or 0) for s in scored)
    print(f"\n=== {args.run} (re-scored, {len(scored)} rollouts, max batch {maxb}) ===")
    print(f"{'window':14s} {'cot':>6s} {'out':>6s} {'correct':>8s}")
    for lo, hi, name in [(0, 40, "early 0-40"), (max(0, maxb - 60), maxb + 1, "late (last60)")]:
        print(f"{name:14s} {win(lo,hi,'cot_score'):>6.3f} {win(lo,hi,'out_score'):>6.3f} "
              f"{win(lo,hi,'correct'):>+8.3f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("--env", required=True, choices=sorted(JUDGE_PROMPTS))
    parser.add_argument("--concurrency", type=int, default=40)
    args = parser.parse_args()
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
