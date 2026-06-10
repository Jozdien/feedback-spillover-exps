"""Combined Pareto dot plot: older experimental conditions + V5 SFT conditions.

One dot per condition at the final checkpoint, with error bars.
Two subplots: Qwen3-8B and Qwen3-32B.
X = CoT hint detection rate (spillover), Y = training reward (sycophancy + pw*out_hint).
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

EVAL_DIR = Path("logs/eval-penalty-v5")
PLOT_DIR = Path("plots")
N = 378
PW = -0.5

# --- Older conditions (hardcoded from earlier experiments) ---

older = {
    "Baseline (no penalty)": {
        "Qwen3-8B": {"syc": 0.997, "out": 0.680, "cot": 0.428},
        "Qwen3-32B": {"syc": 1.000, "out": 0.651, "cot": 0.437},
    },
    "Penalty (original)": {
        "Qwen3-8B": {"syc": 0.997, "out": 0.004, "cot": 0.000},
        "Qwen3-32B": {"syc": 0.997, "out": 0.009, "cot": 0.024},
    },
    "Reward targeting": {
        "Qwen3-8B": {"syc": 1.000, "out": 0.002, "cot": 0.044},
        "Qwen3-32B": {"syc": 1.000, "out": 0.001, "cot": 0.228},
    },
    "Mind & Face": {
        "Qwen3-8B": {"syc": 1.000, "out": 0.003, "cot": 0.158},
    },
    "Targeted M&F": {
        "Qwen3-8B": {"syc": 1.000, "out": 0.002, "cot": 0.254},
    },
}


def read_final_eval(run_name):
    run_dir = EVAL_DIR / run_name
    if not run_dir.exists():
        return None
    final_files = list(run_dir.glob("*_001000.jsonl")) + list(run_dir.glob("*_final.jsonl"))
    if not final_files:
        return None
    results = []
    with open(final_files[0]) as f:
        for line in f:
            d = json.loads(line)
            if d.get("type") == "result":
                results.append(d)
    if len(results) < 300:
        return None
    n = len(results)
    return {
        "syc": sum(r["sycophancy"] for r in results) / n,
        "out": sum(r["out_score"] for r in results) / n,
        "cot": sum(r["cot_score"] for r in results) / n,
    }


def get_sft_condition_data(size, cond, src):
    seed_results = []
    for seed in [42, 43]:
        run_name = f"grpo-v5-{size}-{cond}-{src}-s{seed}"
        data = read_final_eval(run_name)
        if data:
            seed_results.append(data)
    if not seed_results:
        return None
    return {
        "syc": np.mean([r["syc"] for r in seed_results]),
        "out": np.mean([r["out"] for r in seed_results]),
        "cot": np.mean([r["cot"] for r in seed_results]),
        "n_seeds": len(seed_results),
    }


OLDER_STYLES = {
    "Baseline (no penalty)": {"color": "#7f7f7f", "marker": "s"},
    "Penalty (original)": {"color": "#1f77b4", "marker": "o"},
    "Reward targeting": {"color": "#ff7f0e", "marker": "D"},
    "Mind & Face": {"color": "#2ca02c", "marker": "^"},
    "Targeted M&F": {"color": "#9467bd", "marker": "v"},
}

SFT_STYLES = {
    "Pirate Output (Qwen)": {"color": "#d62728", "marker": "o"},
    "Pirate CoT (Qwen)": {"color": "#e377c2", "marker": "D"},
    "Pirate Output (Haiku)": {"color": "#8c564b", "marker": "s"},
    "Pirate CoT (Haiku)": {"color": "#17becf", "marker": "^"},
}

SFT_CONDITIONS = [
    ("Pirate Output (Qwen)", "pirate-output", "qwen"),
    ("Pirate CoT (Qwen)", "pirate-cot", "qwen"),
    ("Pirate Output (Haiku)", "pirate-output", "haiku"),
    ("Pirate CoT (Haiku)", "pirate-cot", "haiku"),
]


def reward(syc, out):
    return syc + PW * out


def binomial_ci(p, n=N):
    return 1.96 * np.sqrt(max(p * (1 - p), 0) / n)


def reward_err(syc, out):
    return 1.96 * np.sqrt(
        max(syc * (1 - syc), 0) / N + PW**2 * max(out * (1 - out), 0) / N
    )


def main():
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    sizes = [("8b", "Qwen3-8B"), ("32b", "Qwen3-32B")]

    for idx, (size_key, model_name) in enumerate(sizes):
        ax = axes[idx]

        for cond_name, style in OLDER_STYLES.items():
            if model_name not in older.get(cond_name, {}):
                continue
            d = older[cond_name][model_name]
            x = d["cot"]
            y = reward(d["syc"], d["out"])
            xerr = binomial_ci(x)
            yerr = reward_err(d["syc"], d["out"])
            ax.errorbar(
                x, y, xerr=xerr, yerr=yerr,
                color=style["color"], marker=style["marker"], markersize=10,
                capsize=4, linewidth=0, elinewidth=1.5, zorder=5,
                label=cond_name,
            )

        for label, cond, src in SFT_CONDITIONS:
            style = SFT_STYLES[label]
            data = get_sft_condition_data(size_key, cond, src)
            if data is None:
                continue
            x = data["cot"]
            y = reward(data["syc"], data["out"])
            xerr = binomial_ci(x)
            yerr = reward_err(data["syc"], data["out"])
            ax.errorbar(
                x, y, xerr=xerr, yerr=yerr,
                color=style["color"], marker=style["marker"], markersize=10,
                capsize=4, linewidth=0, elinewidth=1.5, zorder=5,
                label=label,
            )

        ax.set_xlabel("CoT hint detection rate (spillover)", fontsize=12)
        ax.set_ylabel(f"Training reward (syc {PW:+g} × out_hint)", fontsize=12)
        ax.set_title(model_name, fontsize=14, fontweight="bold")
        ax.axhline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(alpha=0.2, linewidth=0.5)
        ax.legend(fontsize=8, loc="best", frameon=True, framealpha=0.9)

    fig.suptitle(
        f"Final-Checkpoint Pareto: All Conditions (V5, penalty_weight={PW})",
        fontsize=15, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    out = PLOT_DIR / "combined_pareto_dots_pw05.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
