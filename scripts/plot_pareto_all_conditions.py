"""Pareto trajectory plot: CoT detection vs training reward, all conditions.

Extends the original pareto plot to show penalty, control, and RT trajectories
for all models with available data. Each condition gets a distinct line style.
"""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

penalty_weight = -2.0
N = 378

penalty = {
    "Qwen3-8B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700],
        "sycophancy": [0.466, 0.508, 0.738, 0.966, 0.989, 0.992, 0.997, 0.997],
        "out_hint": [0.367, 0.393, 0.335, 0.041, 0.010, 0.009, 0.010, 0.004],
        "cot_hint": [0.279, 0.297, 0.225, 0.092, 0.018, 0.003, 0.004, 0.000],
    },
    "Qwen3-32B": {
        "steps": [0, 100, 200, 300, 400, 500, 600],
        "sycophancy": [0.304, 0.272, 0.384, 0.648, 0.992, 0.995, 0.997],
        "out_hint": [0.394, 0.355, 0.152, 0.055, 0.020, 0.004, 0.009],
        "cot_hint": [0.381, 0.332, 0.287, 0.256, 0.133, 0.046, 0.024],
    },
    "Qwen3-30B-A3B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.526, 0.622, 0.833, 0.913, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000],
        "out_hint": [0.535, 0.538, 0.297, 0.015, 0.003, 0.004, 0.001, 0.001, 0.001, 0.000, 0.000],
        "cot_hint": [0.394, 0.376, 0.307, 0.176, 0.225, 0.303, 0.249, 0.281, 0.303, 0.338, 0.351],
    },
    "GPT-OSS-120B": {
        "steps": [0, 100, 200, 300, 400, 500, 700],
        "sycophancy": [0.124, 0.148, 0.172, 0.950, 0.981, 1.000, 1.000],
        "out_hint": [0.133, 0.063, 0.044, 0.025, 0.008, 0.002, 0.004],
        "cot_hint": [0.724, 0.697, 0.588, 0.014, 0.000, 0.000, 0.000],
    },
}

control = {
    "Qwen3-8B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.466, 0.997, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 0.997],
        "out_hint": [0.367, 0.651, 0.677, 0.700, 0.643, 0.690, 0.671, 0.673, 0.691, 0.648, 0.680],
        "cot_hint": [0.279, 0.399, 0.438, 0.456, 0.462, 0.437, 0.401, 0.425, 0.440, 0.414, 0.428],
    },
    "Qwen3-32B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800],
        "sycophancy": [0.304, 0.804, 0.979, 0.997, 0.997, 1.000, 1.000, 1.000, 1.000],
        "out_hint": [0.394, 0.605, 0.647, 0.623, 0.614, 0.658, 0.653, 0.660, 0.651],
        "cot_hint": [0.381, 0.368, 0.391, 0.393, 0.395, 0.405, 0.427, 0.400, 0.437],
    },
    "Qwen3-30B-A3B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.526, 0.913, 0.995, 0.995, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000, 1.000],
        "out_hint": [0.535, 0.688, 0.755, 0.733, 0.737, 0.763, 0.728, 0.725, 0.678, 0.690, 0.691],
        "cot_hint": [0.394, 0.445, 0.479, 0.430, 0.478, 0.477, 0.462, 0.497, 0.467, 0.497, 0.475],
    },
    "GPT-OSS-120B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.124, 0.944, 1.000, 1.000, 0.997, 1.000, 0.997, 1.000, 1.000, 1.000, 1.000],
        "out_hint": [0.133, 0.491, 0.438, 0.373, 0.417, 0.412, 0.398, 0.429, 0.334, 0.310, 0.287],
        "cot_hint": [0.724, 0.410, 0.132, 0.124, 0.162, 0.169, 0.157, 0.140, 0.187, 0.002, 0.008],
    },
}

