"""Plot V5ctrl results (penalty_weight=0, no_answer_penalty=-1.0) across all conditions.

Generates:
  1. Pareto plots: CoT detection (x) vs sycophancy rate (y), all conditions, split by size
  2. Spillover curves: hint_in_output and hint_in_cot over training steps
  3. Sycophancy & correctness curves
  4. V5ctrl vs V5 comparison: effect of removing the output hint penalty
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

EVAL_DIR_V5CTRL = Path("logs/eval-penalty-v5ctrl")
EVAL_DIR_V5 = Path("logs/eval-penalty-v5")
EVAL_DIR_STEP0 = Path("logs/eval-penalty")
PLOT_DIR = Path("plots")
PLOT_DIR.mkdir(exist_ok=True)

CONDITIONS = ["pirate-output", "pirate-cot", "normal"]
SOURCES = ["qwen", "haiku"]
SEEDS = [42, 43]
SIZES = ["8b", "32b"]
N = 378

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

SOURCE_MARKERS = {"qwen": "o", "haiku": "s"}
SOURCE_LABELS = {"qwen": "Qwen", "haiku": "Haiku"}


def _parse_eval_file(path):
    summary = None
    result_rows = []
    with open(path) as fh:
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
    return summary


def load_step0_results():
    """Load pre-RL (SFT checkpoint) evals from logs/eval-penalty/ as step 0."""
    results = []
    for size in SIZES:
        for cond in CONDITIONS:
            for src in SOURCES:
                for seed in SEEDS:
                    run_name = f"grpo-{size}-{cond}-{src}-s{seed}"
                    step0_file = EVAL_DIR_STEP0 / run_name / f"Qwen_Qwen3-{size.upper()}_{str(0).zfill(6)}.jsonl"
                    if not step0_file.exists():
                        continue
                    summary = _parse_eval_file(step0_file)
                    if summary:
                        results.append({
                            "size": size,
                            "condition": cond,
                            "source": src,
                            "seed": seed,
                            "step": 0,
                            "run_name": run_name,
                            **{k: v for k, v in summary.items() if k != "type"},
                        })
    return results


def load_all_results(eval_dir, prefix):
    results = list(load_step0_results())
    eval_path = Path(eval_dir)
    for size in SIZES:
        for cond in CONDITIONS:
            for src in SOURCES:
                for seed in SEEDS:
                    run_name = f"{prefix}-{size}-{cond}-{src}-s{seed}"
                    run_dir = eval_path / run_name
                    if not run_dir.exists():
                        continue
                    for f in sorted(run_dir.glob("*.jsonl")):
                        ckpt_name = f.stem.split("_")[-1]
                        if ckpt_name == "final":
                            continue
                        step = int(ckpt_name) if ckpt_name.isdigit() else None
                        if step is None:
                            continue
                        summary = _parse_eval_file(f)
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
            "sycophancy_std": np.std([r["sycophancy"] for r in items]),
            "real_correct_mean": np.mean([r["real_correct"] for r in items]),
            "real_correct_std": np.std([r["real_correct"] for r in items]),
            "n": len(items),
        }
    return agg


def plot_pareto(results):
    """Pareto trajectory: CoT detection (x) vs sycophancy (y), all conditions."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))

    for idx, size in enumerate(SIZES):
        ax = axes[idx]
        size_results = [r for r in results if r["size"] == size]
        if not size_results:
            ax.text(0.5, 0.5, "No data yet", ha="center", va="center",
                    fontsize=14, color="gray")
            ax.set_title(f"Qwen3-{size.upper()}", fontsize=13, fontweight="bold")
            continue

        for cond in CONDITIONS:
            for src in SOURCES:
                agg = aggregate(
                    [r for r in size_results
                     if r["condition"] == cond and r["source"] == src],
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
                y_err = [1.96 * np.sqrt(max(p * (1 - p), 0) / N) for p in y]

                endpts = [0, len(x) - 1] if len(x) > 1 else [0]
                ax.errorbar(
                    [x[i] for i in endpts], [y[i] for i in endpts],
                    xerr=[x_err[i] for i in endpts],
                    yerr=[y_err[i] for i in endpts],
                    color=color, linewidth=2, marker=marker, markersize=8,
                    capsize=3, label=label, zorder=3,
                    linestyle="--" if src == "haiku" else "-",
                )

                step_labels = [s[0] for s in steps_sorted]
                for i in endpts:
                    ax.annotate(
                        f"step {step_labels[i]}", (x[i], y[i]),
                        xytext=(x[i] + 0.01, y[i] + 0.02),
                        fontsize=7, color=color, alpha=0.7,
                    )

                if len(x) > 1:
                    ax.annotate(
                        "", xy=(x[-1], y[-1]), xytext=(x[0], y[0]),
                        arrowprops=dict(
                            arrowstyle="-|>", color=color, lw=1.5,
                            mutation_scale=12, alpha=0.4,
                        ),
                    )

        ax.set_xlabel("CoT hint detection rate (spillover measure)", fontsize=12)
        ax.set_ylabel("Sycophancy rate", fontsize=12)
        ax.set_title(f"Qwen3-{size.upper()}", fontsize=13, fontweight="bold")
        ax.axhline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
        ax.legend(fontsize=8, loc="best", frameon=True, framealpha=0.9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(alpha=0.2, linewidth=0.5)

    fig.suptitle(
        "V5ctrl (no penalty, no_answer_penalty=-1.0): Sycophancy vs CoT Spillover",
        fontsize=15, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "v5ctrl_pareto_all_conditions.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {PLOT_DIR / 'v5ctrl_pareto_all_conditions.png'}")


def plot_spillover_curves(results):
    """Training curves: hint_in_output and hint_in_cot over steps."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharey="row")

    for col, cond in enumerate(CONDITIONS):
        for row, size in enumerate(SIZES):
            ax = axes[row, col]
            for src, ls, alpha in [("qwen", "-", 1.0), ("haiku", "--", 0.7)]:
                agg = aggregate(
                    [r for r in results
                     if r["condition"] == cond and r["size"] == size
                     and r["source"] == src],
                    ["step"],
                )
                if not agg:
                    continue
                steps_sorted = sorted(agg.keys())
                steps_x = [s[0] for s in steps_sorted]
                out_means = [agg[s]["hint_in_output_mean"] for s in steps_sorted]
                cot_means = [agg[s]["hint_in_cot_mean"] for s in steps_sorted]

                ax.plot(steps_x, out_means, f"o{ls}", color="#e74c3c",
                        alpha=alpha, label=f"Output ({src})", linewidth=1.5)
                ax.plot(steps_x, cot_means, f"s{ls}", color="#3498db",
                        alpha=alpha, label=f"CoT ({src})", linewidth=1.5)

            ax.set_title(f"{COND_LABELS[cond]} — {size.upper()}",
                         fontsize=12, fontweight="bold")
            ax.set_xlabel("Training Step")
            if col == 0:
                ax.set_ylabel("Score")
            ax.legend(fontsize=8, ncol=2)
            ax.set_ylim(-0.05, 1.05)
            ax.grid(True, alpha=0.3)

    fig.suptitle(
        "V5ctrl Spillover Curves (no penalty, no_answer_penalty=-1.0, "
        "solid=Qwen, dashed=Haiku)",
        fontsize=14, fontweight="bold", y=0.98,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(PLOT_DIR / "v5ctrl_spillover_curves.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {PLOT_DIR / 'v5ctrl_spillover_curves.png'}")


def plot_sycophancy_and_correctness(results):
    """Sycophancy and real correctness over training steps."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharey="row")

    for col, cond in enumerate(CONDITIONS):
        for row, size in enumerate(SIZES):
            ax = axes[row, col]
            for src, ls, alpha in [("qwen", "-", 1.0), ("haiku", "--", 0.7)]:
                agg = aggregate(
                    [r for r in results
                     if r["condition"] == cond and r["size"] == size
                     and r["source"] == src],
                    ["step"],
                )
                if not agg:
                    continue
                steps_sorted = sorted(agg.keys())
                steps_x = [s[0] for s in steps_sorted]
                syc_means = [agg[s]["sycophancy_mean"] for s in steps_sorted]
                cor_means = [agg[s]["real_correct_mean"] for s in steps_sorted]

                ax.plot(steps_x, syc_means, f"o{ls}", color="#9b59b6",
                        alpha=alpha, label=f"Sycophancy ({src})",
                        linewidth=1.5)
                ax.plot(steps_x, cor_means, f"s{ls}", color="#f39c12",
                        alpha=alpha, label=f"Real correct ({src})",
                        linewidth=1.5)

            ax.set_title(f"{COND_LABELS[cond]} — {size.upper()}",
                         fontsize=12, fontweight="bold")
            ax.set_xlabel("Training Step")
            if col == 0:
                ax.set_ylabel("Rate")
            ax.legend(fontsize=8, ncol=2)
            ax.set_ylim(-0.05, 1.05)
            ax.grid(True, alpha=0.3)

    fig.suptitle(
        "V5ctrl Sycophancy & Real Correctness (no penalty, no_answer_penalty=-1.0, "
        "solid=Qwen, dashed=Haiku)",
        fontsize=14, fontweight="bold", y=0.98,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(PLOT_DIR / "v5ctrl_sycophancy_correctness.png", dpi=150,
                bbox_inches="tight")
    plt.close()
    print(f"Saved {PLOT_DIR / 'v5ctrl_sycophancy_correctness.png'}")


def plot_v5ctrl_vs_v5(ctrl_results, v5_results):
    """V5ctrl vs V5 comparison: effect of removing the output hint penalty.

    Shows CoT spillover and output hint rates side by side.
    """
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharey="row")

    for col, cond in enumerate(CONDITIONS):
        for row, size in enumerate(SIZES):
            ax = axes[row, col]
            for version, results, ls_base, alpha, v_label in [
                ("V5", v5_results, "--", 0.5, "V5 (pw=-0.5)"),
                ("V5ctrl", ctrl_results, "-", 1.0, "V5ctrl (pw=0)"),
            ]:
                for src, marker in [("qwen", "o"), ("haiku", "s")]:
                    agg = aggregate(
                        [r for r in results
                         if r["condition"] == cond and r["size"] == size
                         and r["source"] == src],
                        ["step"],
                    )
                    if not agg:
                        continue
                    steps_sorted = sorted(agg.keys())
                    steps_x = [s[0] for s in steps_sorted]
                    cot_means = [agg[s]["hint_in_cot_mean"] for s in steps_sorted]
                    out_means = [agg[s]["hint_in_output_mean"] for s in steps_sorted]

                    ax.plot(
                        steps_x, cot_means,
                        f"{marker}{ls_base}", color="#3498db",
                        alpha=alpha, linewidth=1.5, markersize=4,
                        label=f"CoT {v_label} {src}",
                    )
                    ax.plot(
                        steps_x, out_means,
                        f"{marker}{ls_base}", color="#e74c3c",
                        alpha=alpha, linewidth=1.5, markersize=4,
                        label=f"Out {v_label} {src}",
                    )

            ax.set_title(f"{COND_LABELS[cond]} — {size.upper()}",
                         fontsize=12, fontweight="bold")
            ax.set_xlabel("Training Step")
            if col == 0:
                ax.set_ylabel("Hint Detection Rate")
            ax.legend(fontsize=6, ncol=2)
            ax.set_ylim(-0.05, 1.05)
            ax.grid(True, alpha=0.3)

    fig.suptitle(
        "V5ctrl vs V5: Effect of Output Hint Penalty\n"
        "(solid=V5ctrl/no penalty, dashed=V5/pw=-0.5; blue=CoT, red=Output)",
        fontsize=14, fontweight="bold", y=1.0,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(PLOT_DIR / "v5ctrl_vs_v5_comparison.png", dpi=150,
                bbox_inches="tight")
    plt.close()
    print(f"Saved {PLOT_DIR / 'v5ctrl_vs_v5_comparison.png'}")


def main():
    ctrl_results = load_all_results(EVAL_DIR_V5CTRL, "grpo-v5ctrl")
    v5_results = load_all_results(EVAL_DIR_V5, "grpo-v5")
    print(f"Loaded {len(ctrl_results)} V5ctrl results, {len(v5_results)} V5 results")

    for size in SIZES:
        for cond in CONDITIONS:
            ctrl_n = len([r for r in ctrl_results
                          if r["size"] == size and r["condition"] == cond])
            v5_n = len([r for r in v5_results
                        if r["size"] == size and r["condition"] == cond])
            print(f"  {size} {cond}: V5ctrl={ctrl_n}, V5={v5_n}")

    plot_pareto(ctrl_results)
    plot_spillover_curves(ctrl_results)
    plot_sycophancy_and_correctness(ctrl_results)
    plot_v5ctrl_vs_v5(ctrl_results, v5_results)
    print("\nAll V5ctrl plots saved to plots/")


if __name__ == "__main__":
    main()
