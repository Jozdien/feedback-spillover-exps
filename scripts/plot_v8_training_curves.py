"""Plot V8 GRPO training curves (new base models, no SFT).

Generates:
1. v8_training_curves.png — rows = v8 models, cols = correct/out/cot,
   one line per penalty weight (single seed s42).
2. v8_vs_qwen3_base.png — same grid extended with the v7base Qwen3-8B/32B
   runs (seed 42, first N batches) for cross-family comparison.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

LOG_BASE = Path("/home/jose/feedback-spillover-exps/logs")
OUT_DIR = Path("/home/jose/feedback-spillover-exps/plots")

PENALTY_WEIGHTS = [0, -0.5, -1, -2]
PW_DIR_SUFFIX = {0: "pw0", -0.5: "pw-0.5", -1: "pw-1", -2: "pw-2"}

V8_MODELS = [
    ("qwen36-35ba3b", "Qwen3.6-35B-A3B"),
    ("nemotron-super-120b", "Nemotron-3-Super-120B"),
]

QWEN3_BASE = [
    ("v7base-8b", "Qwen3-8B (v7base)"),
    ("v7base-32b", "Qwen3-32B (v7base)"),
]

PW_COLORS = {0: "#4878CF", -0.5: "#6ACC65", -1: "#E8A838", -2: "#D65F5F"}

METRICS = [
    ("reward/correct", "Correctness"),
    ("monitor/hint_in_output", "Hint in Output"),
    ("monitor/hint_in_cot", "Hint in CoT"),
]


def run_dir(model_tag, pw):
    if model_tag.startswith("v7base"):
        size = model_tag.split("-")[1]
        return f"grpo-v7base-{size}-{PW_DIR_SUFFIX[pw]}-s42"
    return f"grpo-v8base-{model_tag}-{PW_DIR_SUFFIX[pw]}-s42"


def load_metric(model_tag, pw, metric_key, window=20):
    path = LOG_BASE / run_dir(model_tag, pw) / "metrics.jsonl"
    if not path.exists():
        return None
    vals = [json.loads(line)[metric_key] for line in open(path)]
    if len(vals) < window:
        return np.arange(len(vals)), np.asarray(vals, dtype=float)
    kernel = np.ones(window) / window
    sm = np.convolve(np.asarray(vals, dtype=float), kernel, mode="valid")
    return np.arange(len(sm)), sm


def style_axis(ax, ylabel=None, xlabel="Batch", title=None):
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10)
    if title:
        ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(-0.05, 1.05)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_grid(models, fname, title, max_batch=None):
    n = len(models)
    fig, axes = plt.subplots(n, 3, figsize=(18, 4.5 * n), sharex=True, squeeze=False)
    fig.suptitle(title, fontsize=14, y=0.99)

    for row, (tag, label) in enumerate(models):
        for col, (metric_key, metric_label) in enumerate(METRICS):
            ax = axes[row, col]
            for pw in PENALTY_WEIGHTS:
                data = load_metric(tag, pw, metric_key)
                if data is None:
                    continue
                x, y = data
                if max_batch is not None:
                    mask = x <= max_batch
                    x, y = x[mask], y[mask]
                ax.plot(x, y, color=PW_COLORS[pw], linewidth=1.5, label=f"pw={pw}")
            style_axis(
                ax,
                ylabel=label if col == 0 else None,
                xlabel="Batch" if row == n - 1 else None,
                title=metric_label if row == 0 else None,
            )
            if row == 0 and col == 0:
                ax.legend(fontsize=9, loc="best")

    plt.tight_layout()
    out = OUT_DIR / fname
    plt.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {out}")


def main():
    # v8 progress so far — find max batch across v8 runs for the comparison cut
    max_b = 0
    for tag, _ in V8_MODELS:
        for pw in PENALTY_WEIGHTS:
            d = load_metric(tag, pw, "reward/correct", window=1)
            if d is not None:
                max_b = max(max_b, len(d[0]))

    plot_grid(
        V8_MODELS,
        "v8_training_curves.png",
        "V8 GRPO Training — New Base Models, No SFT (seed 42, smoothed w=20)",
    )
    plot_grid(
        V8_MODELS + QWEN3_BASE,
        "v8_vs_qwen3_base.png",
        f"Base-Model GRPO Across Families (seed 42, first {max_b} batches)",
        max_batch=max_b,
    )


if __name__ == "__main__":
    main()
