"""Pareto plot (CoT monitor detection vs training reward), the original paper's Fig 4 format, for
the T=300 / GPT-4.1-judge / GRPO protocol runs: 10-seed no-SFT control + penalty, 5-seed
pirate-output control + penalty, reward targeting, Mind & Face, targeted M&F. Per-seed dots +
arm means with 95% CI across seeds. Reads logs/grpo-grpo300-* and logs/grpo-mit300-*.
Output: plots/mit300_pareto.png (+ .pdf). Usage: uv run scripts/plot_mit300.py
"""
import glob
import json
import re
from collections import defaultdict

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LAST = 27
ARMS = {  # key -> (label, color, marker)
    "nosft-ctrl": ("No penalty (no-SFT control)", "#4878CF", "o"),
    "nosft-pen": ("Penalty (no-SFT)", "#D65F5F", "s"),
    "pirate-ctrl": ("Pirate-output, no penalty", "#8C8C8C", "o"),
    "pirate-pen": ("Pirate-output + penalty", "#6ACC65", "s"),
    "rt": ("Reward targeting", "#B47CC7", "D"),
    "mf": ("Mind & Face", "#C4AD66", "^"),
    "tmf": ("Targeted Mind & Face", "#77BEDB", "P"),
}


def load():
    arms = defaultdict(list)
    for d in glob.glob("logs/grpo-grpo300-*-s??") + glob.glob("logs/grpo-mit300-*-s??"):
        m = re.match(r"logs/grpo-(?:grpo300|mit300)-(.+)-8b-s(\d+)$", d)
        if not m:
            continue
        arm = m.group(1)
        ms = {}
        for ln in open(f"{d}/metrics.jsonl"):
            x = json.loads(ln)
            ms[x["step"]] = x
        tail = [ms[s] for s in sorted(ms)[-LAST:]]
        task = np.mean([x["reward/correct"] for x in tail])
        out = np.mean([x["monitor/hint_in_output"] for x in tail])
        cot = np.mean([x["monitor/hint_in_cot"] for x in tail])
        arms[arm].append((cot, task - 2 * out, task, out))
    return arms


def main():
    arms = load()
    fig, ax = plt.subplots(figsize=(10, 7))
    for key, (label, color, marker) in ARMS.items():
        pts = np.array(arms.get(key, []))
        if not len(pts):
            continue
        x, y = pts[:, 0], pts[:, 1]
        ax.scatter(x, y, color=color, marker=marker, s=40, alpha=0.35, edgecolors="none")
        n = len(pts)
        ci = lambda v: 1.96 * v.std(ddof=1) / np.sqrt(n) if n > 1 else 0  # noqa: E731
        ax.errorbar(x.mean(), y.mean(), xerr=ci(x), yerr=ci(y), color=color, marker=marker, markersize=13,
                    markeredgecolor="black", capsize=4, linewidth=1.5, label=f"{label} (n={n})", zorder=5)
        ax.annotate(f"{x.mean():.2f}", (x.mean(), y.mean()), textcoords="offset points", xytext=(0, 12),
                    ha="center", fontsize=10, color=color)
    ax.set_xlabel("CoT monitor detection rate (↑ = more monitorable)", fontsize=14)
    ax.set_ylabel("Training reward = task − 2·M_out (↑ higher is better)", fontsize=14)
    ax.set_title("Pirate-output keeps the CoT monitorable at full reward; RT and TMF close behind\n"
                 "(Qwen3-8B, T=300, GPT-4.1 judge, GRPO, 3200 episodes; dots = seeds, markers = mean ± 95% CI)",
                 fontsize=13)
    ax.set_xlim(0, 0.8)
    ax.set_ylim(-1.0, 1.1)
    ax.axhline(0, color="#bbbbbb", linewidth=0.8)
    ax.grid(axis="y", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=12)
    ax.legend(fontsize=10.5, loc="lower left", frameon=False)
    plt.tight_layout()
    plt.savefig("plots/mit300_pareto.png", dpi=200)
    plt.savefig("plots/mit300_pareto.pdf")
    print("saved plots/mit300_pareto.png")


if __name__ == "__main__":
    main()
