"""Regenerate all paper figures as titleless vector PDFs with one shared palette.

Per the writing-papers skill: no on-figure titles (captions carry the takeaway),
vector PDF with editable text, one semantic palette reused across every figure.
Reads the same eval/training data as the working plots in ../scripts.

Run: cd paper && uv run make_figures.py   (writes figures/*.pdf)
"""

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figstyle import set_paper_style, figsize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIG = Path(__file__).resolve().parent / "figures"
N, PW = 378, -2.0

set_paper_style()
plt.rcParams.update({"grid.alpha": 0.3, "lines.linewidth": 1.4})
MS = 6  # scatter marker size, proportioned to the paper-column figure

# --- One semantic palette + marker for the whole paper ---------------------
# A colour means the same condition in every figure it appears in.
C = {
    "no_sft":     ("#868e96", "o"),   # gray  — no intervention / baseline
    "normal":     ("#0c8599", "^"),   # teal  — normal SFT (SFT-not-style control)
    "pirate":     ("#e8590c", "s"),   # orange — pirate output (ours)
    "pirate_cot": ("#c2255c", "D"),   # raspberry — pirate CoT
    "rt":         ("#1c7ed6", "D"),   # blue   — reward targeting
    "mf":         ("#2f9e44", "^"),   # green  — Mind & Face
    "tmf":        ("#7048e8", "v"),   # violet — Targeted M&F
    "penalty":    ("#e03131", "o"),   # red    — plain penalty (poly)
    "pirate_ctrl":("#ffa94d", "s"),   # light orange — pirate, no penalty (poly)
}
PW_COLORS = {0: "#1c7ed6", -0.5: "#2f9e44", -1: "#f08c00", -2: "#e03131"}

EVAL_DIRS = [ROOT / "logs" / d for d in
             ("eval-penalty-v6", "eval-penalty-v7", "eval-penalty-v9mf")]


# ===================== data helpers =====================
def read_final(run, dirs=None):
    for d in (dirs or EVAL_DIRS):
        rd = d / run
        if not rd.exists():
            continue
        fs = list(rd.glob("*_001000.jsonl")) + list(rd.glob("*_final.jsonl"))
        if not fs:
            continue
        res = [json.loads(l) for l in open(fs[0]) if json.loads(l).get("type") == "result"]
        if len(res) < 300:
            continue
        n = len(res)
        return tuple(sum(r[k] for r in res) / n for k in ("sycophancy", "out_score", "cot_score"))
    return None


def pt(runs, dirs=None):
    vals = [v for v in (read_final(r, dirs) for r in runs) if v]
    if not vals:
        return None
    syc, out, cot = (np.mean([v[i] for v in vals]) for i in range(3))
    return (cot, syc + PW * out,
            1.96 * np.sqrt(max(cot * (1 - cot), 0) / N),
            1.96 * np.sqrt(max(syc * (1 - syc), 0) / N + PW**2 * max(out * (1 - out), 0) / N))


def v6(size, pw, s):
    return f"grpo-{'v6ctrl' if pw == 0 else 'v6pw-2'}-{size}-pirate-output-alpaca-qwen-s{s}"


def v7(c, size, pw, s):
    return f"grpo-{c}-{size}-{'pw0' if pw == 0 else f'pw{pw:g}'}-s{s}"


def v9(tag, size, s):
    return f"grpo-{tag}-{size}-pw-2-s{s}"


def curve(run_dir, key, w=25):
    p = ROOT / "logs" / run_dir / "metrics.jsonl"
    if not p.exists():
        return None
    vals = [json.loads(l)[key] for l in open(p) if key in json.loads(l)]
    if not vals:
        return None
    a = np.asarray(vals, float)
    return a if len(a) < w else np.convolve(a, np.ones(w) / w, "valid")


def seed_curve(runs, key):
    cs = [c for c in (curve(r, key) for r in runs) if c is not None]
    if not cs:
        return None
    n = min(len(c) for c in cs)
    return np.arange(n), np.mean([c[:n] for c in cs], axis=0)


def dot(ax, p, color, mk, label=None, hollow=False):
    # Draws the point with error bars but adds NO legend entry: legends use the
    # clean marker-only proxies from handle() instead, so error bars don't clutter
    # (and don't make a '+' read like an 'o').
    if p is None:
        return
    ax.errorbar(p[0], p[1], xerr=p[2], yerr=p[3], color=color, marker=mk, ms=MS,
                mfc="none" if hollow else color, mew=1.2, lw=0,
                elinewidth=1.3, capsize=3, zorder=5)


def handle(label, color, mk, hollow=False):
    """A marker-only legend proxy (no line, no error bars)."""
    return Line2D([], [], color=color, marker=mk, linestyle="none", ms=MS,
                  mfc="none" if hollow else color, mew=1.2, label=label)


def pareto_axes(ax, ylim=(-0.05, 1.08)):
    ax.set_xlabel("CoT hint detection  (monitorability →)")
    ax.set_ylabel(f"Training reward  (syc {PW:+g}×out)")
    ax.axhline(0, color="gray", lw=0.8, ls="--", alpha=0.5)
    ax.set_ylim(*ylim)


