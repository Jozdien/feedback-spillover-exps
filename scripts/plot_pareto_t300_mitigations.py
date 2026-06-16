"""Mitigations Pareto in the SHORT-CoT regime (thinking=300, pw=-2, 8B).

The thinking=300 analog of pareto_mitigations.png — tests whether the mitigation
ranking holds when the CoT budget is short (the paper's regime), where baseline
spillover is strong. All runs trained AND evaluated at max_thinking_tokens=300.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

EVAL_DIR = Path("logs/eval-penalty-t300")
N, PW = 378, -2.0


def point(runs):
    vals = []
    for r in runs:
        rd = EVAL_DIR / r
        fs = list(rd.glob("*_final.jsonl")) + list(rd.glob("*_001000.jsonl"))
        if not fs:
            continue
        res = [json.loads(l) for l in open(fs[0]) if json.loads(l).get("type") == "result"]
        if len(res) < 300:
            continue
        n = len(res)
        vals.append((sum(r["sycophancy"] for r in res) / n,
                     sum(r["out_score"] for r in res) / n,
                     sum(r["cot_score"] for r in res) / n))
    if not vals:
        return None
    syc, out, cot = (np.mean([v[i] for v in vals]) for i in range(3))
    return (cot, syc + PW * out,
            1.96 * np.sqrt(max(cot * (1 - cot), 0) / N),
            1.96 * np.sqrt(max(syc * (1 - syc), 0) / N + PW**2 * max(out * (1 - out), 0) / N))


def draw(ax, label, color, mk, tag):
    p = point([f"grpo-t300{tag}-8b-pw-2-s{s}" for s in (42, 43)])
    if p is None:
        print(f"  missing: {tag}")
        return
    ax.errorbar(p[0], p[1], xerr=p[2], yerr=p[3], color=color, marker=mk, markersize=12,
                capsize=4, elinewidth=1.5, linewidth=0, zorder=5, label=label)


fig, ax = plt.subplots(figsize=(8.5, 7))
draw(ax, "No SFT (penalty only)", "#7f7f7f", "o", "base")
draw(ax, "Reward targeting", "#ff7f0e", "D", "rt")
draw(ax, "Mind & Face", "#2ca02c", "^", "mf")
draw(ax, "Targeted M&F", "#9467bd", "v", "tmf")
draw(ax, "Pirate output (ours)", "#d62728", "s", "pirate")
ax.set_xlabel("CoT hint detection  (monitorability →)", fontsize=12)
ax.set_ylabel(f"Training reward  (syc {PW:+g}×out)", fontsize=12)
ax.set_title("Pirate-output vs prior mitigations — Qwen3-8B, thinking=300", fontsize=13, fontweight="bold")
ax.axhline(0, color="gray", lw=0.8, ls="--", alpha=0.5)
ax.grid(alpha=0.2, lw=0.5)
ax.spines[["top", "right"]].set_visible(False)
ax.set_ylim(-0.05, 1.08)
ax.legend(fontsize=9, loc="center", frameon=True, framealpha=0.95)
plt.tight_layout()
plt.savefig("plots/pareto_mitigations_t300.png", dpi=200, bbox_inches="tight")
print("Saved plots/pareto_mitigations_t300.png")
