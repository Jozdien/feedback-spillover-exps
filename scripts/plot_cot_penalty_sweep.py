"""Plot hint_in_output and hint_in_cot across the cot_penalty_prob sweep."""

import argparse

import matplotlib.pyplot as plt

from src.analysis.metrics import load_metrics, smooth

RUNS = [
    ("cot-penalty-p000", 0.00, "#4878CF"),
    ("cot-penalty-p001", 0.01, "#6ACC65"),
    ("cot-penalty-p005", 0.05, "#D4A64F"),
    ("cot-penalty-p010", 0.10, "#D65F5F"),
    ("cot-penalty-p025", 0.25, "#8E44AD"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/tmp/spillover-exps")
    ap.add_argument("--out", default="cot_penalty_sweep.png")
    ap.add_argument("--smoothing", type=int, default=5)
    args = ap.parse_args()

    fig, (ax_out, ax_cot) = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    for name, prob, color in RUNS:
        try:
            run = load_metrics(f"{args.root}/{name}", name)
        except FileNotFoundError:
            print(f"skip {name}: no metrics yet")
            continue
        if not run.steps:
            print(f"skip {name}: empty")
            continue
        label = f"p={prob:.2f}"
        ax_out.plot(
            run.steps, smooth(run.hint_in_output, args.smoothing),
            color=color, linewidth=2, label=label,
        )
        ax_cot.plot(
            run.steps, smooth(run.hint_in_cot, args.smoothing),
            color=color, linewidth=2, label=label,
        )

    for ax, title in [(ax_out, "hint_in_output"), (ax_cot, "hint_in_cot")]:
        ax.set_xlabel("batch", fontsize=12)
        ax.set_title(title, fontsize=14)
        ax.set_ylim(-0.05, 1.05)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(fontsize=10, title="cot_penalty_prob")
    ax_out.set_ylabel("rate", fontsize=12)

    fig.suptitle(
        "CoT-hint penalty sweep (1600 episodes, penalty_weight=-2)",
        fontsize=15, y=1.02,
    )
    plt.tight_layout()
    plt.savefig(args.out, dpi=200, bbox_inches="tight")
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
