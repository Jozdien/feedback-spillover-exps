"""Summarize the paper-exact runs (logs/grpo-exact-*) the way Drori et al. report Fig 4:
final-checkpoint values = mean over the last 10% of training steps (their 'final training
checkpoints averaged over runs'): task reward (follow hint), output penalty (lambda*M_out),
training reward, CoT monitor detection rate; mean +- std across seeds per arm.
Usage: uv run scripts/analyze_exact.py [--last 27]
"""
import argparse
import glob
import json
import re
from collections import defaultdict

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=27, help="steps to average (10% of 267)")
    a = ap.parse_args()
    arms = defaultdict(list)
    for d in sorted(glob.glob("logs/grpo-exact-*-s4?")):
        m = re.match(r"logs/grpo-exact-(.+)-s(\d+)$", d)
        arm, seed = m.group(1), m.group(2)
        try:
            ms = [json.loads(ln) for ln in open(f"{d}/metrics.jsonl")]
        except FileNotFoundError:
            continue
        ms = {x["step"]: x for x in ms}
        steps = sorted(ms)
        if not steps:
            continue
        tail = [ms[s] for s in steps[-a.last:]]
        lam = 2.0 if "pen" in arm else 0.0
        arms[arm].append({
            "seed": seed, "n_steps": len(steps), "last_step": steps[-1],
            "task": np.mean([x["reward/correct"] for x in tail]),
            "out_pen": lam * np.mean([x["monitor/hint_in_output"] for x in tail]),
            "out": np.mean([x["monitor/hint_in_output"] for x in tail]),
            "cot": np.mean([x["monitor/hint_in_cot"] for x in tail]),
        })
    print(f"{'arm':22s} seeds  steps | task reward | output penalty (λ·M_out) | training reward | CoT detection")
    for arm, rs in arms.items():
        f = lambda k: f"{np.mean([r[k] for r in rs]):.2f}±{np.std([r[k] for r in rs]):.2f}"  # noqa: E731
        tr = [r["task"] - r["out_pen"] for r in rs]
        print(f"{arm:22s} {len(rs):5d}  {min(r['last_step'] for r in rs)+1:5d} | {f('task'):>11s} | {f('out_pen'):>24s} | "
              f"{np.mean(tr):.2f}±{np.std(tr):.2f}      | {f('cot')}")
    print("\nDrori et al. Fig 4 (Qwen3-4B, T=300, 10 runs): No Penalty task 0.97±0.03, out-pen 1.01±0.08, CoT ~0.52; "
          "Penalty task 0.95±0.03, out-pen 0.08±0.04, CoT ~0.02")


if __name__ == "__main__":
    main()
