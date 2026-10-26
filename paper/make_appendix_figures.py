"""Appendix figures drawn from figures/paper_numbers.json (no logs needed).

- qa_all_seeds.pdf: every QA run under the penalty on Qwen3-8B and Qwen3.6-27B, in the layout of the
  body's composition figure (each prior mitigation alone and combined with each style).
- poly_seeds.pdf: every polynomial-factoring run under the penalty on Qwen3.6-27B.
- sft_dumbbell.pdf: CoT hint detection without and with the penalty for each model RL starts from
  (no SFT, unstyled SFT, the three styled outputs, the pirate CoT), on both main models.
- screen.pdf: the spillover screen of every model and environment (no penalty vs plain penalty).
- other_qwen.pdf: the other Qwen models we ran mitigations on (Qwen3.5-9B, also combined with the
  prior mitigations; Qwen3.6-35B-A3B; Qwen3.5-397B-A17B).
- terminal_bars.pdf: CoT detection in the terminal environment on Qwen3-8B, marking the styled seeds
  that stopped reading the verifier.

Bars are means over seeds and dots are seeds. Run: cd paper && uv run --no-sync make_appendix_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

import make_paper_figures as mpf

FIG = Path(__file__).resolve().parent / "figures"
DATA = json.loads((FIG / "paper_numbers.json").read_text())
W, INK, C = mpf.W, mpf.INK, mpf.COND
GRAY_TXT = "#8a8880"
COLORS = {k: v[1] for k, v in C.items()} | {"normalm": "#8a8880", "pcot": "#7a5c99"}
LABELS = {k: v[0] for k, v in C.items()} | {"normalm": "Unstyled SFT"}
GROUPS = [("Controls", ["pen", "normalm"]), ("Prior mitigations", ["rt", "mf", "tmf"]),
          ("Style separation (ours)", ["pirate", "piglatin", "chinese"])]
# Seeds marked by hand from the run audits: pirate-CoT runs whose CoT collapsed into filler during RL (per
# setting), and terminal-environment styled runs that stopped reading the verifier (read rate < 0.5).
COLLAPSED = {"qa8b": {"pcot_ctrl": {"43"}},
             "qa27b": {"pcot": {"42", "45", "46", "49", "51"}, "pcot_ctrl": {"44"}}}
STOPPED = {"pirate": {"42", "43", "44", "45", "46"}, "chinese": {"42", "43", "45", "46"}, "piglatin": {"42", "46"}}

KEY_NOPEN = (Line2D([], [], ls="--", lw=0.8, color=C["ctrl"][1]), "No penalty")
KEY_SEED = (Line2D([], [], ls="none", marker="o", ms=2.6, mew=0, color=INK), "Seed")
KEY_UNSCR = (Line2D([], [], ls="none", marker="o", ms=2.9, mew=0.7, mfc="white", mec=INK), "Output not scrubbed")
KEY_LOST = (Line2D([], [], ls="none", marker="x", ms=3.4, mew=0.9, color=INK), "Lost its task reward")
KEY_STOP = (Line2D([], [], ls="none", marker="^", ms=3.2, mew=0.7, mfc="white", mec=INK),
            "Stopped reading the verifier")


def seed_marks(ax, x, a, marked=frozenset(), mark="lost", jit_w=0.62, nopen=False):
    """One dot per seed; hollow if the output was never scrubbed (penalized runs only), a cross if the
    run lost its task reward, and `mark` for the seeds in `marked`."""
    n = a["n"]
    for i, s in enumerate(a["seeds"]):
        x_s = x + (i - (n - 1) / 2) * (jit_w / max(n, 2))
        kind = mark if s["seed"] in marked else ("lost" if s["task"] < 0.2 else
                                                 "unscrubbed" if s["out"] > 0.5 and not nopen else "seed")
        if kind == "lost":
            ax.plot(x_s, s["cot"], "x", ms=3.4, mew=0.9, color=INK, zorder=5)
        elif kind == "unscrubbed":
            ax.plot(x_s, s["cot"], "o", ms=2.9, mew=0.7, mfc="white", mec=INK, zorder=5)
        elif kind == "stopped":
            ax.plot(x_s, s["cot"], "^", ms=3.2, mew=0.7, mfc="white", mec=INK, zorder=5)
        else:
            ax.plot(x_s, s["cot"], "o", ms=2.6, mew=0, color=INK, zorder=5)


def style_axes(ax, title, xlim):
    ax.set_xlim(*xlim)
    ax.set_ylim(0, 1.04)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.spines["bottom"].set_color("#b0aea5")
    ax.set_title(title, fontweight="bold", fontsize=7.8)


def condition_panel(ax, d, title, groups=GROUPS, marked=None, ylabel=None):
    """One bar per penalized condition (conditions not run are labeled); the no-penalty control as a
    dashed line."""
    xs, x = {}, 0.0
    for gi, (_, keys) in enumerate(groups):
        x += 0.55 if gi else 0.0
        for k in keys:
            xs[k], x = x, x + 1.0
    for k, x in xs.items():
        if k not in d:
            ax.text(x, 0.02, "not run", rotation=90, ha="center", va="bottom", fontsize=6, color=GRAY_TXT)
            continue
        ax.bar(x, d[k]["cot"], width=0.8, color=COLORS[k], lw=0, zorder=3)
        seed_marks(ax, x, d[k], (marked or {}).get(k, frozenset()), mark="stopped")
    ax.axhline(d["ctrl"]["cot"], ls="--", lw=0.8, color=C["ctrl"][1], zorder=1)
    ax.set_xticks([])
    style_axes(ax, title, (min(xs.values()) - 0.7, max(xs.values()) + 0.7))
    if ylabel:
        ax.set_ylabel(ylabel)


def compose_panel(ax, d, mits, styles, title, gap=1.2):
    """Each prior mitigation alone and combined with each style, grouped by mitigation."""
    nb, ticks = 1 + len(styles), []
    names = {"pen": "None", "rt": "Reward\ntargeting", "mf": "Mind &\nFace", "tmf": "Targeted\nM&F"}
    for gi, m in enumerate(mits):
        members = [(m, m)] + [(s, s if m == "pen" else f"{s}+{m}") for s in styles]
        for j, (ckey, dkey) in enumerate(members):
            x = gi * (nb + gap) + j
            if dkey not in d:
                ax.text(x, 0.02, "not run", rotation=90, ha="center", va="bottom", fontsize=6, color=GRAY_TXT)
                continue
            ax.bar(x, d[dkey]["cot"], width=0.86, color=COLORS[ckey], lw=0, zorder=2)
            seed_marks(ax, x, d[dkey], jit_w=0.55)
        ticks.append(gi * (nb + gap) + (nb - 1) / 2)
    ax.axhline(d["ctrl"]["cot"], ls="--", lw=0.8, color=C["ctrl"][1], zorder=1)
    ax.set_xticks(ticks)
    ax.set_xticklabels([names[m] for m in mits], fontsize=7.2, linespacing=1.0)
    ax.tick_params(axis="x", length=0)
    style_axes(ax, title, (-0.8, (len(mits) - 1) * (nb + gap) + nb - 0.2))


def legend(fig, keys, extra, single_column=False, **kw):
    """Color legend in columns by condition group, plus a column of markers; bold column headers."""
    cols = [[(Line2D([], [], ls="none"), g, True)] + [(Patch(color=COLORS[k], lw=0), LABELS[k], False)
                                                     for k in ks if k in keys]
            for g, ks in GROUPS if any(k in keys for k in ks)]
    cols.append([(Line2D([], [], ls="none"), "Markers", True)] + [(h, lab, False) for h, lab in extra])
    if not single_column:
        n = max(map(len, cols))
        for c in cols:
            c += [(Line2D([], [], ls="none"), "", False)] * (n - len(c))
        kw["ncol"] = len(cols)
    entries = [e for c in cols for e in c]
    leg = fig.legend([e[0] for e in entries], [e[1] for e in entries], frameon=False, handlelength=1.1,
                     handleheight=0.8, handletextpad=0.5, labelspacing=0.3, columnspacing=1.6, **kw)
    for t, e in zip(leg.get_texts(), entries):
        if e[2]:
            t.set_fontweight("bold")
            t.set_position((-14, 0))


def compose_legend(fig, styles, markers, **kw):
    """Legend of the body's composition figure: mitigations without and with a style, plus markers."""
    hdr = Line2D([], [], ls="none")
    left = [(hdr, "Without style separation", True), (KEY_NOPEN[0], "No penalty", False)] + \
           [(Patch(color=COLORS[k], lw=0), LABELS[k], False) for k in ("pen", "rt", "mf", "tmf")]
    mid = [(hdr, "With style separation (ours)", True)] + \
          [(Patch(color=COLORS[s], lw=0), "+ " + LABELS[s], False) for s in styles]
    right = [(hdr, "Markers", True)] + [(h, lab, False) for h, lab in markers]
    cols = [left, mid, right]
    n = max(map(len, cols))
    for c in cols:
        c += [(hdr, "", False)] * (n - len(c))
    entries = [e for c in cols for e in c]
    leg = fig.legend([e[0] for e in entries], [e[1] for e in entries], ncol=3, frameon=False, handlelength=1.1,
                     handleheight=0.8, handletextpad=0.5, labelspacing=0.3, columnspacing=1.8, **kw)
    for t, e in zip(leg.get_texts(), entries):
        if e[2]:
            t.set_fontweight("bold")
            t.set_position((-14, 0))


