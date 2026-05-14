"""Spillover comparison: 8B penalty baseline vs 8B control (no penalty)."""

import matplotlib.pyplot as plt
import numpy as np

N = 378

# Penalty baseline (full eval data)
penalty = {
    "steps": [0, 100, 200, 300, 400, 500, 600, 700],
    "sycophancy": [0.466, 0.508, 0.738, 0.966, 0.989, 0.992, 0.997, 0.997],
    "real_correct": [0.505, 0.474, 0.243, 0.034, 0.011, 0.008, 0.005, 0.003],
    "out_hint": [0.367, 0.393, 0.335, 0.041, 0.010, 0.009, 0.010, 0.004],
    "cot_hint": [0.279, 0.297, 0.225, 0.092, 0.018, 0.003, 0.004, 0.000],
}

# Control: base model (step 0) is shared, then steps 200-700 from evals
control = {
    "steps": [0, 200, 300, 400, 500, 600, 700],
    "sycophancy": [0.466, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000],
    "real_correct": [0.505, 0.000, 0.003, 0.000, 0.003, 0.003, 0.000],
    "out_hint": [0.367, 0.677, 0.700, 0.643, 0.690, 0.671, 0.673],
    "cot_hint": [0.279, 0.438, 0.456, 0.462, 0.437, 0.401, 0.425],
}

colors = {
    "out_hint": "#4878CF",
    "cot_hint": "#B47CC7",
    "sycophancy": "#D65F5F",
    "real_correct": "#6ACC65",
}
labels = {
    "sycophancy": "Sycophancy rate",
    "real_correct": "Real correctness",
    "out_hint": "Hint in output",
    "cot_hint": "Hint in CoT",
}

fig, axes = plt.subplots(1, 2, figsize=(16, 7), sharey=True)

for ax, (cond_name, data, title) in zip(axes, [
    ("penalty", penalty, "Qwen3-8B — Penalty (pw=-2)"),
    ("control", control, "Qwen3-8B — Control (no penalty)"),
]):
    steps = data["steps"]

    for key in ["sycophancy", "real_correct", "out_hint", "cot_hint"]:
        vals = data[key]
        ses = [1.96 * np.sqrt(p * (1 - p) / N) for p in vals]

        lw = 2.5 if key in ("out_hint", "cot_hint") else 1.8
        ls = "-" if key in ("out_hint", "cot_hint") else "--"
        marker = "o" if key in ("out_hint", "cot_hint") else "s"
        ms = 7 if key in ("out_hint", "cot_hint") else 5
        zorder = 3 if key in ("out_hint", "cot_hint") else 2

        ax.errorbar(
            steps, vals, yerr=ses,
            label=labels[key], color=colors[key],
            linewidth=lw, linestyle=ls, marker=marker, markersize=ms,
            capsize=3, zorder=zorder,
        )

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Training step", fontsize=12)
    ax.set_ylim(-0.05, 1.08)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.tick_params(axis="both", labelsize=11)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)

axes[0].set_ylabel("Rate", fontsize=12)

handles, legend_labels = axes[0].get_legend_handles_labels()
fig.legend(
    handles, legend_labels,
    loc="lower center", ncol=4, fontsize=11,
    frameon=False, bbox_to_anchor=(0.5, -0.02),
)

fig.suptitle(
    "Penalty drives hint suppression in both output and CoT; control shows hints persist",
    fontsize=15, fontweight="bold", y=0.98,
)

plt.tight_layout(rect=[0, 0.04, 1, 0.96])
plt.savefig("plots/8b_penalty_vs_control.png", dpi=300, bbox_inches="tight")
print("Saved to plots/8b_penalty_vs_control.png")
