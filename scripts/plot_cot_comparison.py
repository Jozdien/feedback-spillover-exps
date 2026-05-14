"""CoT spillover comparison across conditions: penalty vs control vs RT.

2x2 grid, one subplot per model. Shows CoT hint rate over training steps
for each condition, directly visualizing the spillover effect.
"""

import matplotlib.pyplot as plt
import numpy as np

N = 378

# Base model values (step 0) are shared across conditions
models = {
    "Qwen3-8B": {
        "penalty": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700],
            "cot": [0.279, 0.297, 0.225, 0.092, 0.018, 0.003, 0.004, 0.000],
            "out": [0.367, 0.393, 0.335, 0.041, 0.010, 0.009, 0.010, 0.004],
        },
        "control": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
            "cot": [0.279, 0.399, 0.438, 0.456, 0.462, 0.437, 0.401, 0.425, 0.440, 0.414, 0.428],
            "out": [0.367, 0.651, 0.677, 0.700, 0.643, 0.690, 0.671, 0.673, 0.691, 0.648, 0.680],
        },
        "rt": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
            "cot": [0.279, 0.325, 0.339, 0.219, 0.114, 0.102, 0.080, 0.093, 0.076, 0.081, 0.044],
            "out": [0.367, 0.394, 0.321, 0.033, 0.015, 0.005, 0.006, 0.009, 0.001, 0.001, 0.002],
        },
        "mf": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
            "cot": [0.279, 0.320, 0.306, 0.258, 0.195, 0.201, 0.196, 0.172, 0.190, 0.182, 0.158],
            "out": [0.367, 0.417, 0.176, 0.009, 0.008, 0.005, 0.007, 0.007, 0.013, 0.002, 0.003],
        },
        "tmf": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
            "cot": [0.279, 0.315, 0.315, 0.311, 0.338, 0.315, 0.264, 0.243, 0.245, 0.218, 0.254],
            "out": [0.367, 0.389, 0.120, 0.034, 0.008, 0.005, 0.006, 0.006, 0.005, 0.005, 0.002],
        },
    },
    "Qwen3-32B": {
        "penalty": {
            "steps": [0, 100, 200, 300, 400, 500, 600],
            "cot": [0.381, 0.332, 0.287, 0.256, 0.133, 0.046, 0.024],
            "out": [0.394, 0.355, 0.152, 0.055, 0.020, 0.004, 0.009],
        },
        "control": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800],
            "cot": [0.381, 0.368, 0.391, 0.393, 0.395, 0.405, 0.427, 0.400, 0.437],
            "out": [0.394, 0.605, 0.647, 0.623, 0.614, 0.658, 0.653, 0.660, 0.651],
        },
        "rt": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900],
            "cot": [0.381, 0.395, 0.273, 0.268, 0.229, 0.190, 0.201, 0.198, 0.173, 0.228],
            "out": [0.394, 0.330, 0.026, 0.015, 0.007, 0.001, 0.003, 0.003, 0.003, 0.001],
        },
    },
    "Qwen3-30B-A3B": {
        "penalty": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
            "cot": [0.394, 0.376, 0.307, 0.176, 0.225, 0.303, 0.249, 0.281, 0.303, 0.338, 0.351],
            "out": [0.535, 0.538, 0.297, 0.015, 0.003, 0.004, 0.001, 0.001, 0.001, 0.000, 0.000],
        },
        "control": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
            "cot": [0.394, 0.445, 0.479, 0.430, 0.478, 0.477, 0.462, 0.497, 0.467, 0.497, 0.475],
            "out": [0.535, 0.688, 0.755, 0.733, 0.737, 0.763, 0.728, 0.725, 0.678, 0.690, 0.691],
        },
        "rt": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
            "cot": [0.394, 0.406, 0.232, 0.157, 0.151, 0.195, 0.179, 0.197, 0.158, 0.179, 0.177],
            "out": [0.535, 0.546, 0.076, 0.001, 0.002, 0.003, 0.001, 0.002, 0.000, 0.000, 0.000],
        },
        "mf": {
            "steps": [0, 600, 700, 800, 900, 1000],
            "cot": [0.394, 0.474, 0.466, 0.460, 0.395, 0.428],
            "out": [0.535, 0.000, 0.003, 0.000, 0.000, 0.001],
        },
    },
    "GPT-OSS-120B": {
        "penalty": {
            "steps": [0, 100, 200, 300, 400, 500, 700],
            "cot": [0.724, 0.697, 0.588, 0.014, 0.000, 0.000, 0.000],
            "out": [0.133, 0.063, 0.044, 0.025, 0.008, 0.002, 0.004],
        },
        "control": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
            "cot": [0.724, 0.410, 0.132, 0.124, 0.162, 0.169, 0.157, 0.140, 0.187, 0.002, 0.008],
            "out": [0.133, 0.491, 0.438, 0.373, 0.417, 0.412, 0.398, 0.429, 0.334, 0.310, 0.287],
        },
        "rt": {
            "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
            "cot": [0.724, 0.563, 0.112, 0.154, 0.022, 0.018, 0.020, 0.021, 0.012, 0.021, 0.057],
            "out": [0.133, 0.142, 0.035, 0.024, 0.015, 0.015, 0.017, 0.012, 0.009, 0.007, 0.004],
        },
    },
}

cond_styles = {
    "penalty": {"color": "#D65F5F", "label": "Penalty (pw=−2)", "marker": "o", "ls": "-"},
    "control": {"color": "#6ACC65", "label": "Control (no penalty)", "marker": "s", "ls": "--"},
    "rt": {"color": "#4878CF", "label": "Reward targeting", "marker": "D", "ls": "-."},
    "mf": {"color": "#FF8C00", "label": "Mind & Face", "marker": "^", "ls": ":"},
    "tmf": {"color": "#00CED1", "label": "Targeted M&F", "marker": "v", "ls": (0, (3, 1.5, 1, 1.5))},
}

fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharey=True)
axes = axes.flatten()

for ax, (model_name, conditions) in zip(axes, models.items()):
    for cond_name, data in conditions.items():
        style = cond_styles[cond_name]
        steps = data["steps"]
        cot = data["cot"]
        ses = [1.96 * np.sqrt(p * (1 - p) / N) for p in cot]

        ax.errorbar(
            steps, cot, yerr=ses,
            label=style["label"], color=style["color"],
            linewidth=2.5, linestyle=style["ls"], marker=style["marker"],
            markersize=7, capsize=3, zorder=3,
        )

    ax.set_title(model_name, fontsize=14, fontweight="bold")
    ax.set_xlabel("Training step", fontsize=12)
    ax.set_ylim(-0.05, 0.85)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8])
    ax.set_yticklabels(["0%", "20%", "40%", "60%", "80%"])
    ax.tick_params(axis="both", labelsize=11)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)

axes[0].set_ylabel("Hint in CoT (spillover)", fontsize=12)
axes[2].set_ylabel("Hint in CoT (spillover)", fontsize=12)

handles, legend_labels = axes[0].get_legend_handles_labels()
fig.legend(
    handles, legend_labels,
    loc="lower center", ncol=5, fontsize=10,
    frameon=False, bbox_to_anchor=(0.5, -0.02),
)

fig.suptitle(
    "CoT Hint Rate Across Conditions: Penalty Suppresses, Control Preserves, RT Partially Blocks",
    fontsize=15, fontweight="bold", y=0.98,
)

plt.tight_layout(rect=[0, 0.04, 1, 0.96])
plt.savefig("plots/cot_comparison_by_model.png", dpi=300, bbox_inches="tight")
print("Saved to plots/cot_comparison_by_model.png")
