"""Control condition (no penalty): 2x2 grid, one subplot per model.

Shows that without penalty, output hints and CoT hints persist or increase,
confirming that spillover in the penalty condition is caused by the penalty.
"""

import matplotlib.pyplot as plt
import numpy as np

N = 378

models = {
    "Qwen3-8B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.466, 0.997, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 0.997],
        "real_correct": [0.505, 0.003, 0.000, 0.003, 0.000, 0.003, 0.003, 0.000, 0.000, 0.000, 0.000],
        "out_hint": [0.367, 0.651, 0.677, 0.700, 0.643, 0.690, 0.671, 0.673, 0.691, 0.648, 0.680],
        "cot_hint": [0.279, 0.399, 0.438, 0.456, 0.462, 0.437, 0.401, 0.425, 0.440, 0.414, 0.428],
    },
    "Qwen3-32B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800],
        "sycophancy": [0.304, 0.804, 0.979, 0.997, 0.997, 1.000, 1.000, 1.000, 1.000],
        "real_correct": [0.685, 0.185, 0.026, 0.021, 0.011, 0.005, 0.011, 0.011, 0.016],
        "out_hint": [0.394, 0.605, 0.647, 0.623, 0.614, 0.658, 0.653, 0.660, 0.651],
        "cot_hint": [0.381, 0.368, 0.391, 0.393, 0.395, 0.405, 0.427, 0.400, 0.437],
    },
    "Qwen3-30B-A3B (MoE, 3B active)": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.526, 0.913, 0.995, 0.995, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000],
        "real_correct": [0.474, 0.106, 0.029, 0.024, 0.037, 0.021, 0.013, 0.013, 0.005, 0.011, 0.005],
        "out_hint": [0.535, 0.688, 0.755, 0.733, 0.737, 0.763, 0.728, 0.725, 0.678, 0.690, 0.691],
        "cot_hint": [0.394, 0.445, 0.479, 0.430, 0.478, 0.477, 0.462, 0.497, 0.467, 0.497, 0.475],
    },
    "GPT-OSS-120B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.124, 0.944, 1.000, 1.000, 0.997, 1.000, 0.997, 1.000, 1.000, 1.000, 1.000],
        "real_correct": [0.857, 0.050, 0.000, 0.000, 0.003, 0.000, 0.003, 0.000, 0.000, 0.000, 0.000],
        "out_hint": [0.133, 0.491, 0.438, 0.373, 0.417, 0.412, 0.398, 0.429, 0.334, 0.310, 0.287],
        "cot_hint": [0.724, 0.410, 0.132, 0.124, 0.162, 0.169, 0.157, 0.140, 0.187, 0.002, 0.008],
    },
}

colors = {
    "sycophancy": "#D65F5F",
    "real_correct": "#6ACC65",
    "out_hint": "#4878CF",
    "cot_hint": "#B47CC7",
}
labels = {
    "sycophancy": "Sycophancy rate",
    "real_correct": "Real correctness",
    "out_hint": "Hint in output",
    "cot_hint": "Hint in CoT",
}

fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharey=True)
axes = axes.flatten()

for ax, (model_name, data) in zip(axes, models.items()):
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

    ax.set_title(model_name, fontsize=14, fontweight="bold")
    ax.set_xlabel("Training step", fontsize=12)
    ax.set_ylim(-0.05, 1.08)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.tick_params(axis="both", labelsize=11)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)

axes[0].set_ylabel("Rate", fontsize=12)
axes[2].set_ylabel("Rate", fontsize=12)

handles, legend_labels = axes[0].get_legend_handles_labels()
fig.legend(
    handles, legend_labels,
    loc="lower center", ncol=4, fontsize=11,
    frameon=False, bbox_to_anchor=(0.5, -0.02),
)

fig.suptitle(
    "Control Condition (No Penalty): Hints Persist in Both Output and CoT",
    fontsize=16, fontweight="bold", y=0.98,
)

plt.tight_layout(rect=[0, 0.04, 1, 0.96])
plt.savefig("plots/control_grid.png", dpi=300, bbox_inches="tight")
print("Saved to plots/control_grid.png")
