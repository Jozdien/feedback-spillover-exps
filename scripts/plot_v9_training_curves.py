"""Plot V9 training curves: mitigation baselines (QA, 32B) and the polynomial env suite.

1. v9_qa_mitigations_32b.png — all mitigation conditions at pw=-2 on the QA env,
   with no-mitigation references (v7base penalty, v6pw-2 pirate-output).
2. v9_poly_32b.png — the polynomial-env condition suite.

Curves are seed-averaged (where both seeds exist), smoothed, one color per condition.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

LOG_BASE = Path("/home/jose/feedback-spillover-exps/logs")
OUT_DIR = Path("/home/jose/feedback-spillover-exps/plots")

METRICS = [
    ("reward/correct", "Correctness"),
    ("monitor/hint_in_output", "Hint in Output"),
    ("monitor/hint_in_cot", "Hint in CoT"),
]

QA_CONDITIONS = [
    ("Penalty (no mitigation)", "#7f7f7f", ["grpo-v7base-32b-pw-2-s42", "grpo-v7base-32b-pw-2-s43"]),
    ("Reward targeting", "#1f77b4", ["grpo-v9rt-32b-pw-2-s42", "grpo-v9rt-32b-pw-2-s43"]),
    ("Mind & Face", "#2ca02c", ["grpo-v9mf-32b-pw-2-s42", "grpo-v9mf-32b-pw-2-s43"]),
    ("Targeted M&F", "#9467bd", ["grpo-v9tmf-32b-pw-2-s42", "grpo-v9tmf-32b-pw-2-s43"]),
    ("Pirate output (style only)", "#d62728", ["grpo-v6pw-2-32b-pirate-output-alpaca-qwen-s42", "grpo-v6pw-2-32b-pirate-output-alpaca-qwen-s43"]),
    ("Pirate + RT", "#ff7f0e", ["grpo-v9rtpirate-32b-pw-2-s42", "grpo-v9rtpirate-32b-pw-2-s43"]),
    ("Pirate + M&F", "#e377c2", ["grpo-v9mfpirate-32b-pw-2-s42", "grpo-v9mfpirate-32b-pw-2-s43"]),
    ("Pirate + TMF", "#17becf", ["grpo-v9tmfpirate-32b-pw-2-s42", "grpo-v9tmfpirate-32b-pw-2-s43"]),
]

POLY_CONDITIONS = [
    ("Control (pw=0)", "#7f7f7f", ["grpo-v9poly-ctrl-32b-pw0-s42", "grpo-v9poly-ctrl-32b-pw0-s43"]),
    ("Penalty", "#1f77b4", ["grpo-v9poly-pen-32b-pw-2-s42", "grpo-v9poly-pen-32b-pw-2-s43"]),
    ("Reward targeting", "#ff7f0e", ["grpo-v9poly-rt-32b-pw-2-s42", "grpo-v9poly-rt-32b-pw-2-s43"]),
    ("Mind & Face", "#2ca02c", ["grpo-v9poly-mf-32b-pw-2-s42", "grpo-v9poly-mf-32b-pw-2-s43"]),
    ("Targeted M&F", "#9467bd", ["grpo-v9poly-tmf-32b-pw-2-s42", "grpo-v9poly-tmf-32b-pw-2-s43"]),
    ("Pirate output", "#d62728", ["grpo-v9poly-pirate-32b-pw-2-s42", "grpo-v9poly-pirate-32b-pw-2-s43"]),
    ("Pirate control (pw=0)", "#e377c2", ["grpo-v9poly-piratectrl-32b-pw0-s42", "grpo-v9poly-piratectrl-32b-pw0-s43"]),
]


def smooth(vals, window=20):
    arr = np.asarray(vals, dtype=float)
    if len(arr) < window:
        return arr
    return np.convolve(arr, np.ones(window) / window, mode="valid")


def condition_curve(run_names, metric_key, window=20):
    curves = []
    for r in run_names:
        path = LOG_BASE / r / "metrics.jsonl"
        if not path.exists():
            continue
        vals = []
        for line in open(path):
            d = json.loads(line)
            if metric_key in d:
                vals.append(d[metric_key])
        if vals:
            curves.append(smooth(vals, window))
    if not curves:
        return None
    n = min(len(c) for c in curves)
    aligned = np.array([c[:n] for c in curves])
    return np.arange(n), aligned.mean(axis=0)


POLY_METRICS = [
    ("reward/correct", "Correctness"),
    ("monitor/expanded_in_output", "Expanded form in Output"),
    ("monitor/expanded_in_cot", "Expanded form in CoT"),
]


def plot_suite(conditions, fname, title, metrics=METRICS):
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    fig.suptitle(title, fontsize=14, y=1.0)
    for col, (metric_key, metric_label) in enumerate(metrics):
        ax = axes[col]
        for label, color, runs in conditions:
            data = condition_curve(runs, metric_key)
            if data is None:
                continue
            x, y = data
            ax.plot(x, y, color=color, linewidth=1.6, label=label)
        ax.set_title(metric_label, fontsize=11)
        ax.set_xlabel("Batch", fontsize=10)
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if col == 0:
            ax.legend(fontsize=8, loc="best")
    plt.tight_layout()
    out = OUT_DIR / fname
    plt.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {out}")


def main():
    plot_suite(
        QA_CONDITIONS, "v9_qa_mitigations_32b.png",
        "QA env, Qwen3-32B, pw=-2 — mitigation baselines vs style separation (seed-avg, w=20)",
    )
    plot_suite(
        POLY_CONDITIONS, "v9_poly_32b.png",
        "Polynomial env, Qwen3-32B — condition suite (seed-avg, w=20)",
        metrics=POLY_METRICS,
    )


if __name__ == "__main__":
    main()