def fig_qa_all():
    styles = ["pirate", "piglatin", "chinese"]
    fig, axes = plt.subplots(2, 1, figsize=(W, W * 0.62), sharey=True)
    for ax, (key, title) in zip(axes, [("qa8b", "QA, Qwen3-8B"), ("qa27b", "QA, Qwen3.6-27B")]):
        compose_panel(ax, DATA[key], ["pen", "rt", "mf", "tmf"], styles, title, gap=0.8)
        ax.set_xticklabels(["None", "Reward targeting", "Mind & Face", "Targeted M&F"], fontsize=7.4)
        ax.set_ylabel("CoT hint detection")
    fig.tight_layout(h_pad=1.0)
    compose_legend(fig, styles, [KEY_SEED, KEY_UNSCR], loc="upper center", bbox_to_anchor=(0.5, 0.0))
    fig.savefig(FIG / "qa_all_seeds.pdf")
    plt.close(fig)


def fig_poly():
    fig = plt.figure(figsize=(W, W * 0.34))
    ax = fig.add_axes([0.1, 0.08, 0.48, 0.82])
    groups = [("Controls", ["pen"]), GROUPS[1], GROUPS[2]]
    condition_panel(ax, DATA["poly27b"], "Polynomial, Qwen3.6-27B", groups=groups,
                    ylabel="CoT detection of\nthe expanded form")
    legend(fig, ["pen", "rt", "mf", "tmf", "pirate", "piglatin", "chinese"],
           [KEY_NOPEN, KEY_SEED, KEY_UNSCR, KEY_LOST], single_column=True, loc="center left",
           bbox_to_anchor=(0.62, 0.5))
    fig.savefig(FIG / "poly_seeds.pdf")
    plt.close(fig)


