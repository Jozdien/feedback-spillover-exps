"""Pareto plot (CoT monitor detection vs training reward) for the definitive QA protocol: T=300, GRPO,
GPT-4.1 judge, 3200 episodes, lambda=2, and — where marked "gated" — the GPT-4.1 explanation gate
(RESULTS §16c/16d). Per-seed dots + arm means with 95% CI. Arms and their run families:
  no-SFT control (grpo300, 10 seeds) · no-SFT penalty, gated (explj300, 5) · reward targeting (mit300, 5)
  Mind & Face (mit300, 5) · targeted M&F, explanation required (expl300, 5)
  pirate v2 + style reward, gated: control / penalty (explj300 *sr*, 10/10) · Pig-Latin + style reward,
  gated: control / penalty (5/10) · pirate v2 / Pig-Latin gated WITHOUT style reward (5/5; style decays)
  normal-Alpaca SFT penalty, gated (5) · pirate v1 penalty, no gate (mit300, 5; bare outputs — the
  paper's original number, shown hollow).
Output: plots/gated_pareto.png/.pdf + plots/gated_pareto.json. Usage: uv run scripts/plot_gated_pareto.py
"""
import glob
import json
from collections import defaultdict

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LAST = 27
# key -> (glob, label, color, marker, filled)
ARMS = {
    "nosft-ctrl": ("logs/grpo-grpo300-nosft-ctrl-8b-s??", "No penalty (no-SFT control)", "#4878CF", "o", True),
    "nosft-pen": ("logs/grpo-explj300-nosft-pen-8b-s??", "Penalty, no-SFT (gated)", "#D65F5F", "s", True),
    "rt": ("logs/grpo-mit300-rt-8b-s??", "Reward targeting", "#B47CC7", "D", True),
    "mf": ("logs/grpo-mit300-mf-8b-s??", "Mind & Face", "#C4AD66", "^", True),
    "tmf": ("logs/grpo-expl300-tmf-8b-s??", "Targeted Mind & Face (expl. required)", "#77BEDB", "P", True),
    "piglatinsr-ctrl": ("logs/grpo-explj300-piglatinsr-ctrl-8b-s??", "Pig-Latin + style reward, no penalty", "#8FA37A", "o", True),
    "piglatinsr-pen": ("logs/grpo-explj300-piglatinsr-pen-8b-s??", "Pig-Latin + style reward + penalty (gated)", "#2E8B57", "s", True),
    "piratev2sr-ctrl": ("logs/grpo-explj300-piratev2sr-ctrl-8b-s??", "Pirate v2 + style reward, no penalty", "#B8A27A", "o", True),
    "piratev2sr-pen": ("logs/grpo-explj300-piratev2sr-pen-8b-s??", "Pirate v2 + style reward + penalty (gated)", "#E08E2B", "s", True),
    "piglatin-pen": ("logs/grpo-explj300-piglatin-pen-8b-s??", "Pig-Latin, style not rewarded (gated)", "#2E8B57", "s", False),
    "piratev2-pen": ("logs/grpo-explj300-piratev2-pen-8b-s??", "Pirate v2, style not rewarded (gated)", "#E08E2B", "s", False),
    "normalalpaca-pen": ("logs/grpo-explj300-normalalpaca-pen-8b-s??", "Normal-output SFT + penalty (gated)", "#8C8C8C", "v", True),
    "pirate-v1-pen": ("logs/grpo-mit300-pirate-pen-8b-s??", "Pirate v1 + penalty, no gate (bare outputs)", "#6ACC65", "x", False),
}


def load():
    arms = defaultdict(list)
    for key, (pat, *_) in ARMS.items():
        for d in sorted(glob.glob(pat)):
            ms = {}
            for ln in open(f"{d}/metrics.jsonl"):
                x = json.loads(ln)
                ms[x["step"]] = x
            steps = sorted(ms)
            if len(steps) < 266:
                continue
            tail = [ms[s] for s in steps[-LAST:]]
            task = np.mean([x["reward/correct"] for x in tail])
            out = np.mean([x["monitor/hint_in_output"] for x in tail])
            cot = np.mean([x["monitor/hint_in_cot"] for x in tail])
            arms[key].append((cot, task - 2 * out, task, out))
    return arms


def main():
    arms = load()
    fig, ax = plt.subplots(figsize=(11, 7.5))
    summary = {}
    for key, (_, label, color, marker, filled) in ARMS.items():
        pts = np.array(arms.get(key, []))
        if not len(pts):
            continue
        x, y = pts[:, 0], pts[:, 1]
        n = len(pts)
        face = color if filled else "none"
        ax.scatter(x, y, facecolors=face, edgecolors=color, marker=marker, s=40, alpha=0.35 if filled else 0.6, linewidths=1) if marker != "x" else ax.scatter(x, y, color=color, marker=marker, s=40, alpha=0.6)
        ci = lambda v: 1.96 * v.std(ddof=1) / np.sqrt(n) if n > 1 else 0  # noqa: E731
        ax.errorbar(x.mean(), y.mean(), xerr=ci(x), yerr=ci(y), color=color, marker=marker, markersize=13,
                    markerfacecolor=face, markeredgecolor="black" if filled else color, capsize=4, linewidth=1.5,
                    label=f"{label} (n={n})", zorder=5)
        dy = 12 if filled else -18
        ax.annotate(f"{x.mean():.2f}", (x.mean(), y.mean()), textcoords="offset points", xytext=(0, dy),
                    ha="center", fontsize=10, color=color)
        summary[key] = {"label": label, "n": n, "cot": round(float(x.mean()), 3), "cot_sd": round(float(x.std(ddof=1)), 3) if n > 1 else 0.0,
                        "train_reward": round(float(y.mean()), 3), "task": round(float(pts[:, 2].mean()), 3), "m_out": round(float(pts[:, 3].mean()), 3)}
    ax.set_xlabel("CoT monitor detection rate (↑ = more monitorable)", fontsize=14)
    ax.set_ylabel("Training reward = task − 2·M_out (↑ higher is better)", fontsize=14)
    ax.set_title("Explanation gate on: a maintained output style keeps the CoT monitorable; a decaying one does not\n"
                 "Qwen3-8B, T=300, GRPO, GPT-4.1 judges. Dots = seeds, markers = mean ± 95% CI. Hollow = style not rewarded / bare outputs",
                 fontsize=12)
    ax.set_xlim(0, 0.85)
    ax.set_ylim(-1.0, 1.1)
    ax.axhline(0, color="#bbbbbb", linewidth=0.8)
    ax.grid(axis="y", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=12)
    ax.legend(fontsize=9.5, loc="lower left", frameon=False, ncol=1)
    plt.tight_layout()
    plt.savefig("plots/gated_pareto.png", dpi=200)
    plt.savefig("plots/gated_pareto.pdf")
    json.dump(summary, open("plots/gated_pareto.json", "w"), indent=1)
    for k, v in summary.items():
        print(f"{v['label']:48s} n={v['n']:2d}  CoT {v['cot']:.2f}±{v['cot_sd']:.2f}  reward {v['train_reward']:.2f}  task {v['task']:.2f}  M_out {v['m_out']:.2f}")
    print("saved plots/gated_pareto.png")


if __name__ == "__main__":
    main()
