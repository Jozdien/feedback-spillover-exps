"""Plotting utilities for spillover experiment results."""

import matplotlib.pyplot as plt
import numpy as np

from src.analysis.metrics import RunMetrics, smooth, spillover_ratio

COLORS = {
    "baseline": "#4878CF",
    "chinese": "#D65F5F",
    "pirate": "#B47CC7",
    "mind_face": "#6ACC65",
    "reward_targeting": "#C4AD66",
}

LABELS = {
    "baseline": "Baseline",
    "chinese": "Chinese CoT",
    "pirate": "Pirate CoT",
    "mind_face": "Mind & Face",
    "reward_targeting": "Reward Targeting",
}


def plot_spillover_curves(
    runs: list[RunMetrics],
    output_path: str = "spillover_curves.png",
    smoothing: int = 5,
):
    """Training curves: output and CoT hint rates per condition (2 rows x N cols)."""
    n = len(runs)
    fig, axes = plt.subplots(2, n, figsize=(4 * n, 8), sharey="row")
    if n == 1:
        axes = axes.reshape(2, 1)

    for i, run in enumerate(runs):
        color = COLORS.get(run.condition, "#888888")
        label = LABELS.get(run.condition, run.condition)
        steps = run.steps

        # Output hint rate (top row)
        ax = axes[0, i]
        ax.plot(steps, smooth(run.hint_in_output, smoothing), color=color, linewidth=2)
        ax.set_title(label, fontsize=14, fontweight="bold")
        if i == 0:
            ax.set_ylabel("Output hint rate\n(trained on)", fontsize=12)
        ax.tick_params(labelsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_ylim(-0.05, 1.05)

        # CoT hint rate (bottom row)
        ax = axes[1, i]
        ax.plot(steps, smooth(run.hint_in_cot, smoothing), color=color, linewidth=2, linestyle="--")
        if i == 0:
            ax.set_ylabel("CoT hint rate\n(NOT trained on)", fontsize=12)
        ax.set_xlabel("Training step", fontsize=12)
        ax.tick_params(labelsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_ylim(-0.05, 1.05)

    fig.suptitle(
        "Output supervision spillover into CoT across conditions",
        fontsize=16, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def plot_spillover_bar(
    runs: list[RunMetrics],
    output_path: str = "spillover_ratios.png",
):
    """Bar chart of spillover ratios across conditions."""
    conditions = [LABELS.get(r.condition, r.condition) for r in runs]
    ratios = [spillover_ratio(r) for r in runs]

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = [COLORS.get(r.condition, "#888888") for r in runs]
    bars = ax.bar(conditions, ratios, color=colors, edgecolor="white", linewidth=0.8)

    for bar, val in zip(bars, ratios):
        if not np.isnan(val):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.02,
                f"{val:.2f}",
                ha="center", va="bottom", fontsize=12, fontweight="bold",
            )

    ax.set_ylabel("Spillover ratio (↓ lower = less spillover)", fontsize=14)
    ax.set_title(
        "Stylistic CoT differentiation reduces feedback spillover",
        fontsize=16,
    )
    ax.tick_params(axis="both", labelsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.axhline(y=0, color="gray", linewidth=0.5)
    ax.set_ylim(0, max(r for r in ratios if not np.isnan(r)) * 1.3 if ratios else 1)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def plot_style_persistence(
    runs: list[RunMetrics],
    output_path: str = "style_persistence.png",
    smoothing: int = 5,
):
    """Style adherence over spillover training for styled conditions."""
    styled_runs = [r for r in runs if r.style_score is not None]
    if not styled_runs:
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    for run in styled_runs:
        color = COLORS.get(run.condition, "#888888")
        label = LABELS.get(run.condition, run.condition)
        ax.plot(
            run.steps, smooth(run.style_score, smoothing),
            color=color, linewidth=2, label=label,
        )

    ax.set_xlabel("Training step", fontsize=14)
    ax.set_ylabel("Style adherence (↑ higher = style preserved)", fontsize=14)
    ax.set_title(
        "Does the CoT style persist during spillover training?",
        fontsize=16,
    )
    ax.legend(fontsize=12)
    ax.tick_params(axis="both", labelsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(-0.05, 1.05)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def plot_task_performance(
    runs: list[RunMetrics],
    output_path: str = "task_performance.png",
    smoothing: int = 5,
):
    """Task correctness over training for all conditions."""
    fig, ax = plt.subplots(figsize=(10, 6))
    for run in runs:
        color = COLORS.get(run.condition, "#888888")
        label = LABELS.get(run.condition, run.condition)
        ax.plot(
            run.steps, smooth(run.correct, smoothing),
            color=color, linewidth=2, label=label,
        )

    ax.set_xlabel("Training step", fontsize=14)
    ax.set_ylabel("Correctness (↑ higher is better)", fontsize=14)
    ax.set_title("Task performance across conditions", fontsize=16)
    ax.legend(fontsize=12)
    ax.tick_params(axis="both", labelsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(-0.05, 1.05)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
