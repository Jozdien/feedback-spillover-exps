"""Paper-figure style for matplotlib, matching the user's publication aesthetic.

Drop this next to a plotting script and `from figure_style import *`. It encodes
the conventions in SKILL.md: no on-figure title (the LaTeX caption carries it),
vector-PDF output with editable text, one semantic palette reused across the
whole paper, legends outside the axes, error bars/CI always, baseline reference
lines, and sizing tuned for a single \\textwidth column.

Contrast with the `making-plots` skill, which targets slides: there, titles go
ON the plot, every bar is value-annotated, and output is PNG@300dpi. For papers
those are reversed here.
"""

from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt

# --- One semantic palette for the ENTIRE paper -----------------------------
# A color means the same thing in every figure. Adapt the *labels* to your
# paper, but choose the mapping once and reuse it everywhere.
PALETTE = {
    "baseline": "#4d4d4d",   # gray  — control / no intervention
    "robust": "#1f4e79",     # blue  — robust / safe condition
    "intervention": "#d0591b",  # orange — the thing under study (e.g. SDF)
    "worst": "#b3142a",      # red   — worst case / no mitigation
    "neutral": "#e6b800",    # yellow — secondary condition
}

# Page geometry for a typical single-column letter-size paper (inches).
TEXTWIDTH_IN = 6.5   # \textwidth at default margins; size figures to this
GOLDEN = 0.618


def set_paper_style() -> None:
    """Set rcParams so figures look right *after* being scaled to \\textwidth.

    Fonts are chosen so that a figure saved at ~TEXTWIDTH_IN and included with
    `\\includegraphics[width=\\textwidth]` renders body-sized (~8-9pt) text.
    """
    mpl.rcParams.update({
        # Vector output with editable (TrueType) text, not outlines/Type-3.
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "savefig.format": "pdf",
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.01,
        # A clean sans face for figures; switch to "serif" to match a Times body.
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        # Sizes are for a figure drawn near \textwidth and not downscaled much.
        "font.size": 9,
        "axes.titlesize": 10,   # used only for *panel* titles, never a fig title
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        # Clean frame: no top/right spines, light horizontal grid only.
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": "#cccccc",
        "grid.linewidth": 0.6,
        "grid.alpha": 0.5,
        "figure.dpi": 150,
        "errorbar.capsize": 3,
    })


def figsize(width_frac: float = 1.0, aspect: float = GOLDEN) -> tuple[float, float]:
    """Figure size in inches for a fraction of \\textwidth at a chosen aspect.

    Pick the aspect deliberately and include the PDF with `width=` only so
    LaTeX never stretches it.
    """
    w = TEXTWIDTH_IN * width_frac
    return (w, w * aspect)


def despine(ax: plt.Axes) -> None:
    """Remove top/right spines (rcParams already do this for new axes)."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def legend_outside(ax: plt.Axes, **kw) -> None:
    """Place the legend just outside the axes on the right (bar-chart default)."""
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
              frameon=False, **kw)


def baseline_line(ax: plt.Axes, y: float, label: str, color: str = "#000000") -> None:
    """Dashed horizontal reference line with an inline label sitting on it."""
    ax.axhline(y, ls="--", lw=1.2, color=color, zorder=1)
    ax.text(0.01, y, label, transform=ax.get_yaxis_transform(),
            va="bottom", ha="left", fontsize=9, fontweight="bold", color=color)


def save_pdf(fig: plt.Figure, path: str) -> None:
    """Save as vector PDF with a tight bounding box (no surrounding whitespace)."""
    if not path.endswith(".pdf"):
        path += ".pdf"
    fig.savefig(path)  # format/bbox come from rcParams


# --- Worked example: grouped bar chart in the paper style ------------------
# Mirrors `em_bars.pdf`: two setting-groups, four semantic conditions, error
# bars, two labeled baselines, legend outside, NO title (caption owns it).
if __name__ == "__main__":
    import numpy as np

    set_paper_style()

    groups = ["Prompted setting", "SDF setting"]
    conditions = ["robust", "neutral", "intervention", "worst"]
    cond_labels = [
        "RL on robust environment,\nno reward hacking.",
        'RL, inoculation prompt ("Please\nreward hack whenever [...]").',
        'RL, inoculation prompt ("Your\nonly goal is to pass [...]").',
        "RL on hackable environment,\nno inoculation prompt.",
    ]
    # rows = groups, cols = conditions
    values = np.array([[0.27, 0.28, 0.27, 0.32],
                       [0.35, 0.36, 0.43, 0.52]])
    errs = np.full_like(values, 0.02)

    fig, ax = plt.subplots(figsize=figsize(width_frac=1.0, aspect=0.5))
    x = np.arange(len(groups))
    w = 0.2
    for i, cond in enumerate(conditions):
        ax.bar(x + (i - 1.5) * w, values[:, i], w,
               yerr=errs[:, i], color=PALETTE[cond],
               edgecolor="white", linewidth=0.8, label=cond_labels[i])

    baseline_line(ax, 0.255, "Baseline", color="#000000")
    baseline_line(ax, 0.355, "SDF Baseline", color=PALETTE["intervention"])

    ax.set_xticks(x)
    ax.set_xticklabels(groups)
    ax.set_ylabel("Misalignment score")
    ax.set_ylim(0, 0.6)
    ax.grid(axis="x", visible=False)  # horizontal gridlines only
    legend_outside(ax)
    # NOTE: deliberately no ax.set_title(...) — the LaTeX \caption carries it.

    save_pdf(fig, "example_em_bars.pdf")
    print("wrote example_em_bars.pdf")
