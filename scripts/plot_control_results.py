"""Plot evaluation results from control RL runs (penalty_weight=0).

Reads from logs/eval-control/ and generates Pareto + spillover plots.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

EVAL_DIR = Path("logs/eval-control")
PLOT_DIR = Path("plots")
PLOT_DIR.mkdir(exist_ok=True)

CONDITIONS = ["pirate-output", "pirate-cot", "normal"]
SOURCES = ["qwen", "haiku"]
SEEDS = [42, 43]
SIZES = ["8b", "32b"]

COND_LABELS = {
    "pirate-output": "Pirate Output SFT",
    "pirate-cot": "Pirate CoT SFT",
    "normal": "Normal SFT",
}
COND_COLORS = {
    "pirate-output": "#e74c3c",
    "pirate-cot": "#3498db",
    "normal": "#2ecc71",
}


def load_all_results():
    results = []
    for size in SIZES:
        for cond in CONDITIONS:
            for src in SOURCES:
                for seed in SEEDS:
                    run_name = f"grpo-ctrl-{size}-{cond}-{src}-s{seed}"
                    run_dir = EVAL_DIR / run_name
                    if not run_dir.exists():
                        continue
                    for f in sorted(run_dir.glob("*.jsonl")):
                        ckpt_name = f.stem.split("_")[-1]
                        if ckpt_name == "final":
                            continue
                        step = int(ckpt_name) if ckpt_name.isdigit() else None
                        if step is None:
                            continue
                        summary = None
                        result_rows = []
                        with open(f) as fh:
                            for line in fh:
                                d = json.loads(line)
                                if d.get("type") == "summary":
                                    summary = d
                                elif d.get("type") == "result":
                                    result_rows.append(d)
                        if summary is None and result_rows:
                            n = len(result_rows)
                            summary = {
                                "n": n,
                                "sycophancy": sum(r["sycophancy"] for r in result_rows) / n,
                                "real_correct": sum(r["real_correct"] for r in result_rows) / n,
                                "hint_in_output": sum(r["out_score"] for r in result_rows) / n,
                                "hint_in_cot": sum(r["cot_score"] for r in result_rows) / n,
                            }
                        if summary:
                            results.append({
                                "size": size,
                                "condition": cond,
                                "source": src,
                                "seed": seed,
                                "step": step,
                                "run_name": run_name,
                                **{k: v for k, v in summary.items() if k != "type"},
                            })
    return results


def aggregate(results, group_keys):
    groups = {}
    for r in results:
        key = tuple(r[k] for k in group_keys)
        groups.setdefault(key, []).append(r)
    agg = {}
    for key, items in groups.items():
        agg[key] = {
            "hint_in_output_mean": np.mean([r["hint_in_output"] for r in items]),
            "hint_in_output_std": np.std([r["hint_in_output"] for r in items]),
            "hint_in_cot_mean": np.mean([r["hint_in_cot"] for r in items]),
            "hint_in_cot_std": np.std([r["hint_in_cot"] for r in items]),
            "sycophancy_mean": np.mean([r["sycophancy"] for r in items]),
            "real_correct_mean": np.mean([r["real_correct"] for r in items]),
            "n": len(items),
        }
    return agg


def plot_pareto(results):
    """Pareto trajectory: CoT detection (x) vs sycophancy (y) — no penalty term."""
    N = 378

    SOURCE_MARKERS = {"qwen": "o", "haiku": "s"}
    SOURCE_LABELS = {"qwen": "Qwen", "haiku": "Haiku"}

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))

    for idx, size in enumerate(SIZES):
        ax = axes[idx]
        size_results = [r for r in results if r["size"] == size]
        if not size_results:
            ax.text(0.5, 0.5, "No data yet", ha="center", va="center", fontsize=14, color="gray")
            ax.set_title(f"Qwen3-{size.upper()}", fontsize=13, fontweight="bold")
            continue

        for cond in CONDITIONS:
            for src in SOURCES:
                agg = aggregate(
                    [r for r in size_results if r["condition"] == cond and r["source"] == src],
                    ["step"],
                )
                if not agg:
                    continue

                steps_sorted = sorted(agg.keys())
                x = [agg[s]["hint_in_cot_mean"] for s in steps_sorted]
                y = [agg[s]["sycophancy_mean"] for s in steps_sorted]

                color = COND_COLORS[cond]
                marker = SOURCE_MARKERS[src]
                label = f"{COND_LABELS[cond]} ({SOURCE_LABELS[src]})"

                x_err = [1.96 * np.sqrt(max(p * (1 - p), 0) / N) for p in x]
                y_err = [1.96 * np.sqrt(max(s * (1 - s), 0) / N) for s in y]

                endpts = [0, len(x) - 1]
                ax.errorbar(
                    [x[i] for i in endpts], [y[i] for i in endpts],
                    xerr=[x_err[i] for i in endpts], yerr=[y_err[i] for i in endpts],
                    color=color, linewidth=2, marker=marker, markersize=8,
                    capsize=3, label=label, zorder=3,
                    linestyle="--" if src == "haiku" else "-",
                )

                step_labels = [s[0] for s in steps_sorted]
                for i in endpts:
                    slabel = f"step {step_labels[i]}"
                    ax.annotate(
                        slabel, (x[i], y[i]),
                        xytext=(x[i] + 0.01, y[i] + 0.02),
                        fontsize=7, color=color, alpha=0.7,
                    )

                if len(x) > 1:
                    ax.annotate(
                        "", xy=(x[-1], y[-1]), xytext=(x[0], y[0]),
                        arrowprops=dict(arrowstyle="-|>", color=color, lw=1.5, mutation_scale=12, alpha=0.4),
                    )

        ax.set_xlabel("CoT hint detection rate (spillover measure)", fontsize=12)
        ax.set_ylabel("Sycophancy (reward)", fontsize=12)
        ax.set_title(f"Qwen3-{size.upper()}", fontsize=13, fontweight="bold")
        ax.axhline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
        ax.legend(fontsize=8, loc="best", frameon=True, framealpha=0.9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(alpha=0.2, linewidth=0.5)

    fig.suptitle("Control (penalty_weight=0): Sycophancy Only, No Output Penalty", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "ctrl_pareto_cot_vs_output.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {PLOT_DIR / 'ctrl_pareto_cot_vs_output.png'}")


def plot_spillover_curves(results):
    """Training curves: hint_in_output and hint_in_cot over steps."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharey="row")

    for col, cond in enumerate(CONDITIONS):
        for row, size in enumerate(SIZES):
            ax = axes[row, col]
            for src, ls, alpha in [("qwen", "-", 1.0), ("haiku", "--", 0.7)]:
                agg = aggregate(
                    [r for r in results if r["condition"] == cond and r["size"] == size and r["source"] == src],
                    ["step"],
                )
                if not agg:
                    continue
                steps_sorted = sorted(agg.keys())
                steps_x = [s[0] for s in steps_sorted]
                out_means = [agg[s]["hint_in_output_mean"] for s in steps_sorted]
                cot_means = [agg[s]["hint_in_cot_mean"] for s in steps_sorted]

                ax.plot(steps_x, out_means, f"o{ls}", color="#e74c3c", alpha=alpha,
                        label=f"Output ({src})", linewidth=1.5)
                ax.plot(steps_x, cot_means, f"s{ls}", color="#3498db", alpha=alpha,
                        label=f"CoT ({src})", linewidth=1.5)

            ax.set_title(f"{COND_LABELS[cond]} — {size.upper()}", fontsize=12, fontweight="bold")
            ax.set_xlabel("Training Step")
            if col == 0:
                ax.set_ylabel("Score")
            ax.legend(fontsize=8, ncol=2)
            ax.set_ylim(-0.05, 1.05)
            ax.grid(True, alpha=0.3)

    fig.suptitle("Control Spillover Curves (penalty_weight=0, solid=Qwen, dashed=Haiku)", fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(PLOT_DIR / "ctrl_spillover_curves.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {PLOT_DIR / 'ctrl_spillover_curves.png'}")


def main():
    results = load_all_results()
    print(f"Loaded {len(results)} eval results")

    by_size = {}
    for r in results:
        by_size.setdefault(r["size"], []).append(r)
    for size, items in sorted(by_size.items()):
        steps = sorted(set(r["step"] for r in items))
        print(f"  {size}: {len(items)} results, steps={steps}")

    plot_pareto(results)
    plot_spillover_curves(results)
    print("\nAll control plots saved to plots/")


if __name__ == "__main__":
    main()