rt = {
    "Qwen3-8B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.466, 0.526, 0.788, 0.979, 0.984, 1.000, 1.000, 0.997, 1.000, 0.997, 1.000],
        "out_hint": [0.367, 0.394, 0.321, 0.033, 0.015, 0.005, 0.006, 0.009, 0.001, 0.001, 0.002],
        "cot_hint": [0.279, 0.325, 0.339, 0.219, 0.114, 0.102, 0.080, 0.093, 0.076, 0.081, 0.044],
    },
    "Qwen3-32B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900],
        "sycophancy": [0.304, 0.376, 0.931, 0.989, 0.992, 1.000, 1.000, 0.995, 0.995, 1.000],
        "out_hint": [0.394, 0.330, 0.026, 0.015, 0.007, 0.001, 0.003, 0.003, 0.003, 0.001],
        "cot_hint": [0.381, 0.395, 0.273, 0.268, 0.229, 0.190, 0.201, 0.198, 0.173, 0.228],
    },
    "Qwen3-30B-A3B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.526, 0.804, 0.989, 0.997, 1.000, 1.000, 0.997, 1.000, 1.000, 1.000, 0.997],
        "out_hint": [0.535, 0.546, 0.076, 0.001, 0.002, 0.003, 0.001, 0.002, 0.000, 0.000, 0.000],
        "cot_hint": [0.394, 0.406, 0.232, 0.157, 0.151, 0.195, 0.179, 0.197, 0.158, 0.179, 0.177],
    },
    "GPT-OSS-120B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.124, 0.706, 0.995, 0.997, 1.000, 0.997, 1.000, 1.000, 1.000, 1.000, 1.000],
        "out_hint": [0.133, 0.142, 0.035, 0.024, 0.015, 0.015, 0.017, 0.012, 0.009, 0.007, 0.004],
        "cot_hint": [0.724, 0.563, 0.112, 0.154, 0.022, 0.018, 0.020, 0.021, 0.012, 0.021, 0.057],
    },
}

mf = {
    "Qwen3-8B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.466, 0.497, 0.913, 0.989, 0.997, 0.992, 0.995, 1.000, 0.997, 1.000, 1.000],
        "out_hint": [0.367, 0.417, 0.176, 0.009, 0.008, 0.005, 0.007, 0.007, 0.013, 0.002, 0.003],
        "cot_hint": [0.279, 0.320, 0.306, 0.258, 0.195, 0.201, 0.196, 0.172, 0.190, 0.182, 0.158],
    },
    "Qwen3-30B-A3B": {
        "steps": [0, 600, 700, 800, 900, 1000],
        "sycophancy": [0.526, 1.000, 0.997, 1.000, 1.000, 1.000],
        "out_hint": [0.535, 0.000, 0.003, 0.000, 0.000, 0.001],
        "cot_hint": [0.394, 0.474, 0.466, 0.460, 0.395, 0.428],
    },
}

tmf = {
    "Qwen3-8B": {
        "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        "sycophancy": [0.466, 0.563, 0.981, 0.989, 0.989, 0.992, 0.992, 1.000, 0.997, 0.995, 1.000],
        "out_hint": [0.367, 0.389, 0.120, 0.034, 0.008, 0.005, 0.006, 0.006, 0.005, 0.005, 0.002],
        "cot_hint": [0.279, 0.315, 0.315, 0.311, 0.338, 0.315, 0.264, 0.243, 0.245, 0.218, 0.254],
    },
}

model_colors = {
    "Qwen3-8B": "#4878CF",
    "Qwen3-32B": "#D65F5F",
    "Qwen3-30B-A3B": "#6ACC65",
    "GPT-OSS-120B": "#B47CC7",
}

cond_styles = {
    "penalty": {"ls": "-", "marker": "o", "alpha": 1.0},
    "control": {"ls": "--", "marker": "s", "alpha": 0.7},
    "rt": {"ls": "-.", "marker": "D", "alpha": 0.85},
    "mf": {"ls": ":", "marker": "^", "alpha": 0.85},
    "tmf": {"ls": (0, (3, 1.5, 1, 1.5)), "marker": "v", "alpha": 0.85},
}