SFT_ROWS = [("No SFT", "#3d3d3a", "ctrl", "pen"), ("Unstyled SFT", COLORS["normalm"], "normalm_ctrl", "normalm"),
            ("Pirate output", COLORS["pirate"], "pirate_ctrl", "pirate"),
            ("Pig-Latin output", COLORS["piglatin"], "piglatin_ctrl", "piglatin"),
            ("Chinese output", COLORS["chinese"], "chinese_ctrl", "chinese"),
            ("Pirate CoT", COLORS["pcot"], "pcot_ctrl", "pcot")]


def dumbbell_panel(ax, d, rows, title, collapsed=None):
    """One row per starting model: hollow = no penalty, filled = penalty, the line between them the drop;
    faint dots are seeds (no penalty above the line, penalty below)."""
    collapsed = collapsed or {}
    for i, (_, col, kc, kp) in enumerate(rows):
        y = -i
        ax.plot([d[kc]["cot"], d[kp]["cot"]], [y, y], color=col, lw=1.8, alpha=0.45, zorder=1,
                solid_capstyle="round")
        for key, dy in ((kc, 0.18), (kp, -0.18)):
            for s in d[key]["seeds"]:
                if s["seed"] in collapsed.get(key, set()):
                    ax.plot(s["cot"], y + dy, "x", ms=3.2, mew=0.8, color=col, zorder=2)
                else:
                    ax.plot(s["cot"], y + dy, "o", ms=2.4, mew=0, color=col, alpha=0.7, zorder=2)
        ax.plot(d[kc]["cot"], y, "o", ms=6, mfc="white", mec=col, mew=1.4, zorder=3)
        ax.plot(d[kp]["cot"], y, "o", ms=6, color=col, zorder=3)
    ax.set_yticks(-np.arange(len(rows)))
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_ylim(-len(rows) + 0.45, 0.55)
    ax.set_xlim(-0.02, 1.02)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_title(title, fontweight="bold", fontsize=7.8)
    ax.set_xlabel("CoT hint detection")


