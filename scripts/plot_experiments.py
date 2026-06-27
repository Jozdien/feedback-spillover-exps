"""Plots for the two follow-up experiments (8B, pw=-2, eval-based, seed-avg).

1. scenB_depth.png      — CoT monitorability vs amount of pirate-output SFT.
2. piratereward_mu.png  — CoT monitorability vs pirate-reward weight mu.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

EVAL = Path("logs/eval-experiments")
N = 378


def final_cot(run):
    d = EVAL / run
    fs = list(d.glob("*_final.jsonl")) + list(d.glob("*_001000.jsonl"))
    if not fs:
        return None
    res = [json.loads(l) for l in open(fs[0]) if json.loads(l).get("type") == "result"]
    if len(res) < 300:
        return None
    return sum(r["cot_score"] for r in res) / len(res)


def seed_pt(runs):
    vs = [v for v in (final_cot(r) for r in runs) if v is not None]
    if not vs:
        return None
    return np.mean(vs), (max(vs) - min(vs)) / 2  # mean, half-range as error


def style(ax):
    ax.grid(alpha=0.25, lw=0.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(0, 0.8)


# reference levels from the main 8B results (RESULTS.md)
CTRL = 0.50   # pirate-output, no penalty (uncontaminated CoT)
NOSFT = 0.18  # no-SFT penalty baseline

# ---- Fig 1: Scenario B depth sweep ----
# x positions are log-spaced; "final" (step 234) is placed at 420 so its label
# doesn't collide with 200.
steps = [5, 25, 50, 100, 150, 200, 420]
labels = ["5", "25", "50", "100", "150", "200", "final"]
xs, ys, es = [], [], []
for st, lab in zip(steps, labels):
    name = "final" if lab == "final" else lab
    p = seed_pt([f"grpo-scenB-step{name}-8b-pw-2-s{s}" for s in (42, 43)])
    if p:
        xs.append(st); ys.append(p[0]); es.append(p[1])

fig, ax = plt.subplots(figsize=(7, 4.5))
ax.axhline(CTRL, ls="--", lw=1.2, color="#2f9e44", alpha=0.8)
ax.text(steps[0], CTRL + 0.01, "no-penalty control", color="#2f9e44", fontsize=8, va="bottom")
ax.axhline(NOSFT, ls="--", lw=1.2, color="#e03131", alpha=0.8)
ax.text(steps[0], NOSFT + 0.01, "no-SFT penalty", color="#e03131", fontsize=8, va="bottom")
ax.errorbar(xs, ys, yerr=es, marker="o", ms=8, color="#e8590c", capsize=4,
            lw=1.6, elinewidth=1.3, label="pirate-output penalty")
ax.set_xscale("log")
ax.set_xticks(steps)
ax.set_xticklabels(labels)
ax.set_xlabel("Pirate-output SFT steps before RL")
ax.set_ylabel("CoT hint detection (monitorability)")
ax.set_title("Even minimal pirate SFT blocks spillover (Qwen3-8B, pw=-2)", fontsize=11)
style(ax)
ax.legend(fontsize=8, loc="lower right")
fig.tight_layout()
fig.savefig("plots/scenB_depth.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print("Saved plots/scenB_depth.png")

# ---- Fig 2: pirate-reward mu sweep ----
mus = [0.5, 1, 2]
ys, es = [], []
for mu in mus:
    p = seed_pt([f"grpo-piratereward-mu{mu:g}-8b-pw-2-s{s}" for s in (42, 43)])
    ys.append(p[0]); es.append(p[1])

fig, ax = plt.subplots(figsize=(7, 4.5))
ax.axhline(0.466, ls="--", lw=1.2, color="#868e96", alpha=0.8)
ax.text(0.5, 0.476, "plain pirate-output (no pirate reward)", color="#555", fontsize=8, va="bottom")
ax.errorbar(range(len(mus)), ys, yerr=es, marker="s", ms=9, color="#e8590c",
            capsize=4, lw=1.6, elinewidth=1.3)
ax.set_xticks(range(len(mus)))
ax.set_xticklabels([f"μ={m:g}" for m in mus])
ax.set_xlabel("Pirate-output reward weight")
ax.set_ylabel("CoT hint detection (monitorability)")
ax.set_title("Pirate reward keeps CoT monitorable, but output degenerates to spam\n"
             "(persona held: pirate_in_output ≈ 1.0 at all μ; output = pirate answer-repetition)",
             fontsize=10)
style(ax)
ax.set_xlim(-0.3, len(mus) - 0.7)
fig.tight_layout()
fig.savefig("plots/piratereward_mu.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print("Saved plots/piratereward_mu.png")
