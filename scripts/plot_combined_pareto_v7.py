"""Combined Pareto dot plot: older experimental conditions + latest V6/V7 runs.

One dot per condition at the final checkpoint, with error bars.
Two subplots: Qwen3-8B and Qwen3-32B.
X = CoT hint detection rate (spillover), Y = training reward (sycophancy + pw*out_hint).

Mind & Face / Reward targeting / Targeted M&F dots are hardcoded from earlier
experiments. All other dots are read from the V6/V7 eval results
(logs/eval-penalty-v6 and logs/eval-penalty-v7). Conditions whose final-checkpoint
evals don't exist yet are skipped and reported; re-run as evals complete.

Usage: uv run scripts/plot_combined_pareto_v7.py [--pw {-0.5,-1,-2}]
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

EVAL_DIRS = [Path("logs/eval-penalty-v6"), Path("logs/eval-penalty-v7")]
PLOT_DIR = Path("plots")
N = 378

# --- Older conditions (hardcoded from earlier experiments) ---

older = {
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

OLDER_STYLES = {
    "Reward targeting": {"color": "#ff7f0e", "marker": "D"},
    "Mind & Face": {"color": "#2ca02c", "marker": "^"},
    "Targeted M&F": {"color": "#9467bd", "marker": "v"},
}

# --- V6/V7 run naming ---

V6_BY_PW = {0.0: "v6ctrl", -0.5: "v6", -1.0: "v6pw-1", -2.0: "v6pw-2"}


def pw_str(pw):
    return "pw0" if pw == 0 else f"pw{pw:g}"


def v6_run(size, pw, seed):
    return f"grpo-{V6_BY_PW[pw]}-{size}-pirate-output-alpaca-qwen-s{seed}"


def v7_run(cond, size, pw, seed):
    return f"grpo-{cond}-{size}-{pw_str(pw)}-s{seed}"


def new_conditions(pw):
    """(label, style, run-name builder, hollow) — for each SFT condition, a
    penalized dot (filled) and a pw=0 control dot (hollow, same color/marker).
    Control dots are scored under the plot's penalty weight, like the old
    'Baseline (no penalty)' dot."""
    conds = [
        ("No SFT", {"color": "#1f77b4", "marker": "o"},
         lambda p: lambda size, seed: v7_run("v7base", size, p, seed)),
        ("Normal SFT", {"color": "#bcbd22", "marker": "p"},
         lambda p: lambda size, seed: v7_run("v7norm", size, p, seed)),
        ("Pirate Output", {"color": "#d62728", "marker": "o"},
         lambda p: lambda size, seed: v6_run(size, p, seed)),
        ("Pirate CoT", {"color": "#e377c2", "marker": "D"},
         lambda p: lambda size, seed: v7_run("v7pcot", size, p, seed)),
    ]
    out = []
    for label, style, make_builder in conds:
        out.append((f"{label} (no penalty)", style, make_builder(0.0), True))
        out.append((label, style, make_builder(pw), False))
    return out


def read_final_eval(run_name):
    for eval_dir in EVAL_DIRS:
        run_dir = eval_dir / run_name
        if not run_dir.exists():
            continue
        final_files = list(run_dir.glob("*_001000.jsonl")) + list(run_dir.glob("*_final.jsonl"))
        if not final_files:
            continue
        results = []
        with open(final_files[0]) as f:
            for line in f:
                d = json.loads(line)
                if d.get("type") == "result":
                    results.append(d)
        if len(results) < 300:
            continue
        n = len(results)
        return {
            "syc": sum(r["sycophancy"] for r in results) / n,
            "out": sum(r["out_score"] for r in results) / n,
            "cot": sum(r["cot_score"] for r in results) / n,
        }
    return None


def get_condition_data(run_builder, size):
    seed_results = []
    for seed in [42, 43]:
        data = read_final_eval(run_builder(size, seed))
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


def binomial_ci(p, n=N):
    return 1.96 * np.sqrt(max(p * (1 - p), 0) / n)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pw", type=float, default=-2.0, choices=[-0.5, -1.0, -2.0],
                        help="Penalty weight for the penalized conditions (default: -2)")
    args = parser.parse_args()
    pw = args.pw

    def reward(syc, out):
        return syc + pw * out

    def reward_err(syc, out):
        return 1.96 * np.sqrt(
            max(syc * (1 - syc), 0) / N + pw**2 * max(out * (1 - out), 0) / N
        )

    missing = []
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    sizes = [("8b", "Qwen3-8B"), ("32b", "Qwen3-32B")]

    for idx, (size_key, model_name) in enumerate(sizes):
        ax = axes[idx]

        for label, style, run_builder, hollow in new_conditions(pw):
            data = get_condition_data(run_builder, size_key)
            if data is None:
                missing.append(f"{model_name}: {label} ({run_builder(size_key, '<seed>')})")
                continue
            if data["n_seeds"] < 2:
                print(f"note: {model_name} {label} has only {data['n_seeds']} seed(s)")
            x = data["cot"]
            y = reward(data["syc"], data["out"])
            ax.errorbar(
                x, y, xerr=binomial_ci(x), yerr=reward_err(data["syc"], data["out"]),
                color=style["color"], marker=style["marker"], markersize=10,
                markerfacecolor="none" if hollow else style["color"],
                markeredgewidth=2 if hollow else 1,
                capsize=4, linewidth=0, elinewidth=1.5, zorder=5,
                label=label,
            )

        for cond_name, style in OLDER_STYLES.items():
            if model_name not in older.get(cond_name, {}):
                continue
            d = older[cond_name][model_name]
            x = d["cot"]
            y = reward(d["syc"], d["out"])
            ax.errorbar(
                x, y, xerr=binomial_ci(x), yerr=reward_err(d["syc"], d["out"]),
                color=style["color"], marker=style["marker"], markersize=10,
                capsize=4, linewidth=0, elinewidth=1.5, zorder=5,
                label=cond_name,
            )

        ax.set_xlabel("CoT hint detection rate (spillover)", fontsize=12)
        ax.set_ylabel(f"Training reward (syc {pw:+g} × out_hint)", fontsize=12)
        ax.set_title(model_name, fontsize=14, fontweight="bold")
        ax.axhline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(alpha=0.2, linewidth=0.5)
        ax.legend(fontsize=8, loc="best", frameon=True, framealpha=0.9)

    fig.suptitle(
        f"Final-Checkpoint Pareto: All Conditions (V6/V7, penalty_weight={pw:g})",
        fontsize=15, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    out = PLOT_DIR / f"combined_pareto_dots_v7_pw{abs(pw):g}.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {out}")

    if missing:
        print(f"\nMissing final-checkpoint evals ({len(missing)}):")
        for m in missing:
            print(f"  - {m}")


if __name__ == "__main__":
    main()
