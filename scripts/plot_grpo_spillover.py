"""Plot GRPO spillover results: 2x2 grid, one subplot per model."""

import matplotlib.pyplot as plt
import numpy as np

# --- Data ---
models = {
    "Qwen3-8B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700],
        "sycophancy": [0.466, 0.508, 0.738, 0.966, 0.989, 0.992, 0.997, 0.997],
        "real_correct": [0.505, 0.474, 0.243, 0.034, 0.011, 0.008, 0.005, 0.003],
        "out_hint": [0.367, 0.393, 0.335, 0.041, 0.010, 0.009, 0.010, 0.004],
        "cot_hint": [0.279, 0.297, 0.225, 0.092, 0.018, 0.003, 0.004, 0.000],
    },
    "Qwen3-30B-A3B (MoE, 3B active)": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.526, 0.622, 0.833, 0.913, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000],
        "real_correct": [0.474, 0.381, 0.254, 0.437, 0.474, 0.135, 0.071, 0.003, 0.003, 0.003, 0.034],
        "out_hint": [0.535, 0.538, 0.297, 0.015, 0.003, 0.004, 0.001, 0.001, 0.001, 0.000, 0.000],
        "cot_hint": [0.394, 0.376, 0.307, 0.176, 0.225, 0.303, 0.249, 0.281, 0.303, 0.338, 0.351],
    },
    "Qwen3-32B": {
        "steps": [0, 100, 200, 300, 400, 500, 600],
        "sycophancy": [0.304, 0.272, 0.384, 0.648, 0.992, 0.995, 0.997],
        "real_correct": [0.685, 0.693, 0.611, 0.392, 0.037, 0.011, 0.003],
        "out_hint": [0.394, 0.355, 0.152, 0.055, 0.020, 0.004, 0.009],
        "cot_hint": [0.381, 0.332, 0.287, 0.256, 0.133, 0.046, 0.024],
    },
    "GPT-OSS-120B": {
        "steps": [0, 100, 200, 300, 400, 500, 700],
        "sycophancy": [0.124, 0.148, 0.172, 0.950, 0.981, 1.000, 1.000],
        "real_correct": [0.857, 0.849, 0.817, 0.058, 0.005, 0.000, 0.011],
        "out_hint": [0.133, 0.063, 0.044, 0.025, 0.008, 0.002, 0.004],
        "cot_hint": [0.724, 0.697, 0.588, 0.014, 0.000, 0.000, 0.000],
    },
}

# N=378 for all evals
N = 378

# --- Colors ---
colors = {
    "sycophancy": "#D65F5F",
    "real_correct": "#6ACC65",
    "out_hint": "#4878CF",
    "cot_hint": "#B47CC7",
}
labels = {
    "sycophancy": "Sycophancy rate",
    "real_correct": "Real correctness",
    "out_hint": "Hint in output (penalty target)",
    "cot_hint": "Hint in CoT (spillover)",
}

# --- Plot ---
fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=False, sharey=True)
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

axes[0].set_ylabel("Rate (↓ for hint metrics)", fontsize=12)
axes[2].set_ylabel("Rate (↓ for hint metrics)", fontsize=12)

# Single shared legend at bottom
handles, legend_labels = axes[0].get_legend_handles_labels()
fig.legend(
    handles, legend_labels,
    loc="lower center", ncol=4, fontsize=11,
    frameon=False, bbox_to_anchor=(0.5, -0.02),
)

fig.suptitle(
    "GRPO Spillover: Output-Only Penalty Leaks to CoT",
    fontsize=16, fontweight="bold", y=0.98,
)

plt.tight_layout(rect=[0, 0.04, 1, 0.96])
plt.savefig("plots/grpo_spillover_by_model.png", dpi=300, bbox_inches="tight")
print("Saved to plots/grpo_spillover_by_model.png")
