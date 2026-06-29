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
    "normal":     ("#0c8599", "P"),   # teal  — normal SFT (SFT-not-style control)
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


def dot(ax, p, color, mk, label, hollow=False):
    if p is None:
        return
    # lw=0 -> no line between points; elinewidth set explicitly so error bars
    # actually render (they default to the line width, which is 0 here).
    ax.errorbar(p[0], p[1], xerr=p[2], yerr=p[3], color=color, marker=mk, ms=MS,
                mfc="none" if hollow else color, mew=1.2, lw=0,
                elinewidth=1.3, capsize=3, zorder=5, label=label)


def pareto_axes(ax, ylim=(-0.05, 1.08)):
    ax.set_xlabel("CoT hint detection  (monitorability →)")
    ax.set_ylabel(f"Training reward  (syc {PW:+g}×out)")
    ax.axhline(0, color="gray", lw=0.8, ls="--", alpha=0.5)
    ax.set_ylim(*ylim)


# ===================== figures =====================
def fig_sft():
    fig, axes = plt.subplots(1, 2, figsize=figsize(1.0, 0.46))
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
            dot(ax, pt(pen), color, mk, label)
        pareto_axes(ax)
        ax.set_title(name, fontsize=10)  # panel title (allowed), not a figure title
        ax.legend(loc="lower right", fontsize=7.5, frameon=True, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(FIG / "pareto_sft.pdf")
    plt.close(fig)


def fig_mitigations():
    # figsize matches the 0.49\textwidth subfigure it is shown at, so fonts land
    # at caption size rather than shrinking when LaTeX downscales.
    fig, ax = plt.subplots(figsize=figsize(0.49, 0.85))
    dot(ax, pt([v7("v7base", "8b", -2, s) for s in (42, 43)]), *C["no_sft"], "No SFT (penalty only)")
    dot(ax, pt([v9("v9rt", "8b", s) for s in (42, 43)]), *C["rt"], "Reward targeting")
    dot(ax, pt([v9("v9mf", "8b", s) for s in (42, 43)]), *C["mf"], "Mind & Face")
    dot(ax, pt([v9("v9tmf", "8b", s) for s in (42, 43)]), *C["tmf"], "Targeted M&F")
    dot(ax, pt([v6("8b", -2, s) for s in (42, 43)]), *C["pirate"], "Pirate output (ours)")
    pareto_axes(ax)
    ax.legend(loc="center", fontsize=8, frameon=True, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(FIG / "pareto_mitigations.pdf")
    plt.close(fig)


def fig_stacking():
    fig, ax = plt.subplots(figsize=figsize(0.49, 0.85))
    dot(ax, pt([v6("8b", -2, s) for s in (42, 43)]), *C["pirate"], "Pirate output")
    dot(ax, pt([v9("v9rtpirate", "8b", s) for s in (42, 43)]), C["rt"][0], C["pirate"][1], "Pirate + Reward targeting")
    dot(ax, pt([v9("v9mfpirate", "8b", s) for s in (42, 43)]), C["mf"][0], C["pirate"][1], "Pirate + Mind & Face")
    dot(ax, pt([v9("v9tmfpirate", "8b", s) for s in (42, 43)]), C["tmf"][0], C["pirate"][1], "Pirate + Targeted M&F")
    pareto_axes(ax)
    ax.legend(loc="center", fontsize=8, frameon=True, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(FIG / "pareto_stacking.pdf")
    plt.close(fig)


def fig_mitigations_t300():
    d = [ROOT / "logs" / "eval-penalty-t300"]
    fig, ax = plt.subplots(figsize=figsize(0.6, 0.85))
    for tag, ckey, label in [("base", "no_sft", "No SFT (penalty only)"),
                             ("rt", "rt", "Reward targeting"), ("mf", "mf", "Mind & Face"),
                             ("tmf", "tmf", "Targeted M&F"), ("pirate", "pirate", "Pirate output (ours)")]:
        dot(ax, pt([f"grpo-t300{tag}-8b-pw-2-s{s}" for s in (42, 43)], d), *C[ckey], label)
    pareto_axes(ax)
    ax.legend(loc="center", fontsize=8, frameon=True, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(FIG / "pareto_mitigations_t300.pdf")
    plt.close(fig)


def fig_t300_vs_4096():
    metrics = [("reward/correct", "Task reward (follows hint)"),
               ("monitor/hint_in_output", "Hint acknowledged in output"),
               ("monitor/hint_in_cot", "Hint acknowledged in CoT  (spillover)")]
    conds = [("think=300, no penalty", "#1c7ed6", "-", ["grpo-t300base-8b-pw0-s42", "grpo-t300base-8b-pw0-s43"]),
             ("think=300, penalty", "#e8590c", "-", ["grpo-t300base-8b-pw-2-s42", "grpo-t300base-8b-pw-2-s43"]),
             ("think=4096, no penalty", "#1c7ed6", "--", ["grpo-v7base-8b-pw0-s42", "grpo-v7base-8b-pw0-s43"]),
             ("think=4096, penalty", "#e8590c", "--", ["grpo-v7base-8b-pw-2-s42", "grpo-v7base-8b-pw-2-s43"])]
    fig, axes = plt.subplots(1, 3, figsize=figsize(1.0, 0.34))
    for ax, (key, lab) in zip(axes, metrics):
        for name, color, ls, runs in conds:
            d = seed_curve(runs, key)
            if d:
                ax.plot(d[0], d[1], color=color, ls=ls, lw=1.6, label=name)
        ax.set_title(lab, fontsize=9)
        ax.set_xlabel("Batch")
        ax.set_ylim(-0.05, 1.05)
    axes[0].legend(fontsize=7, loc="best")
    fig.tight_layout()
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


def fig_v8():
    metrics = [("reward/correct", "Correctness"),
               ("monitor/hint_in_output", "Hint in output"),
               ("monitor/hint_in_cot", "Hint in CoT")]
    models = [("qwen36-35ba3b", "Qwen3.6-35B-A3B", "grpo-v8base-qwen36-35ba3b-{pw}-s42"),
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
    fig, axes = plt.subplots(1, 2, figsize=figsize(1.0, 0.42), sharey=True)
    for ax, (size, name) in zip(axes, [("8b", "Qwen3-8B"), ("32b", "Qwen3-32B")]):
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
    axes[0].set_ylabel("CoT hint detection")
    axes[0].legend(loc="upper right", fontsize=7.5, frameon=True, framealpha=0.95)
    fig.tight_layout(); fig.savefig(FIG / "lambda_sweep.pdf"); plt.close(fig)


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


if __name__ == "__main__":
    for f in (fig_sft, fig_mitigations, fig_stacking, fig_mitigations_t300,
              fig_t300_vs_4096, fig_poly, fig_v8, fig_extra, fig_sweep):
        f()
        print(f"  {f.__name__}")
    print("Done. PDFs in figures/.")
