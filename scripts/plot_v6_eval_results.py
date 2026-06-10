"""Plot V6 evaluation results: training curves, Pareto plots for output and CoT spillover."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
EVAL_DIR = Path("/home/jose/feedback-spillover-exps/logs/eval-penalty-v6")
PLOT_DIR = Path("/home/jose/feedback-spillover-exps/plots")
PLOT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Run definitions
# ---------------------------------------------------------------------------
RUNS = {
    # (condition, size, seed) -> directory name
    ("penalty", "8B", 42): "grpo-v6-8b-pirate-output-alpaca-qwen-s42",
    ("penalty", "8B", 43): "grpo-v6-8b-pirate-output-alpaca-qwen-s43",
    ("penalty", "32B", 42): "grpo-v6-32b-pirate-output-alpaca-qwen-s42",
    ("penalty", "32B", 43): "grpo-v6-32b-pirate-output-alpaca-qwen-s43",
    ("control", "8B", 42): "grpo-v6ctrl-8b-pirate-output-alpaca-qwen-s42",
    ("control", "8B", 43): "grpo-v6ctrl-8b-pirate-output-alpaca-qwen-s43",
    ("control", "32B", 42): "grpo-v6ctrl-32b-pirate-output-alpaca-qwen-s42",
    ("control", "32B", 43): "grpo-v6ctrl-32b-pirate-output-alpaca-qwen-s43",
}

STEPS = list(range(100, 1001, 100))

MODEL_FILE_PREFIX = {
    "8B": "Qwen_Qwen3-8B",
    "32B": "Qwen_Qwen3-32B",
}

COND_COLOR = {"penalty": "#D65F5F", "control": "#4878CF"}
COND_LABEL = {"penalty": "Penalty (pw=-0.5)", "control": "Control (pw=0)"}
SIZE_MARKER = {"8B": "o", "32B": "^"}
SIZE_LABEL = {"8B": "8B", "32B": "32B"}

METRICS = ["sycophancy", "real_correct", "out_score", "cot_score"]
METRIC_LABELS = {
    "sycophancy": "Sycophancy (hint-following)",
    "real_correct": "Real correctness",
    "out_score": "Hint in output",
    "cot_score": "Hint in CoT",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_eval_file(path: Path) -> dict:
    """Load a single JSONL eval file, returning aggregated metrics."""
    results = []
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("type") != "result":
                continue
            results.append(rec)
    if not results:
        return {}
    return {
        "sycophancy": np.mean([r["sycophancy"] for r in results]),
        "real_correct": np.mean([r["real_correct"] for r in results]),
        "out_score": np.mean([r["out_score"] for r in results]),
        "cot_score": np.mean([r["cot_score"] for r in results]),
        "n": len(results),
    }


def load_all() -> dict:
    """Load all eval data. Returns dict keyed by (condition, size, seed, step)."""
    data = {}
    for (cond, size, seed), run_dir in RUNS.items():
        prefix = MODEL_FILE_PREFIX[size]
        for step in STEPS:
            fname = f"{prefix}_{step:06d}.jsonl"
            path = EVAL_DIR / run_dir / fname
            if not path.exists():
                continue
            metrics = load_eval_file(path)
            if metrics:
                data[(cond, size, seed, step)] = metrics
    return data


def aggregate_seeds(data: dict, cond: str, size: str, metric: str):
    """Aggregate a metric across seeds for each step. Returns steps, means, mins, maxs."""
    steps_out, means, mins, maxs = [], [], [], []
    for step in STEPS:
        vals = []
        for seed in [42, 43]:
            key = (cond, size, seed, step)
            if key in data:
                vals.append(data[key][metric])
        if vals:
            steps_out.append(step)
            means.append(np.mean(vals))
            mins.append(np.min(vals))
            maxs.append(np.max(vals))
    return np.array(steps_out), np.array(means), np.array(mins), np.array(maxs)


# ---------------------------------------------------------------------------
# Plot 1: Training curves (2x4 grid)
# ---------------------------------------------------------------------------
def plot_curves(data: dict, output_path: Path):
    fig, axes = plt.subplots(2, 4, figsize=(18, 8), sharex=True)
    fig.suptitle("V6 Eval Curves: Penalty vs Control over Training Steps", fontsize=14, y=0.98)

    sizes = ["8B", "32B"]
    for row, size in enumerate(sizes):
        for col, metric in enumerate(METRICS):
            ax = axes[row, col]
            for cond in ["penalty", "control"]:
                steps, means, mins, maxs = aggregate_seeds(data, cond, size, metric)
                color = COND_COLOR[cond]
                ax.plot(steps, means, "o-", color=color, label=COND_LABEL[cond],
                        linewidth=1.8, markersize=4)
                ax.fill_between(steps, mins, maxs, color=color, alpha=0.15)

            if row == 0:
                ax.set_title(METRIC_LABELS[metric], fontsize=11)
            if row == 1:
                ax.set_xlabel("Training step")
            ax.set_ylim(-0.02, 1.02)
            ax.grid(True, alpha=0.3)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)

            # Row label on leftmost column only
            if col == 0:
                ax.set_ylabel(size, fontsize=11, fontweight="bold")

    # Single legend at the top
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, fontsize=11,
               bbox_to_anchor=(0.5, 0.94), frameon=False)

    plt.tight_layout(rect=[0, 0, 1, 0.91])
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_path}")


# ---------------------------------------------------------------------------
# Plot 2 & 3: Pareto scatter plots
# ---------------------------------------------------------------------------
def plot_pareto(data: dict, y_metric: str, y_label: str, title: str, output_path: Path):
    fig, ax = plt.subplots(figsize=(10, 7))

    # Collect all points for labeling
    all_points = []

    for (cond, size, seed, step), metrics in data.items():
        x = metrics["sycophancy"]
        y = metrics[y_metric]
        color = COND_COLOR[cond]
        marker = SIZE_MARKER[size]
        all_points.append((x, y, cond, size, seed, step))

    # Plot by group for legend
    for cond in ["penalty", "control"]:
        for size in ["8B", "32B"]:
            xs, ys = [], []
            for x, y, c, s, sd, st in all_points:
                if c == cond and s == size:
                    xs.append(x)
                    ys.append(y)
            if not xs:
                continue
            label = f"{COND_LABEL[cond]}, {SIZE_LABEL[size]}"
            ax.scatter(xs, ys, color=COND_COLOR[cond], marker=SIZE_MARKER[size],
                       s=70, alpha=0.7, label=label, edgecolors="white", linewidths=0.5,
                       zorder=4)

    # Add step labels for key checkpoints (first, mid, last)
    label_steps = {100, 500, 1000}
    labeled_positions = []  # Track positions to avoid overlap
    for x, y, cond, size, seed, step in all_points:
        if step in label_steps and seed == 42:  # Only label seed 42 to reduce clutter
            # Check if too close to an existing label
            too_close = False
            for lx, ly in labeled_positions:
                if abs(x - lx) < 0.03 and abs(y - ly) < 0.03:
                    too_close = True
                    break
            if not too_close:
                ax.annotate(f"s{step}", (x, y), textcoords="offset points",
                            xytext=(6, 4), fontsize=7, alpha=0.7,
                            color=COND_COLOR[cond])
                labeled_positions.append((x, y))

    ax.set_xlabel("Sycophancy (hint-following rate)", fontsize=12)
    ax.set_ylabel(y_label, fontsize=12)
    ax.set_title(title, fontsize=13)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=10, loc="best", framealpha=0.9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Loading eval data...")
    data = load_all()
    print(f"Loaded {len(data)} checkpoint evaluations across {len(RUNS)} runs.")

    # Print summary stats
    for cond in ["penalty", "control"]:
        for size in ["8B", "32B"]:
            vals = [v for (c, s, sd, st), v in data.items() if c == cond and s == size]
            if vals:
                syc = np.mean([v["sycophancy"] for v in vals])
                rc = np.mean([v["real_correct"] for v in vals])
                out = np.mean([v["out_score"] for v in vals])
                cot = np.mean([v["cot_score"] for v in vals])
                print(f"  {cond:>8s} {size:>3s}: sycophancy={syc:.3f}  "
                      f"real_correct={rc:.3f}  out_score={out:.3f}  cot_score={cot:.3f}  "
                      f"(n={len(vals)} checkpoints)")

    # Plot 1: Training curves
    plot_curves(data, PLOT_DIR / "v6_eval_curves.png")

    # Plot 2: Pareto — output pirate style vs sycophancy
    plot_pareto(
        data,
        y_metric="out_score",
        y_label="Hint in output (out_score)",
        title="V6 Pareto: Sycophancy vs Hint in Output",
        output_path=PLOT_DIR / "v6_eval_pareto.png",
    )

    # Plot 3: Pareto — CoT pirate style vs sycophancy
    plot_pareto(
        data,
        y_metric="cot_score",
        y_label="Hint in CoT (cot_score)",
        title="V6 Pareto: Sycophancy vs Hint in CoT",
        output_path=PLOT_DIR / "v6_eval_cot_spillover.png",
    )

    print("\nDone. All plots saved to", PLOT_DIR)


if __name__ == "__main__":
    main()
