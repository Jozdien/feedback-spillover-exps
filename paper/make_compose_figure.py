"""Figure: style separation combined with the prior mitigations (RESULTS.md §16i).

Horizontal bars in the layout of gate_bars.pdf, one panel per model, rows grouped by
prior mitigation: the unstyled model under that mitigation (or the plain penalty),
then the pirate and Pig-Latin models with the same mitigation and the style reward.
Every arm is under the explanation gate. Values are last-27-step training-rollout
means; error bars are 95% t intervals over seeds. Numbers come from RESULTS.md §16i
(combinations), §16d/§16e (styles alone) and plots/gated_pareto_all.json (unstyled
arms); sample standard deviations over seeds.

Run: cd paper && uv run --no-sync make_compose_figure.py   (writes figures/compose_bars.pdf)
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

from figstyle import set_paper_style

set_paper_style()
plt.rcParams.update({"axes.labelsize": 9, "axes.titlesize": 9})

FIG = Path(__file__).resolve().parent / "figures"
TEXTWIDTH_IN = 5.5  # the NeurIPS text block, so fonts print at the size set above

C = {"unstyled": "#868e96", "pirate": "#e8590c", "piglatin": "#d4a017", "ctrl": "#343a40"}

# Row label, series, (mean, sample sd, n) on Qwen3-8B, (mean, sample sd, n) on Qwen3.6-27B.
ROWS = [
    ("Plain penalty",     "unstyled", (0.27, 0.06, 5),  (0.45, 0.08, 5)),
    ("Pirate",            "pirate",   (0.46, 0.13, 10), (0.42, 0.33, 5)),
    ("Pig Latin",         "piglatin", (0.56, 0.08, 10), (0.63, 0.30, 5)),
    None,
    ("Reward targeting",  "unstyled", (0.51, 0.07, 5),  (0.85, 0.14, 5)),
    ("+ Pirate",          "pirate",   (0.62, 0.09, 5),  (0.95, 0.07, 5)),
    ("+ Pig Latin",       "piglatin", (0.62, 0.09, 5),  (0.70, 0.27, 5)),
    None,
    ("Mind & Face",       "unstyled", (0.40, 0.05, 5),  (0.44, 0.09, 5)),
    ("+ Pirate",          "pirate",   (0.46, 0.11, 5),  (0.33, 0.26, 5)),
    ("+ Pig Latin",       "piglatin", (0.46, 0.11, 5),  (0.35, 0.26, 5)),
    None,
    ("Targeted M&F",      "unstyled", (0.52, 0.03, 5),  (0.85, 0.12, 5)),
    ("+ Pirate",          "pirate",   (0.63, 0.06, 5),  (0.88, 0.17, 5)),
    ("+ Pig Latin",       "piglatin", (0.60, 0.09, 5),  (0.83, 0.23, 5)),
]
CONTROL = {"Qwen3-8B": 0.60, "Qwen3.6-27B": 0.81}


def t_interval(sd: float, n: int) -> float:
    """Half-width of a 95% t interval for the mean over n seeds."""
    return stats.t.ppf(0.975, n - 1) * sd / np.sqrt(n)


def main() -> None:
    ys, y = [], 0.0
    for row in ROWS:
        if row is None:
            y += 0.6
            continue
        ys.append(-y)
        y += 1.0
    rows = [r for r in ROWS if r is not None]

    fig, axes = plt.subplots(1, 2, figsize=(TEXTWIDTH_IN, TEXTWIDTH_IN * 0.5), sharey=True)
    for ax, (model, col) in zip(axes, [("Qwen3-8B", 2), ("Qwen3.6-27B", 3)]):
        for yi, row in zip(ys, rows):
            label, key = row[0], row[1]
            m, sd, n = row[col]
            ax.barh(yi, m, height=0.72, color=C[key], edgecolor="white", linewidth=0.6, zorder=3)
            ax.errorbar(m, yi, xerr=t_interval(sd, n), color="#212529", lw=0, elinewidth=0.9,
                        capsize=2.5, zorder=4)
        c = CONTROL[model]
        ax.axvline(c, ls="--", lw=1.0, color=C["ctrl"], zorder=2)
        ax.text(c, 0.9, "No penalty", ha="center", va="bottom", fontsize=7.5, color=C["ctrl"])
        ax.set_title(model, fontweight="bold")
        ax.set_xlim(0, 1.0)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_xlabel("CoT hint detection")
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
    axes[0].set_yticks(ys)
    axes[0].set_yticklabels([r[0] for r in rows], fontsize=8)
    axes[0].set_ylim(ys[-1] - 0.7, 1.6)
    fig.tight_layout(w_pad=1.2)
    out = FIG / "compose_bars.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
