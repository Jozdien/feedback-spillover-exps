"""Plot evaluation results from penalty RL runs.

Reads summary lines from all eval files and generates:
1. Spillover curves: hint_in_output and hint_in_cot over training steps
2. Pareto plots: hint_in_cot vs hint_in_output across conditions
3. Condition comparison at final checkpoint
"""

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

EVAL_DIR = Path("logs/eval-penalty")
PLOT_DIR = Path("plots")
PLOT_DIR.mkdir(exist_ok=True)

CONDITIONS = ["pirate-output", "pirate-cot", "normal"]
SOURCES = ["qwen", "haiku"]
SEEDS = [42, 43]
SIZES = ["8b", "32b"]
STEPS = [100, 200, 300, 400, 500, 600, 700, 800, 900, "final"]

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
                    run_name = f"grpo-{size}-{cond}-{src}-s{seed}"
                    run_dir = EVAL_DIR / run_name
                    if not run_dir.exists():
                        continue
                    for f in sorted(run_dir.glob("*.jsonl")):
                        ckpt_name = f.stem.split("_")[-1]
                        step = int(ckpt_name) if ckpt_name.isdigit() else 1000
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


def plot_spillover_curves(results):
    """Training curves: hint_in_output and hint_in_cot over steps, by condition and model size."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharey="row")

    for col, cond in enumerate(CONDITIONS):
        for row, size in enumerate(SIZES):
            ax = axes[row, col]
            agg = aggregate(
                [r for r in results if r["condition"] == cond and r["size"] == size],
                ["step"],
            )
            steps_sorted = sorted(agg.keys())
            steps_x = [s[0] for s in steps_sorted]
            out_means = [agg[s]["hint_in_output_mean"] for s in steps_sorted]
            out_stds = [agg[s]["hint_in_output_std"] for s in steps_sorted]
            cot_means = [agg[s]["hint_in_cot_mean"] for s in steps_sorted]
            cot_stds = [agg[s]["hint_in_cot_std"] for s in steps_sorted]

            ax.plot(steps_x, out_means, "o-", color="#e74c3c", label="Hint in Output", linewidth=2)
            ax.fill_between(steps_x,
                            np.array(out_means) - np.array(out_stds),
                            np.array(out_means) + np.array(out_stds),
                            color="#e74c3c", alpha=0.15)
            ax.plot(steps_x, cot_means, "s-", color="#3498db", label="Hint in CoT", linewidth=2)
            ax.fill_between(steps_x,
                            np.array(cot_means) - np.array(cot_stds),
                            np.array(cot_means) + np.array(cot_stds),
                            color="#3498db", alpha=0.15)
            ax.set_title(f"{COND_LABELS[cond]} — {size.upper()}", fontsize=12, fontweight="bold")
            ax.set_xlabel("Training Step")
            if col == 0:
                ax.set_ylabel("Score")
            ax.legend(fontsize=9)
            ax.set_ylim(-0.05, 1.05)
            ax.grid(True, alpha=0.3)

    fig.suptitle("Output Penalty Spillover into CoT Over Training", fontsize=15, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(PLOT_DIR / "spillover_curves.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {PLOT_DIR / 'spillover_curves.png'}")


def plot_spillover_by_source(results):
    """Same as above but split by data source (qwen vs haiku)."""
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

    fig.suptitle("Spillover by Data Source (solid=Qwen, dashed=Haiku)", fontsize=15, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(PLOT_DIR / "spillover_by_source.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {PLOT_DIR / 'spillover_by_source.png'}")


def plot_pareto(results):
    """Pareto trajectory: CoT detection (x) vs training reward (y), arrow from first to last step."""
    penalty_weight = -2.0
    N = 378

    SOURCE_MARKERS = {"qwen": "o", "haiku": "s"}
    SOURCE_LABELS = {"qwen": "Qwen", "haiku": "Haiku"}

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))

    for idx, size in enumerate(SIZES):
        ax = axes[idx]

        for cond in CONDITIONS:
            for src in SOURCES:
                agg = aggregate(
                    [r for r in results if r["condition"] == cond and r["size"] == size and r["source"] == src],
                    ["step"],
                )
                if not agg:
                    continue

                steps_sorted = sorted(agg.keys())
                x = [agg[s]["hint_in_cot_mean"] for s in steps_sorted]
                y = [agg[s]["sycophancy_mean"] + penalty_weight * agg[s]["hint_in_output_mean"]
                     for s in steps_sorted]

                color = COND_COLORS[cond]
                marker = SOURCE_MARKERS[src]
                label = f"{COND_LABELS[cond]} ({SOURCE_LABELS[src]})"

                x_err = [1.96 * np.sqrt(p * (1 - p) / N) for p in x]
                syc = [agg[s]["sycophancy_mean"] for s in steps_sorted]
                oh = [agg[s]["hint_in_output_mean"] for s in steps_sorted]
                y_err = [
                    1.96 * np.sqrt(s * (1 - s) / N + penalty_weight**2 * o * (1 - o) / N)
                    for s, o in zip(syc, oh)
                ]

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
                    slabel = f"step {step_labels[i]}" if step_labels[i] != 1000 else "final"
                    if i == 0:
                        slabel = f"step {step_labels[i]}"
                    ax.annotate(
                        slabel, (x[i], y[i]),
                        xytext=(x[i] + 0.01, y[i] + 0.02),
                        fontsize=7, color=color, alpha=0.7,
                    )

                ax.annotate(
                    "", xy=(x[-1], y[-1]), xytext=(x[0], y[0]),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=1.5, mutation_scale=12, alpha=0.4),
                )

        ax.set_xlabel("CoT hint detection rate (spillover measure)", fontsize=12)
        ax.set_ylabel("Training reward (sycophancy - 2 * out_hint)", fontsize=12)
        ax.set_title(f"Qwen3-{size.upper()}", fontsize=13, fontweight="bold")
        ax.axhline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
        ax.legend(fontsize=8, loc="best", frameon=True, framealpha=0.9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(alpha=0.2, linewidth=0.5)

    fig.suptitle("Output Penalty Spillover: CoT Detection vs Reward", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "pareto_cot_vs_output.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {PLOT_DIR / 'pareto_cot_vs_output.png'}")


def plot_final_comparison(results):
    """Bar chart comparing conditions at the final checkpoint."""
    final = [r for r in results if r["step"] == 1000]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    for idx, size in enumerate(SIZES):
        ax = axes[idx]
        agg = aggregate(
            [r for r in final if r["size"] == size],
            ["condition"],
        )
        x = np.arange(len(CONDITIONS))
        width = 0.35
        out_vals = [agg.get((c,), {}).get("hint_in_output_mean", 0) for c in CONDITIONS]
        out_errs = [agg.get((c,), {}).get("hint_in_output_std", 0) for c in CONDITIONS]
        cot_vals = [agg.get((c,), {}).get("hint_in_cot_mean", 0) for c in CONDITIONS]
        cot_errs = [agg.get((c,), {}).get("hint_in_cot_std", 0) for c in CONDITIONS]

        bars1 = ax.bar(x - width / 2, out_vals, width, yerr=out_errs,
                        label="Hint in Output", color="#e74c3c", alpha=0.8, capsize=4)
        bars2 = ax.bar(x + width / 2, cot_vals, width, yerr=cot_errs,
                        label="Hint in CoT", color="#3498db", alpha=0.8, capsize=4)

        ax.set_xticks(x)
        ax.set_xticklabels([COND_LABELS[c] for c in CONDITIONS], fontsize=10)
        ax.set_ylabel("Score")
        ax.set_title(f"Qwen3-{size.upper()} — Final Checkpoint", fontsize=13, fontweight="bold")
        ax.legend(fontsize=10)
        ax.set_ylim(0, 1.0)
        ax.grid(True, alpha=0.3, axis="y")

    fig.suptitle("Final Hint Scores by SFT Condition", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "final_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {PLOT_DIR / 'final_comparison.png'}")


def plot_correctness_curves(results):
    """Real correctness over training steps."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for idx, size in enumerate(SIZES):
        ax = axes[idx]
        for cond in CONDITIONS:
            agg = aggregate(
                [r for r in results if r["condition"] == cond and r["size"] == size],
                ["step"],
            )
            steps_sorted = sorted(agg.keys())
            steps_x = [s[0] for s in steps_sorted]
            vals = [agg[s]["real_correct_mean"] for s in steps_sorted]
            ax.plot(steps_x, vals, "o-", color=COND_COLORS[cond],
                    label=COND_LABELS[cond], linewidth=2)

        ax.set_xlabel("Training Step")
        ax.set_ylabel("Real Correctness")
        ax.set_title(f"Qwen3-{size.upper()}", fontsize=13, fontweight="bold")
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)

    fig.suptitle("Real Correctness Over Training", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "correctness_curves.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {PLOT_DIR / 'correctness_curves.png'}")


def main():
    results = load_all_results()
    print(f"Loaded {len(results)} eval results")

    by_size = {}
    for r in results:
        by_size.setdefault(r["size"], []).append(r)
    for size, items in by_size.items():
        print(f"  {size}: {len(items)} results")

    plot_spillover_curves(results)
    plot_spillover_by_source(results)
    plot_pareto(results)
    plot_final_comparison(results)
    plot_correctness_curves(results)
    print("\nAll plots saved to plots/")


if __name__ == "__main__":
    main()
