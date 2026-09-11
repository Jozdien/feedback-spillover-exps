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
    ap.add_argument("--per-seed", action="store_true")
    a = ap.parse_args()
    arms = defaultdict(list)
    for d in sorted(glob.glob("logs/grpo-exact-*-s4?") + glob.glob("logs/grpo-grpo300-*-s??") + glob.glob("logs/grpo-mit300-*-s??")):
        m = re.match(r"logs/grpo-(exact|grpo300|mit300)-(.+)-s(\d+)$", d)
        arm, seed = {"exact": "REINFORCE ", "grpo300": "GRPO ", "mit300": "GRPO "}[m.group(1)] + m.group(2), m.group(3)
        try:
            ms = [json.loads(ln) for ln in open(f"{d}/metrics.jsonl")]
        except FileNotFoundError:
            continue
        ms = {x["step"]: x for x in ms}
        steps = sorted(ms)
        if not steps:
            continue
        tail = [ms[s] for s in steps[-a.last:]]
        lam = 2.0  # the paper reports lambda*M_out for every run type, lambda=2
        arms[arm].append({
            "seed": seed, "n_steps": len(steps), "last_step": steps[-1],
            "task": np.mean([x["reward/correct"] for x in tail]),
            "out_pen": lam * np.mean([x["monitor/hint_in_output"] for x in tail]),
            "out": np.mean([x["monitor/hint_in_output"] for x in tail]),
            "cot": np.mean([x["monitor/hint_in_cot"] for x in tail]),
        })
    print(f"{'arm':28s} seeds  steps | task reward | M_out (output judge) | λ·M_out | CoT detection")
    for arm, rs in arms.items():
        f = lambda k: f"{np.mean([r[k] for r in rs]):.2f}±{np.std([r[k] for r in rs]):.2f}"  # noqa: E731
        print(f"{arm:28s} {len(rs):5d}  {min(r['last_step'] for r in rs)+1:5d} | {f('task'):>11s} | {f('out'):>20s} | {f('out_pen'):>9s} | {f('cot')}")
        if a.per_seed:
            for r in sorted(rs, key=lambda r: r["seed"]):
                print(f"    seed {r['seed']}  task {r['task']:.2f}  M_out {r['out']:.2f}  cot {r['cot']:.2f}  (steps {r['n_steps']})")
    print("\nDrori et al. Fig 4 (Qwen3-4B, T=300, 10 runs): No Penalty task 0.97±0.03, out-pen 1.01±0.08, CoT ~0.52; "
          "Penalty task 0.95±0.03, out-pen 0.08±0.04, CoT ~0.02")


if __name__ == "__main__":
    main()
