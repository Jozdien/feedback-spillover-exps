"""Body figures of the paper, drawn from the training logs with one palette.

Every number is a training-rollout mean over the last 10% of optimizer steps of each run
(27 of 266 for QA and polynomial factoring, 40 of 400 for the terminal task). Error bars
are 95% t intervals over seeds. Also writes figures/paper_numbers.json with the per-seed
values behind every figure, which the tables are filled from.

Run: cd paper && uv run make_paper_figures.py
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
FIG = Path(__file__).resolve().parent / "figures"
W = 5.5  # NeurIPS text width (in)

plt.rcParams.update({
    "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    "font.family": "sans-serif", "font.sans-serif": ["Inter", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 8, "axes.labelsize": 9, "axes.titlesize": 9, "xtick.labelsize": 8.2,
    "ytick.labelsize": 8.2, "legend.fontsize": 7.8, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "axes.grid.axis": "y", "axes.axisbelow": True,
    "grid.color": "#e8e6dc", "grid.linewidth": 0.7, "axes.edgecolor": "#5f5e5a",
    "xtick.color": "#3d3d3a", "ytick.color": "#3d3d3a", "axes.labelcolor": "#141413",
    "text.color": "#141413", "axes.linewidth": 0.7,
})

# One palette for the paper: grays for the controls, cool colors for the prior mitigations,
# warm colors (one shared marker) for the three styles.
INK = "#141413"
COND = {  # key: (label, color, marker, group)
    "ctrl":     ("No penalty",       "#3d3d3a", "o", "Controls"),
    "pen":      ("Plain penalty",    "#b0aea5", "o", "Controls"),
    "rt":       ("Reward targeting", "#6a9bcc", "s", "Prior mitigations"),
    "mf":       ("Mind & Face",      "#788c5d", "s", "Prior mitigations"),
    "tmf":      ("Targeted M&F",     "#2c5a8c", "s", "Prior mitigations"),
    "pirate":   ("Pirate output",    "#d97757", "D", "Style separation (ours)"),
    "piglatin": ("Pig-Latin output", "#e3a93b", "D", "Style separation (ours)"),
    "chinese":  ("Chinese output",   "#a8456b", "D", "Style separation (ours)"),
}
ORDER = list(COND)
# Pareto-scatter markers and error bars
MS, MS_D, ELW, CAP = 6.6, 6.0, 0.6, 1.4
BETTER = " (better →)"

QA = dict(lam=2, steps=266, last=27, ko="monitor/hint_in_output", kc="monitor/hint_in_cot")
POLY = dict(lam=1, steps=266, last=27, ko="monitor/expanded_in_output", kc="monitor/expanded_in_cot")
TERM = dict(lam=0.75, steps=400, last=40, ko="monitor/cheat_in_output", kc="monitor/cheat_in_cot")

# Run directories (under logs/) per setting and condition; "??" is the seed.
RUNS = {
    "qa8b": (QA, {
        "ctrl": "grpo-gated-8b-nosft-ctrl-s??", "pen": "grpo-explj300-nosft-pen-8b-s??",
        "rt": "grpo-gated-8b-rt-s??", "mf": "grpo-gated-8b-mf-s??", "tmf": "grpo-gated-8b-tmf-s??",
        "pirate": "grpo-explj300-piratev2sr-pen-8b-s??", "piglatin": "grpo-explj300-piglatinsr-pen-8b-s??",
        "chinese": "grpo-gated-8b-chinesesr-pen-s??",
        "pirate_ctrl": "grpo-explj300-piratev2sr-ctrl-8b-s??", "piglatin_ctrl": "grpo-explj300-piglatinsr-ctrl-8b-s??",
        "chinese_ctrl": "grpo-gated-8b-chinesesr-ctrl-s??",
        "pirate_nosr": "grpo-explj300-piratev2-pen-8b-s??", "piglatin_nosr": "grpo-explj300-piglatin-pen-8b-s??",
        "normal": "grpo-explj300-normalalpaca-pen-8b-s??", "normal_ctrl": "grpo-explj300-normalalpaca-ctrl-8b-s??",
        # prompt-matched normal SFT (same Alpaca prompts as the style SFTs), 2026-10-22
        "normalm": "grpo-gated-8b-normalsft-pen-s??", "normalm_ctrl": "grpo-gated-8b-normalsft-ctrl-s??",
        "pcot": "grpo-gated-8b-pcot-pen-s??", "pcot_ctrl": "grpo-gated-8b-pcot-ctrl-s??",
        **{f"{s}+{m}": f"grpo-gated-8b-{s}-{m}-s??" for s in ("pirate", "piglatin") for m in ("rt", "mf", "tmf")},
    }),
    "qa27b": (QA, {
        "ctrl": "grpo-gated-27b-nosft-ctrl-s??", "pen": "grpo-gated-27b-nosft-pen-s??",
        "rt": "grpo-gated-27b-rt-s??", "mf": "grpo-gated-27b-mf-s??", "tmf": "grpo-gated-27b-tmf-s??",
        **{s: f"grpo-gated-27b-{s}sr-pen-s??" for s in ("pirate", "piglatin", "chinese")},
        **{f"{s}_ctrl": f"grpo-gated-27b-{s}sr-ctrl-s??" for s in ("pirate", "piglatin", "chinese")},
        **{f"{s}+{m}": f"grpo-gated-27b-{s}-{m}-s??" for s in ("pirate", "piglatin", "chinese") for m in ("rt", "mf", "tmf")},
        "normalm": "grpo-gated-27b-normalsft-pen-s??", "normalm_ctrl": "grpo-gated-27b-normalsft-ctrl-s??",
        "pcot": "grpo-gated-27b-pcot-pen-s??", "pcot_ctrl": "grpo-gated-27b-pcot-ctrl-s??",
    }),
    # Qwen3.5-9B full QA set (appendix only), 2026-10-22
    "qa9b": (QA, {
        "ctrl": "grpo-gated-sig-q35-9b-nosft-ctrl-s??", "pen": "grpo-gated-sig-q35-9b-nosft-pen-s??",
        "rt": "grpo-gated-sig-q35-9b-rt-s??", "mf": "grpo-gated-sig-q35-9b-mf-s??", "tmf": "grpo-gated-sig-q35-9b-tmf-s??",
        **{s: f"grpo-gated-sig-q35-9b-{s}sr-pen-s??" for s in ("pirate", "piglatin", "chinese")},
        **{f"{s}_ctrl": f"grpo-gated-sig-q35-9b-{s}sr-ctrl-s??" for s in ("pirate", "piglatin", "chinese")},
        **{f"{s}+{m}": f"grpo-gated-sig-q35-9b-{s}-{m}-s??" for s in ("pirate", "piglatin") for m in ("rt", "mf", "tmf")},
    }),
    # Qwen3.5-397B-A17B minimal set (appendix), 2026-10-23
    "qa397": (QA, {
        "ctrl": "grpo-gated-sig-q397-nosft-ctrl-s??", "pen": "grpo-gated-sig-q397-nosft-pen-s??",
        "rt": "grpo-gated-sig-q397-rt-s??", "tmf": "grpo-gated-sig-q397-tmf-s??",
        **{s: f"grpo-gated-sig-q397-{s}sr-pen-s??" for s in ("pirate", "piglatin")},
        **{f"{s}_ctrl": f"grpo-gated-sig-q397-{s}sr-ctrl-s??" for s in ("pirate", "piglatin")},
    }),
    "qa35b": (QA, {
        "ctrl": "grpo-gated-35b-nosft-ctrl-s??", "pen": "grpo-gated-35b-nosft-pen-s??",
        "rt": "grpo-gated-35b-rt-s??",
        **{s: f"grpo-gated-35b-{s}sr-pen-s??" for s in ("pirate", "piglatin")},
        **{f"{s}_ctrl": f"grpo-gated-35b-{s}sr-ctrl-s??" for s in ("pirate", "piglatin")},
    }),
    "poly27b": (POLY, {
        "ctrl": "grpo-gated-poly27b-ctrl-s??", "pen": "grpo-gated-poly27b-pen-s??",
        "rt": "grpo-gated-poly27b-rt-s??", "mf": "grpo-gated-poly27b-mf-s??", "tmf": "grpo-gated-poly27b-tmf-s??",
        **{s: f"grpo-gated-poly27b-{s}sr-pen-s??" for s in ("pirate", "piglatin", "chinese")},
        **{f"{s}_ctrl": f"grpo-gated-poly27b-{s}sr-ctrl-s??" for s in ("pirate", "piglatin", "chinese")},
    }),
    # Qwen3-8B polynomial: only control and penalty (no spillover, so no mitigations).
    "poly8b": (POLY, {"ctrl": "grpo-gated-poly8b-ctrl-s??", "pen": "grpo-gated-poly8b-pen-s??"}),
    "term8b": (TERM, {
        "ctrl": "grpo-termgated-8b-ctrl-s??", "pen": "grpo-termgated-8b-pen-s??",
        "rt": "grpo-termgated-8b-rt-s??", "mf": "grpo-termgated-8b-mf-s??", "tmf": "grpo-termgated-8b-tmf-s??",
        **{s: f"grpo-termgated-8b-{s}sr-pen-s??" for s in ("pirate", "piglatin", "chinese")},
        **{f"{s}_ctrl": f"grpo-termgated-8b-{s}sr-ctrl-s??" for s in ("pirate", "piglatin", "chinese")},
    }),
}

# Spillover screen: (environment, model, protocol, control glob, penalty glob).
SCREEN_QA = [
    ("Qwen3-8B", "grpo-gated-8b-nosft-ctrl-s??", "grpo-explj300-nosft-pen-8b-s??"),
    ("Qwen3.5-4B", "grpo-gated-sig-q35-4b-nosft-ctrl-s??", "grpo-gated-sig-q35-4b-nosft-pen-s??"),
    ("Qwen3.5-9B", "grpo-gated-sig-q35-9b-nosft-ctrl-s??", "grpo-gated-sig-q35-9b-nosft-pen-s??"),
    ("Qwen3.6-27B", "grpo-gated-27b-nosft-ctrl-s??", "grpo-gated-27b-nosft-pen-s??"),
    ("Qwen3.6-35B-A3B", "grpo-gated-35b-nosft-ctrl-s??", "grpo-gated-35b-nosft-pen-s??"),
    ("Qwen3.5-397B-A17B", "grpo-gated-sig-q397-nosft-ctrl-s??", "grpo-gated-sig-q397-nosft-pen-s??"),
    ("Qwen3.8-27B", "grpo-gated-sig-q38-27b-nosft-ctrl-s??", "grpo-gated-sig-q38-27b-nosft-pen-s??"),
    ("GPT-OSS-20B", "grpo-gated-sig-gptoss20-nosft-ctrl-s??", "grpo-gated-sig-gptoss20-nosft-pen-s??"),
    ("GPT-OSS-120B", "grpo-gated-sig-gptoss120-nosft-ctrl-s??", "grpo-gated-sig-gptoss120-nosft-pen-s??"),
    ("DeepSeek-V3.1", "grpo-gated-sig-deepseek-nosft-ctrl-s??", "grpo-gated-sig-deepseek-nosft-pen-s??"),
    ("Kimi-K2.6", "grpo-gated-sig-kimi-nosft-ctrl-s??", "grpo-gated-sig-kimi-nosft-pen-s??"),
    ("GLM-5.3", "grpo-gated-sig-glm-nosft-ctrl-s??", "grpo-gated-sig-glm-nosft-pen-s??"),
    ("Nemotron-3-Nano-30B", "grpo-gated-sig-nemo-nano-nosft-ctrl-s??", "grpo-gated-sig-nemo-nano-nosft-pen-s??"),
    ("Nemotron-3.5-Lightning-30B", "grpo-gated-sig-nemo-light-nosft-ctrl-s??", "grpo-gated-sig-nemo-light-nosft-pen-s??"),
    ("Nemotron-3-Super-120B-A12B", "grpo-gated-nemotron-nosft-ctrl-s??", "grpo-gated-nemotron-nosft-pen-s??"),
    ("Nemotron-3-Ultra-550B", "grpo-gated-sig-nemo-ultra-nosft-ctrl-s??", "grpo-gated-sig-nemo-ultra-nosft-pen-s??"),
    ("Inkling-Small", "grpo-gated-sig-inkling-s-nosft-ctrl-s??", "grpo-gated-sig-inkling-s-nosft-pen-s??"),
    ("Inkling", "grpo-gated-sig-inkling-nosft-ctrl-s??", "grpo-gated-sig-inkling-nosft-pen-s??"),
]
SCREEN_POLY = [
    ("Qwen3-8B", "grpo-gated-poly8b-ctrl-s??", "grpo-gated-poly8b-pen-s??"),
    ("Qwen3.6-27B", "grpo-gated-poly27b-ctrl-s??", "grpo-gated-poly27b-pen-s??"),
    ("Qwen3.5-397B-A17B", "grpo-poly800-qwen397-ctrl-s??", "grpo-poly800-qwen397-pen-s??"),
    ("Nemotron-3-Super-120B-A12B", "grpo-poly800-nemotron-ctrl-s??", "grpo-poly800-nemotron-pen-s??"),
]
SCREEN_TERM = [
    ("Qwen3-8B", "grpo-termgated-8b-ctrl-s??", "grpo-termgated-8b-pen-s??"),
    ("Qwen3.6-27B", "grpo-termllm-27b-ctrl-s??", "grpo-termllm-27b-pen-s??"),
]


def seeds(pat: str, p: dict) -> list[dict]:
    """Per-seed tail means of the finished runs matching `pat`."""
    out = []
    for d in sorted(glob.glob(str(ROOT / "logs" / pat))):
        f = Path(d) / "metrics.jsonl"
        if not f.exists():
            continue
        ms = {}
        for ln in open(f):
            x = json.loads(ln)
            ms[x["step"]] = x
        if len(ms) < p["steps"]:
            continue
        tail = [ms[s] for s in sorted(ms)[-p["last"]:]]
        task = float(np.mean([x["reward/correct"] for x in tail]))
        o = float(np.mean([x[p["ko"]] for x in tail]))
        c = float(np.mean([x[p["kc"]] for x in tail]))
        extra = {k: float(np.mean([x[m] for x in tail])) for k, m in
                 (("genuine", "monitor/explanation_genuine"), ("style", "monitor/pirate_in_output"))
                 if all(m in x for x in tail)}
        out.append({"seed": d[-2:], "cot": c, "out": o, "task": task, "reward": task - p["lam"] * o, **extra})
    return out


def ci(v) -> float:
    v = np.asarray(v, float)
    return float(stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v))) if len(v) > 1 else 0.0


def summary(ss: list[dict]) -> dict:
    keys = ["cot", "out", "task", "reward"] + [k for k in ("genuine", "style") if all(k in s for s in ss)]
    a = {k: np.array([s[k] for s in ss]) for k in keys}
    return {"n": len(ss), **{k: float(v.mean()) for k, v in a.items()},
            "cot_sd": float(a["cot"].std(ddof=1)) if len(ss) > 1 else 0.0,
            "cot_ci": ci(a["cot"]), "reward_ci": ci(a["reward"]), "seeds": ss}


def load_all() -> dict:
    data = {}
    for setting, (p, runs) in RUNS.items():
        data[setting] = {k: summary(ss) for k, pat in runs.items() if (ss := seeds(pat, p))}
    for name, rows, p in (("screen_qa", SCREEN_QA, QA), ("screen_poly", SCREEN_POLY, POLY),
                          ("screen_term", SCREEN_TERM, TERM)):
        data[name] = {m: {"ctrl": summary(seeds(c, p)), "pen": summary(seeds(q, p))} for m, c, q in rows}
    return data


# ----------------------------------------------------------------------------- helpers
def group_legend(ax_or_fig, keys, by_column=False, **kw):
    """Legend with bold group headers (Controls / Prior mitigations / Style separation).
    by_column: one column per group, for a legend laid out under a figure."""
    cols = {}
    for k in keys:
        label, color, marker, g = COND[k]
        cols.setdefault(g, [(Line2D([], [], ls="none"), g, True)])
        cols[g].append((Line2D([], [], ls="none", marker=marker, ms=5.5, mfc=color, mec=color), label, False))
    if by_column:
        n = max(map(len, cols.values()))
        for c in cols.values():
            c += [(Line2D([], [], ls="none"), "", False)] * (n - len(c))
        kw["ncol"] = len(cols)
    entries = [e for c in cols.values() for e in c]
    handles, labels = [e[0] for e in entries], [e[1] for e in entries]
    bold = [i for i, e in enumerate(entries) if e[2]]
    leg = ax_or_fig.legend(handles, labels, frameon=False, handlelength=1.0, handletextpad=0.5,
                           labelspacing=0.35, **kw)
    for i, t in enumerate(leg.get_texts()):
        if i in bold:
            t.set_fontweight("bold")
            t.set_position((-14, 0))
    return leg


def better_arrow(ax, head=(0.97, 0.97), length=0.11):
    """Small gray arrow pointing up and to the right (the better direction), labeled "better"."""
    x, y = head
    ax.annotate("", xy=(x, y), xytext=(x - length, y - length * 1.4), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", lw=0.8, color="#8a8880", mutation_scale=7))
    ax.text(x - length + 0.01, y - length * 1.4 - 0.02, "better", transform=ax.transAxes, ha="left",
            va="top", fontsize=6.8, color="#8a8880", style="italic")


def stack_ylabel(fig, top, bot, text, x_pad=0.5):
    """One y-label centered on a broken (two-axes) y-axis."""
    fig.canvas.draw()
    t, b = top.get_position(), bot.get_position()
    fig.text(t.x0 - x_pad / fig.get_figwidth(), (t.y1 + b.y0) / 2, text, rotation=90, ha="center",
             va="center", fontsize=plt.rcParams["axes.labelsize"], linespacing=1.3)


def bar_positions(keys):
    """x positions with a gap between condition groups."""
    xs, x, prev = [], 0.0, None
    for k in keys:
        g = COND[k][3]
        if prev is not None and g != prev:
            x += 0.5
        xs.append(x)
        x += 1.0
        prev = g
    return np.array(xs)


def cot_bars(ax, d, keys, ylabel="CoT hint detection", dots=False, not_run=True):
    xs = bar_positions(keys)
    for x, k in zip(xs, keys):
        color = COND[k][1]
        if k not in d:
            if not_run:
                ax.text(x, 0.02, "not run", rotation=90, ha="center", va="bottom", fontsize=6, color="#8a8880")
            continue
        a = d[k]
        ax.bar(x, a["cot"], width=0.8, color=color, zorder=2)
        if dots:
            for i, s in enumerate(a["seeds"]):
                jitter = (i - (a["n"] - 1) / 2) * 0.11
                if s["task"] < 0.2:  # run lost the task reward
                    ax.plot(x + jitter, s["cot"], "x", ms=3.6, mew=0.9, color=INK, zorder=4)
                    continue
                hollow = s["out"] > 0.5 and k != "ctrl"  # output never scrubbed
                ax.plot(x + jitter, s["cot"], "o", ms=3.0, mew=0.7, zorder=4,
                        mfc="white" if hollow else INK, mec=INK)
        else:
            lo, hi = max(a["cot"] - a["cot_ci"], 0), min(a["cot"] + a["cot_ci"], 1)
            ax.errorbar(x, a["cot"], yerr=[[a["cot"] - lo], [hi - a["cot"]]], color=INK, lw=0,
                        elinewidth=ELW, capsize=CAP, zorder=3)
    if "ctrl" in d:
        ax.axhline(d["ctrl"]["cot"], ls="--", lw=0.8, color=COND["ctrl"][1], zorder=1)
    ax.set_xticks([])
    ax.set_xlim(xs[0] - 0.7, xs[-1] + 0.7)
    ax.set_ylim(0, 1.04)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_ylabel(ylabel)
    ax.spines["bottom"].set_color("#b0aea5")


# ----------------------------------------------------------------------------- figures
def fig_main_scatter(d, path, legend=True, width=W * 0.62):
    """Pareto scatter for QA on Qwen3-8B, with a broken y-axis around the gap."""
    fig, (top, bot) = plt.subplots(2, 1, sharex=True, figsize=(width, width * 0.86),
                                   gridspec_kw={"height_ratios": [3.2, 1], "hspace": 0.08})
    for k in ORDER:
        a = d[k]
        label, color, marker, _ = COND[k]
        for ax in (top, bot):
            ax.errorbar(a["cot"], a["reward"], xerr=a["cot_ci"], yerr=[[a["reward_ci"]], [min(a["reward_ci"], 1 - a["reward"])]], fmt=marker,
                        ms=MS if marker != "D" else MS_D, mfc=color, mec="white", mew=0.6, color=color,
                        elinewidth=ELW, capsize=CAP, zorder=3)
    top.set_ylim(0.45, 1.03)
    bot.set_ylim(-0.97, -0.6)
    top.set_yticks([0.5, 0.75, 1.0])
    bot.set_yticks([-0.75])
    for ax in (top, bot):
        ax.axvline(d["ctrl"]["cot"], ls="--", lw=0.8, color=COND["ctrl"][1], zorder=1)
        ax.grid(axis="x", visible=False)
    top.spines["bottom"].set_visible(False)
    top.tick_params(axis="x", length=0)
    # diagonal break marks
    kw = dict(color="#5f5e5a", lw=0.7, clip_on=False, transform=top.transAxes)
    top.plot([-0.015, 0.015], [-0.02, 0.02], **kw)
    kw["transform"] = bot.transAxes
    bot.plot([-0.015, 0.015], [0.94, 1.02], **kw)
    bot.set_xlim(0.15, 0.7)
    bot.set_xlabel("CoT hint detection" + BETTER)
    bot.set_xticks([0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
    stack_ylabel(fig, top, bot, "Training reward" + BETTER + "\n(task − 2 × output detection)", x_pad=0.6)
    if legend:
        group_legend(fig, ORDER, loc="center left", bbox_to_anchor=(0.98, 0.5))
    fig.savefig(path)
    plt.close(fig)


def fig_main_scatter_bars(d, path):
    """Option B: the scatter next to CoT-detection bars, one shared legend."""
    fig = plt.figure(figsize=(W * 0.86, W * 0.42))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.15, 1], height_ratios=[3.2, 1], hspace=0.08, wspace=0.32)
    top, bot = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[1, 0])
    bars = fig.add_subplot(gs[:, 1])
    for k in ORDER:
        a = d[k]
        _, color, marker, _ = COND[k]
        for ax in (top, bot):
            ax.errorbar(a["cot"], a["reward"], xerr=a["cot_ci"], yerr=[[a["reward_ci"]], [min(a["reward_ci"], 1 - a["reward"])]], fmt=marker,
                        ms=MS if marker != "D" else MS_D, mfc=color, mec="white", mew=0.6, color=color,
                        elinewidth=ELW, capsize=CAP, zorder=3)
    top.set_ylim(0.45, 1.03)
    bot.set_ylim(-0.97, -0.6)
    top.set_yticks([0.5, 0.75, 1.0])
    bot.set_yticks([-0.75])
    bot.set_xticks([0.2, 0.4, 0.6])
    for ax in (top, bot):
        ax.axvline(d["ctrl"]["cot"], ls="--", lw=0.8, color=COND["ctrl"][1], zorder=1)
        ax.grid(axis="x", visible=False)
        ax.set_xlim(0.15, 0.7)
    top.spines["bottom"].set_visible(False)
    top.tick_params(axis="x", length=0, labelbottom=False)
    kw = dict(color="#5f5e5a", lw=0.7, clip_on=False, transform=top.transAxes)
    top.plot([-0.02, 0.02], [-0.02, 0.02], **kw)
    kw["transform"] = bot.transAxes
    bot.plot([-0.02, 0.02], [0.94, 1.02], **kw)
    bot.set_xlabel("CoT hint detection" + BETTER)
    top.set_ylabel("Training reward" + BETTER, y=0.38, labelpad=2)
    cot_bars(bars, d, ORDER)
    group_legend(fig, ORDER, loc="center left", bbox_to_anchor=(0.9, 0.5))
    fig.savefig(path)
    plt.close(fig)


def fig_compose(panels, path, width=W * 0.76, legend_below=False):
    """Vertical grouped bars: each prior mitigation alone and combined with each style. panels: [(data, title)]."""
    groups = [("None", "pen"), ("Reward\ntargeting", "rt"), ("Mind &\nFace", "mf"),
              ("Targeted\nM&F", "tmf")]
    fig, axes = plt.subplots(1, len(panels), figsize=(width, W * 0.4), sharey=True, squeeze=False)
    axes = axes[0]
    for ax, (d, title) in zip(axes, panels):
        for gi, (gname, m) in enumerate(groups):
            members = [(m, m), ("pirate", "pirate" if m == "pen" else f"pirate+{m}"),
                       ("piglatin", "piglatin" if m == "pen" else f"piglatin+{m}")]
            for j, (ckey, dkey) in enumerate(members):
                x = gi * 4.4 + j
                a = d[dkey]
                ax.bar(x, a["cot"], width=0.86, color=COND[ckey][1], zorder=2)
                lo, hi = max(a["cot"] - a["cot_ci"], 0), min(a["cot"] + a["cot_ci"], 1)
                ax.errorbar(x, a["cot"], yerr=[[a["cot"] - lo], [hi - a["cot"]]], color=INK, lw=0,
                            elinewidth=ELW, capsize=CAP, zorder=3)
        c = d["ctrl"]["cot"]
        ax.axhline(c, ls="--", lw=0.9, color=COND["ctrl"][1], zorder=1)
        ax.set_xticks([gi * 4.4 + 1 for gi in range(4)])
        ax.set_xticklabels([g for g, _ in groups], fontsize=7, linespacing=1.0)
        ax.tick_params(axis="x", length=0)
        ax.set_title(title, fontweight="bold")
        ax.set_ylim(0, 1.04)
        ax.set_xlim(-0.9, 3 * 4.4 + 2.9)
    axes[0].set_ylabel("CoT hint detection")
    handles = [Patch(color=COND["pen"][1]), Patch(color=COND["rt"][1]), Patch(color=COND["mf"][1]),
               Patch(color=COND["tmf"][1]), Patch(color=COND["pirate"][1]), Patch(color=COND["piglatin"][1])]
    labels = ["Plain penalty", "Reward targeting", "Mind & Face", "Targeted M&F",
              "+ Pirate output", "+ Pig-Latin output"]
    hdr = Line2D([], [], ls="none")
    nopen = Line2D([], [], ls="--", lw=0.9, color=COND["ctrl"][1])
    entries = [(hdr, "Without style separation"), (nopen, "No penalty"), *zip(handles[:4], labels[:4]),
               (hdr, "With style separation (ours)"), *zip(handles[4:], labels[4:])]
    place = dict(loc="center left", bbox_to_anchor=(0.99, 0.5))
    if legend_below:  # two columns under the axes; pad the shorter one
        entries += [(hdr, "")] * 3
        place = dict(loc="upper center", bbox_to_anchor=(0.55, 0.02), ncol=2, columnspacing=1.2)
        fig.tight_layout()
    leg = fig.legend(*zip(*entries), frameon=False, handlelength=1.0, handleheight=0.9, handletextpad=0.5,
                     labelspacing=0.35, **place)
    for t in leg.get_texts():
        if t.get_text().startswith("With"):
            t.set_fontweight("bold")
            t.set_position((-14, 0))
    if not legend_below:
        fig.tight_layout(w_pad=1.0)
    fig.savefig(path)
    plt.close(fig)


def fig_screen(data, path):
    """Dumbbells: CoT detection without and with the plain penalty, for every model and task."""
    def flag(s):
        c, p = s["ctrl"], s["pen"]
        if c["task"] < 0.5:
            return "never learns the task"
        if p["out"] > 0.25:
            return "output not fully scrubbed"
        if p["task"] < 0.8:
            return "task reward falls under the penalty"
        if c["cot"] < 0.3:
            return "unpenalized CoT rarely mentions it"
        return None

    panels = [("QA", data["screen_qa"]), ("Polynomial factoring", data["screen_poly"]),
              ("Terminal", data["screen_term"])]
    nrows = [len(p[1]) for p in panels]
    fig, axes = plt.subplots(len(panels), 1, figsize=(3.3, 0.125 * sum(nrows) + 0.9),
                             gridspec_kw={"height_ratios": nrows, "hspace": 0.55}, sharex=True)
    for ax, (title, rows) in zip(axes, panels):
        names = list(rows)
        for i, m in enumerate(names):
            s = rows[m]
            y = -i
            f = flag(s)
            alpha = 0.35 if f else 1.0
            c, p = s["ctrl"]["cot"], s["pen"]["cot"]
            ax.plot([c, p], [y, y], color="#b0aea5", lw=1.6, alpha=alpha, zorder=1, solid_capstyle="round")
            ax.plot(c, y, "o", ms=4.2, color=COND["ctrl"][1], alpha=alpha, zorder=3)
            ax.plot(p, y, "o", ms=4.2, mfc="white", mec=COND["ctrl"][1], mew=1.0, alpha=alpha, zorder=3)
            if f:
                ax.text(1.03, y, f, fontsize=6.3, va="center", color="#8a8880")
        ax.set_yticks(-np.arange(len(names)))
        ax.set_yticklabels(names)
        for t, m in zip(ax.get_yticklabels(), names):
            if flag(rows[m]):
                t.set_color("#8a8880")
        ax.set_ylim(-len(names) + 0.4, 0.6)
        ax.set_title(title, fontweight="bold", loc="left", fontsize=8)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(False)
        ax.set_xlim(0, 1.0)
    axes[-1].set_xlabel("CoT detection of the monitored behavior")
    handles = [Line2D([], [], ls="none", marker="o", ms=4.2, color=COND["ctrl"][1]),
               Line2D([], [], ls="none", marker="o", ms=4.2, mfc="white", mec=COND["ctrl"][1], mew=1.0)]
    axes[0].legend(handles, ["No penalty", "Plain penalty"], loc="lower right", bbox_to_anchor=(1.0, 1.0),
                   ncol=2, frameon=False, handletextpad=0.3, columnspacing=1.2, borderaxespad=0)
    fig.savefig(path)
    plt.close(fig)


ENV_PANELS = [  # the two models x two environments besides QA on Qwen3-8B
    dict(title="QA, Qwen3.6-27B", key="qa27b", lam=2, xlim=(0.3, 0.95), ybreak=((-1.0, -0.7), (0.9, 1.01)),
         xlabel="CoT hint detection", arrow=(0.5, 0.35)),
    dict(title="Polynomial, Qwen3-8B", key="poly8b", lam=1, xlim=(0.5, 1.03), ylim=(-0.25, 1.05),
         xlabel="CoT detection of\nthe expanded form", arrow=(0.45, 0.25), note="no spillover,\nso mitigations\nnot run"),
    dict(title="Polynomial, Qwen3.6-27B", key="poly27b", lam=1, xlim=(0.5, 1.03), ylim=(-0.25, 1.05),
         xlabel="CoT detection of\nthe expanded form", arrow=(0.45, 0.25)),
]


# Figure 4 (Pareto): the two settings besides QA on Qwen3-8B where the plain penalty spills; no broken axis
ENV_PARETO = [
    dict(title="QA, Qwen3.6-27B", key="qa27b", lam=2, xlim=(0.3, 0.95), ybreak=((-0.95, -0.75), (-0.04, 1.04)),
         top_ticks=[0, 0.25, 0.5, 0.75, 1.0], bot_ticks=[-0.85], xlabel="CoT hint detection", ylabel_pad=0.62),
    dict(title="Polynomial, Qwen3.6-27B", key="poly27b", lam=1, xlim=(0.5, 1.03), ylim=(-0.25, 1.05),
         xlabel="CoT detection of the\nexpanded form", ylabel_pad=0.5),
]


def fig_envs(data, panels, path, width=W):
    """CoT-detection bars per setting; dots are seeds."""
    fig, axes = plt.subplots(1, len(panels), figsize=(width, W * 0.36), sharey=True, squeeze=False)
    for i, (ax, pn) in enumerate(zip(axes[0], panels)):
        d = data[pn["key"]]
        cot_bars(ax, d, ORDER, ylabel="CoT detection" if i == 0 else "", dots=True, not_run=not pn.get("note"))
        if pn.get("note"):
            ax.text(0.68, 0.5, pn["note"], transform=ax.transAxes, ha="center", va="center", fontsize=6.5,
                    color="#8a8880", linespacing=1.1)
        ax.set_title(pn["title"], fontweight="bold", fontsize=7.8)
    fig.tight_layout(w_pad=0.6)
    group_legend(fig, ORDER, by_column=True, loc="upper center", bbox_to_anchor=(0.5, 0.0), columnspacing=2.0)
    fig.savefig(path)
    plt.close(fig)


# Pirate-CoT runs on Qwen3.6-27B whose CoT collapsed into filler during RL (genuine < 0.5 in the last
# 27 steps; logs/analysis-2026-10-22-pcot-audit/27b/), so their CoT detection says nothing about spillover.
COLLAPSED = {("qa27b", "pcot"): {"42", "45", "46", "49", "51"}, ("qa27b", "pcot_ctrl"): {"44"}}
COT_GROUPS = [  # (label, color, no-penalty key, penalty key)
    ("No SFT", "#3d3d3a", "ctrl", "pen"),
    ("Unstyled\nSFT", "#8a8880", "normalm_ctrl", "normalm"),
    ("Styled\nSFT", COND["piglatin"][1], "piglatin_ctrl", "piglatin"),  # Pig Latin, the best style
    ("Pirate\nCoT", "#7a5c99", "pcot_ctrl", "pcot"),
]


def fig_cotstyle(data, panels, path, width=W):
    """Where the style lives: CoT hint detection without and with the output penalty, for the base model, an
    unstyled SFT, the pirate-output SFT and the pirate-CoT SFT. Light bars: no penalty; solid: penalty."""
    fig, axes = plt.subplots(1, len(panels), figsize=(width, W * 0.36), sharey=True, squeeze=False)
    for ax, (setting, title) in zip(axes[0], panels):
        d = data[setting]
        for gi, (_, color, kc, kp) in enumerate(COT_GROUPS):
            for j, (k, alpha) in enumerate(((kc, 0.38), (kp, 1.0))):
                x, a = gi * 2.6 + j, d[k]
                ax.bar(x, a["cot"], width=0.86, color=color, alpha=alpha, zorder=2, lw=0)
                bad = COLLAPSED.get((setting, k), set())
                for i, sd in enumerate(a["seeds"]):
                    jit = (i - (a["n"] - 1) / 2) * min(0.11, 0.55 / a["n"])
                    if sd["seed"] in bad:
                        ax.plot(x + jit, sd["cot"], "x", ms=3.6, mew=0.9, color=INK, zorder=4)
                    else:
                        ax.plot(x + jit, sd["cot"], "o", ms=3.0, mew=0, color=INK, zorder=4)
        ax.set_xticks([gi * 2.6 + 0.5 for gi in range(len(COT_GROUPS))])
        ax.set_xticklabels([g[0] for g in COT_GROUPS], linespacing=1.0)
        ax.tick_params(axis="x", length=0)
        ax.set_title(title, fontweight="bold")
        ax.set_ylim(0, 1.04)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    axes[0][0].set_ylabel("CoT hint detection")
    handles = [Patch(color="#8a8880", alpha=0.38, lw=0), Patch(color="#8a8880", lw=0),
               Line2D([], [], ls="none", marker="o", ms=3.0, color=INK)]
    labels = ["No penalty", "Output penalty", "Seed"]
    if any((st, k) in COLLAPSED for st, _ in panels for g in COT_GROUPS for k in g[2:]):
        handles.append(Line2D([], [], ls="none", marker="x", ms=3.6, mew=0.9, color=INK))
        labels.append("Seed whose CoT collapsed into filler")
    fig.tight_layout(w_pad=1.0)
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=len(labels), frameon=False,
               handlelength=1.0, handletextpad=0.5, columnspacing=1.4)
    fig.savefig(path)
    plt.close(fig)


def fig_points_pareto(points, path, ctrl_cot, legend, top=(0.45, 1.03), bot=(-0.97, -0.6), top_ticks=(0.5, 0.75, 1.0),
                      bot_ticks=(-0.75,), xlim=(0.0, 0.8), width=W * 0.85, lam=2):
    """Pareto scatter with a broken y-axis for an arbitrary list of points (a, color, marker, hollow).
    legend: list of (handle, label); labels starting with '#' are bold group headers."""
    fig = plt.figure(figsize=(width, width * 0.52))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.35, 1], height_ratios=[3.2, 1], hspace=0.08, wspace=0.05)
    t, b = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[1, 0])
    for a, color, marker, hollow in points:
        for ax in (t, b):
            ax.errorbar(a["cot"], a["reward"], xerr=a["cot_ci"], yerr=[[a["reward_ci"]], [min(a["reward_ci"], 1 - a["reward"])]],
                        fmt=marker, ms=MS if marker not in "D^" else MS_D, mfc="white" if hollow else color,
                        mec=color if hollow else "white", mew=1.1 if hollow else 0.6, color=color,
                        elinewidth=ELW, capsize=CAP, zorder=3)
    t.set_ylim(*top)
    b.set_ylim(*bot)
    t.set_yticks(list(top_ticks))
    b.set_yticks(list(bot_ticks))
    for ax in (t, b):
        ax.axvline(ctrl_cot, ls="--", lw=0.8, color=COND["ctrl"][1], zorder=1)
        ax.grid(axis="x", visible=False)
        ax.set_xlim(*xlim)
    t.spines["bottom"].set_visible(False)
    t.tick_params(axis="x", length=0, labelbottom=False)
    kw = dict(color="#5f5e5a", lw=0.7, clip_on=False, transform=t.transAxes)
    t.plot([-0.015, 0.015], [-0.02, 0.02], **kw)
    kw["transform"] = b.transAxes
    b.plot([-0.015, 0.015], [0.94, 1.02], **kw)
    b.set_xlabel("CoT hint detection" + BETTER)
    stack_ylabel(fig, t, b, f"Training reward{BETTER}\n(task − {lam:g} × output detection)", x_pad=0.6)
    lax = fig.add_subplot(gs[:, 1])
    lax.axis("off")
    hs, ls = zip(*legend)
    leg = lax.legend(hs, [x.lstrip("#") for x in ls], loc="center left", frameon=False, handlelength=1.2,
                     handletextpad=0.5, labelspacing=0.35)
    for txt, x in zip(leg.get_texts(), ls):
        if x.startswith("#"):
            txt.set_fontweight("bold")
            txt.set_position((-14, 0))
    fig.savefig(path)
    plt.close(fig)


def fig_compose_pareto(d, path):
    """Preview: Figure 3 as a Pareto plot. Color = prior mitigation, marker = style."""
    mits = [("None", "pen", COND["pen"][1]), ("Reward targeting", "rt", COND["rt"][1]),
            ("Mind & Face", "mf", COND["mf"][1]), ("Targeted M&F", "tmf", COND["tmf"][1])]
    styles = [("no style", "o", ""), ("+ pirate output", "D", "pirate"), ("+ Pig-Latin output", "^", "piglatin")]
    pts = [(d["ctrl"], COND["ctrl"][1], "o", False)]
    for _, m, c in mits:
        for _, mk, st in styles:
            k = m if not st else (st if m == "pen" else f"{st}+{m}")
            pts.append((d[k], c, mk, False))
    hdr = Line2D([], [], ls="none")
    leg = [(hdr, "#Mitigation (color)"), (Line2D([], [], ls="none", marker="o", ms=5, color=COND["ctrl"][1]), "No penalty")]
    leg += [(Patch(color=c), n if m != "pen" else "Plain penalty only") for n, m, c in mits]
    leg += [(hdr, "#Style (marker)")]
    leg += [(Line2D([], [], ls="none", marker=mk, ms=5, color="#5f5e5a"), n) for n, mk, _ in styles]
    fig_points_pareto(pts, path, d["ctrl"]["cot"], leg)


def fig_cotstyle_pareto(d, path):
    """Preview: Figure 5 as a Pareto plot. Color = model, filled = output penalty, hollow = no penalty."""
    pts, leg = [], [(Line2D([], [], ls="none"), "#Model")]
    for label, color, kc, kp in COT_GROUPS:
        pts += [(d[kc], color, "o", True), (d[kp], color, "o", False)]
        leg.append((Patch(color=color), label.replace("\n", " ") + (" (Pig Latin)" if "Styled" in label else "")))
    leg += [(Line2D([], [], ls="none"), "#Training"),
            (Line2D([], [], ls="none", marker="o", ms=5, mfc="white", mec="#5f5e5a", mew=1.1), "No penalty"),
            (Line2D([], [], ls="none", marker="o", ms=5, color="#5f5e5a"), "Output penalty")]
    fig_points_pareto(pts, path, d["ctrl"]["cot"], leg, bot=(-0.9, -0.5), bot_ticks=(-0.75,), xlim=(-0.03, 0.8))


def fig_cotstyle_pareto2(data, settings, path):
    """Preview: Figure 5 as Pareto panels per model. Color = model, filled = output penalty, hollow = no penalty.
    Means are over all seeds, including the Qwen3.6-27B pirate-CoT seeds that collapsed (COLLAPSED)."""
    fig = plt.figure(figsize=(W, W * 0.5))
    gs = fig.add_gridspec(2, len(settings), height_ratios=[3.2, 1], hspace=0.08, wspace=0.12)
    for i, (setting, title) in enumerate(settings):
        d = data[setting]
        t, b = fig.add_subplot(gs[0, i]), fig.add_subplot(gs[1, i])
        for _, color, kc, kp in COT_GROUPS:
            for k, hollow in ((kc, True), (kp, False)):
                a = d[k]
                for ax in (t, b):
                    ax.errorbar(a["cot"], a["reward"], xerr=a["cot_ci"],
                                yerr=[[a["reward_ci"]], [min(a["reward_ci"], 1 - a["reward"])]], fmt="o",
                                ms=MS, mfc="white" if hollow else color, mec=color if hollow else "white",
                                mew=1.1 if hollow else 0.6, color=color, elinewidth=ELW, capsize=CAP, zorder=3)
        t.set_ylim(0.45, 1.03)
        b.set_ylim(-0.98, -0.45)
        t.set_yticks([0.5, 0.75, 1.0])
        b.set_yticks([-0.75])
        for ax in (t, b):
            ax.axvline(d["ctrl"]["cot"], ls="--", lw=0.8, color=COND["ctrl"][1], zorder=1)
            ax.grid(axis="x", visible=False)
            ax.set_xlim(-0.03, 1.02)
            if i:
                ax.tick_params(axis="y", labelleft=False)
        t.spines["bottom"].set_visible(False)
        t.tick_params(axis="x", length=0, labelbottom=False)
        kw = dict(color="#5f5e5a", lw=0.7, clip_on=False, transform=t.transAxes)
        t.plot([-0.015, 0.015], [-0.02, 0.02], **kw)
        kw["transform"] = b.transAxes
        b.plot([-0.015, 0.015], [0.94, 1.02], **kw)
        b.set_xlabel("CoT hint detection" + BETTER)
        t.set_title(title, fontweight="bold")
        if i == 0:
            t0, b0 = t, b
    fig.subplots_adjust(left=0.12, right=0.99, top=0.92, bottom=0.3)
    stack_ylabel(fig, t0, b0, f"Training reward{BETTER}\n(task − 2 × output detection)", x_pad=0.6)
    gray = "#5f5e5a"
    hs = [Patch(color=c) for _, c, _, _ in COT_GROUPS]
    ls = [g[0].replace("\n", " ") for g in COT_GROUPS]
    hs += [Line2D([], [], ls="none", marker="o", ms=5, mfc="white", mec=gray, mew=1.1),
           Line2D([], [], ls="none", marker="o", ms=5, color=gray)]
    ls += ["No penalty", "Output penalty"]
    fig.legend(hs, ls, loc="upper center", bbox_to_anchor=(0.55, 0.13), ncol=3, frameon=False,
               handlelength=1.0, handletextpad=0.5, columnspacing=1.4)
    fig.savefig(path)
    plt.close(fig)


def fig_envs_pareto(data, panels, path, height=W * 0.45, wspace=0.55, bottom=0.17):
    """Pareto scatter (CoT detection vs training reward), one panel per setting. A panel with "ybreak"
    gets a broken y-axis (top range, bottom range); consecutive panels with the same lam share a y-axis.
    Error bars are 95% t intervals over seeds."""
    fig = plt.figure(figsize=(W, height))
    gs = fig.add_gridspec(2, len(panels), height_ratios=[3.2, 1], hspace=0.08, wspace=wspace)
    prev = None
    for i, pn in enumerate(panels):
        d = data[pn["key"]]
        shared = i > 0 and panels[i - 1]["lam"] == pn["lam"] and "ybreak" not in pn
        if "ybreak" in pn:
            top, bot = fig.add_subplot(gs[0, i]), fig.add_subplot(gs[1, i])
            axes = (top, bot)
        else:
            top = bot = fig.add_subplot(gs[:, i], sharey=prev if shared else None)
            axes = (top,)
        for ax in axes:
            for k in ORDER:
                if k not in d:
                    continue
                a = d[k]
                _, color, marker, _ = COND[k]
                ax.errorbar(a["cot"], a["reward"], xerr=a["cot_ci"], yerr=[[a["reward_ci"]], [min(a["reward_ci"], 1 - a["reward"])]],
                            fmt=marker, ms=MS if marker != "D" else MS_D, mfc=color, mec="white", mew=0.6, color=color,
                            elinewidth=ELW, capsize=CAP, zorder=3)
            ax.axvline(d["ctrl"]["cot"], ls="--", lw=0.8, color=COND["ctrl"][1], zorder=1)
            ax.grid(axis="x", visible=False)
            ax.set_xlim(*pn["xlim"])
        if "ybreak" in pn:
            (blo, bhi), (tlo, thi) = pn["ybreak"]
            top.set_ylim(tlo, thi)
            bot.set_ylim(blo, bhi)
            top.set_yticks(pn.get("top_ticks", [0.9, 1.0]))
            bot.set_yticks(pn.get("bot_ticks", [-0.8]))
            top.spines["bottom"].set_visible(False)
            top.tick_params(axis="x", length=0, labelbottom=False)
            kw = dict(color="#5f5e5a", lw=0.7, clip_on=False, transform=top.transAxes)
            top.plot([-0.03, 0.03], [-0.02, 0.02], **kw)
            kw["transform"] = bot.transAxes
            bot.plot([-0.03, 0.03], [0.94, 1.02], **kw)
        else:
            top.set_ylim(*pn.get("ylim", (-0.25, 1.05)))
        if shared:
            top.tick_params(axis="y", labelleft=False)
        top.set_title(pn["title"], fontweight="bold", fontsize=7.8)
        bot.set_xlabel(pn["xlabel"] + BETTER, linespacing=1.2)
        if "arrow" in pn:
            better_arrow(top, head=pn["arrow"])
        if pn.get("note"):
            top.text(0.6, 0.5, pn["note"], transform=top.transAxes, ha="center", va="center", fontsize=6.5,
                     color="#8a8880", linespacing=1.1)
        prev = top
        pn["_axes"] = (top, bot, shared)
    fig.subplots_adjust(left=0.115, right=0.99, top=0.92, bottom=bottom)
    for pn in panels:
        top, bot, shared = pn.pop("_axes")
        if not shared:
            stack_ylabel(fig, top, bot, f"Training reward{BETTER}\n(task − {pn['lam']:g} × output detection)",
                         x_pad=pn.get("ylabel_pad", 0.36))
    group_legend(fig, ORDER, by_column=True, loc="upper center", bbox_to_anchor=(0.5, 0.0), columnspacing=2.0)
    fig.savefig(path)
    plt.close(fig)


def main():
    data = load_all()
    (FIG / "paper_numbers.json").write_text(json.dumps(data, indent=1))
    fig_main_scatter(data["qa8b"], FIG / "main_scatter.pdf")
    fig_main_scatter(data["qa8b"], FIG / "main_scatter_nolegend.pdf", legend=False, width=W * 0.48)
    fig_main_scatter_bars(data["qa8b"], FIG / "main_scatter_bars.pdf")
    fig_compose([(data["qa8b"], "Qwen3-8B"), (data["qa27b"], "Qwen3.6-27B")], FIG / "compose_vertical.pdf")
    fig_compose([(data["qa8b"], "Qwen3-8B")], FIG / "compose_8b.pdf", width=W * 0.5, legend_below=True)
    fig_cotstyle(data, [("qa8b", "QA, Qwen3-8B")], FIG / "cotstyle.pdf", width=W * 0.55)
    # previews (not in the paper): Pareto versions of Figures 3 and 5
    fig_compose_pareto(data["qa8b"], FIG / "preview_compose_pareto.pdf")
    fig_cotstyle_pareto(data["qa8b"], FIG / "preview_cotstyle_pareto.pdf")
    fig_cotstyle_pareto2(data, [("qa8b", "QA, Qwen3-8B"), ("qa27b", "QA, Qwen3.6-27B")],
                         FIG / "cotstyle_pareto.pdf")
    # Qwen3.5-9B (appendix): condition bars and the composition with the prior mitigations
    fig_envs(data, [dict(title="QA, Qwen3.5-9B", key="qa9b", lam=2)], FIG / "qa9b_bars.pdf", width=W * 0.55)
    fig_compose([(data["qa9b"], "Qwen3.5-9B")], FIG / "compose_9b.pdf", width=W * 0.5)
    # Qwen3.5-397B-A17B minimal set (appendix)
    fig_envs(data, [dict(title="QA, Qwen3.5-397B-A17B", key="qa397", lam=2)], FIG / "qa397_bars.pdf", width=W * 0.55)
    fig_screen(data, FIG / "spillover_screen.pdf")
    fig_envs(data, ENV_PANELS, FIG / "envs_bars.pdf")
    fig_envs_pareto(data, ENV_PANELS, FIG / "envs_pareto.pdf")
    fig_envs_pareto(data, ENV_PARETO, FIG / "envs_pareto2.pdf", height=W * 0.46, wspace=0.5, bottom=0.25)
    fig_envs_pareto(data, [
        dict(title="Polynomial factoring, Qwen3.6-27B", key="poly27b", lam=1, xlim=(0.5, 1.03),
             xlabel="CoT detection of the expanded form", arrow=(0.5, 0.42)),
        dict(title="Terminal, Qwen3-8B", key="term8b", lam=0.75, xlim=(-0.03, 1.03),
             xlabel="CoT detection of reading the verifier", arrow=(0.76, 0.3),
             notes=[((0.06, 0.12), "styled runs that stopped\nreading the verifier")]),
    ], FIG / "envs_pareto_term.pdf")
    for s in ("qa8b", "qa27b", "qa9b", "qa397", "qa35b", "poly8b", "poly27b", "term8b"):
        print(f"== {s}")
        for k, a in data[s].items():
            print(f"  {k:16s} n={a['n']:2d} cot {a['cot']:.3f}±{a['cot_sd']:.3f} out {a['out']:.3f} "
                  f"task {a['task']:.3f} R {a['reward']:+.3f}  seeds " + " ".join(f"{x['cot']:.2f}" for x in a["seeds"]))
    for s in ("screen_qa", "screen_poly", "screen_term"):
        print(f"== {s}")
        for m, v in data[s].items():
            c, p = v["ctrl"], v["pen"]
            print(f"  {m:28s} n={c['n']}/{p['n']} ctrl cot {c['cot']:.2f} task {c['task']:.2f} | pen cot {p['cot']:.2f} "
                  f"task {p['task']:.2f} out {p['out']:.2f}")


if __name__ == "__main__":
    main()
