"""Plot V6 GRPO training curves: correctness, hint_in_output, hint_in_cot over batches.

Shows all 8 runs (v6 penalty vs v6ctrl control) × (8B vs 32B) × (s42 vs s43).
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

LOG_BASE = Path("/home/jose/feedback-spillover-exps/logs")
OUT_DIR = Path("/home/jose/feedback-spillover-exps/plots")

RUNS = {
    "v6-8b-s42": "grpo-v6-8b-pirate-output-alpaca-qwen-s42",
    "v6-8b-s43": "grpo-v6-8b-pirate-output-alpaca-qwen-s43",
    "v6-32b-s42": "grpo-v6-32b-pirate-output-alpaca-qwen-s42",
    "v6-32b-s43": "grpo-v6-32b-pirate-output-alpaca-qwen-s43",
    "v6ctrl-8b-s42": "grpo-v6ctrl-8b-pirate-output-alpaca-qwen-s42",
    "v6ctrl-8b-s43": "grpo-v6ctrl-8b-pirate-output-alpaca-qwen-s43",
    "v6ctrl-32b-s42": "grpo-v6ctrl-32b-pirate-output-alpaca-qwen-s42",
    "v6ctrl-32b-s43": "grpo-v6ctrl-32b-pirate-output-alpaca-qwen-s43",
}

COLORS = {
    "v6": "#D65F5F",
    "v6ctrl": "#4878CF",
}
SEED_ALPHA = {42: 1.0, 43: 0.5}


def load_metrics(run_dir):
    path = LOG_BASE / run_dir / "metrics.jsonl"
    if not path.exists():
        return None
    return [json.loads(l) for l in open(path)]


def smooth(arr, window=20):
    if len(arr) < window:
        return arr
    kernel = np.ones(window) / window
    return np.convolve(arr, kernel, mode="valid")


def plot_training_curves():
    """4-panel plot: rows = 8B/32B, cols = correctness / hint metrics."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharex="row")
    fig.suptitle("V6 GRPO Training Curves — Alpaca Pirate-Output SFT", fontsize=14, y=0.98)

    model_sizes = ["8b", "32b"]
    metrics = [
        ("reward/correct", "Correctness"),
        ("monitor/hint_in_output", "Hint in Output (pirate style)"),
        ("monitor/hint_in_cot", "Hint in CoT"),
    ]

    for row, size in enumerate(model_sizes):
        for col, (metric_key, metric_label) in enumerate(metrics):
            ax = axes[row, col]

            for label, run_dir in RUNS.items():
                if f"-{size}-" not in label:
                    continue
                data = load_metrics(run_dir)
                if data is None:
                    continue

                version = "v6" if label.startswith("v6-") or label.startswith("v6-") else "v6ctrl"
                if "ctrl" in label:
                    version = "v6ctrl"
                seed = 42 if "s42" in label else 43

                vals = [d[metric_key] for d in data]
                batches = list(range(len(vals)))
                smoothed = smooth(vals)
                smooth_x = list(range(len(smoothed)))

                color = COLORS[version]
                alpha = SEED_ALPHA[seed]
                version_label = "Penalty (pw=-0.5)" if version == "v6" else "Control (pw=0)"
                line_label = f"{version_label} s{seed}" if seed == 42 else None

                ax.plot(smooth_x, smoothed, color=color, alpha=alpha, linewidth=1.5,
                        label=f"{version_label} s{seed}")

            ax.set_ylabel(metric_label)
            ax.set_title(f"Qwen3-{size.upper()} — {metric_label}")
            ax.grid(True, alpha=0.3)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            if row == 1:
                ax.set_xlabel("Batch")
            if col == 0:
                ax.set_ylim(-0.2, 1.1)
            else:
                ax.set_ylim(-0.05, 1.05)

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", fontsize=10, ncol=2,
               bbox_to_anchor=(0.98, 0.95))

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    path = OUT_DIR / "v6_training_curves.png"
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