# ===================== figures =====================
def fig_sft():
    fig, axes = plt.subplots(1, 2, figsize=figsize(1.0, 0.5))
    sft = [("No SFT", "no_sft", "v7base"), ("Normal SFT", "normal", "v7norm"),
           ("Pirate output", "pirate", None), ("Pirate CoT", "pirate_cot", "v7pcot")]
    for ax, (sz, name) in zip(axes, [("8b", "Qwen3-8B"), ("32b", "Qwen3-32B")]):
        for label, ckey, tag in sft:
            color, mk = C[ckey]
            ctrl = [v6(sz, 0, s) for s in (42, 43)] if tag is None else [v7(tag, sz, 0, s) for s in (42, 43)]
            pen = [v6(sz, -2, s) for s in (42, 43)] if tag is None else [v7(tag, sz, -2, s) for s in (42, 43)]
            cp = pt(ctrl)
            if cp:
                ax.axvline(cp[0], color=color, ls=":", lw=1.3, alpha=0.5, zorder=1)
            dot(ax, pt(pen), color, mk)
        pareto_axes(ax)
        ax.set_title(name, fontsize=10)  # panel title (allowed), not a figure title
    # one shared legend below both panels (outside the plot area)
    fig.legend(handles=[handle(lab, *C[ck]) for lab, ck, _ in sft],
               loc="lower center", ncol=4, fontsize=8.5, frameon=False,
               bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(FIG / "pareto_sft.pdf")
    plt.close(fig)


def fig_mit():
    # (a) vs prior mitigations, (b) composition — one shared \textwidth figure so
    # each panel has room for a legend below its axes (outside the plot area).
    fig, axes = plt.subplots(1, 2, figsize=figsize(1.0, 0.56))

    ax = axes[0]
    rows_a = [("No SFT", *C["no_sft"], pt([v7("v7base", "8b", -2, s) for s in (42, 43)])),
              ("Reward targeting", *C["rt"], pt([v9("v9rt", "8b", s) for s in (42, 43)])),
              ("Mind & Face", *C["mf"], pt([v9("v9mf", "8b", s) for s in (42, 43)])),
              ("Targeted M&F", *C["tmf"], pt([v9("v9tmf", "8b", s) for s in (42, 43)])),
              ("Pirate (ours)", *C["pirate"], pt([v6("8b", -2, s) for s in (42, 43)]))]
    for label, color, mk, p in rows_a:
        dot(ax, p, color, mk)
    pareto_axes(ax)
    ax.set_title("(a) vs. prior mitigations", fontsize=9)
    ax.legend(handles=[handle(l, c, m) for l, c, m, _ in rows_a],
              loc="upper center", bbox_to_anchor=(0.5, -0.26), ncol=2,
              fontsize=7.5, frameon=False)

    ax = axes[1]
    pc = C["pirate"][1]
    rows_b = [("Pirate", C["pirate"][0], pc, pt([v6("8b", -2, s) for s in (42, 43)])),
              ("+ Reward targeting", C["rt"][0], pc, pt([v9("v9rtpirate", "8b", s) for s in (42, 43)])),
              ("+ Mind & Face", C["mf"][0], pc, pt([v9("v9mfpirate", "8b", s) for s in (42, 43)])),
              ("+ Targeted M&F", C["tmf"][0], pc, pt([v9("v9tmfpirate", "8b", s) for s in (42, 43)]))]
    for label, color, mk, p in rows_b:
        dot(ax, p, color, mk)
    pareto_axes(ax)
    ax.set_title("(b) composition", fontsize=9)
    ax.legend(handles=[handle(l, c, m) for l, c, m, _ in rows_b],
              loc="upper center", bbox_to_anchor=(0.5, -0.26), ncol=2,
              fontsize=7.5, frameon=False)

    fig.tight_layout()
    fig.savefig(FIG / "pareto_mit_combined.pdf")
    plt.close(fig)


def fig_mitigations_t300():
    d = [ROOT / "logs" / "eval-penalty-t300"]
    fig, ax = plt.subplots(figsize=figsize(0.62, 0.92))
    rows = [("No SFT", "no_sft", "base"), ("Reward targeting", "rt", "rt"),
            ("Mind & Face", "mf", "mf"), ("Targeted M&F", "tmf", "tmf"),
            ("Pirate (ours)", "pirate", "pirate")]
    for label, ckey, tag in rows:
        dot(ax, pt([f"grpo-t300{tag}-8b-pw-2-s{s}" for s in (42, 43)], d), *C[ckey])
    pareto_axes(ax)
    ax.legend(handles=[handle(lab, *C[ck]) for lab, ck, _ in rows],
              loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3,
              fontsize=7.5, frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "pareto_mitigations_t300.pdf")
    plt.close(fig)


def fig_t300_vs_4096():
    metrics = [("reward/correct", "Task reward (follows hint)"),
               ("monitor/hint_in_output", "Hint acknowledged in output"),
               ("monitor/hint_in_cot", "Hint acknowledged in CoT  (spillover)")]
    # color = penalty status; marker shape = CoT budget. All lines solid, so the
    # budget contrast reads off the markers rather than washed-out dashes.
    NP, PEN = "#1c7ed6", "#e8590c"
    conds = [("think=300, no penalty", NP, "o", ["grpo-t300base-8b-pw0-s42", "grpo-t300base-8b-pw0-s43"]),
             ("think=300, penalty", PEN, "o", ["grpo-t300base-8b-pw-2-s42", "grpo-t300base-8b-pw-2-s43"]),
             ("think=4096, no penalty", NP, "s", ["grpo-v7base-8b-pw0-s42", "grpo-v7base-8b-pw0-s43"]),
             ("think=4096, penalty", PEN, "s", ["grpo-v7base-8b-pw-2-s42", "grpo-v7base-8b-pw-2-s43"])]
    fig, axes = plt.subplots(1, 3, figsize=figsize(1.0, 0.36))
    for ax, (key, lab) in zip(axes, metrics):
        for name, color, mk, runs in conds:
            d = seed_curve(runs, key)
            if d:
                me = max(1, len(d[0]) // 6)
                ax.plot(d[0], d[1], color=color, lw=1.6, marker=mk, ms=5,
                        markevery=me, markeredgecolor="white", markeredgewidth=0.5)
        ax.set_title(lab, fontsize=9)
        ax.set_xlabel("Batch")
        ax.set_ylim(-0.05, 1.05)
    leg = [Line2D([], [], color=c, marker=m, lw=1.6, ms=6, markeredgecolor="white",
                  markeredgewidth=0.5, label=name) for name, c, m, _ in conds]
    fig.legend(handles=leg, loc="lower center", ncol=4, fontsize=8, frameon=False,
               bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(FIG / "t300_vs_4096_spillover.pdf")
    plt.close(fig)


def fig_poly():
    metrics = [("reward/correct", "Correctness"),
               ("monitor/expanded_in_output", "Expanded form in output"),
               ("monitor/expanded_in_cot", "Expanded form in CoT")]
    conds = [("Penalty", C["penalty"][0], "grpo-v9poly-pen-32b-pw-2"),
             ("Control (pw=0)", C["no_sft"][0], "grpo-v9poly-ctrl-32b-pw0"),
             ("Reward targeting", C["rt"][0], "grpo-v9poly-rt-32b-pw-2"),
             ("Mind & Face", C["mf"][0], "grpo-v9poly-mf-32b-pw-2"),
             ("Targeted M&F", C["tmf"][0], "grpo-v9poly-tmf-32b-pw-2"),
             ("Pirate output", C["pirate"][0], "grpo-v9poly-pirate-32b-pw-2"),
             ("Pirate (pw=0)", C["pirate_ctrl"][0], "grpo-v9poly-piratectrl-32b-pw0")]
    fig, axes = plt.subplots(1, 3, figsize=figsize(1.0, 0.34))
    for ax, (key, lab) in zip(axes, metrics):
        for label, color, base in conds:
            d = seed_curve([f"{base}-s{s}" for s in (42, 43)], key)
            if d:
                ax.plot(d[0], d[1], color=color, lw=1.6, label=label)
        ax.set_title(lab, fontsize=9)
        ax.set_xlabel("Batch")
        ax.set_ylim(-0.05, 1.05)
    axes[0].legend(fontsize=7, loc="best")
    fig.tight_layout()
    fig.savefig(FIG / "v9_poly_32b.pdf")
    plt.close(fig)


def fig_v8_pareto():
    # Cross-family Pareto (Qwen3.6-35B-A3B, seed 42): no-SFT vs pirate-output,
    # final-checkpoint evals (same protocol/format as fig_sft). Dotted vlines are
    # each condition's no-penalty (pw0) CoT level.
    v8dir = [ROOT / "logs" / "eval-penalty-v8"]
    fig, ax = plt.subplots(figsize=figsize(0.55, 0.72))
    rows = [("No SFT", "no_sft", "grpo-v8base-qwen36-35ba3b-{pw}-s42"),
            ("Pirate output", "pirate", "grpo-v8pirate-qwen36-35ba3b-{pw}-s42")]
    for label, ckey, tmpl in rows:
        color, mk = C[ckey]
        cp = pt([tmpl.format(pw="pw0")], dirs=v8dir)
        if cp:
            ax.axvline(cp[0], color=color, ls=":", lw=1.3, alpha=0.5, zorder=1)
        dot(ax, pt([tmpl.format(pw="pw-2")], dirs=v8dir), color, mk)
    pareto_axes(ax)
    ax.set_title("Qwen3.6-35B-A3B", fontsize=10)
    ax.legend(handles=[handle(l, *C[ck]) for l, ck, _ in rows],
              loc="lower left", fontsize=8, frameon=True, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(FIG / "pareto_v8_35ba3b.pdf")
    plt.close(fig)


def fig_v8():
    metrics = [("reward/correct", "Correctness"),
               ("monitor/hint_in_output", "Hint in output"),
               ("monitor/hint_in_cot", "Hint in CoT")]
    models = [("qwen36-35ba3b", "Qwen3.6-35B-A3B", "grpo-v8base-qwen36-35ba3b-{pw}-s42"),
              ("qwen36-35ba3b-pirate", "35B-A3B + pirate SFT", "grpo-v8pirate-qwen36-35ba3b-{pw}-s42"),
              ("nemotron", "Nemotron-3-Super-120B", "grpo-v8base-nemotron-super-120b-{pw}-s42"),
              ("q8", "Qwen3-8B", "grpo-v7base-8b-{pw}-s42"),
              ("q32", "Qwen3-32B", "grpo-v7base-32b-{pw}-s42")]
    pw_list = [(0, "pw0"), (-0.5, "pw-0.5"), (-1, "pw-1"), (-2, "pw-2")]
    fig, axes = plt.subplots(len(models), 3, figsize=figsize(1.0, 1.15), sharex="col")
    for r, (_, mname, tmpl) in enumerate(models):
        for c, (key, lab) in enumerate(metrics):
            ax = axes[r, c]
            for pwv, pws in pw_list:
                d = seed_curve([tmpl.format(pw=pws)], key)
                if d:
                    ax.plot(d[0], d[1], color=PW_COLORS[pwv], lw=1.4, label=f"pw={pwv:g}")
            ax.set_ylim(-0.05, 1.05)
            if r == 0:
                ax.set_title(lab, fontsize=9)
            if c == 0:
                ax.set_ylabel(mname, fontsize=8)
            if r == len(models) - 1:
                ax.set_xlabel("Batch")
    axes[0, 0].legend(fontsize=6.5, loc="best")
    fig.tight_layout()
    fig.savefig(FIG / "v8_vs_qwen3_base.pdf")
    plt.close(fig)


def _exp_cot(run):
    d = ROOT / "logs" / "eval-experiments" / run
    fs = list(d.glob("*_final.jsonl")) + list(d.glob("*_001000.jsonl"))
    if not fs:
        return None
    res = [json.loads(l) for l in open(fs[0]) if json.loads(l).get("type") == "result"]
    if len(res) < 300:
        return None
    return sum(r["cot_score"] for r in res) / len(res)


def _half(vs):
    return (np.mean(vs), (max(vs) - min(vs)) / 2) if vs else None


def _exp_pt(runs):
    return _half([v for v in (_exp_cot(r) for r in runs) if v is not None])


def _main_pt(runs):  # CoT from the main eval dirs (read_final returns syc,out,cot)
    return _half([v[2] for v in (read_final(r) for r in runs) if v is not None])


def fig_sweep():
    # Penalty-weight sweep: CoT detection vs lambda for the four SFT conditions,
    # one panel per model size. Shows pirate-output staying near its control while
    # the others drop. lambda = |penalty_weight|.
    lams = [0, 0.5, 1, 2]
    pmap = {0: "v6ctrl", -0.5: "v6", -1: "v6pw-1", -2: "v6pw-2"}

    def pws(p):
        return "pw0" if p == 0 else f"pw{p:g}"

    def runs(ckey, size, p):
        if ckey == "pirate":
            return [f"grpo-{pmap[p]}-{size}-pirate-output-alpaca-qwen-s{s}" for s in (42, 43)]
        tag = {"no_sft": "v7base", "normal": "v7norm", "pirate_cot": "v7pcot"}[ckey]
        return [f"grpo-{tag}-{size}-{pws(p)}-s{s}" for s in (42, 43)]

    conds = [("No SFT", "no_sft"), ("Normal SFT", "normal"),
             ("Pirate output", "pirate"), ("Pirate CoT", "pirate_cot")]
    fig, axes = plt.subplots(1, 3, figsize=figsize(1.0, 0.34), sharey=True)
    for ax, (size, name) in zip(axes[:2], [("8b", "Qwen3-8B"), ("32b", "Qwen3-32B")]):
        for label, ckey in conds:
            color, mk = C[ckey]
            ys, es = [], []
            for p in (0, -0.5, -1, -2):
                vals = [v[2] for v in (read_final(r) for r in runs(ckey, size, p)) if v is not None]
                m, e = _half(vals)
                ys.append(m); es.append(e)
            ax.errorbar(lams, ys, yerr=es, color=color, marker=mk, ms=MS,
                        capsize=3, lw=1.4, elinewidth=1.3, label=label)
        ax.set_xlabel("Penalty weight $\\lambda$")
        ax.set_xticks(lams)
        ax.set_title(name, fontsize=10)
        ax.set_ylim(-0.03, 0.9)
    # Panel (c): the prior mitigations across lambda (8B; lambda=0 is degenerate for
    # a mitigation -- no penalty to target or route -- so lines start at 0.5).
    ax = axes[2]
    for label, ckey in [("No SFT", "no_sft"), ("Pirate output", "pirate")]:
        color, mk = C[ckey]
        ys, es = [], []
        for p in (0, -0.5, -1, -2):
            vals = [v[2] for v in (read_final(r) for r in runs(ckey, "8b", p)) if v is not None]
            m, e = _half(vals)
            ys.append(m); es.append(e)
        ax.errorbar(lams, ys, yerr=es, color=color, marker=mk, ms=MS, capsize=3,
                    lw=1.0, elinewidth=1.0, alpha=0.45, label=label)
    for label, key in [("Reward targeting", "rt"), ("Mind & Face", "mf"),
                       ("Targeted M&F", "tmf")]:
        color, mk = C[key]
        ys, es = [], []
        for p in (-0.5, -1, -2):
            rs = [f"grpo-v9{key}-8b-{pws(p)}-s{s}" for s in (42, 43)]
            vals = [v[2] for v in (read_final(r) for r in rs) if v is not None]
            m, e = _half(vals)
            ys.append(m); es.append(e)
        ax.errorbar([0.5, 1, 2], ys, yerr=es, color=color, marker=mk, ms=MS,
                    capsize=3, lw=1.4, elinewidth=1.3, label=label)
    ax.set_xlabel("Penalty weight $\\lambda$")
    ax.set_xticks(lams)
    ax.set_title("Qwen3-8B, mitigations", fontsize=10)
    axes[0].set_ylabel("CoT hint detection")
    # One shared legend below the panels; dedupe the faded reference entries.
    handles, labels = [], []
    for a in (axes[0], axes[2]):
        for h, l in zip(*a.get_legend_handles_labels()):
            if l not in labels:
                handles.append(h); labels.append(l)
    fig.legend(handles, labels, loc="lower center", ncol=7, fontsize=7,
               frameon=False, columnspacing=1.1, handletextpad=0.4,
               bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=[0, 0.09, 1, 1])
    fig.savefig(FIG / "lambda_sweep.pdf", bbox_inches="tight"); plt.close(fig)


def fig_extra():
    # Two single-series "cheapness/robustness" plots merged into one shared-y
    # figure: (a) how little style SFT is needed, (b) rewarding the style.
    fig, axes = plt.subplots(1, 2, figsize=figsize(1.0, 0.40), sharey=True)

    # --- Panel (a): depth of style SFT ---
    ax = axes[0]
    labels = ["0", "5", "25", "50", "100", "150", "200", "final"]
    ys, es = [], []
    for lab in labels:
        if lab == "0":  # step 0 = no pirate SFT (the no-SFT penalty run)
            p = _main_pt([f"grpo-v7base-8b-pw-2-s{s}" for s in (42, 43)])
        else:
            p = _exp_pt([f"grpo-scenB-step{lab}-8b-pw-2-s{s}" for s in (42, 43)])
        ys.append(p[0]); es.append(p[1])
    x = range(len(labels))
    ax.axhline(0.50, ls="--", lw=1.1, color=C["mf"][0], alpha=0.85)
    ax.text(0, 0.51, "no-penalty control", color=C["mf"][0], fontsize=7, va="bottom")
    ax.errorbar(x, ys, yerr=es, marker="o", ms=MS, color=C["pirate"][0],
                capsize=3, lw=1.4, elinewidth=1.3)
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_xlabel("Pirate-output SFT steps before RL")
    ax.set_ylabel("CoT hint detection")
    ax.set_title("(a) Depth of style SFT", fontsize=9)
    ax.set_ylim(0, 0.8)

    # --- Panel (b): pirate-reward weight mu (mu=0 = plain pirate-output) ---
    ax = axes[1]
    mus = [0, 0.5, 1, 2]
    ys, es = [], []
    for mu in mus:
        if mu == 0:
            p = _main_pt([f"grpo-v6pw-2-8b-pirate-output-alpaca-qwen-s{s}" for s in (42, 43)])
        else:
            p = _exp_pt([f"grpo-piratereward-mu{mu:g}-8b-pw-2-s{s}" for s in (42, 43)])
        ys.append(p[0]); es.append(p[1])
    x = range(len(mus))
    ax.errorbar(x, ys, yerr=es, marker="s", ms=MS, color=C["pirate"][0],
                capsize=3, lw=1.4, elinewidth=1.3)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"$\\mu$={m:g}" for m in mus])
    ax.set_xlabel("Pirate-output reward weight $\\mu$")
    ax.set_title("(b) Rewarding the style", fontsize=9)
    ax.set_xlim(-0.3, len(mus) - 0.7)

    fig.tight_layout(); fig.savefig(FIG / "extra_depth_mu.pdf"); plt.close(fig)


# ===================== campaign figures: explanation-gated protocol =====================
# Sources: RESULTS.md §12/§12b, §16b–§16f, §14f, §13h, §18; CHECKIN.md 2026-09-24. Run globs come
# from scripts/plot_gated_pareto_all.py::PANELS (the source of truth), and the loader below mirrors
# its logic. Every plotted number is a TRAINING-ROLLOUT mean over the last 27 steps (QA / poly) or
# the last 40 steps (terminal) of each run's metrics.jsonl; training reward = task − λ·M_out with
# λ = 2 (QA), 1 (poly), 0.75 (terminal). ERROR BARS = 95% CI ACROSS SEEDS (1.96·SD/√n_seeds) unless
# a comment says binomial.
sys.path.insert(0, str(ROOT / "scripts"))
from plot_gated_pareto_all import PANELS  # noqa: E402

# Palette additions (same semantic palette as C above; a colour means one condition everywhere).
C.update({
    "ctrl":     ("#343a40", "o"),   # charcoal — no-penalty control, no SFT
    "piglatin": ("#d4a017", "p"),   # gold — Pig-Latin output
    "chinese":  ("#c2255c", "h"),   # raspberry — Chinese output
})
# Fill conventions (all four figures): filled = penalized arm (style rewarded, or an unstyled
# mitigation); tinted face = that arm's no-penalty control; hollow = style installed by SFT but
# NOT rewarded during RL; '×' = the original ungated pirate run (bare \boxed{X} outputs).
# PANELS label -> (palette key, fill, display label). Labels missing here are not plotted.
ARM_STYLE = {
    "No penalty":                         ("ctrl",     "tint",   "No penalty (no SFT)"),
    "Penalty, no-SFT":                    ("no_sft",   "full",   "Plain penalty (no SFT)"),
    "Reward targeting":                   ("rt",       "full",   "Reward targeting"),
    "Mind & Face":                        ("mf",       "full",   "Mind & Face"),
    "Targeted M&F":                       ("tmf",      "full",   "Targeted M&F"),
    "Pirate + style reward + penalty":    ("pirate",   "full",   "Pirate + style reward"),
    "Pig-Latin + style reward + penalty": ("piglatin", "full",   "Pig-Latin + style reward"),
    "Chinese + style reward + penalty":   ("chinese",  "full",   "Chinese + style reward"),
    "Pirate + style reward, no penalty":  ("pirate",   "tint",   "Pirate, no penalty"),
    "Pig-Latin + style reward, no penalty": ("piglatin", "tint", "Pig-Latin, no penalty"),
    "Chinese + style reward, no penalty": ("chinese",  "tint",   "Chinese, no penalty"),
    "Pirate, style not rewarded":         ("pirate",   "hollow", "Pirate, style not rewarded"),
    "Pig-Latin, style not rewarded":      ("piglatin", "hollow", "Pig-Latin, style not rewarded"),
    "Pirate v1 + penalty, no gate (bare outputs)": ("pirate", "x", "Pirate, no gate (bare outputs)"),
}
ENV_OF = {"qa8b": "qa", "qa27b": "qa", "poly27b": "poly", "term8b": "term"}
XLABEL = {"qa": "CoT hint detection", "poly": "Expanded form in CoT", "term": "Verifier read in CoT"}
YLABEL = "Training reward  (gated task $-\\ \\lambda\\,M_\\mathrm{out}$)"


def tail_means(run_dir, lam, n_expected, last, ko, kc):
    """(cot, task − λ·out, task, out) over the last `last` steps; None if the run is incomplete."""
    p = Path(run_dir) / "metrics.jsonl"
    if not p.exists():
        return None
    ms = {}
    for ln in open(p):
        x = json.loads(ln)
        ms[x["step"]] = x
    steps = sorted(ms)
    if len(steps) < n_expected:
        return None
    tail = [ms[s] for s in steps[-last:]]
    task, out, cot = (np.mean([x[k] for x in tail]) for k in ("reward/correct", ko, kc))
    return cot, task - lam * out, task, out


def panel_arms(panel):
    """Yield (display label, palette key, fill, per-seed points[n, 4]) for one PANELS entry."""
    _, lam, n_exp, last, ko, kc, arms = PANELS[panel]
    for pat, label, *_ in arms:
        if label not in ARM_STYLE:
            continue
        ckey, fill, disp = ARM_STYLE[label]
        pts = [tail_means(d, lam, n_exp, last, ko, kc) for d in sorted(ROOT.glob(pat))]
        pts = np.array([p for p in pts if p is not None])
        if len(pts):
            yield disp, ckey, fill, pts


def ci95(v):
    """95% CI half-width across seeds (t≈1.96; 0 for a single seed)."""
    v = np.asarray(v, float)
    return 1.96 * v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else 0.0


def binom_ci(k, n):
    """95% normal-approximation binomial CI half-width for k successes in n trials."""
    p = k / n
    return 1.96 * np.sqrt(p * (1 - p) / n)


def _face(color, fill):
    from matplotlib.colors import to_rgba
    return {"full": color, "tint": to_rgba(color, 0.35), "hollow": "white", "x": color}[fill]


def pareto_arm(ax, pts, color, mk, fill):
    """Faint per-seed dots + mean marker with 95% CI (across seeds) on both axes."""
    x, y = pts[:, 0], pts[:, 1]
    mk = "x" if fill == "x" else mk
    face = _face(color, fill)
    if mk == "x":
        ax.scatter(x, y, color=color, marker="x", s=14, alpha=0.35, linewidths=0.9, zorder=3)
    else:
        ax.scatter(x, y, facecolors="none" if fill == "hollow" else face, edgecolors=color,
                   marker=mk, s=14, alpha=0.35, linewidths=0.7, zorder=3)
    ax.errorbar(x.mean(), y.mean(), xerr=ci95(x), yerr=ci95(y), color=color, marker=mk, ms=MS,
                mfc=face, mec=color, mew=1.2, lw=0, elinewidth=1.0, capsize=2.5, zorder=5)


def gated_handle(label, color, mk, fill):
    mk = "x" if fill == "x" else mk
    return Line2D([], [], color=color, marker=mk, linestyle="none", ms=MS, mfc=_face(color, fill),
                  mec=color, mew=1.2, label=label)


def gated_axes(ax, env, xlabel=True, ylabel=True, short=False):
    lam = {"qa": 2, "poly": 1, "term": 0.75}[env]
    if xlabel:
        ax.set_xlabel(XLABEL[env] if short else f"{XLABEL[env]}  (monitorability →)")
    if ylabel:  # two lines on the narrow multi-panel axes so the label is not clipped
        ax.set_ylabel(YLABEL.replace("  (", "\n(") if short else YLABEL, fontsize=9)
    if not short:  # multi-panel figures carry λ in the panel title instead
        ax.text(0.98, 0.03, f"$\\lambda={lam:g}$", transform=ax.transAxes, fontsize=8, color="#495057", ha="right")
    ax.axhline(0, color="gray", lw=0.8, ls="--", alpha=0.5)
    ax.set_xlim(0, 1.02)
    ax.set_ylim(-1.05, 1.1)
    ax.grid(axis="x", visible=False)


def _print_pareto_table(title, rows):
    print(f"\n== {title}  (mean over seeds; ± = 95% CI across seeds)")
    print(f"   {'arm':32s} {'n':>2s}  {'CoT det.':>13s}  {'train reward':>13s}  {'task':>5s}  {'M_out':>5s}")
    for disp, _, _, pts in rows:
        x, y = pts[:, 0], pts[:, 1]
        print(f"   {disp:32s} {len(pts):2d}  {x.mean():.2f} ± {ci95(x):.2f}   {y.mean():.2f} ± {ci95(y):.2f}"
              f"   {pts[:, 2].mean():.2f}  {pts[:, 3].mean():.2f}")


def fig_pareto_gated_8b():
    """Main figure: QA on Qwen3-8B under the explanation gate (RESULTS §16f; 10 seeds for the two
    style-rewarded SFT arms, 5 otherwise). Hollow = style not rewarded (§16c); × = ungated §12b pirate."""
    rows = list(panel_arms("qa8b"))
    fig, ax = plt.subplots(figsize=figsize(1.0, 0.55))
    ctrl = next(r for r in rows if r[2] == "tint")
    ax.axvline(ctrl[3][:, 0].mean(), color=C["ctrl"][0], ls=":", lw=1.1, alpha=0.6, zorder=1)
    for disp, ckey, fill, pts in rows:
        pareto_arm(ax, pts, C[ckey][0], C[ckey][1], fill)
    gated_axes(ax, "qa")
    # Legend sits in the interior whitespace (x < 0.45, y < 0.4 is empty for every arm).
    ax.legend(handles=[gated_handle(d, C[k][0], C[k][1], f) for d, k, f, _ in rows],
              loc="lower left", bbox_to_anchor=(0.005, 0.02), frameon=False, fontsize=7.5,
              handletextpad=0.5, labelspacing=0.45, borderaxespad=0.0)
    fig.tight_layout()
    fig.savefig(FIG / "pareto_gated_8b.pdf")
    plt.close(fig)
    _print_pareto_table("pareto_gated_8b (QA, Qwen3-8B, gated)", rows)


def fig_pareto_envs_models():
    """(a) QA Qwen3.6-27B, (b) polynomial Qwen3.6-27B, (c) terminal Qwen3-8B — RESULTS §16e/16f, §14f, §13h.
    Tinted markers are the styled arms' own no-penalty controls."""
    # Short facet labels (model names belong in the caption): QA / poly on Qwen3.6-27B, terminal on Qwen3-8B.
    panels = [("qa27b", "QA, 27B  ($\\lambda=2$)"), ("poly27b", "Polynomial, 27B  ($\\lambda=1$)"),
              ("term8b", "Terminal, 8B  ($\\lambda=0.75$)")]
    fig, axes = plt.subplots(1, 3, figsize=figsize(1.0, 0.46), sharey=True)
    legend, seen = [], set()
    for i, (ax, (key, title)) in enumerate(zip(axes, panels)):
        rows = list(panel_arms(key))
        for disp, ckey, fill, pts in rows:
            pareto_arm(ax, pts, C[ckey][0], C[ckey][1], fill)
            if disp not in seen:
                seen.add(disp)
                legend.append(gated_handle(disp, C[ckey][0], C[ckey][1], fill))
        gated_axes(ax, ENV_OF[key], ylabel=(i == 0), short=True)
        ax.set_title(title, fontsize=9, fontweight="bold")
        _print_pareto_table(f"pareto_envs_models / {title}", rows)
    # Order the shared legend: unstyled arms, then styled penalty arms, then styled controls.
    order = ["No penalty (no SFT)", "Plain penalty (no SFT)", "Reward targeting", "Mind & Face",
             "Targeted M&F", "Pirate + style reward", "Pig-Latin + style reward", "Chinese + style reward",
             "Pirate, no penalty", "Pig-Latin, no penalty", "Chinese, no penalty"]
    legend.sort(key=lambda h: order.index(h.get_label()) if h.get_label() in order else 99)
    fig.legend(handles=legend, loc="lower center", ncol=4, fontsize=7.5, frameon=False,
               bbox_to_anchor=(0.5, -0.02), columnspacing=1.2, handletextpad=0.4)
    fig.tight_layout(rect=(0, 0.12, 1, 1), w_pad=1.0)
    fig.savefig(FIG / "pareto_envs_models.pdf")
    plt.close(fig)


# --- gate_bars data: (row label, CoT-detection run glob, palette key, fill, genuine source) ---
# genuine source: ("eq", <file stem>) = logs/explanation-quality/<stem>.jsonl (150 late outputs, GPT-4.1
# GENUINE judge); ("rollouts", None) = mean of `explanation_genuine` over the last 27 batches of each
# run's rollouts.jsonl (the gate's own verdicts). Fill: hatch 'xx' = no gate, hatch '//' = word-count
# gate, hollow = judge gate with the style not rewarded, full = judge gate (style rewarded / unstyled).
GATE_ROWS = [
    ("No SFT (no gate)",                     "logs/grpo-grpo300-nosft-pen-8b-s??",       "no_sft",   "xx",     ("eq", "grpo300-nosft-pen")),
    ("Pirate SFT (no gate)",                 "logs/grpo-mit300-pirate-pen-8b-s??",       "pirate",   "xx",     ("eq", "mit300-pirate-pen")),
    ("Pirate, word-count gate",              "logs/grpo-expl300-pirate-pen-8b-s??",      "pirate",   "//",     ("eq", "expl300-pirate-pen")),
    ("Pirate, judge gate",                   "logs/grpo-explj300-piratev2-pen-8b-s??",   "pirate",   "hollow", ("rollouts", None)),
    ("Pirate, judge gate + style reward",    "logs/grpo-explj300-piratev2sr-pen-8b-s??", "pirate",   "full",   ("rollouts", None)),
    ("Pig-Latin SFT (no gate)",              "logs/grpo-style300-piglatin-pen-8b-s??",   "piglatin", "xx",     ("eq", "style300-piglatin-pen")),
    ("Pig-Latin, word-count gate",           "logs/grpo-expl300-piglatin-pen-8b-s??",    "piglatin", "//",     ("eq", "expl300-piglatin-pen")),
    ("Pig-Latin, judge gate",                "logs/grpo-explj300-piglatin-pen-8b-s??",   "piglatin", "hollow", ("rollouts", None)),
    ("Pig-Latin, judge gate + style reward", "logs/grpo-explj300-piglatinsr-pen-8b-s??", "piglatin", "full",   ("rollouts", None)),
    ("Chinese, judge gate + style reward",   "logs/grpo-gated-8b-chinesesr-pen-s??",     "chinese",  "full",   ("rollouts", None)),
    ("Reward targeting (judge gate)",        "logs/grpo-gated-8b-rt-s??",                "rt",       "full",   ("rollouts", None)),
    ("Targeted M&F (judge gate)",            "logs/grpo-gated-8b-tmf-s??",               "tmf",      "full",   ("rollouts", None)),
]
GATE_GROUPS = [1, 5, 9, 10, 12]  # row indices where a new family starts (for group gaps)


def genuine_counts(source, pat):
    """(k, n) genuine-explanation counts for one arm (see GATE_ROWS comment)."""
    kind, stem = source
    if kind == "eq":
        g = [json.loads(ln)["genuine"] for ln in open(ROOT / "logs" / "explanation-quality" / f"{stem}.jsonl")]
        g = [v for v in g if v is not None]
        return int(sum(g)), len(g)
    k = n = 0
    for d in sorted(ROOT.glob(pat)):
        rs = [json.loads(ln) for ln in open(Path(d) / "rollouts.jsonl")]
        last = max(r["batch"] for r in rs) - 27
        g = [r["explanation_genuine"] for r in rs if r["batch"] > last and r.get("explanation_genuine") is not None]
        k += int(sum(g))
        n += len(g)
    return k, n


def fig_gate_bars():
    """Two horizontal-bar panels sharing the row categories: (left) CoT hint detection under the output
    penalty, 95% CI across seeds; (right) fraction of late outputs judged a genuine explanation, 95%
    binomial CI. RESULTS §12/§12b (no gate), §16b (word-count gate), §16c/§16d/§16f (judge gate)."""
    _, lam, n_exp, last, ko, kc, _ = PANELS["qa8b"]
    table = []
    for label, pat, ckey, fill, src in GATE_ROWS:
        pts = [tail_means(d, lam, n_exp, last, ko, kc) for d in sorted(ROOT.glob(pat))]
        pts = np.array([p for p in pts if p is not None])
        k, n = genuine_counts(src, pat)
        table.append((label, ckey, fill, pts, k, n))

    # y positions, top to bottom, with a gap between families
    ys, y = [], 0.0
    for i in range(len(GATE_ROWS)):
        if i in GATE_GROUPS:
            y += 0.6
        ys.append(-y)
        y += 1.0
    fig, axes = plt.subplots(1, 2, figsize=figsize(1.0, 0.52), sharey=True)
    for ax, which in zip(axes, ("cot", "gen")):
        for yi, (label, ckey, fill, pts, k, n) in zip(ys, table):
            color = C[ckey][0]
            if which == "cot":
                v, e = pts[:, 0].mean(), ci95(pts[:, 0])
            else:
                v, e = k / n, binom_ci(k, n)
            kw = dict(height=0.72, edgecolor=color, linewidth=1.0, zorder=3)
            if fill == "full":
                ax.barh(yi, v, color=color, **kw)
            elif fill == "hollow":
                ax.barh(yi, v, color="white", **kw)
            else:
                ax.barh(yi, v, color="white", hatch=fill, **kw)
            ax.errorbar(v, yi, xerr=e, color="#212529", lw=0, elinewidth=1.0, capsize=2.5, zorder=4)
        ax.set_xlim(0, 1.0)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
    axes[0].set_yticks(ys)
    axes[0].set_yticklabels([r[0] for r in GATE_ROWS], fontsize=8)
    axes[0].set_xlabel("CoT hint detection")
    axes[1].set_xlabel("Genuine-explanation rate")
    fig.tight_layout(w_pad=1.2)
    fig.savefig(FIG / "gate_bars.pdf")
    plt.close(fig)

    print("\n== gate_bars (QA, Qwen3-8B; CoT ± 95% CI across seeds; genuine = k/n ± binomial 95% CI)")
    print(f"   {'row':36s} {'n_seeds':>7s}  {'CoT det.':>13s}  {'genuine':>20s}  {'source':8s}")
    for (label, ckey, fill, pts, k, n), (_, _, _, _, src) in zip(table, GATE_ROWS):
        x = pts[:, 0]
        print(f"   {label:36s} {len(pts):7d}  {x.mean():.2f} ± {ci95(x):.2f}   "
              f"{k / n:.3f} ± {binom_ci(k, n):.3f} ({k:4d}/{n:4d})  {src[0]}")


def _explanation_words_fallback(out_text):
    # Verbatim copy of src/spillover/train_grpo._explanation_words (used only if that import fails).
    import re
    m = re.search(r"### (?:Explanation|解释|Xplanationeay)\s*(.*)", out_text or "", re.S)
    return len((m.group(1) if m else "").replace("<|im_end|>", "").split())


def fig_coupling_bars():
    """At initialization (batches 0–9 of the no-penalty control runs): P(output judged clean | CoT
    mentions the hint), split into clean outputs that are real explanations (≥20 words in the
    '### Explanation' section) vs bare/short ones. 95% binomial CI on the total (n = hint-mentioning
    rollouts pooled over seeds). Matches CHECKIN.md 2026-09-24."""
    try:
        sys.path.insert(0, str(ROOT))
        from src.spillover.train_grpo import _explanation_words as ew
    except Exception as e:  # heavy deps (tinker/torch) may be missing outside the training env
        print(f"   [coupling] using local copy of _explanation_words ({type(e).__name__})")
        ew = _explanation_words_fallback
    # (label, control-run glob, palette key, hatch). Hatch 'xx' = the legacy pirate v1 checkpoint
    # (38% well-formed at init, §16c); '//' = style requested in the prompt, no SFT.
    conds = [("No SFT", "grpo-grpo300-nosft-ctrl-8b-s4[2-6]", "no_sft", None),  # seeds 42-46, as in CHECKIN 2026-09-24
             ("Normal SFT", "grpo-explj300-normalalpaca-ctrl-8b-s??", "normal", None),
             ("Pirate (v1 data)", "grpo-mit300-pirate-ctrl-8b-s??", "pirate", "xx"),
             ("Pirate (v2 data)", "grpo-explj300-piratev2-ctrl-8b-s??", "pirate", None),
             ("Pig-Latin SFT", "grpo-style300-piglatin-ctrl-8b-s??", "piglatin", None),
             ("Chinese SFT", "grpo-style300-chinese-ctrl-8b-s??", "chinese", None),
             ("Prompted pirate", "grpo-prompt300-pirate-ctrl-8b-s??", "pirate", "//")]
    rows = []
    for label, pat, ckey, hatch in conds:
        n_cot = n_clean = n_real = 0
        runs = sorted((ROOT / "logs").glob(pat))
        for d in runs:
            for ln in open(d / "rollouts.jsonl"):
                r = json.loads(ln)
                if r["batch"] > 9:
                    break
                if not r.get("valid", True) or r["cot_score"] != 1:
                    continue
                n_cot += 1
                if r["out_score"] == 0:
                    n_clean += 1
                    n_real += ew(r["out_text"]) >= 20
        rows.append((label, ckey, hatch, len(runs), n_cot, n_clean, n_real))

    fig, ax = plt.subplots(figsize=figsize(0.5, 0.88))
    x = np.arange(len(rows))
    for xi, (label, ckey, hatch, _, n_cot, n_clean, n_real) in zip(x, rows):
        color = C[ckey][0]
        real, bare = n_real / n_cot, (n_clean - n_real) / n_cot
        ax.bar(xi, real, 0.68, color=color, edgecolor=color, hatch=hatch, linewidth=1.0, zorder=3)
        ax.bar(xi, bare, 0.68, bottom=real, color="white", edgecolor=color, hatch=hatch,
               linewidth=1.0, zorder=3)
        ax.errorbar(xi, n_clean / n_cot, yerr=binom_ci(n_clean, n_cot), color="#212529", lw=0,
                    elinewidth=1.0, capsize=2.5, zorder=4)
    ax.set_xticks(x)
    ax.set_xticklabels([r[0] for r in rows], fontsize=7.5, rotation=30, ha="right", rotation_mode="anchor")
    ax.set_ylabel("P(clean output | hint in CoT)", fontsize=9)
    ax.set_ylim(0, 0.6)
    ax.grid(axis="x", visible=False)
    ax.legend(handles=[Patch(facecolor="#495057", edgecolor="#495057", label="clean, real explanation"),
                       Patch(facecolor="white", edgecolor="#495057", label="clean, bare / short")],
              loc="upper right", fontsize=7.5, frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "coupling_bars.pdf")
    plt.close(fig)

    print("\n== coupling_bars (init, batches 0–9 of control runs; ± = binomial 95% CI on the total)")
    print(f"   {'condition':18s} {'runs':>4s} {'n_cot':>5s}  {'P(clean|cot)':>16s}  {'real':>5s}  {'bare':>5s}  {'real share':>10s}")
    for label, _, _, nr, n_cot, n_clean, n_real in rows:
        lab = label.replace("\n", " ")
        print(f"   {lab:18s} {nr:4d} {n_cot:5d}  {n_clean / n_cot:.3f} ± {binom_ci(n_clean, n_cot):.3f}   "
              f"{n_real / n_cot:.3f}  {(n_clean - n_real) / n_cot:.3f}  {n_real / max(n_clean, 1):10.2f}")


NEW_FIGS = (fig_pareto_gated_8b, fig_gate_bars, fig_pareto_envs_models, fig_coupling_bars)
OLD_FIGS = (fig_sft, fig_mit, fig_mitigations_t300, fig_t300_vs_4096, fig_poly, fig_v8,
            fig_v8_pareto, fig_extra, fig_sweep)

if __name__ == "__main__":
    # `--new` runs only the gated-campaign figures; default keeps the original behaviour.
    figs = NEW_FIGS if "--new" in sys.argv[1:] else OLD_FIGS
    for f in figs:
        f()
        print(f"  {f.__name__}")
    print("Done. PDFs in figures/.")
