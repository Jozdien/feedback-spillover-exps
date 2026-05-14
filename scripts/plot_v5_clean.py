"""Clean v5 Pareto plot: baselines + aggregated pirate region + highlighted best points."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.tri as mtri
import numpy as np
from scipy.spatial import ConvexHull

BASE = Path("/tmp/spillover-exps")

BASELINES = {
    "Control": ["paper-control", "v3-control-s43", "v3-control-s44"],
    "Penalty": ["v3-penalty", "v3-penalty-s43", "v3-penalty-s44"],
    "Reward Targeting": ["v3-reward-target", "v3-reward-target-s43", "v3-reward-target-s44"],
    "Mind & Face": ["mind-face", "v3-mind-face-s43", "v3-mind-face-s44"],
}

V5_STEPS_PER_EPOCH = 127
V5_PIRATE_STEPS = sorted([25, 41, 63] + [V5_STEPS_PER_EPOCH * e for e in range(1, 21)])

COLORS = {
    "Control": "#4878CF", "Penalty": "#D65F5F",
    "Reward Targeting": "#C4AD66", "Mind & Face": "#6ACC65",
}
MARKERS = {
    "Control": "o", "Penalty": "s", "Reward Targeting": "D", "Mind & Face": "^",
}
PIRATE_COLOR = "#6A0DAD"
PIRATE_CMAP = mcolors.LinearSegmentedColormap.from_list("pirate", ["#E8D5F5", "#6A0DAD"])


def load_final(run_dir, window=50):
    path = BASE / run_dir / "metrics.jsonl"
    lines = [json.loads(l) for l in open(path)]
    last = lines[-window:]
    return {
        "correct": np.mean([l["reward/correct"] for l in last]),
        "hint_out": np.mean([l["monitor/hint_in_output"] for l in last]),
        "hint_cot": np.mean([l["monitor/hint_in_cot"] for l in last]),
    }


def get_available_steps():
    available = []
    for step in V5_PIRATE_STEPS:
        path = BASE / f"v5-pirate-step{step}" / "metrics.jsonl"
        if path.exists() and sum(1 for _ in open(path)) >= 266:
            available.append(step)
    return available


def draw_region(ax, xs, ys, values, cmap, border_color, alpha=0.35):
    """Draw a gradient-shaded region using Delaunay triangulation of the points.
    values is a per-point scalar (e.g. epoch) used for the gradient color."""
    pts = np.column_stack([xs, ys])
    if len(pts) < 3:
        return
    tri = mtri.Triangulation(xs, ys)
    ax.tripcolor(tri, values, cmap=cmap, shading="gouraud", alpha=alpha, zorder=2,
                 rasterized=True)
    # Outer hull border
    hull = ConvexHull(pts)
    poly = pts[hull.vertices]
    ax.plot(np.append(poly[:, 0], poly[0, 0]), np.append(poly[:, 1], poly[0, 1]),
            color=border_color, alpha=0.5, linewidth=1, zorder=3)


def plot_pareto_and_trajectory(output_path, show_region=True):
    fig = plt.figure(figsize=(14, 9))
    gs = fig.add_gridspec(2, 2, height_ratios=[2, 1], hspace=0.35, wspace=0.25)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])

    fig.suptitle("Pirate Output SFT (Qwen data) — Qwen3-8B LoRA, MMLU QA", fontsize=13, y=0.96)

    # Baselines
    for name, runs in BASELINES.items():
        finals = [load_final(r) for r in runs]
        cot_mean = np.mean([f["hint_cot"] for f in finals])
        cot_se = np.std([f["hint_cot"] for f in finals], ddof=1) / np.sqrt(len(finals))
        cor_mean = np.mean([f["correct"] for f in finals])
        cor_se = np.std([f["correct"] for f in finals], ddof=1) / np.sqrt(len(finals))
        full = [f["correct"] - 2 * f["hint_out"] for f in finals]
        full_mean = np.mean(full)
        full_se = np.std(full, ddof=1) / np.sqrt(len(finals))

        kw = dict(color=COLORS[name], marker=MARKERS[name], s=80, zorder=5, label=name)
        ax1.scatter(cot_mean, cor_mean, **kw)
        ax1.errorbar(cot_mean, cor_mean, xerr=cot_se, yerr=cor_se,
                     color=COLORS[name], fmt="none", capsize=3, zorder=4)
        ax2.scatter(cot_mean, full_mean, **kw)
        ax2.errorbar(cot_mean, full_mean, xerr=cot_se, yerr=full_se,
                     color=COLORS[name], fmt="none", capsize=3, zorder=4)

    # Pirate aggregation
    steps = get_available_steps()
    finals = [(s, load_final(f"v5-pirate-step{s}")) for s in steps]
    epochs = np.array([s / V5_STEPS_PER_EPOCH for s, _ in finals])
    cots = np.array([f["hint_cot"] for _, f in finals])
    cors = np.array([f["correct"] for _, f in finals])
    fulls = np.array([f["correct"] - 2 * f["hint_out"] for _, f in finals])

    if show_region:
        # Gradient-shaded regions (colored by epoch)
        draw_region(ax1, cots, cors, epochs, PIRATE_CMAP, PIRATE_COLOR)
        draw_region(ax2, cots, fulls, epochs, PIRATE_CMAP, PIRATE_COLOR)

        # Mean point
        ax1.scatter(cots.mean(), cors.mean(), color=PIRATE_COLOR, marker="P", s=100, zorder=6,
                    edgecolors="black", linewidths=0.5, label=f"Pirate SFT (mean, n={len(steps)})")
        ax2.scatter(cots.mean(), fulls.mean(), color=PIRATE_COLOR, marker="P", s=100, zorder=6,
                    edgecolors="black", linewidths=0.5, label=f"Pirate SFT (mean, n={len(steps)})")

    # Highlighted points: least spillover = highest hint_cot, best correctness, and final epoch
    idx_high_cot = int(np.argmax(cots))
    idx_high_cor = int(np.argmax(cors))
    idx_final = int(np.argmax(epochs))
    low_sp_label = f"Least spillover (ep {epochs[idx_high_cot]:.0f})"
    best_cor_label = f"Best correctness (ep {epochs[idx_high_cor]:.0f})"
    final_label = f"Final epoch (ep {epochs[idx_final]:.0f})"

    star_kw = dict(marker="*", s=250, zorder=7, edgecolors="black", linewidths=0.8)
    for ax, ys in [(ax1, cors), (ax2, fulls)]:
        ax.scatter(cots[idx_high_cot], ys[idx_high_cot], color="#FFD700", label=low_sp_label, **star_kw)
        ax.scatter(cots[idx_high_cor], ys[idx_high_cor], color="#00CED1", label=best_cor_label, **star_kw)
        ax.scatter(cots[idx_final], ys[idx_final], color="#FF6B6B", label=final_label, **star_kw)

    for ax, ylabel in [(ax1, "Task reward (correctness)"), (ax2, "Full reward (R_task − 2·R_hint)")]:
        ax.set_xlabel("CoT monitor detection rate")
        ax.set_ylabel(ylabel)
        ax.legend(fontsize=8, loc="best")
        ax.set_xlim(0, 1)
        ax.grid(True, alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    ax1.set_ylim(0, 1)
    ax2.set_ylim(-1, 1)
    ax2.axhline(0, color="black", linewidth=0.8)

    # Trajectory plot: hint_cot, correctness, hint_out vs epoch
    order = np.argsort(epochs)
    eps_sorted = epochs[order]
    cots_sorted = cots[order]
    cors_sorted = cors[order]
    hint_outs = np.array([f["hint_out"] for _, f in finals])[order]

    ax3.plot(eps_sorted, cots_sorted, "o-", color="#D65F5F", label="CoT hint detection", linewidth=1.5, markersize=5)
    ax3.plot(eps_sorted, cors_sorted, "s-", color="#4878CF", label="Correctness", linewidth=1.5, markersize=5)
    ax3.plot(eps_sorted, hint_outs, "^-", color="#6ACC65", label="Output hint rate", linewidth=1.5, markersize=5)

    # Mark the two special points on the trajectory
    ax3.axvline(epochs[idx_high_cot], color="#FFD700", linestyle="--", alpha=0.6, linewidth=1)
    ax3.axvline(epochs[idx_high_cor], color="#00CED1", linestyle="--", alpha=0.6, linewidth=1)

    ax3.set_xlabel("Pirate SFT epoch")
    ax3.set_ylabel("Rate")
    ax3.set_title("Metric trajectory across pirate SFT epochs (final 50-batch window of each RL run)")
    ax3.set_ylim(0, 1)
    ax3.set_xlim(0, max(epochs) * 1.02)
    ax3.legend(fontsize=9, loc="best")
    ax3.grid(True, alpha=0.3)
    ax3.spines["top"].set_visible(False)
    ax3.spines["right"].set_visible(False)

    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_path}")

    print(f"\nPirate stats across {len(steps)} epochs:")
    print(f"  hint_cot: mean={cots.mean():.3f} std={cots.std():.3f} min={cots.min():.3f} max={cots.max():.3f}")
    print(f"  correct:  mean={cors.mean():.3f} std={cors.std():.3f} min={cors.min():.3f} max={cors.max():.3f}")
    print(f"  Least spillover (highest hint_cot): epoch {epochs[idx_high_cot]:.1f}  (hint_cot={cots[idx_high_cot]:.3f}, correct={cors[idx_high_cot]:.3f})")
    print(f"  Best correctness:                    epoch {epochs[idx_high_cor]:.1f}  (hint_cot={cots[idx_high_cor]:.3f}, correct={cors[idx_high_cor]:.3f})")


def spillover_ratio(run_dir, early_n=5, late_n=50):
    lines = [json.loads(l) for l in open(BASE / run_dir / "metrics.jsonl")]
    early_out = np.mean([l["monitor/hint_in_output"] for l in lines[:early_n]])
    late_out = np.mean([l["monitor/hint_in_output"] for l in lines[-late_n:]])
    early_cot = np.mean([l["monitor/hint_in_cot"] for l in lines[:early_n]])
    late_cot = np.mean([l["monitor/hint_in_cot"] for l in lines[-late_n:]])
    d_out = early_out - late_out
    if abs(d_out) < 1e-6:
        return float("nan")
    return (early_cot - late_cot) / d_out


def plot_spillover_scaling(output_path, early_n=5, late_n=50, title_suffix=""):
    steps = get_available_steps()
    finals = [(s, load_final(f"v5-pirate-step{s}")) for s in steps]
    epochs = np.array([s / V5_STEPS_PER_EPOCH for s, _ in finals])
    cots = np.array([f["hint_cot"] for _, f in finals])
    cors = np.array([f["correct"] for _, f in finals])
    hint_outs = np.array([f["hint_out"] for _, f in finals])
    ratios = np.array([spillover_ratio(f"v5-pirate-step{s}", early_n, late_n) for s in steps])

    order = np.argsort(epochs)
    eps = epochs[order]

    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.plot(eps, cots[order], "o-", color="#D65F5F", alpha=0.35,
            label="CoT hint detection", linewidth=1, markersize=4)
    ax.plot(eps, cors[order], "s-", color="#4878CF", alpha=0.35,
            label="Correctness", linewidth=1, markersize=4)
    ax.plot(eps, hint_outs[order], "^-", color="#6ACC65", alpha=0.35,
            label="Output hint rate", linewidth=1, markersize=4)
    ax.plot(eps, ratios[order], "D-", color="#6A0DAD",
            label="Spillover ratio  Δ_cot / Δ_out", linewidth=2.5, markersize=7,
            zorder=5)

    ax.axhline(0, color="black", linewidth=0.6, alpha=0.5)
    ax.axhline(1, color="black", linewidth=0.4, linestyle=":", alpha=0.4)

    # Mark values outside y-limits
    y_max, y_min = 1.5, -0.5
    for e, r in zip(eps, ratios[order]):
        if r > y_max:
            ax.annotate(f"{r:.1f}", (e, y_max), textcoords="offset points",
                        xytext=(4, -2), fontsize=8, color="#6A0DAD", ha="left", va="top")
        elif r < y_min:
            ax.annotate(f"{r:.1f}", (e, y_min), textcoords="offset points",
                        xytext=(4, 2), fontsize=8, color="#6A0DAD", ha="left", va="bottom")

    ax.set_xlabel("Pirate SFT epoch")
    ax.set_ylabel("Value")
    title = f"Spillover scaling with pirate SFT (Qwen data){title_suffix} — Qwen3-8B LoRA, MMLU QA"
    ax.set_title(title)
    ax.set_xlim(0, max(eps) * 1.02)
    ax.set_ylim(y_min, y_max)
    ax.legend(fontsize=9, loc="best")
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_path}")

    valid = ratios[~np.isnan(ratios)]
    print(f"  Spillover ratio: mean={np.mean(valid):.3f} "
          f"min={np.min(valid):.3f} max={np.max(valid):.3f}  "
          f"(early={early_n} batches, late={late_n} batches)")


if __name__ == "__main__":
    out = Path("/home/jose/feedback-spillover-exps")
    plot_pareto_and_trajectory(out / "v5_pirate_clean.png", show_region=True)
    plot_pareto_and_trajectory(out / "v5_pirate_stars_only.png", show_region=False)
    plot_spillover_scaling(out / "v5_spillover_scaling.png",
                           early_n=5, late_n=50, title_suffix=" [early=batches 0-4]")
    plot_spillover_scaling(out / "v5_spillover_scaling_b0.png",
                           early_n=1, late_n=50, title_suffix=" [early=batch 0 only]")