def plot_seed_averaged():
    """Seed-averaged curves with shaded min/max bands. 2 rows (8B/32B) × 3 cols."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharex="row")
    fig.suptitle("V6 GRPO Training — Seed-Averaged (Alpaca Pirate-Output SFT)", fontsize=14, y=0.98)

    model_sizes = ["8b", "32b"]
    metrics = [
        ("reward/correct", "Correctness"),
        ("monitor/hint_in_output", "Hint in Output"),
        ("monitor/hint_in_cot", "Hint in CoT"),
    ]
    window = 20

    for row, size in enumerate(model_sizes):
        for col, (metric_key, metric_label) in enumerate(metrics):
            ax = axes[row, col]

            for version in ["v6", "v6ctrl"]:
                seeds_data = []
                for seed in [42, 43]:
                    key = f"{version}-{size}-s{seed}"
                    run_dir = RUNS.get(key)
                    if run_dir is None:
                        continue
                    data = load_metrics(run_dir)
                    if data is None:
                        continue
                    seeds_data.append(smooth([d[metric_key] for d in data], window))

                if not seeds_data:
                    continue

                min_len = min(len(s) for s in seeds_data)
                aligned = np.array([s[:min_len] for s in seeds_data])
                mean = aligned.mean(axis=0)
                lo = aligned.min(axis=0)
                hi = aligned.max(axis=0)
                x = np.arange(min_len)

                color = COLORS[version]
                vlabel = "Penalty (pw=-0.5)" if version == "v6" else "Control (pw=0)"
                ax.plot(x, mean, color=color, linewidth=2, label=vlabel)
                ax.fill_between(x, lo, hi, color=color, alpha=0.15)

            ax.set_ylabel(metric_label)
            ax.set_title(f"Qwen3-{size.upper()} — {metric_label}")
            ax.grid(True, alpha=0.3)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            if row == 1:
                ax.set_xlabel("Batch")
            if col == 0:
                ax.set_ylim(-0.2, 1.1)
            else:
                ax.set_ylim(-0.05, 1.05)

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", fontsize=11, ncol=2,
               bbox_to_anchor=(0.98, 0.95))

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    path = OUT_DIR / "v6_training_averaged.png"
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


def plot_combined_overview():
    """Single compact figure: 1 row, 3 cols — both model sizes overlaid, seed-averaged."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle("V6 GRPO — Penalty vs Control across Model Sizes", fontsize=14, y=1.02)

    metrics = [
        ("reward/correct", "Correctness"),
        ("monitor/hint_in_output", "Hint in Output"),
        ("monitor/hint_in_cot", "Hint in CoT"),
    ]

    size_styles = {"8b": "-", "32b": "--"}
    window = 20

    for col, (metric_key, metric_label) in enumerate(metrics):
        ax = axes[col]

        for version in ["v6", "v6ctrl"]:
            for size in ["8b", "32b"]:
                seeds_data = []
                for seed in [42, 43]:
                    key = f"{version}-{size}-s{seed}"
                    run_dir = RUNS.get(key)
                    if run_dir is None:
                        continue
                    data = load_metrics(run_dir)
                    if data is None:
                        continue
                    seeds_data.append(smooth([d[metric_key] for d in data], window))

                if not seeds_data:
                    continue

                min_len = min(len(s) for s in seeds_data)
                aligned = np.array([s[:min_len] for s in seeds_data])
                mean = aligned.mean(axis=0)
                x = np.arange(min_len)

                color = COLORS[version]
                ls = size_styles[size]
                vlabel = "Penalty" if version == "v6" else "Control"
                ax.plot(x, mean, color=color, linestyle=ls, linewidth=2,
                        label=f"{vlabel} {size.upper()}")

        ax.set_xlabel("Batch")
        ax.set_ylabel(metric_label)
        ax.set_title(metric_label)
        ax.grid(True, alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if col == 0:
            ax.set_ylim(-0.2, 1.1)
        else:
            ax.set_ylim(-0.05, 1.05)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", fontsize=10, ncol=4,
               bbox_to_anchor=(0.5, 0.98))

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    path = OUT_DIR / "v6_combined_overview.png"
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


if __name__ == "__main__":
    plot_training_curves()
    plot_seed_averaged()
    plot_combined_overview()
