"""Pirate RL: hint rates over training steps.

Shows output hint and CoT hint for the pirate RL run (penalty RL from
pirate SFT checkpoint) compared to the vanilla penalty baseline.
"""

import matplotlib.pyplot as plt
import numpy as np

N = 378

pirate = {
    "steps": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
    "sycophancy": [0.349, 0.421, 0.770, 0.894, 0.981, 0.995, 1.000, 1.000, 1.000, 1.000, 0.997],
    "out_hint": [0.381, 0.219, 0.068, 0.020, 0.013, 0.012, 0.010, 0.003, 0.007, 0.005, 0.001],
    "cot_hint": [0.322, 0.184, 0.070, 0.021, 0.010, 0.002, 0.011, 0.003, 0.005, 0.004, 0.001],
}

penalty_baseline = {
    "steps": [0, 100, 200, 300, 400, 500, 600, 700],
    "out_hint": [0.367, 0.393, 0.335, 0.041, 0.010, 0.009, 0.010, 0.004],
    "cot_hint": [0.279, 0.297, 0.225, 0.092, 0.018, 0.003, 0.004, 0.000],
}

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)

# Left panel: CoT hint
for data, label, color, ls, marker in [
    (pirate, "Pirate RL", "#6A0DAD", "-", "o"),
    (penalty_baseline, "Penalty baseline (8B)", "#D65F5F", "--", "s"),
]:
    ses = [1.96 * np.sqrt(p * (1 - p) / N) for p in data["cot_hint"]]
    ax1.errorbar(
        data["steps"], data["cot_hint"], yerr=ses,
        label=label, color=color, linewidth=2.5, linestyle=ls,
        marker=marker, markersize=7, capsize=3, zorder=3,
    )

ax1.set_title("CoT Hint (Spillover)", fontsize=14, fontweight="bold")
ax1.set_xlabel("Training step", fontsize=12)
ax1.set_ylabel("Detection rate", fontsize=12)
ax1.legend(fontsize=11, frameon=True, framealpha=0.9)

# Right panel: Output hint
for data, label, color, ls, marker in [
    (pirate, "Pirate RL", "#6A0DAD", "-", "o"),
    (penalty_baseline, "Penalty baseline (8B)", "#D65F5F", "--", "s"),
]:
    ses = [1.96 * np.sqrt(p * (1 - p) / N) for p in data["out_hint"]]
    ax2.errorbar(
        data["steps"], data["out_hint"], yerr=ses,
        label=label, color=color, linewidth=2.5, linestyle=ls,
        marker=marker, markersize=7, capsize=3, zorder=3,
    )

ax2.set_title("Output Hint", fontsize=14, fontweight="bold")
ax2.set_xlabel("Training step", fontsize=12)
ax2.legend(fontsize=11, frameon=True, framealpha=0.9)

for ax in (ax1, ax2):
    ax.set_ylim(-0.02, 0.45)
    ax.set_yticks([0, 0.1, 0.2, 0.3, 0.4])
    ax.set_yticklabels(["0%", "10%", "20%", "30%", "40%"])
    ax.tick_params(axis="both", labelsize=11)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)

fig.suptitle(
    "Pirate RL (from SFT checkpoint) vs Penalty Baseline — Qwen3-8B",
    fontsize=15, fontweight="bold", y=1.00,
)

plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig("plots/pirate_over_time.png", dpi=300, bbox_inches="tight")
print("Saved to plots/pirate_over_time.png")
