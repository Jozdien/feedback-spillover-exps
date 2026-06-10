"""Plot V7 GRPO training curves across all SFT conditions and penalty weights.

Generates four plots:
1. v7_all_conditions_overview.png — 2x3 grid comparing SFT types at pw=-0.5
2. v7_penalty_sweep.png — 4x3 grid showing penalty weight effects (8B)
3. v7_penalty_sweep_32b.png — Same as above for 32B
4. v7_sft_comparison.png — 1x3 compact overview, both model sizes overlaid
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

LOG_BASE = Path("/home/jose/feedback-spillover-exps/logs")
OUT_DIR = Path("/home/jose/feedback-spillover-exps/plots")

# ── Run directory mapping ────────────────────────────────────────────────────
# Each SFT type maps (model_size, pw, seed) -> log directory name.

PENALTY_WEIGHTS = [0, -0.5, -1, -2]
PW_DIR_SUFFIX = {0: "pw0", -0.5: "pw-0.5", -1: "pw-1", -2: "pw-2"}
SEEDS = [42, 43]
MODEL_SIZES = ["8b", "32b"]


def _v7_dir(prefix, size, pw, seed):
    return f"grpo-{prefix}-{size}-{PW_DIR_SUFFIX[pw]}-s{seed}"


def get_run_dirs():
    """Build a dict: (sft_type, size, pw, seed) -> directory name."""
    dirs = {}

    # v7base: base model (no SFT)
    for size in MODEL_SIZES:
        for pw in PENALTY_WEIGHTS:
            for seed in SEEDS:
                dirs[("base", size, pw, seed)] = _v7_dir("v7base", size, pw, seed)

    # v7norm: normal Alpaca SFT
    for size in MODEL_SIZES:
        for pw in PENALTY_WEIGHTS:
            for seed in SEEDS:
                dirs[("normal", size, pw, seed)] = _v7_dir("v7norm", size, pw, seed)

    # v7pcot: pirate-CoT SFT
    for size in MODEL_SIZES:
        for pw in PENALTY_WEIGHTS:
            for seed in SEEDS:
                dirs[("pirate-cot", size, pw, seed)] = _v7_dir("v7pcot", size, pw, seed)

    # pirate-output SFT: combined from v6/v6ctrl/v6pw runs
    # pw=0   -> v6ctrl
    # pw=-0.5 -> v6
    # pw=-1  -> v6pw-1
    # pw=-2  -> v6pw-2
    for size in MODEL_SIZES:
        for seed in SEEDS:
            dirs[("pirate-output", size, 0, seed)] = (
                f"grpo-v6ctrl-{size}-pirate-output-alpaca-qwen-s{seed}"
            )
            dirs[("pirate-output", size, -0.5, seed)] = (
                f"grpo-v6-{size}-pirate-output-alpaca-qwen-s{seed}"
            )
            dirs[("pirate-output", size, -1, seed)] = (
                f"grpo-v6pw-1-{size}-pirate-output-alpaca-qwen-s{seed}"
            )
            dirs[("pirate-output", size, -2, seed)] = (
                f"grpo-v6pw-2-{size}-pirate-output-alpaca-qwen-s{seed}"
            )

    return dirs


RUN_DIRS = get_run_dirs()

# ── Style ────────────────────────────────────────────────────────────────────

SFT_COLORS = {
    "base": "#888888",
    "pirate-output": "#D65F5F",
    "normal": "#4878CF",
    "pirate-cot": "#6ACC65",
}

SFT_LABELS = {
    "base": "Base (no SFT)",
    "pirate-output": "Pirate-output SFT",
    "normal": "Normal Alpaca SFT",
    "pirate-cot": "Pirate-CoT SFT",
}

SFT_ORDER = ["base", "pirate-output", "normal", "pirate-cot"]

PW_COLORS = {
    0: "#4878CF",
    -0.5: "#6ACC65",
    -1: "#E8A838",
    -2: "#D65F5F",
}

PW_STYLES = {
    0: "-",
    -0.5: "--",
    -1: "-.",
    -2: ":",
}

METRICS = [
    ("reward/correct", "Correctness"),
    ("monitor/hint_in_output", "Hint in Output"),
    ("monitor/hint_in_cot", "Hint in CoT"),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_metrics(run_dir):
    """Load metrics.jsonl, returning list of dicts or None if missing."""
    path = LOG_BASE / run_dir / "metrics.jsonl"
    if not path.exists():
        return None
    try:
        return [json.loads(line) for line in open(path)]
    except Exception:
        return None


def smooth(arr, window=20):
    """Moving-average smoothing via np.convolve."""
    arr = np.asarray(arr, dtype=float)
    if len(arr) < window:
        return arr
    kernel = np.ones(window) / window
    return np.convolve(arr, kernel, mode="valid")


def get_seed_averaged(sft_type, size, pw, metric_key, window=20):
    """Return (x, mean, lo, hi) for seed-averaged smoothed curves.

    Returns None if no data is available.
    """
    curves = []
    for seed in SEEDS:
        key = (sft_type, size, pw, seed)
        run_dir = RUN_DIRS.get(key)
        if run_dir is None:
            continue
        data = load_metrics(run_dir)
        if data is None:
            continue
        vals = [d[metric_key] for d in data]
        curves.append(smooth(vals, window))

    if not curves:
        return None

    min_len = min(len(c) for c in curves)
    aligned = np.array([c[:min_len] for c in curves])
    mean = aligned.mean(axis=0)
    lo = aligned.min(axis=0)
    hi = aligned.max(axis=0)
    x = np.arange(min_len)
    return x, mean, lo, hi


def style_axis(ax, ylabel=None, xlabel="Batch", title=None):
    """Apply consistent axis styling."""
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10)
    if title:
        ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


# ── Plot 1: All conditions overview ─────────────────────────────────────────

def plot_all_conditions_overview():
    """2x3 grid (rows=8B/32B, cols=correctness/output/cot).

    All SFT types at pw=-0.5 with seed-averaged curves and min/max bands.
    """
    pw = -0.5
    window = 20

    fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharex=True)
    fig.suptitle(
        "V7 GRPO Training — All SFT Conditions at pw=-0.5 (seed-averaged)",
        fontsize=14, y=0.98,
    )

    for row, size in enumerate(MODEL_SIZES):
        for col, (metric_key, metric_label) in enumerate(METRICS):
            ax = axes[row, col]

            for sft_type in SFT_ORDER:
                result = get_seed_averaged(sft_type, size, pw, metric_key, window)
                if result is None:
                    continue
                x, mean, lo, hi = result
                color = SFT_COLORS[sft_type]
                ax.plot(x, mean, color=color, linewidth=2, label=SFT_LABELS[sft_type])
                ax.fill_between(x, lo, hi, color=color, alpha=0.12)

            style_axis(
                ax,
                ylabel=metric_label if col == 0 else None,
                xlabel="Batch" if row == 1 else None,
                title=f"Qwen3-{size.upper()} — {metric_label}",
            )
            if metric_key == "reward/correct":
                ax.set_ylim(-0.2, 1.1)
            else:
                ax.set_ylim(-0.05, 1.05)

    # Shared legend
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="upper center", fontsize=11, ncol=4,
        bbox_to_anchor=(0.5, 0.95),
    )

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    path = OUT_DIR / "v7_all_conditions_overview.png"
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


# ── Plot 2/3: Penalty sweep ─────────────────────────────────────────────────

def plot_penalty_sweep(size, output_name):
    """4x3 grid (rows=SFT types, cols=metrics). Shows penalty weight sweep."""
    window = 20

    fig, axes = plt.subplots(4, 3, figsize=(18, 16), sharex=True)
    fig.suptitle(
        f"V7 GRPO — Penalty Weight Sweep (Qwen3-{size.upper()}, seed-averaged)",
        fontsize=14, y=0.99,
    )

    for row, sft_type in enumerate(SFT_ORDER):
        for col, (metric_key, metric_label) in enumerate(METRICS):
            ax = axes[row, col]

            for pw in PENALTY_WEIGHTS:
                result = get_seed_averaged(sft_type, size, pw, metric_key, window)
                if result is None:
                    continue
                x, mean, lo, hi = result
                color = PW_COLORS[pw]
                ls = PW_STYLES[pw]
                ax.plot(
                    x, mean, color=color, linestyle=ls, linewidth=2,
                    label=f"pw={pw}",
                )
                ax.fill_between(x, lo, hi, color=color, alpha=0.08)

            # Title: top row gets "SFT type — Metric", other rows just SFT type
            if row == 0:
                title = f"{SFT_LABELS[sft_type]} — {metric_label}"
            else:
                title = f"{SFT_LABELS[sft_type]}" if col == 0 else None

            style_axis(
                ax,
                ylabel=metric_label if col == 0 else None,
                xlabel="Batch" if row == 3 else None,
                title=title,
            )

            if metric_key == "reward/correct":
                ax.set_ylim(-0.2, 1.1)
            else:
                ax.set_ylim(-0.05, 1.05)

    # Shared legend (from first panel that has all pw values)
    handles, labels = [], []
    for pw in PENALTY_WEIGHTS:
        handles.append(plt.Line2D(
            [0], [0], color=PW_COLORS[pw], linestyle=PW_STYLES[pw], linewidth=2,
        ))
        labels.append(f"pw={pw}")
    fig.legend(
        handles, labels, loc="upper center", fontsize=11, ncol=4,
        bbox_to_anchor=(0.5, 0.97),
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    path = OUT_DIR / output_name
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


# ── Plot 4: SFT comparison (compact) ────────────────────────────────────────

def plot_sft_comparison():
    """1x3 compact overview: all SFT types at pw=-0.5, both model sizes overlaid.

    solid=8B, dashed=32B. Seed-averaged with bands.
    """
    pw = -0.5
    window = 20
    size_styles = {"8b": "-", "32b": "--"}

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle(
        "V7 GRPO — SFT Comparison at pw=-0.5 (8B solid, 32B dashed)",
        fontsize=14, y=1.02,
    )

    for col, (metric_key, metric_label) in enumerate(METRICS):
        ax = axes[col]

        for sft_type in SFT_ORDER:
            for size in MODEL_SIZES:
                result = get_seed_averaged(sft_type, size, pw, metric_key, window)
                if result is None:
                    continue
                x, mean, lo, hi = result
                color = SFT_COLORS[sft_type]
                ls = size_styles[size]
                label = f"{SFT_LABELS[sft_type]} {size.upper()}"
                ax.plot(x, mean, color=color, linestyle=ls, linewidth=2, label=label)
                ax.fill_between(x, lo, hi, color=color, alpha=0.08)

        style_axis(ax, ylabel=metric_label, xlabel="Batch", title=metric_label)
        if metric_key == "reward/correct":
            ax.set_ylim(-0.2, 1.1)
        else:
            ax.set_ylim(-0.05, 1.05)

    # Build legend with both SFT color and size linestyle info
    handles, labels = [], []
    for sft_type in SFT_ORDER:
        for size in MODEL_SIZES:
            h = plt.Line2D(
                [0], [0],
                color=SFT_COLORS[sft_type],
                linestyle=size_styles[size],
                linewidth=2,
            )
            handles.append(h)
            labels.append(f"{SFT_LABELS[sft_type]} {size.upper()}")
    fig.legend(
        handles, labels, loc="upper center", fontsize=9, ncol=4,
        bbox_to_anchor=(0.5, 0.99),
    )

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    path = OUT_DIR / "v7_sft_comparison.png"
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Plot 1: All conditions overview ===")
    plot_all_conditions_overview()

    print("\n=== Plot 2: Penalty sweep (8B) ===")
    plot_penalty_sweep("8b", "v7_penalty_sweep.png")

    print("\n=== Plot 3: Penalty sweep (32B) ===")
    plot_penalty_sweep("32b", "v7_penalty_sweep_32b.png")

    print("\n=== Plot 4: SFT comparison ===")
    plot_sft_comparison()

    print("\nDone.")
