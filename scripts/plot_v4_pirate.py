"""Plot v4 pirate SFT scaling results alongside baselines."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import numpy as np

BASE = Path("/tmp/spillover-exps")

BASELINES = {
    "Control": ["paper-control", "v3-control-s43", "v3-control-s44"],
    "Penalty": ["v3-penalty", "v3-penalty-s43", "v3-penalty-s44"],
    "Reward Targeting": ["v3-reward-target", "v3-reward-target-s43", "v3-reward-target-s44"],
    "Mind & Face": ["mind-face", "v3-mind-face-s43", "v3-mind-face-s44"],
}

V4_STEPS_PER_EPOCH = 175
V4_PIRATE_STEPS = sorted([35, 58, 87] + [V4_STEPS_PER_EPOCH * e for e in range(1, 21)])

V5_STEPS_PER_EPOCH = 127
V5_PIRATE_STEPS = sorted([25, 41, 63] + [V5_STEPS_PER_EPOCH * e for e in range(1, 21)])

COLORS = {
    "Control": "#4878CF",
    "Penalty": "#D65F5F",
    "Reward Targeting": "#C4AD66",
    "Mind & Face": "#6ACC65",
}
MARKERS = {
    "Control": "o", "Penalty": "s", "Reward Targeting": "D", "Mind & Face": "^",
}

PIRATE_CMAP_V4 = mcolors.LinearSegmentedColormap.from_list("pirate_v4", ["#E8D5F5", "#6A0DAD"])
PIRATE_CMAP_V5 = mcolors.LinearSegmentedColormap.from_list("pirate_v5", ["#D5E8F5", "#0D6AAD"])


def load_final(run_dir, window=50, max_lines=None):
    path = BASE / run_dir / "metrics.jsonl"
    lines = [json.loads(l) for l in open(path)]
    if max_lines:
        lines = lines[:max_lines]
    last = lines[-window:]
    return {
        "correct": np.mean([l["reward/correct"] for l in last]),
        "hint_out": np.mean([l["monitor/hint_in_output"] for l in last]),
        "hint_cot": np.mean([l["monitor/hint_in_cot"] for l in last]),
    }


def get_available_steps(prefix, step_list):
    available = []
    for step in step_list:
        path = BASE / f"{prefix}{step}" / "metrics.jsonl"
        if path.exists():
            n = sum(1 for _ in open(path))
            if n >= 266:
                available.append(step)
    return available


def add_gradient_colorbar(fig, ax, cmap, steps, steps_per_epoch, label, rect):
    cbar_ax = fig.add_axes(rect)
    norm = mcolors.Normalize(vmin=0, vmax=max(steps) / steps_per_epoch)
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
    cbar.set_label(label, fontsize=8)
    cbar.ax.tick_params(labelsize=7)


def plot_pareto(output_path, include_v4=True, include_v5=False):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 7))
    title = "Pirate Output SFT Scaling"
    if include_v4 and include_v5:
        title += " (Haiku vs Qwen data)"
    elif include_v5 and not include_v4:
        title += " (Qwen-generated data)"
    title += " — Qwen3-8B LoRA, MMLU QA"
    fig.suptitle(title, fontsize=13, y=0.98)

    for name, runs in BASELINES.items():
        finals = [load_final(r) for r in runs]
        cot_mean = np.mean([f["hint_cot"] for f in finals])
        cot_se = np.std([f["hint_cot"] for f in finals], ddof=1) / np.sqrt(len(finals))
        cor_mean = np.mean([f["correct"] for f in finals])
        cor_se = np.std([f["correct"] for f in finals], ddof=1) / np.sqrt(len(finals))
        full_rewards = [f["correct"] - 2 * f["hint_out"] for f in finals]
        full_mean = np.mean(full_rewards)
        full_se = np.std(full_rewards, ddof=1) / np.sqrt(len(finals))

        kw = dict(color=COLORS[name], marker=MARKERS[name], s=80, zorder=5, label=name)
        ax1.scatter(cot_mean, cor_mean, **kw)
        ax1.errorbar(cot_mean, cor_mean, xerr=cot_se, yerr=cor_se,
                     color=COLORS[name], fmt="none", capsize=3, zorder=4)
        ax2.scatter(cot_mean, full_mean, **kw)
        ax2.errorbar(cot_mean, full_mean, xerr=cot_se, yerr=full_se,
                     color=COLORS[name], fmt="none", capsize=3, zorder=4)

    # V4: Haiku-generated data
    v4_available = get_available_steps("v4-pirate-step", V4_PIRATE_STEPS) if include_v4 else []
    if v4_available:
        max_step = max(v4_available)
        for step in v4_available:
            max_lines = 266 if step == 58 else None
            f = load_final(f"v4-pirate-step{step}", max_lines=max_lines)
            t = step / max_step
            color = PIRATE_CMAP_V4(t)
            for ax, y_val in [(ax1, f["correct"]), (ax2, f["correct"] - 2 * f["hint_out"])]:
                ax.scatter(f["hint_cot"], y_val, color=color, marker="P", s=80,
                           zorder=5, edgecolors="black", linewidths=0.3)

    # V5: Qwen-generated data
    v5_available = get_available_steps("v5-pirate-step", V5_PIRATE_STEPS) if include_v5 else []
    if v5_available:
        max_step = max(v5_available)
        for step in v5_available:
            f = load_final(f"v5-pirate-step{step}")
            t = step / max_step
            color = PIRATE_CMAP_V5(t)
            for ax, y_val in [(ax1, f["correct"]), (ax2, f["correct"] - 2 * f["hint_out"])]:
                ax.scatter(f["hint_cot"], y_val, color=color, marker="H", s=80,
                           zorder=5, edgecolors="black", linewidths=0.3)

    for ax, ylabel in [(ax1, "Task reward (correctness)"), (ax2, "Full reward (R_task − 2·R_hint)")]:
        ax.set_xlabel("CoT monitor detection rate")
        ax.set_ylabel(ylabel)
        ax.legend(fontsize=8, loc="upper right")
        ax.set_xlim(0, 1)
        ax.grid(True, alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    ax1.set_ylim(0, 1)
    ax2.set_ylim(-1, 1)
    ax2.axhline(0, color="black", linewidth=0.8)

    plt.subplots_adjust(bottom=0.22)

    # Gradient colorbars below the plots
    if v4_available and v5_available:
        add_gradient_colorbar(fig, ax1, PIRATE_CMAP_V4, v4_available, V4_STEPS_PER_EPOCH,
                              "Pirate SFT epoch (Haiku data)", [0.15, 0.06, 0.3, 0.02])
        add_gradient_colorbar(fig, ax2, PIRATE_CMAP_V5, v5_available, V5_STEPS_PER_EPOCH,
                              "Pirate SFT epoch (Qwen data)", [0.55, 0.06, 0.3, 0.02])
    elif v4_available:
        add_gradient_colorbar(fig, ax1, PIRATE_CMAP_V4, v4_available, V4_STEPS_PER_EPOCH,
                              "Pirate SFT epoch", [0.35, 0.06, 0.3, 0.02])
    elif v5_available:
        add_gradient_colorbar(fig, ax1, PIRATE_CMAP_V5, v5_available, V5_STEPS_PER_EPOCH,
                              "Pirate SFT epoch", [0.35, 0.06, 0.3, 0.02])

    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_path}")

    print("\nV4 Pirate step results (Haiku data):")
    for step in v4_available:
        max_lines = 266 if step == 58 else None
        f = load_final(f"v4-pirate-step{step}", max_lines=max_lines)
        epoch = step / V4_STEPS_PER_EPOCH
        print(f"  epoch {epoch:5.1f} (step {step:4d}): "
              f"correct={f['correct']:.3f}  hint_out={f['hint_out']:.3f}  hint_cot={f['hint_cot']:.3f}")

    if v5_available:
        print("\nV5 Pirate step results (Qwen data):")
        for step in v5_available:
            f = load_final(f"v5-pirate-step{step}")
            epoch = step / V5_STEPS_PER_EPOCH
            print(f"  epoch {epoch:5.1f} (step {step:4d}): "
                  f"correct={f['correct']:.3f}  hint_out={f['hint_out']:.3f}  hint_cot={f['hint_cot']:.3f}")


if __name__ == "__main__":
    out = Path("/home/jose/feedback-spillover-exps")
    plot_pareto(out / "v4_pirate_pareto.png", include_v4=True, include_v5=False)
    plot_pareto(out / "v5_pirate_pareto.png", include_v4=False, include_v5=True)
    plot_pareto(out / "v4v5_pirate_pareto.png", include_v4=True, include_v5=True)