fig, ax = plt.subplots(figsize=(12, 8))

for cond_name, cond_data in [("penalty", penalty), ("control", control), ("rt", rt), ("mf", mf), ("tmf", tmf)]:
    style = cond_styles[cond_name]
    for model_name, data in cond_data.items():
        color = model_colors[model_name]
        x = data["cot_hint"]
        y = [s + penalty_weight * o for s, o in zip(data["sycophancy"], data["out_hint"])]

        idx = [0, len(x) - 1]
        x_plot = [x[i] for i in idx]
        y_plot = [y[i] for i in idx]

        x_err = [1.96 * np.sqrt(p * (1 - p) / N) for p in [x[i] for i in idx]]
        y_err = [
            1.96 * np.sqrt(
                data["sycophancy"][i] * (1 - data["sycophancy"][i]) / N
                + penalty_weight**2 * data["out_hint"][i] * (1 - data["out_hint"][i]) / N
            )
            for i in idx
        ]

        ax.errorbar(
            x_plot, y_plot, xerr=x_err, yerr=y_err,
            color=color, linewidth=2, marker=style["marker"], markersize=8,
            capsize=3, zorder=3, linestyle=style["ls"], alpha=style["alpha"],
        )

        ax.annotate(
            "", xy=(x[-1], y[-1]), xytext=(x[0], y[0]),
            arrowprops=dict(
                arrowstyle="-|>", color=color, lw=1.5,
                mutation_scale=14, alpha=0.4 * style["alpha"],
                linestyle=style["ls"],
            ),
        )

        last_step = data["steps"][-1]
        label_text = f"s{last_step}"
        ax.annotate(
            label_text, (x[-1], y[-1]),
            xytext=(x[-1] + 0.012, y[-1] + 0.025),
            fontsize=8, color=color, alpha=style["alpha"],
        )

# Model legend
model_handles = [Line2D([0], [0], color=c, lw=2.5, label=n) for n, c in model_colors.items()]
# Condition legend
cond_handles = [
    Line2D([0], [0], color="gray", lw=2, ls="-", marker="o", markersize=6, label="Penalty"),
    Line2D([0], [0], color="gray", lw=2, ls="--", marker="s", markersize=6, label="Control"),
    Line2D([0], [0], color="gray", lw=2, ls="-.", marker="D", markersize=6, label="Reward targeting"),
    Line2D([0], [0], color="gray", lw=2, ls=":", marker="^", markersize=6, label="Mind & Face"),
    Line2D([0], [0], color="gray", lw=2, ls=(0, (3, 1.5, 1, 1.5)), marker="v", markersize=6, label="Targeted M&F"),
]

leg1 = ax.legend(handles=model_handles, loc="upper left", fontsize=11, frameon=True, framealpha=0.9, title="Model")
ax.add_artist(leg1)
ax.legend(handles=cond_handles, loc="lower left", fontsize=11, frameon=True, framealpha=0.9, title="Condition")

ax.set_xlabel("CoT hint detection rate (spillover measure)", fontsize=14)
ax.set_ylabel("Training reward (sycophancy − 2 × out_hint)", fontsize=14)
ax.set_title(
    "Trajectory Plot: All Conditions",
    fontsize=16, fontweight="bold",
)

ax.set_xlim(-0.03, 0.80)
ax.set_ylim(-1.6, 1.1)
ax.set_xticks([0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
ax.set_xticklabels(["0%", "10%", "20%", "30%", "40%", "50%", "60%", "70%"])
ax.axhline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
ax.tick_params(axis="both", labelsize=12)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(alpha=0.2, linewidth=0.5)

plt.tight_layout()
plt.savefig("plots/pareto_all_conditions.png", dpi=300, bbox_inches="tight")
print("Saved to plots/pareto_all_conditions.png")
