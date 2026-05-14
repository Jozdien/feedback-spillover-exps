"""Generate final v3 plots with 3-seed error bars."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

BASE = Path("/tmp/spillover-exps")

SEEDS = {
    "Control": ["paper-control", "v3-control-s43", "v3-control-s44"],
    "Penalty": ["v3-penalty", "v3-penalty-s43", "v3-penalty-s44"],
    "Reward Targeting": ["v3-reward-target", "v3-reward-target-s43", "v3-reward-target-s44"],
    "Mind & Face": ["mind-face", "v3-mind-face-s43", "v3-mind-face-s44"],
    "Pirate (control)": ["pirate-output-control", "v3-pirate-control-s43", "v3-pirate-control-s44"],
    "Pirate (final)": ["v3-pirate-penalty", "v3-pirate-final-s43", "v3-pirate-final-s44"],
    "Pirate (step 20)": ["v3-pirate-step000020", "v3-pirate-step20-s43", "v3-pirate-step20-s44"],
    "Pirate (step 100)": ["v3-pirate-step000100", "v3-pirate-step100-s43", "v3-pirate-step100-s44"],
    "Pirate (step 500)": ["v3-pirate-step000500", "v3-pirate-step500-s43", "v3-pirate-step500-s44"],
}

COLORS = {
    "Control": "#4878CF",
    "Penalty": "#D65F5F",
    "Reward Targeting": "#C4AD66",
    "Mind & Face": "#6ACC65",
    "Pirate (control)": "#E8D5F5",
    "Pirate (step 20)": "#C9A0E8",
    "Pirate (step 100)": "#A86BD4",
    "Pirate (step 500)": "#8736C0",
    "Pirate (final)": "#6A0DAD",
}

MARKERS = {
    "Control": "o", "Penalty": "s", "Reward Targeting": "D",
    "Mind & Face": "^", "Pirate (control)": "P", "Pirate (step 20)": "P",
    "Pirate (step 100)": "P", "Pirate (step 500)": "P", "Pirate (final)": "P",
}


def load_final(run_dir, window=50):
    path = BASE / run_dir / "metrics.jsonl"
    lines = [json.loads(l) for l in open(path)]
    last = lines[-window:]
    return {
        "correct": np.mean([l["reward/correct"] for l in last]),
        "hint_out": np.mean([l["monitor/hint_in_output"] for l in last]),
        "hint_cot": np.mean([l["monitor/hint_in_cot"] for l in last]),
    }


def load_timeseries(run_dir):
    path = BASE / run_dir / "metrics.jsonl"
    lines = [json.loads(l) for l in open(path)]
    return {
        "steps": [l.get("progress/batch", l.get("step", i)) for i, l in enumerate(lines)],
        "correct": [l["reward/correct"] for l in lines],
        "hint_out": [l["monitor/hint_in_output"] for l in lines],
        "hint_cot": [l["monitor/hint_in_cot"] for l in lines],
    }


def spillover_ratio(run_dir, window=50):
    path = BASE / run_dir / "metrics.jsonl"
    lines = [json.loads(l) for l in open(path)]
    early_out = np.mean([l["monitor/hint_in_output"] for l in lines[:window]])
    late_out = np.mean([l["monitor/hint_in_output"] for l in lines[-window:]])
    early_cot = np.mean([l["monitor/hint_in_cot"] for l in lines[:window]])
    late_cot = np.mean([l["monitor/hint_in_cot"] for l in lines[-window:]])
    d_out = early_out - late_out
    if abs(d_out) < 1e-6:
        return float("nan")
    return (early_cot - late_cot) / d_out


def smooth(vals, w=10):
    kernel = np.ones(w) / w
    padded = np.pad(vals, (w // 2, w - 1 - w // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def plot_pareto(output_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("All Conditions (3 seeds, mean ± SE) — Qwen3-8B LoRA, MMLU QA", fontsize=13)

    for name, runs in SEEDS.items():
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

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_path}")


def plot_curves(output_path):
    conditions = ["Control", "Penalty", "Reward Targeting", "Mind & Face", "Pirate (final)"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle("Training Curves — Qwen3-8B LoRA, MMLU QA", fontsize=13)

    for name in conditions:
        ts = load_timeseries(SEEDS[name][0])
        kw = dict(color=COLORS[name], label=name, linewidth=1.5)
        axes[0].plot(ts["steps"], smooth(ts["correct"]), **kw)
        axes[1].plot(ts["steps"], smooth(ts["hint_out"]), **kw)
        axes[2].plot(ts["steps"], smooth(ts["hint_cot"]), **kw)

    titles = ["Correctness", "Hint in Output", "Hint in CoT (Spillover)"]
    for ax, title in zip(axes, titles):
        ax.set_title(title)
        ax.set_xlabel("Batch")
        ax.set_ylim(0, 1)
        ax.legend(fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_path}")


def plot_pirate_scaling(output_path):
    steps_labels = [("Penalty", 0), ("Pirate (step 20)", 20), ("Pirate (step 100)", 100),
                    ("Pirate (step 500)", 500), ("Pirate (final)", 880)]
    fig, ax = plt.subplots(figsize=(8, 5))

    xs, ys, yerrs = [], [], []
    for name, x in steps_labels:
        ratios = [spillover_ratio(r) for r in SEEDS[name]]
        ratios = [r for r in ratios if not np.isnan(r)]
        if not ratios:
            continue
        xs.append(x)
        ys.append(np.mean(ratios))
        yerrs.append(np.std(ratios, ddof=1) / np.sqrt(len(ratios)))
        ax.annotate(f"{np.mean(ratios):.2f}", (x, np.mean(ratios)),
                    textcoords="offset points", xytext=(0, 12), ha="center", fontsize=9)

    ax.errorbar(xs, ys, yerr=yerrs, fmt="o-", color="#2ECC71", capsize=5, markersize=8, linewidth=2)

    ax.axhline(ys[0], color="#D65F5F", linestyle="--", alpha=0.3,
               label=f"Penalty baseline ({ys[0]:.2f})")

    ax.set_xlabel("Pirate SFT steps (0 = base model)")
    ax.set_ylabel("Spillover ratio")
    ax.set_title("Effect of Pirate Output SFT on Spillover (3 seeds)\nPenalty condition, Qwen3-8B LoRA, MMLU QA")
    ax.legend()
    ax.set_ylim(0, 0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_path}")


if __name__ == "__main__":
    out = Path("/home/jose/feedback-spillover-exps")
    plot_pareto(out / "v3_all_pareto_errorbars.png")
    plot_curves(out / "v3_all_curves.png")
    plot_pirate_scaling(out / "v3_pirate_scaling_errorbars.png")

    print("\nSpillover ratios (3 seeds, mean ± SE):")
    for name, runs in SEEDS.items():
        ratios = [spillover_ratio(r) for r in runs]
        ratios = [r for r in ratios if not np.isnan(r)]
        if ratios:
            print(f"  {name:25s}: {np.mean(ratios):.3f} ± {np.std(ratios, ddof=1)/np.sqrt(len(ratios)):.3f}")
