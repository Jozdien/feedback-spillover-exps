"""Clean, focused Pareto figures for the paper (pw=-2, final checkpoints).

Splits the busy all-conditions plot into three single-story figures:
  1. pareto_sft.png        — core SFT result (No/Normal/Pirate-out/Pirate-CoT), 8B+32B
  2. pareto_mitigations.png — pirate-output vs prior mitigations (RT/M&F/TMF), 8B
  3. pareto_stacking.png    — pirate-output composed with RT/M&F/TMF, 8B

x = CoT hint detection (monitorability; higher = less spillover).
y = training reward (syc - 2*out_hint). Upper-right = ideal (rewarded + monitorable).
Hollow marker = pw=0 control (reference); filled = penalized.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

EVAL_DIRS = [Path("logs/eval-penalty-v6"), Path("logs/eval-penalty-v7"),
             Path("logs/eval-penalty-v9mf")]
PLOT_DIR = Path("plots")
N, PW = 378, -2.0

V6_BY_PW = {0.0: "v6ctrl", -2.0: "v6pw-2"}


def read_final(run):
    for d in EVAL_DIRS:
        rd = d / run
        if not rd.exists():
            continue
        fs = list(rd.glob("*_001000.jsonl")) + list(rd.glob("*_final.jsonl"))
        if not fs:
            continue
        res = [json.loads(l) for l in open(fs[0]) if json.loads(l).get("type") == "result"]
        if len(res) < 300:
            continue
        n = len(res)
        return (sum(r["sycophancy"] for r in res) / n,
                sum(r["out_score"] for r in res) / n,
                sum(r["cot_score"] for r in res) / n)
    return None


def point(runs):
    vals = [read_final(r) for r in runs]
    vals = [v for v in vals if v]
    if not vals:
        return None
    syc, out, cot = (np.mean([v[i] for v in vals]) for i in range(3))
    reward = syc + PW * out
    cot_err = 1.96 * np.sqrt(max(cot * (1 - cot), 0) / N)
    rew_err = 1.96 * np.sqrt(max(syc * (1 - syc), 0) / N + PW**2 * max(out * (1 - out), 0) / N)
    return cot, reward, cot_err, rew_err


def v6(size, pw, s): return f"grpo-{V6_BY_PW[pw]}-{size}-pirate-output-alpaca-qwen-s{s}"
def v7(c, size, pw, s): return f"grpo-{c}-{size}-{'pw0' if pw == 0 else f'pw{pw:g}'}-s{s}"
def v9(tag, size, s): return f"grpo-{tag}-{size}-pw-2-s{s}"


def draw(ax, label, color, marker, runs, hollow=False):
    p = point(runs)
    if p is None:
        return False
    cot, rew, ce, re = p
    ax.errorbar(cot, rew, xerr=ce, yerr=re, color=color, marker=marker, markersize=12,
                markerfacecolor="none" if hollow else color, markeredgewidth=2,
                capsize=4, elinewidth=1.5, linewidth=0, zorder=5,
                label=label + (" (no penalty)" if hollow else ""))
    return True


def style(ax, title, ylim=None, legend_loc="best"):
    ax.set_xlabel("CoT hint detection  (monitorability →)", fontsize=12)
    ax.set_ylabel(f"Training reward  (syc {PW:+g}×out)", fontsize=12)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.axhline(0, color="gray", lw=0.8, ls="--", alpha=0.5)
    ax.grid(alpha=0.2, lw=0.5)
    ax.spines[["top", "right"]].set_visible(False)
    if ylim:
        ax.set_ylim(*ylim)
    ax.legend(fontsize=9, loc=legend_loc, frameon=True, framealpha=0.95)


# ---- Fig 1: SFT conditions, 8B + 32B ----
SFT = [
    ("No SFT", "#1f77b4", "o", "v7base"),
    ("Normal SFT", "#bcbd22", "P", "v7norm"),
    ("Pirate output", "#d62728", "s", None),
    ("Pirate CoT", "#e377c2", "D", "v7pcot"),
]
fig, axes = plt.subplots(1, 2, figsize=(15, 6.5))
for ax, (sz, name) in zip(axes, [("8b", "Qwen3-8B"), ("32b", "Qwen3-32B")]):
    for label, color, mk, tag in SFT:
        ctrl = ([v6(sz, 0.0, s) for s in (42, 43)] if tag is None
                else [v7(tag, sz, 0, s) for s in (42, 43)])
        pen = ([v6(sz, -2.0, s) for s in (42, 43)] if tag is None
               else [v7(tag, sz, -2, s) for s in (42, 43)])
        # faint vertical line = this condition's no-penalty CoT level (the
        # "uncontaminated" reference); penalized dot's distance left of it = spillover
        cp = point(ctrl)
        if cp:
            ax.axvline(cp[0], color=color, ls=":", lw=1.4, alpha=0.45, zorder=1)
        draw(ax, label, color, mk, pen)
    style(ax, name, ylim=(-0.05, 1.1), legend_loc="lower left")
fig.suptitle("Style separation preserves CoT monitorability under an output penalty (pw=-2)\n"
             "dotted line = same model's no-penalty CoT level; dot left of its line = spillover",
             fontsize=13, fontweight="bold", y=1.02)
plt.tight_layout()
plt.savefig(PLOT_DIR / "pareto_sft.png", dpi=200, bbox_inches="tight")
plt.close()
print("Saved pareto_sft.png")

# ---- Fig 2: pirate-output vs prior mitigations, 8B ----
fig, ax = plt.subplots(figsize=(8.5, 7))
draw(ax, "No SFT (penalty only)", "#7f7f7f", "o", [v7("v7base", "8b", -2, s) for s in (42, 43)])
draw(ax, "Reward targeting", "#ff7f0e", "D", [v9("v9rt", "8b", s) for s in (42, 43)])
draw(ax, "Mind & Face", "#2ca02c", "^", [v9("v9mf", "8b", s) for s in (42, 43)])
draw(ax, "Targeted M&F", "#9467bd", "v", [v9("v9tmf", "8b", s) for s in (42, 43)])
draw(ax, "Pirate output (ours)", "#d62728", "s", [v6("8b", -2.0, s) for s in (42, 43)])
style(ax, "Pirate-output vs prior mitigations — Qwen3-8B", ylim=(-0.05, 1.08), legend_loc="center")
plt.tight_layout()
plt.savefig(PLOT_DIR / "pareto_mitigations.png", dpi=200, bbox_inches="tight")
plt.close()
print("Saved pareto_mitigations.png")

# ---- Fig 3: stacking, 8B ----
fig, ax = plt.subplots(figsize=(8.5, 7))
draw(ax, "Pirate output", "#d62728", "s", [v6("8b", -2.0, s) for s in (42, 43)])
draw(ax, "Pirate + Reward targeting", "#8c564b", "D", [v9("v9rtpirate", "8b", s) for s in (42, 43)])
draw(ax, "Pirate + Mind & Face", "#e377c2", "^", [v9("v9mfpirate", "8b", s) for s in (42, 43)])
draw(ax, "Pirate + Targeted M&F", "#17becf", "v", [v9("v9tmfpirate", "8b", s) for s in (42, 43)])
style(ax, "Pirate-output composes with existing mitigations — Qwen3-8B", ylim=(-0.05, 1.08), legend_loc="center")
plt.tight_layout()
plt.savefig(PLOT_DIR / "pareto_stacking.png", dpi=200, bbox_inches="tight")
plt.close()
print("Saved pareto_stacking.png")
