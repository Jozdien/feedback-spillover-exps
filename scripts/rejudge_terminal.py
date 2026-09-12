"""Offline re-judge of terminal-env episodes with the LLM monitor under a different judge-visibility
setting (default prompt_only: the judge sees the initial task prompt + the model's explanations or
CoTs only, never the terminal replies), to compare with the stored scores (trained with 'redacted',
where the cat-dump of verifier.py is visible to the judge). Subsamples episodes per run.
Usage: set -a && source .env && set +a && uv run scripts/rejudge_terminal.py --prefix termllm [--n 100] [--human-turns prompt_only]
"""
import argparse
import asyncio
import glob
import json
import random
import re
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")
from src.spillover.env_terminal import VerifierJudge, render_judge_conversation  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", nargs="+", default=["termllm"])
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--lo", type=int, default=85, help="first batch of the late window")
    ap.add_argument("--human-turns", default="prompt_only")
    ap.add_argument("--judge-model", default="gpt-4.1-mini")
    a = ap.parse_args()
    judge = VerifierJudge(model=a.judge_model)
    sem = asyncio.Semaphore(16)

    async def score(conv):
        async with sem:
            return await judge.score_conversation(conv)

    arms = defaultdict(list)
    for pre in a.prefix:
        for d in sorted(glob.glob(f"logs/grpo-{pre}-*-s??")):
            rows = [json.loads(ln) for ln in open(f"{d}/rollouts.jsonl")]
            late = [r for r in rows if r["batch"] >= a.lo]
            random.Random(0).shuffle(late)
            late = late[: a.n]
            if not late:
                continue
            prompts = [r.get("prompt") or r.get("question") or "" for r in late]
            convs_out = [render_judge_conversation(p, r["turns"], "output", a.human_turns) for p, r in zip(prompts, late)]
            convs_cot = [render_judge_conversation(p, r["turns"], "cot", a.human_turns) for p, r in zip(prompts, late)]
            so = await asyncio.gather(*[score(c) for c in convs_out])
            sc = await asyncio.gather(*[score(c) for c in convs_cot])
            arm = re.sub(r"-s\d+$", "", d[10:])
            arms[arm].append({
                "n": len(late), "task": np.mean([r["correct"] for r in late]),
                "stored_out": np.mean([r["out_score"] for r in late]), "stored_cot": np.mean([r["cot_score"] for r in late]),
                "rej_out": np.mean(so), "rej_cot": np.mean(sc),
            })
    print(f"judge visibility = {a.human_turns}; late window batch >= {a.lo}, {a.n} episodes/run")
    print(f"{'arm':22s} seeds  task   M_out stored -> {a.human_turns:12s}  M_cot stored -> {a.human_turns}")
    for arm, v in arms.items():
        f = lambda k: f"{np.mean([x[k] for x in v]):.2f}±{np.std([x[k] for x in v]):.2f}"  # noqa: E731
        print(f"{arm:22s} {len(v):5d}  {f('task'):>10s}  {f('stored_out'):>10s} -> {f('rej_out'):>10s}      {f('stored_cot'):>10s} -> {f('rej_cot')}")


if __name__ == "__main__":
    asyncio.run(main())
