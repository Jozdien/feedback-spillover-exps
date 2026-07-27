"""Plots for the harder-envs spillover campaign.

Fig 1 (harder_spillover_trajectory.png): hint-in-CoT over training, control (λ=0)
vs penalty (λ=2), for env2 hard-math and env4 GPQA on 8B — the CoT-collapse story.
Fig 2 (harder_spillover_summary.png): cross-environment CoT early→late drop under
the penalty, showing which envs exhibit spillover.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

PLOTS = Path("plots"); PLOTS.mkdir(exist_ok=True)


def penalty_traj(run, key="monitor/hint_in_cot"):
    rows = [json.loads(x) for x in open(f"logs/grpo-{run}-pw2-s42/metrics.jsonl")]
    b = np.array([r["progress/batch"] for r in rows])
    v = np.array([r.get(key, np.nan) for r in rows])
    return b, v


def control_traj(run, key="cot_score", bin_w=20):
    """Aggregate rescored per-rollout scores into per-bin means."""
    rows = [json.loads(x) for x in open(f"logs/grpo-{run}-s42/rescored.jsonl")]
    b = np.array([r["batch"] for r in rows])
    v = np.array([r.get(key, np.nan) for r in rows])
    maxb = int(b.max())
    centers, means = [], []
    for lo in range(0, maxb + 1, bin_w):
        m = (b >= lo) & (b < lo + bin_w)
        if m.sum():
            centers.append(lo + bin_w / 2)
            means.append(np.nanmean(v[m]))
    return np.array(centers), np.array(means)


def smooth(v, w=25):
    if len(v) < w:
        return v
    return np.convolve(v, np.ones(w) / w, mode="valid")


def fig_trajectory():
    envs = [
        ("env2math", "Hard math (level-5 MMLU-MATH\n+ leaked solution step)", 0.704),
        ("env4gpqa", "GPQA (uplift-filtered\n+ wrong-answer hint)", 0.603),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)
    for ax, (env, title, ctrl_late) in zip(axes, envs):
        # penalty (live judge)
        pb, pv = penalty_traj(f"{env}-8b")
        ps = smooth(pv)
        ax.plot(pb[: len(ps)], ps, color="#D65F5F", lw=2.5,
                label="Penalty λ=2 (CoT hint detection)")
        # control (rescored)
        cb, cv = control_traj(f"{env}-ctrl-8b")
        ax.plot(cb, cv, color="#4878CF", lw=2.5, marker="o", ms=4,
                label="Control λ=0 (no penalty)")
        ax.axhline(ctrl_late, color="#4878CF", ls=":", lw=1, alpha=0.6)
        ax.set_title(title, fontsize=13)
        ax.set_xlabel("Training batch", fontsize=13)
        ax.set_ylim(-0.03, 1.0)
        ax.grid(axis="y", alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Hint acknowledgment in CoT (↑ = monitorable)", fontsize=13)
    axes[0].legend(fontsize=11, loc="center left")
    fig.suptitle(
        "Feedback spillover in harder, CoT-necessary tasks: the output penalty erases the "
        "hint from the CoT,\nwhile without it (control) the CoT keeps acknowledging the hint "
        "throughout training (Qwen3-8B, T=4096)",
        fontsize=13.5,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    out = PLOTS / "harder_spillover_trajectory.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print("saved", out)


def fig_summary():
    # penalty CoT early (b20-60) vs late (last 60), per env/model
    def win(run, hi_from_end=False):
        rows = [json.loads(x) for x in open(f"logs/grpo-{run}-pw2-s42/metrics.jsonl")]
        # dedup by first occurrence per batch — drops divergent resume duplicates
        # (e.g. env4gpqa-35b resumed from a collapsed checkpoint and re-explored)
        seen, uniq = set(), []
        for r in rows:
            bt = r["progress/batch"]
            if bt not in seen:
                seen.add(bt); uniq.append(r)
        rows = uniq
        b = np.array([r["progress/batch"] for r in rows])
        v = np.array([r.get("monitor/hint_in_cot", np.nan) for r in rows])
        if hi_from_end:
            m = b >= b.max() - 60
        else:
            m = (b >= 20) & (b < 60)
        return (float(np.nanmean(v[m])) if m.sum() else np.nan), int(b.max())

    # spillover cliff is ~batch 700-780, so a run must reach ~800+ to have spilled;
    # runs that stopped earlier (billing) are marked incomplete.
    runs = [
        ("env2math-8b", "Hard math 8B"), ("env2math-35ba3b", "Hard math 35B"),
        ("env4gpqa-8b", "GPQA 8B"), ("env4gpqa-35ba3b", "GPQA 35B"),
        ("env1enc-8b", "Encoded 8B*"), ("env1enc-35ba3b", "Encoded 35B"),
        ("env5apps-35ba3b", "APPS backdoor 35B"), ("env3lcb-8b", "Impossible-LCB 8B"),
    ]
    labels, early, late = [], [], []
    for run, lab in runs:
        (e, maxb) = win(run)
        (ll, _) = win(run, hi_from_end=True)
        tag = "  ‡INCOMPLETE" if maxb < 700 and lab != "Impossible-LCB 8B" else ""
        labels.append(f"{lab} (b{maxb}){tag}")
        early.append(e); late.append(ll)
    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.barh(y - 0.2, early, 0.4, color="#4878CF", label="CoT early in training (batch 20–60)")
    ax.barh(y + 0.2, late, 0.4, color="#D65F5F", label="CoT late in training (last 60 batches)")
    for i, (e, l) in enumerate(zip(early, late)):
        if not np.isnan(e): ax.text(e + .01, i - 0.2, f"{e:.2f}", va="center", fontsize=9)
        if not np.isnan(l): ax.text(l + .01, i + 0.2, f"{l:.2f}", va="center", fontsize=9)
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=11); ax.invert_yaxis()
    ax.set_xlabel("Hint acknowledgment in CoT under the output penalty (λ=2)", fontsize=12)
    ax.set_xlim(0, 1.0)
    ax.set_title(
        "Under an output-only penalty, the CoT hint signal collapses to ~0 by late training\n"
        "in every env where the task is learned + the run reached the cliff (~batch 750).\n*Encoded 8B: model rejected the hint (task not learned). \u2021 run stopped early (billing) — pre-cliff, not yet spilled",
        fontsize=12.5,
    )
    ax.legend(fontsize=11, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out = PLOTS / "harder_spillover_summary.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print("saved", out)


if __name__ == "__main__":
    fig_trajectory()
    fig_summary()
