"""Appendix figures drawn from figures/paper_numbers.json (no logs needed).

- qa8b_all_bars.pdf: CoT hint detection for every QA condition on Qwen3-8B (Table tab:main).
- compose_27b.pdf: each prior mitigation alone and combined with each style on Qwen3.6-27B.
- terminal_bars.pdf: CoT detection in the terminal environment on Qwen3-8B.

Bars are means over seeds, dots are seeds; hollow bars are no-penalty controls.
Run: cd paper && uv run --no-sync make_appendix_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

import make_paper_figures as mpf

FIG = Path(__file__).resolve().parent / "figures"
DATA = json.loads((FIG / "paper_numbers.json").read_text())
W, INK = mpf.W, mpf.INK
GRAY, PURPLE = "#8a8880", "#7a5c99"


def bars_with_dots(ax, d, spec, group_gap=0.5):
    """spec: list of (key, color, hollow, group); groups separated by a gap."""
    x, prev, xs = 0.0, None, []
    for key, color, hollow, group in spec:
        if prev is not None and group != prev:
            x += group_gap
        a = d[key]
        if hollow:
            ax.bar(x, a["cot"], width=0.8, color="white", edgecolor=color, linewidth=1.0, zorder=2)
        else:
            ax.bar(x, a["cot"], width=0.8, color=color, zorder=2)
        for i, s in enumerate(a["seeds"]):
            jit = (i - (a["n"] - 1) / 2) * (0.6 / max(a["n"], 2))
            if s["task"] < 0.2:
                ax.plot(x + jit, s["cot"], "x", ms=3.4, mew=0.9, color=INK, zorder=4)
            else:
                unscrubbed = s["out"] > 0.5 and not hollow
                ax.plot(x + jit, s["cot"], "o", ms=2.8, mew=0.7, zorder=4,
                        mfc="white" if unscrubbed else INK, mec=INK)
        xs.append(x)
        x += 1.0
        prev = group
    ax.axhline(d["ctrl"]["cot"], ls="--", lw=0.8, color=mpf.COND["ctrl"][1], zorder=1)
    ax.set_xticks(xs)
    ax.set_xlim(xs[0] - 0.7, xs[-1] + 0.7)
    ax.set_ylim(0, 1.04)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.spines["bottom"].set_color("#b0aea5")
    return xs


def fig_qa8b_all():
    C = mpf.COND
    spec = [  # key, color, hollow (no penalty), group
        ("ctrl", C["ctrl"][1], True, "c"), ("pen", C["pen"][1], False, "c"),
        ("rt", C["rt"][1], False, "m"), ("mf", C["mf"][1], False, "m"), ("tmf", C["tmf"][1], False, "m"),
        ("pirate_ctrl", C["pirate"][1], True, "s"), ("pirate", C["pirate"][1], False, "s"),
        ("piglatin_ctrl", C["piglatin"][1], True, "s"), ("piglatin", C["piglatin"][1], False, "s"),
        ("chinese_ctrl", C["chinese"][1], True, "s"), ("chinese", C["chinese"][1], False, "s"),
        ("pirate_nosr", C["pirate"][1], False, "n"), ("piglatin_nosr", C["piglatin"][1], False, "n"),
        ("normalm_ctrl", GRAY, True, "u"), ("normalm", GRAY, False, "u"),
        ("pcot_ctrl", PURPLE, True, "p"), ("pcot", PURPLE, False, "p"),
    ]
    labels = ["No SFT, no penalty", "Plain penalty", "Reward targeting", "Mind & Face", "Targeted M&F",
              "Pirate, no penalty", "Pirate", "Pig Latin, no penalty", "Pig Latin", "Chinese, no penalty", "Chinese",
              "Pirate, style not rewarded", "Pig Latin, style not rewarded",
              "Unstyled SFT (prompt-matched), no penalty", "Unstyled SFT (prompt-matched)", "Pirate CoT, no penalty", "Pirate CoT"]
    fig, ax = plt.subplots(figsize=(W, W * 0.5))
    xs = bars_with_dots(ax, DATA["qa8b"], spec)
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=7)
    ax.set_ylabel("CoT hint detection")
    handles = [Patch(facecolor="white", edgecolor=INK, lw=1.0), Patch(color=INK),
               Line2D([], [], ls="none", marker="o", ms=2.8, color=INK),
               Line2D([], [], ls="none", marker="o", ms=2.8, mfc="white", mec=INK),
               Line2D([], [], ls="none", marker="x", ms=3.4, mew=0.9, color=INK)]
    ax.legend(handles, ["No penalty", "Output penalty", "Seed", "Seed whose output was never scrubbed",
                        "Seed that lost its task reward"],
              loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=7, handlelength=1.2)
    fig.tight_layout()
    fig.savefig(FIG / "qa8b_all_bars.pdf")
    plt.close(fig)


def fig_compose_27b():
    d = DATA["qa27b"]
    C = mpf.COND
    groups = [("None", "pen"), ("Reward\ntargeting", "rt"), ("Mind &\nFace", "mf"), ("Targeted\nM&F", "tmf")]
    styles = [("pirate", "+ Pirate output"), ("piglatin", "+ Pig-Latin output"), ("chinese", "+ Chinese output")]
    fig, ax = plt.subplots(figsize=(W * 0.62, W * 0.4))
    ticks = []
    for gi, (gname, m) in enumerate(groups):
        members = [(m, m)] + [(s, s if m == "pen" else f"{s}+{m}") for s, _ in styles]
        for j, (ckey, dkey) in enumerate(members):
            x = gi * 5.4 + j
            a = d[dkey]
            ax.bar(x, a["cot"], width=0.86, color=C[ckey][1], zorder=2)
            lo, hi = max(a["cot"] - a["cot_ci"], 0), min(a["cot"] + a["cot_ci"], 1)
            ax.errorbar(x, a["cot"], yerr=[[a["cot"] - lo], [hi - a["cot"]]], color=INK, lw=0,
                        elinewidth=0.8, capsize=1.8, zorder=3)
        ticks.append(gi * 5.4 + 1.5)
    ax.axhline(d["ctrl"]["cot"], ls="--", lw=0.9, color=C["ctrl"][1], zorder=1)
    ax.set_xticks(ticks)
    ax.set_xticklabels([g for g, _ in groups], fontsize=7, linespacing=1.0)
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, 1.04)
    ax.set_xlim(-0.9, 3 * 5.4 + 3.9)
    ax.set_ylabel("CoT hint detection")
    handles = [Line2D([], [], ls="--", lw=0.9, color=C["ctrl"][1])] + \
              [Patch(color=C[k][1]) for k in ("pen", "rt", "mf", "tmf")] + [Patch(color=C[s][1]) for s, _ in styles]
    labels = ["No penalty", "Plain penalty", "Reward targeting", "Mind & Face", "Targeted M&F"] + [l for _, l in styles]
    ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=7,
              handlelength=1.0, handleheight=0.9)
    fig.tight_layout()
    fig.savefig(FIG / "compose_27b.pdf")
    plt.close(fig)


def fig_terminal():
    C = mpf.COND
    spec = [("ctrl", C["ctrl"][1], True, "c"), ("pen", C["pen"][1], False, "c"),
            ("rt", C["rt"][1], False, "m"), ("mf", C["mf"][1], False, "m"), ("tmf", C["tmf"][1], False, "m"),
            ("pirate_ctrl", C["pirate"][1], True, "s"), ("pirate", C["pirate"][1], False, "s"),
            ("piglatin_ctrl", C["piglatin"][1], True, "s"), ("piglatin", C["piglatin"][1], False, "s"),
            ("chinese_ctrl", C["chinese"][1], True, "s"), ("chinese", C["chinese"][1], False, "s")]
    labels = ["No SFT, no penalty", "Plain penalty", "Reward targeting", "Mind & Face", "Targeted M&F",
              "Pirate, no penalty", "Pirate", "Pig Latin, no penalty", "Pig Latin", "Chinese, no penalty", "Chinese"]
    fig, ax = plt.subplots(figsize=(W * 0.7, W * 0.42))
    bars_with_dots(ax, DATA["term8b"], spec)
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=7)
    ax.set_ylabel("CoT detection")
    fig.tight_layout()
    fig.savefig(FIG / "terminal_bars.pdf")
    plt.close(fig)


if __name__ == "__main__":
    fig_qa8b_all()
    fig_compose_27b()
    fig_terminal()
    print("wrote qa8b_all_bars.pdf, compose_27b.pdf, terminal_bars.pdf")