def fig_sft():
    fig, axes = plt.subplots(1, 2, figsize=(W, W * 0.36), sharey=True)
    dumbbell_panel(axes[0], DATA["qa8b"], SFT_ROWS, "QA, Qwen3-8B", collapsed=COLLAPSED["qa8b"])
    dumbbell_panel(axes[1], DATA["qa27b"], SFT_ROWS, "QA, Qwen3.6-27B", collapsed=COLLAPSED["qa27b"])
    fig.tight_layout(w_pad=1.5)
    g = "#5f5e5a"
    hs = [Line2D([], [], ls="none", marker="o", ms=6, mfc="white", mec=g, mew=1.4),
          Line2D([], [], ls="none", marker="o", ms=6, color=g),
          Line2D([], [], ls="none", marker="o", ms=2.4, mew=0, color=g, alpha=0.7),
          Line2D([], [], ls="none", marker="x", ms=3.2, mew=0.8, color=g)]
    ls = ["No penalty", "Output penalty", "Seed", "Seed whose CoT collapsed into filler"]
    fig.legend(hs, ls, loc="upper center", bbox_to_anchor=(0.56, 0.0), ncol=4, frameon=False,
               handletextpad=0.4, columnspacing=1.4)
    fig.savefig(FIG / "sft_dumbbell.pdf")
    plt.close(fig)


def screen_flag(s, qa):
    """Why a no-penalty vs penalty comparison does not measure spillover, or None if it does."""
    c, p = s["ctrl"], s["pen"]
    if c["task"] < 0.5:
        return "never learns the task"
    if p["out"] > 0.25:
        return "output not scrubbed"
    if p["task"] < 0.8:
        if not qa:
            return "task reward falls under the penalty"
        return "stops explaining under the penalty" if p.get("genuine", 1) < 0.8 else \
            "follows the hint less under the penalty"
    if c["cot"] < 0.3:
        return "rarely mentions the hint even without the penalty"
    return None


