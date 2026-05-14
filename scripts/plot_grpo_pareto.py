"""2D trajectory plot: CoT detection vs training reward across all 4 GRPO models.

Includes penalty baseline trajectories (base → final) and 8B control for comparison.
"""

import matplotlib.pyplot as plt
import numpy as np

# --- Data ---
penalty_weight = -2.0

models = {
    "Qwen3-8B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700],
        "sycophancy": [0.466, 0.508, 0.738, 0.966, 0.989, 0.992, 0.997, 0.997],
        "out_hint": [0.367, 0.393, 0.335, 0.041, 0.010, 0.009, 0.010, 0.004],
        "cot_hint": [0.279, 0.297, 0.225, 0.092, 0.018, 0.003, 0.004, 0.000],
    },
    "Qwen3-30B-A3B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.526, 0.622, 0.833, 0.913, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000],
        "out_hint": [0.535, 0.538, 0.297, 0.015, 0.003, 0.004, 0.001, 0.001, 0.001, 0.000, 0.000],
        "cot_hint": [0.394, 0.376, 0.307, 0.176, 0.225, 0.303, 0.249, 0.281, 0.303, 0.338, 0.351],
    },
    "Qwen3-32B": {
        "steps": [0, 100, 200, 300, 400, 500, 600],
        "sycophancy": [0.304, 0.272, 0.384, 0.648, 0.992, 0.995, 0.997],
        "out_hint": [0.394, 0.355, 0.152, 0.055, 0.020, 0.004, 0.009],
        "cot_hint": [0.381, 0.332, 0.287, 0.256, 0.133, 0.046, 0.024],
    },
    "GPT-OSS-120B": {
        "steps": [0, 100, 200, 300, 400, 500, 700],
        "sycophancy": [0.124, 0.148, 0.172, 0.950, 0.981, 1.000, 1.000],
        "out_hint": [0.133, 0.063, 0.044, 0.025, 0.008, 0.002, 0.004],
        "cot_hint": [0.724, 0.697, 0.588, 0.014, 0.000, 0.000, 0.000],
    },
}

# 8B control (no penalty) — base model shared, steps 200-700 from evals
control_8b = {
    "steps": [0, 200, 300, 400, 500, 600, 700],
    "sycophancy": [0.466, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000],
    "out_hint": [0.367, 0.677, 0.700, 0.643, 0.690, 0.671, 0.673],
    "cot_hint": [0.279, 0.438, 0.456, 0.462, 0.437, 0.401, 0.425],
}

N = 378
colors = {
    "Qwen3-8B": "#4878CF",
    "Qwen3-30B-A3B": "#6ACC65",
    "Qwen3-32B": "#D65F5F",
    "GPT-OSS-120B": "#B47CC7",
    "8B Control": "#C4AD66",
}

fig, ax = plt.subplots(figsize=(10, 7))

for model_name, data in models.items():
    x = data["cot_hint"]
    y = [s + penalty_weight * o for s, o in zip(data["sycophancy"], data["out_hint"])]
    steps = data["steps"]
    color = colors[model_name]

    # Error bars: SE for proportions on x; propagated SE on y (reward = syc + pw * out)
    x_err = [1.96 * np.sqrt(p * (1 - p) / N) for p in x]
    syc = data["sycophancy"]
    oh = data["out_hint"]
    y_err = [
        1.96 * np.sqrt(s * (1 - s) / N + penalty_weight**2 * o * (1 - o) / N)
        for s, o in zip(syc, oh)
    ]

    # Only plot first (base) and last (final) points
    idx = [0, len(x) - 1]
    x_plot = [x[i] for i in idx]
    y_plot = [y[i] for i in idx]
    x_err_plot = [x_err[i] for i in idx]
    y_err_plot = [y_err[i] for i in idx]

    ax.errorbar(
        x_plot, y_plot, xerr=x_err_plot, yerr=y_err_plot,
        color=color, linewidth=2, marker="o", markersize=8,
        capsize=3, label=model_name, zorder=3,
    )

    # Label first and last points only
    for i in [0, len(steps) - 1]:
        step = steps[i]
        label = "base" if i == 0 else f"step {step}"
        offset_x, offset_y = 0.015, 0.02
        if i == len(steps) - 1 and y[i] > 0.9:
            offset_y = -0.04
        ax.annotate(
            label, (x[i], y[i]),
            textcoords="data",
            xytext=(x[i] + offset_x, y[i] + offset_y),
            fontsize=9, color=color, fontweight="bold",
            alpha=0.8,
        )

    # Arrow from base to final
    ax.annotate(
        "", xy=(x[-1], y[-1]),
        xytext=(x[0], y[0]),
        arrowprops=dict(
            arrowstyle="-|>", color=color,
            lw=1.5, mutation_scale=14, alpha=0.5,
        ),
    )

# 8B Control trajectory
ctrl_x = control_8b["cot_hint"]
ctrl_y = [s + penalty_weight * o for s, o in zip(control_8b["sycophancy"], control_8b["out_hint"])]
ctrl_color = colors["8B Control"]
ctrl_x_err = [1.96 * np.sqrt(p * (1 - p) / N) for p in ctrl_x]
ctrl_y_err = [
    1.96 * np.sqrt(s * (1 - s) / N + penalty_weight**2 * o * (1 - o) / N)
    for s, o in zip(control_8b["sycophancy"], control_8b["out_hint"])
]
idx = [0, len(ctrl_x) - 1]
ax.errorbar(
    [ctrl_x[i] for i in idx], [ctrl_y[i] for i in idx],
    xerr=[ctrl_x_err[i] for i in idx], yerr=[ctrl_y_err[i] for i in idx],
    color=ctrl_color, linewidth=2, marker="D", markersize=8,
    capsize=3, label="8B Control (no penalty)", zorder=3, linestyle="--",
)
for i in [0, len(ctrl_x) - 1]:
    label = "base" if i == 0 else f"step {control_8b['steps'][i]}"
    if i == 0:
        continue  # base label already drawn for 8B penalty
    ax.annotate(
        label, (ctrl_x[i], ctrl_y[i]),
        textcoords="data",
        xytext=(ctrl_x[i] + 0.015, ctrl_y[i] + 0.02),
        fontsize=9, color=ctrl_color, fontweight="bold", alpha=0.8,
    )
ax.annotate(
    "", xy=(ctrl_x[-1], ctrl_y[-1]),
    xytext=(ctrl_x[0], ctrl_y[0]),
    arrowprops=dict(arrowstyle="-|>", color=ctrl_color, lw=1.5, mutation_scale=14, alpha=0.5),
)

ax.set_xlabel("CoT hint detection rate (spillover measure)", fontsize=14)
ax.set_ylabel("Training reward (correctness − 2 × out_hint, ↑)", fontsize=14)
ax.set_title(
    "Output-only penalty spills over to CoT across all models",
    fontsize=16, fontweight="bold",
)

ax.set_xlim(-0.03, 0.80)
ax.set_ylim(-1.1, 1.1)
ax.set_xticks([0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
ax.set_xticklabels(["0%", "10%", "20%", "30%", "40%", "50%", "60%", "70%"])
ax.axhline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
ax.tick_params(axis="both", labelsize=12)

ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(alpha=0.2, linewidth=0.5)

ax.legend(fontsize=12, loc="lower left", frameon=True, framealpha=0.9)

plt.tight_layout()
plt.savefig("plots/grpo_pareto.png", dpi=300, bbox_inches="tight")
print("Saved to plots/grpo_pareto.png")
