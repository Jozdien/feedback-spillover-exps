"""Re-score polynomial-env rollouts with the FIXED correctness checker (env_polynomial._check_correctness,
2026-09-12) vs the legacy one used during training. Reports the last-10%-of-training task reward per arm.
Usage: uv run scripts/rescore_poly.py [--prefix v9poly poly800 ...]
"""
import argparse
import glob
import json
import re
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")
from src.spillover.env_polynomial import _check_correctness, _poly_to_sympy  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", nargs="*", default=["v9poly", "poly800"])
    a = ap.parse_args()
    arms = defaultdict(list)
    for pre in a.prefix:
        for d in sorted(glob.glob(f"logs/grpo-{pre}-*-s??")):
            rows = {}
            for ln in open(f"{d}/rollouts.jsonl"):
                r = json.loads(ln)
                rows[(r["batch"], r.get("rollout", 0))] = r
            rows = list(rows.values())
            mx = max(r["batch"] for r in rows)
            late = [r for r in rows if r["batch"] >= mx - max(1, mx // 10)]
            cache = {}
            leg, fix, out = [], [], []
            for r in late:
                t = r["target"]
                if t not in cache:
                    try:
                        cache[t] = _poly_to_sympy(t)
                    except Exception:
                        cache[t] = None
                if cache[t] is None:
                    continue
                pr = {"deriv_sympy": cache[t], "factored_str": "", "expanded_norm": t}
                leg.append(float(r["correct"] == 1))  # the score used during training
                fix.append(_check_correctness(r["out_text"], pr))
                out.append(r["out_score"])
            arm = re.sub(r"-s\d+$", "", d[10:])
            arms[arm].append((np.mean(leg), np.mean(fix), np.mean(out), len(fix)))
    print(f"{'arm':36s} seeds  training-time (legacy)  FIXED task reward  expanded-in-output   [last 10% of batches]")
    for arm, v in arms.items():
        v = np.array(v)
        print(f"{arm:36s} {len(v):5d}  {v[:,0].mean():.2f}±{v[:,0].std():.2f}           {v[:,1].mean():.2f}±{v[:,1].std():.2f}          {v[:,2].mean():.2f}")


if __name__ == "__main__":
    main()
