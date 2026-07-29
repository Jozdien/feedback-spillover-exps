"""Presentation figure: CoT hint-acknowledgment trajectories for every run across
the 5 new harder/safety envs.

Data source per run (IMPORTANT — the live judge was corrupted by an OpenAI quota
outage that faked a 'collapse'): use rescored.jsonl (offline re-score with a healthy
judge) wherever it exists; else fall back to the live monitor/hint_in_cot metric
(only used for runs with few, scattered 429s, which smoothing absorbs).

Metric = hint acknowledgment in the CoT (higher = more monitorable). Spillover =
the penalty pushing this down relative to the λ=0 control.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

PLOTS = Path("plots")
PLOTS.mkdir(exist_ok=True)


def load_cot(run, offset=0):
    """(batch, cot) per-batch trajectory. Prefer rescored.jsonl, else live metrics."""
    d = Path(f"logs/grpo-{run}-s42")
    rj, mj = d / "rescored.jsonl", d / "metrics.jsonl"
    if rj.exists():
        by = {}
        for line in open(rj):
            r = json.loads(line)
            by.setdefault(r["batch"], []).append(r.get("cot_score", np.nan))
        bs = sorted(by)
        return (np.array(bs) + offset,
                np.array([np.nanmean(by[b]) for b in bs]), "rescored")
    if mj.exists():
        seen, b, v = set(), [], []
        for line in open(mj):
            r = json.loads(line)
            bt = r.get("progress/batch")
            if bt in seen:
                continue
            seen.add(bt)
            b.append(bt)
            v.append(r.get("monitor/hint_in_cot", np.nan))
        return np.array(b) + offset, np.array(v), "live"
    return np.array([]), np.array([]), "missing"


def smooth(b, v, w=21):
    m = ~np.isnan(v)
    b, v = b[m], v[m]
    if len(v) < w:
        return b, v
    vs = np.convolve(v, np.ones(w) / w, mode="valid")
    return b[w - 1:], vs


# (run, label, color, linestyle, offset, valid_until). red=penalty, blue=control,
# green=pirate mitig., orange=clean rerun, purple=Nemotron. solid=8B, dashed=35B,
# dotted=120B. valid_until = batch at which judge-outage made TRAINING unreliable
# (penalty went off); None = trustworthy throughout. Controls (λ=0) are never
# training-contaminated (judge not in their reward loop) → full length.
PANELS = [
    ("Env 1 — Encoded MMLU hint\n(hack needs the CoT)", [
        ("env1enc-8b-pw2", "8B penalty* (task rejected)", "#D65F5F", "-", 0, None),
        ("env1enc-35ba3b-pw2", "35B penalty", "#D65F5F", "--", 0, 600),
        ("env1enc-ctrl-35ba3b", "35B control λ=0", "#4878CF", "--", 0, None),
    ]),
    ("Env 2 — Hard math\n(leaked solution step)", [
        ("env2math-8b-pw2", "8B penalty", "#D65F5F", "-", 0, 750),
        ("env2math-ctrl-8b", "8B control λ=0", "#4878CF", "-", 0, None),
        ("env2math-35ba3b-pw2", "35B penalty", "#D65F5F", "--", 0, None),
        ("env2pirate-8b-pw2", "8B penalty + pirate-SFT (mitig.)", "#6ACC65", "-", 0, None),
        ("env2math-8b-pw2-r700", "8B penalty clean re-run (700→)", "#EE9040", "-", 700, None),
    ]),
    ("Env 4 — GPQA\n(wrong-answer hint)", [
        ("env4gpqa-8b-pw2", "8B penalty", "#D65F5F", "-", 0, 750),
        ("env4gpqa-ctrl-8b", "8B control λ=0", "#4878CF", "-", 0, None),
        ("env4gpqa-35ba3b-pw2", "35B penalty", "#D65F5F", "--", 0, 500),
        ("env4gpqa-ctrl-35ba3b", "35B control λ=0", "#4878CF", "--", 0, None),
        ("env4pirate-8b-pw2", "8B penalty + pirate-SFT (mitig.)", "#6ACC65", "-", 0, None),
        ("env4gpqa-8b-pw2-r700", "8B penalty clean re-run (700→)", "#EE9040", "-", 700, None),
    ]),
    ("Env 5 — APPS backdoor\n(reward hacking)", [
        ("env5apps-35ba3b-pw2", "35B penalty", "#D65F5F", "--", 0, 400),
        ("env5apps-nemotron120b-pw2", "Nemotron-120B penalty (just started)", "#9B59B6", ":", 0, None),
    ]),
]


def main():
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    for ax, (title, runs) in zip(axes.flat, PANELS):
        for run, label, color, ls, off, valid_until in runs:
            b, v, src = load_cot(run, off)
            if valid_until is not None:
                m = b <= valid_until
                b, v = b[m], v[m]
            if len(b) < 5:
                continue
            is_rerun = "re-run" in label
            bs, vs = smooth(b, v)
            ax.plot(bs, vs, color=color, ls=ls, lw=3.2 if is_rerun else 2.4,
                    label=label, alpha=0.95, zorder=5 if is_rerun else 3)
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Training batch", fontsize=12)
        ax.set_ylabel("Hint acknowledgment in CoT (↑ monitorable)", fontsize=11)
        ax.set_ylim(-0.03, 1.02)
        ax.set_xlim(0, 1000)
        ax.grid(axis="y", alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(fontsize=9.5, loc="best", framealpha=0.92)
    fig.suptitle(
        "Feedback spillover across 5 harder, safety-relevant environments\n"
        "CoT hint acknowledgment over RL training  (↑ = the CoT still reveals the hint = monitorable)",
        fontsize=15, fontweight="bold",
    )
    cap = (
        "Line style = model: solid 8B · dashed 35B-A3B · dotted Nemotron-120B.    "
        "Colour = condition: red output-penalty (λ=2) · blue control (λ=0) · "
        "green +pirate-SFT mitigation · orange clean re-run.\n"
        "Penalty lines are truncated where the OpenAI-judge outage made that training "
        "unreliable (the penalty silently switched off); the orange clean re-runs resume "
        "properly-penalised training from batch 700.  Controls are unaffected.  "
        "Env 3 (Impossible-LCB) omitted — 0 reward variance, untrainable."
    )
    fig.text(0.5, 0.005, cap, ha="center", va="bottom", fontsize=10.5, wrap=True)
    fig.tight_layout(rect=[0, 0.075, 1, 0.93])
    out = PLOTS / "all_env_trajectories.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print("saved", out)


if __name__ == "__main__":
    main()
