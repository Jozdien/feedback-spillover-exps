"""Async-RL validation: compare async_k=4 runs (logs/grpo-async300-*) with the synchronous runs of
the same protocol (logs/grpo-grpo300-nosft-*, logs/grpo-mit300-pirate-pen-*). Prints final-window
means +- std per arm and wall-clock per run, and plots seed-mean curves (task, M_out, CoT) sync vs
async per arm with 95% CI bands. Output: plots/async_vs_sync.png. Usage: uv run scripts/plot_async_vs_sync.py
"""
import glob
import json
import re

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LAST = 27
ARMS = {  # arm -> (sync glob, async glob, label)
    "nosft-ctrl": ("logs/grpo-grpo300-nosft-ctrl-8b-s??", "logs/grpo-async300-nosft-ctrl-8b-s??", "No-SFT control"),
    "nosft-pen": ("logs/grpo-grpo300-nosft-pen-8b-s??", "logs/grpo-async300-nosft-pen-8b-s??", "No-SFT penalty"),
    "pirate-pen": ("logs/grpo-mit300-pirate-pen-8b-s??", "logs/grpo-async300-pirate-pen-8b-s??", "Pirate-output penalty"),
}
KEYS = [("reward/correct", "follow hint"), ("monitor/hint_in_output", "M_out (output judge)"), ("monitor/hint_in_cot", "CoT detection")]


def load(pattern):
    runs = []
    for d in sorted(glob.glob(pattern)):
        ms = {}
        for ln in open(f"{d}/metrics.jsonl"):
            x = json.loads(ln)
            ms[x["step"]] = x
        steps = sorted(ms)
        if len(steps) < 50:
            continue
        seed = re.search(r"-s(\d+)$", d).group(1)
        wall = sum(ms[s].get("time/total", 0) for s in steps)
        stale = np.mean([ms[s].get("async/staleness_mean", 0) for s in steps])
        runs.append({"seed": seed, "steps": steps, "ms": ms, "wall": wall, "stale": stale})
    return runs


def final(runs, key):
    return np.array([np.mean([r["ms"][s][key] for s in r["steps"][-LAST:]]) for r in runs])


def main():
    fig, axes = plt.subplots(len(ARMS), 3, figsize=(15, 4 * len(ARMS)), squeeze=False)
    print(f"{'arm':22s} {'mode':6s} n  follow        M_out         CoT           wall/run   staleness")
    for i, (arm, (gs, ga, label)) in enumerate(ARMS.items()):
        for mode, pat, color in [("sync", gs, "#4878CF"), ("async", ga, "#D65F5F")]:
            runs = load(pat)
            if not runs:
                continue
            f = lambda k: f"{final(runs, k).mean():.2f}±{final(runs, k).std():.2f}"  # noqa: E731
            print(f"{label:22s} {mode:6s} {len(runs)}  {f('reward/correct'):12s}  {f('monitor/hint_in_output'):12s}  "
                  f"{f('monitor/hint_in_cot'):12s}  {np.mean([r['wall'] for r in runs])/60:6.0f} min  {np.mean([r['stale'] for r in runs]):.2f}")
            n = min(len(r["steps"]) for r in runs)
            for j, (key, kl) in enumerate(KEYS):
                mat = np.array([[r["ms"][s][key] for s in r["steps"][:n]] for r in runs])
                k = 15
                sm = np.array([np.convolve(row, np.ones(k) / k, mode="valid") for row in mat])
                x = np.arange(sm.shape[1]) + k // 2
                mu, ci = sm.mean(0), 1.96 * sm.std(0, ddof=1) / np.sqrt(len(runs)) if len(runs) > 1 else 0
                ax = axes[i][j]
                ax.plot(x, mu, color=color, label=f"{mode} (n={len(runs)})", linewidth=1.6)
                ax.fill_between(x, mu - ci, mu + ci, color=color, alpha=0.15)
                ax.set_title(f"{label}: {kl}", fontsize=12)
                ax.set_ylim(-0.02, 1.02)
                ax.set_xlabel("batch", fontsize=11)
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.legend(fontsize=9, frameon=False)
    fig.suptitle("Async (K=4) vs synchronous GRPO at T=300, GPT-4.1 judge — seed means ± 95% CI (15-batch smoothing)", fontsize=13)
    plt.tight_layout()
    plt.savefig("plots/async_vs_sync.png", dpi=170)
    print("saved plots/async_vs_sync.png")


if __name__ == "__main__":
    main()