def fig_screen():
    dark, line = C["ctrl"][1], "#b0aea5"
    panels = [("QA", DATA["screen_qa"], True), ("Polynomial factoring", DATA["screen_poly"], False),
              ("Terminal", DATA["screen_term"], False)]
    nrows = [len(p[1]) for p in panels]
    fig, axes = plt.subplots(len(panels), 1, figsize=(W, 0.15 * sum(nrows) + 1.0), sharex=True,
                             gridspec_kw={"height_ratios": nrows, "hspace": 0.5})
    for ax, (title, rows, qa) in zip(axes, panels):
        names = list(rows)
        for i, m in enumerate(names):
            s, y = rows[m], -i
            f = screen_flag(s, qa)
            al = 0.35 if f else 1.0
            ax.plot([s["ctrl"]["cot"], s["pen"]["cot"]], [y, y], color=line, lw=1.6, alpha=al, zorder=1,
                    solid_capstyle="round")
            for sd in s["pen"]["seeds"]:
                ax.plot(sd["cot"], y, "o", ms=2.2, mew=0, color=dark, alpha=0.45 * al, zorder=2)
            ax.plot(s["ctrl"]["cot"], y, "o", ms=4.6, mfc="white", mec=dark, mew=1.0, alpha=al, zorder=3)
            ax.plot(s["pen"]["cot"], y, "o", ms=4.6, color=dark, alpha=al, zorder=3)
            if f:
                ax.text(1.05, y, f, fontsize=6.6, va="center", color=GRAY_TXT)
        ax.set_yticks(-np.arange(len(names)))
        ax.set_yticklabels(names, fontsize=7.4)
        for t, m in zip(ax.get_yticklabels(), names):
            if screen_flag(rows[m], qa):
                t.set_color(GRAY_TXT)
        ax.set_ylim(-len(names) + 0.4, 0.6)
        ax.set_title(title, fontweight="bold", loc="left", fontsize=8)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(False)
        ax.set_xlim(-0.02, 1.02)
        ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    axes[-1].set_xlabel("CoT detection of the penalized behavior")
    hs = [Line2D([], [], ls="none", marker="o", ms=4.6, mfc="white", mec=dark, mew=1.0),
          Line2D([], [], ls="none", marker="o", ms=4.6, color=dark),
          Line2D([], [], ls="none", marker="o", ms=2.2, mew=0, color=dark, alpha=0.45)]
    fig.subplots_adjust(left=0.27, right=0.62, top=0.905, bottom=0.08)
    fig.legend(hs, ["No penalty", "Plain penalty", "Plain penalty, one seed"], loc="upper center",
               bbox_to_anchor=(0.445, 1.0), ncol=3, frameon=False, handletextpad=0.3, columnspacing=1.2)
    fig.savefig(FIG / "screen.pdf")
    plt.close(fig)


def fig_other_qwen():
    fig = plt.figure(figsize=(W, W * 0.66))
    gs = fig.add_gridspec(2, 2, hspace=0.45, wspace=0.12)
    a = fig.add_subplot(gs[0, 0])
    b, c, e = (fig.add_subplot(gs[i, j], sharey=a) for i, j in ((0, 1), (1, 0), (1, 1)))
    groups = [("Controls", ["pen"]), GROUPS[1], GROUPS[2]]
    condition_panel(a, DATA["qa9b"], "QA, Qwen3.5-9B", groups=groups, ylabel="CoT hint detection")
    compose_panel(b, DATA["qa9b"], ["rt", "mf", "tmf"], ["pirate", "piglatin"], "QA, Qwen3.5-9B, combined")
    condition_panel(c, DATA["qa35b"], "QA, Qwen3.6-35B-A3B", groups=groups, ylabel="CoT hint detection")
    condition_panel(e, DATA["qa397"], "QA, Qwen3.5-397B-A17B", groups=groups)
    for ax in (b, e):
        ax.tick_params(axis="y", labelleft=False)
    fig.subplots_adjust(left=0.09, right=0.99, top=0.95, bottom=0.27)
    legend(fig, ["pen", "rt", "mf", "tmf", "pirate", "piglatin", "chinese"], [KEY_NOPEN, KEY_SEED],
           loc="upper center", bbox_to_anchor=(0.5, 0.19))
    fig.savefig(FIG / "other_qwen.pdf")
    plt.close(fig)


def fig_terminal():
    fig = plt.figure(figsize=(W, W * 0.36))
    ax = fig.add_axes([0.08, 0.08, 0.5, 0.82])
    groups = [("Controls", ["pen"]), GROUPS[1], GROUPS[2]]
    condition_panel(ax, DATA["term8b"], "Terminal, Qwen3-8B", groups=groups, marked=STOPPED, ylabel="CoT detection")
    legend(fig, ["pen", "rt", "mf", "tmf", "pirate", "piglatin", "chinese"],
           [KEY_NOPEN, KEY_SEED, KEY_UNSCR, KEY_STOP], single_column=True,
           loc="center left", bbox_to_anchor=(0.6, 0.5))
    fig.savefig(FIG / "terminal_bars.pdf")
    plt.close(fig)


if __name__ == "__main__":
    fig_qa_all()
    fig_poly()
    fig_sft()
    fig_screen()
    fig_other_qwen()
    fig_terminal()
    print("wrote qa_all_seeds, poly_seeds, sft_dumbbell, screen, other_qwen, terminal_bars")
