"""Plot split-budget paper replication results."""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

RUNS = [
    ("QA baseline", "/tmp/spillover-exps/split-qa-baseline", "#4878CF"),
    ("QA control", "/tmp/spillover-exps/split-qa-control", "#888888"),
    ("Poly baseline", "/tmp/spillover-exps/split-poly-baseline", "#D65F5F"),
    ("Poly control", "/tmp/spillover-exps/split-poly-control", "#B8B8B8"),
]


def load(path):
    steps, out, cot = [], [], []
    with open(Path(path) / "metrics.jsonl") as f:
        for line in f:
            m = json.loads(line)
            steps.append(m["progress/batch"])
            out.append(m.get("monitor/hint_in_output", m.get("monitor/expanded_in_output")))
            cot.append(m.get("monitor/hint_in_cot", m.get("monitor/expanded_in_cot")))
    return steps, out, cot


def smooth(v, w=10):
    v = np.array(v)
    if len(v) < w:
        return v
    k = np.ones(w) / w
    pad = np.pad(v, (w // 2, w - 1 - w // 2), mode="edge")
    return np.convolve(pad, k, mode="valid")


data = {name: load(p) for name, p, _ in RUNS}

print(f"{'Run':<16} {'Start_out':<12} {'Start_cot':<12} {'End_out':<10} {'End_cot':<10}")
print("-" * 62)
for name in data:
    _, out, cot = data[name]
    print(f"{name:<16} {np.mean(out[:5]):<12.3f} {np.mean(cot[:5]):<12.3f} "
          f"{np.mean(out[-5:]):<10.3f} {np.mean(cot[-5:]):<10.3f}")

fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex="col")
for row, key, ylabel in [(0, "out", "Output rate (penalized)"),
                          (1, "cot", "CoT rate (measures spillover)")]:
    for col, pairs in enumerate([
        [("QA baseline", "#4878CF"), ("QA control", "#888888")],
        [("Poly baseline", "#D65F5F"), ("Poly control", "#B8B8B8")],
    ]):
        ax = axes[row, col]
        for name, color in pairs:
            steps, out, cot = data[name]
            series = out if key == "out" else cot
            style = "-" if key == "out" else "--"
            ax.plot(steps, smooth(series), color=color, linewidth=2, linestyle=style, label=name)
        ax.set_ylim(-0.05, 1.1)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(loc="upper right", fontsize=9)
        if col == 0:
            ax.set_ylabel(ylabel)
        if row == 1:
            ax.set_xlabel("Training step")

axes[0, 0].set_title("QA: hint in output")
axes[0, 1].set_title("Poly: expanded form in output")
axes[1, 0].set_title("QA: hint in CoT")
axes[1, 1].set_title("Poly: expanded form in CoT")

fig.suptitle("Split-budget paper replication (Qwen3-8B, 100 steps)",
             fontsize=14, fontweight="bold", y=1.00)
plt.tight_layout()
plt.savefig("split_budget_curves.png", dpi=150, bbox_inches="tight")
print("\nSaved split_budget_curves.png")
