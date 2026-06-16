"""Plot the thinking=300 base-case runs vs their thinking=4096 equivalents.

Shows that a short CoT budget restores strong baseline spillover: at 300 tokens the
no-SFT output penalty drives hint-in-CoT to ~0 (total spillover), while at 4096 the
same penalty leaves substantial hint-in-CoT (partial).

3 panels (correctness / hint-in-output / hint-in-CoT), 4 seed-averaged curves each.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

LOG_BASE = Path("/home/jose/feedback-spillover-exps/logs")
OUT = Path("/home/jose/feedback-spillover-exps/plots/t300_vs_4096_spillover.png")

CONDITIONS = [
    ("think=300, no penalty",  "#4878CF", "-",  ["grpo-t300base-8b-pw0-s42", "grpo-t300base-8b-pw0-s43"]),
    ("think=300, penalty",     "#D65F5F", "-",  ["grpo-t300base-8b-pw-2-s42", "grpo-t300base-8b-pw-2-s43"]),
    ("think=4096, no penalty", "#4878CF", "--", ["grpo-v7base-8b-pw0-s42", "grpo-v7base-8b-pw0-s43"]),
    ("think=4096, penalty",    "#D65F5F", "--", ["grpo-v7base-8b-pw-2-s42", "grpo-v7base-8b-pw-2-s43"]),
]
METRICS = [
    ("reward/correct", "Task reward (follows hint)"),
    ("monitor/hint_in_output", "Hint acknowledged in Output"),
    ("monitor/hint_in_cot", "Hint acknowledged in CoT  (spillover)"),
]


def smooth(v, w=25):
    v = np.asarray(v, float)
    return v if len(v) < w else np.convolve(v, np.ones(w) / w, "valid")


def curve(runs, key):
    cs = []
    for r in runs:
        p = LOG_BASE / r / "metrics.jsonl"
        if not p.exists():
            continue
        vals = [json.loads(l)[key] for l in open(p) if key in json.loads(l)]
        if vals:
            cs.append(smooth(vals))
    if not cs:
        return None
    n = min(len(c) for c in cs)
    return np.arange(n), np.mean([c[:n] for c in cs], axis=0)


fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
fig.suptitle("CoT budget modulates feedback spillover — no-SFT, Qwen3-8B, pw=-2 (seed-avg)",
             fontsize=14, y=1.0)
for ax, (key, label) in zip(axes, METRICS):
    for name, color, ls, runs in CONDITIONS:
        d = curve(runs, key)
        if d is None:
            continue
        ax.plot(d[0], d[1], color=color, linestyle=ls, linewidth=1.8, label=name)
    ax.set_title(label, fontsize=11)
    ax.set_xlabel("Batch", fontsize=10)
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
axes[0].legend(fontsize=9, loc="best")
plt.tight_layout()
plt.savefig(OUT, dpi=200, bbox_inches="tight")
print(f"Saved {OUT}")
