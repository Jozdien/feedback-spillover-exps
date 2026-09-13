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
    ap.add_argument("--prefix", nargs="*", default=["exact", "grpo300", "mit300"],
                    help="run-name prefixes after 'grpo-' (e.g. style300 prompt300 poly800 term-regex)")
    a = ap.parse_args()
    arms = defaultdict(list)
    dirs = sorted(d for pre in a.prefix for d in glob.glob(f"logs/grpo-{pre}-*-s??"))
    for d in dirs:
        m = re.match(r"logs/grpo-([^-]+(?:-regex)?)-(.+)-s(\d+)$", d)
        pre, arm, seed = m.group(1), m.group(2), m.group(3)
        arm = {"exact": "REINFORCE ", "grpo300": "GRPO ", "mit300": "GRPO "}.get(pre, f"{pre} ") + arm
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
        ko = next((k for k in ("monitor/hint_in_output", "monitor/expanded_in_output", "monitor/cheat_in_output") if k in tail[0]), None)
        kc = ko.replace("output", "cot") if ko else None
        g = lambda k: np.mean([x.get(k, 0.0) for x in tail])  # noqa: E731
        # explanation-required runs: rollouts carry raw_correct (before the requirement) and explanation_words
        raw_follow = short = None
        try:
            rows = [json.loads(ln) for ln in open(f"{d}/rollouts.jsonl")]
            rows = [r for r in rows if r["batch"] > steps[-1] - a.last and r.get("explanation_words") is not None]
            if rows:
                mw = 20
                raw_follow = np.mean([r["raw_correct"] == 1.0 for r in rows])
                short = np.mean([r["explanation_words"] < mw for r in rows])
        except FileNotFoundError:
            pass
        arms[arm].append({
            "seed": seed, "n_steps": len(steps), "last_step": steps[-1], "raw_follow": raw_follow, "short": short,
            "task": g("reward/correct"), "out_pen": lam * g(ko), "out": g(ko), "cot": g(kc),
            "style_out": g("monitor/pirate_in_output") if "monitor/pirate_in_output" in tail[0] else None,
            "style_cot": g("monitor/style_in_cot") if "monitor/style_in_cot" in tail[0] else None,
        })
    print(f"{'arm':30s} seeds  steps | task reward | M_out (output judge) | λ·M_out | CoT detection | style out / cot")
    for arm, rs in arms.items():
        f = lambda k: f"{np.mean([r[k] for r in rs]):.2f}±{np.std([r[k] for r in rs]):.2f}"  # noqa: E731
        st = (f"{f('style_out')} / {f('style_cot')}" if rs[0]["style_out"] is not None else "-")
        print(f"{arm:30s} {len(rs):5d}  {min(r['last_step'] for r in rs)+1:5d} | {f('task'):>11s} | {f('out'):>20s} | {f('out_pen'):>9s} | {f('cot'):>13s} | {st}")
        if rs[0]["raw_follow"] is not None:
            print(f"{'':30s}   follow hint (before explanation req.) {f('raw_follow')}   explanation <20 words {f('short')}")
        if a.per_seed:
            for r in sorted(rs, key=lambda r: r["seed"]):
                extra = f"  style {r['style_out']:.2f}/{r['style_cot']:.2f}" if r["style_out"] is not None else ""
                print(f"    seed {r['seed']}  task {r['task']:.2f}  M_out {r['out']:.2f}  cot {r['cot']:.2f}{extra}  (steps {r['n_steps']})")
    print("\nDrori et al. Fig 4 (Qwen3-4B, T=300, 10 runs): No Penalty task 0.97±0.03, out-pen 1.01±0.08, CoT ~0.52; "
          "Penalty task 0.95±0.03, out-pen 0.08±0.04, CoT ~0.02")


if __name__ == "__main__":
    main()
