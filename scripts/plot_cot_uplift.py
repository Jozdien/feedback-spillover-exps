"""Plot CoT uplift: task accuracy vs thinking budget (from eval_cot_uplift.py runs).

Reads logs/cot-uplift/summary.jsonl; writes plots/cot_uplift.png.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SUMMARY = Path("logs/cot-uplift/summary.jsonl")
OUT = Path("plots/cot_uplift.png")

MODEL_STYLE = {
    "Qwen/Qwen3-8B": dict(color="#4878CF", label="Qwen3-8B"),
    "Qwen/Qwen3.6-35B-A3B": dict(color="#D65F5F", label="Qwen3.6-35B-A3B"),
}
PANELS = [
    ("qa_nohint", "real_correct", "MMLU elem. math (no hint)", "Accuracy"),
    ("poly", "correct", "Polynomial factoring", "Accuracy"),
    ("qa_hint", "real_correct", "MMLU elem. math (wrong hint)", "Rate"),
]


def main():
    rows = [json.loads(line) for line in open(SUMMARY)]
    budgets = sorted({r["budget"] for r in rows})
    xpos = np.arange(len(budgets))

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    for ax, (task, metric, title, ylabel) in zip(axes, PANELS):
        for model, style in MODEL_STYLE.items():
            sub = {r["budget"]: r for r in rows if r["model"] == model and r["task"] == task}
            if not sub:
                continue
            xs = [i for i, b in enumerate(budgets) if b in sub]
            ys = [sub[budgets[i]][metric] for i in xs]
            ns = [sub[budgets[i]]["n"] for i in xs]
            errs = [1.96 * np.sqrt(max(y * (1 - y), 1e-9) / n) for y, n in zip(ys, ns)]
            ax.errorbar(xs, ys, yerr=errs, marker="o", markersize=7, linewidth=2,
                        capsize=4, color=style["color"], label=style["label"])
            if task == "qa_hint":
                ys2 = [sub[budgets[i]]["sycophancy"] for i in xs]
                errs2 = [1.96 * np.sqrt(max(y * (1 - y), 1e-9) / n) for y, n in zip(ys2, ns)]
                ax.errorbar(xs, ys2, yerr=errs2, marker="s", markersize=6, linewidth=2,
                            capsize=4, color=style["color"], linestyle="--", alpha=0.6)
        ax.set_title(title, fontsize=15)
        ax.set_xticks(xpos)
        ax.set_xticklabels([str(b) for b in budgets], fontsize=12)
        ax.set_xlabel("Thinking budget $T$ (tokens)", fontsize=13)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", alpha=0.25)
        ax.set_ylim(0, 1.05)
    axes[0].set_ylabel("Accuracy (↑ higher is better)", fontsize=14)
    axes[0].legend(fontsize=12, loc="lower right")
    axes[2].plot([], [], color="gray", linestyle="--", marker="s", label="sycophancy (followed hint)")
    axes[2].plot([], [], color="gray", linestyle="-", marker="o", label="real correct")
    axes[2].legend(fontsize=11, loc="center right")
    fig.suptitle(
        "CoT uplift on the paper's environments: solid = accuracy vs thinking budget "
        "(T=0 is a forced-empty CoT; base models, temp 1.0)",
        fontsize=15,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    OUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUT, dpi=200, bbox_inches="tight")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
