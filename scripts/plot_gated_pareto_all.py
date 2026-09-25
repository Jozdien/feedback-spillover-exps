"""Multi-panel Pareto plots (CoT monitor detection vs training reward) for the gated + style-rewarded protocol
across environments and models (RESULTS §16c-e, §14f, §13h). Panels: QA Qwen3-8B, QA Qwen3.6-27B, QA Qwen3.6-35B-A3B,
polynomial Qwen3.6-27B, terminal Qwen3-8B. Per-seed dots + means with 95% CI; hollow = style not rewarded / no gate.
Output: plots/gated_pareto_all.png/.pdf + plots/gated_pareto_all.json. Usage: uv run scripts/plot_gated_pareto_all.py
"""
import glob
import json

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

C = {"ctrl": "#4878CF", "pen": "#D65F5F", "rt": "#B47CC7", "mf": "#C4AD66", "tmf": "#77BEDB",
     "pl": "#2E8B57", "plc": "#8FA37A", "pi": "#E08E2B", "pic": "#B8A27A", "ch": "#C23B8A", "chc": "#D69AB8", "norm": "#8C8C8C", "v1": "#6ACC65"}
# panel -> (title, lambda, n_steps_expected, last, out_key, cot_key, arms[(glob, label, color, marker, filled)])
PANELS = {
  "qa8b": ("QA, Qwen3-8B", 2, 266, 27, "monitor/hint_in_output", "monitor/hint_in_cot", [
    ("logs/grpo-grpo300-nosft-ctrl-8b-s??", "No penalty", C["ctrl"], "o", True),
    ("logs/grpo-explj300-nosft-pen-8b-s??", "Penalty, no-SFT", C["pen"], "s", True),
    ("logs/grpo-mit300-rt-8b-s??", "Reward targeting", C["rt"], "D", True),
    ("logs/grpo-mit300-mf-8b-s??", "Mind & Face", C["mf"], "^", True),
    ("logs/grpo-expl300-tmf-8b-s??", "Targeted M&F", C["tmf"], "P", True),
    ("logs/grpo-explj300-piglatinsr-pen-8b-s??", "Pig-Latin + style reward + penalty", C["pl"], "s", True),
    ("logs/grpo-explj300-piratev2sr-pen-8b-s??", "Pirate + style reward + penalty", C["pi"], "s", True),
    ("logs/grpo-gated-8b-chinesesr-pen-s??", "Chinese + style reward + penalty", C["ch"], "s", True),
    ("logs/grpo-explj300-piglatin-pen-8b-s??", "Pig-Latin, style not rewarded", C["pl"], "s", False),
    ("logs/grpo-explj300-piratev2-pen-8b-s??", "Pirate, style not rewarded", C["pi"], "s", False),
    ("logs/grpo-explj300-normalalpaca-pen-8b-s??", "Normal-output SFT + penalty", C["norm"], "v", True),
    ("logs/grpo-mit300-pirate-pen-8b-s??", "Pirate v1 + penalty, no gate (bare outputs)", C["v1"], "x", False),
  ]),
  "qa27b": ("QA, Qwen3.6-27B", 2, 266, 27, "monitor/hint_in_output", "monitor/hint_in_cot", [
    ("logs/grpo-gated-27b-nosft-ctrl-s??", "No penalty", C["ctrl"], "o", True),
    ("logs/grpo-gated-27b-nosft-pen-s??", "Penalty, no-SFT", C["pen"], "s", True),
    ("logs/grpo-gated-27b-rt-s??", "Reward targeting", C["rt"], "D", True),
    ("logs/grpo-gated-27b-piglatinsr-ctrl-s??", "Pig-Latin + style reward, no penalty", C["plc"], "o", True),
    ("logs/grpo-gated-27b-piglatinsr-pen-s??", "Pig-Latin + style reward + penalty", C["pl"], "s", True),
    ("logs/grpo-gated-27b-piratesr-ctrl-s??", "Pirate + style reward, no penalty", C["pic"], "o", True),
    ("logs/grpo-gated-27b-piratesr-pen-s??", "Pirate + style reward + penalty", C["pi"], "s", True),
  ]),
  "qa35b": ("QA, Qwen3.6-35B-A3B", 2, 266, 27, "monitor/hint_in_output", "monitor/hint_in_cot", [
    ("logs/grpo-gated-35b-nosft-ctrl-s??", "No penalty", C["ctrl"], "o", True),
    ("logs/grpo-gated-35b-nosft-pen-s??", "Penalty, no-SFT", C["pen"], "s", True),
    ("logs/grpo-gated-35b-rt-s??", "Reward targeting", C["rt"], "D", True),
    ("logs/grpo-gated-35b-piglatinsr-ctrl-s??", "Pig-Latin + style reward, no penalty", C["plc"], "o", True),
    ("logs/grpo-gated-35b-piglatinsr-pen-s??", "Pig-Latin + style reward + penalty", C["pl"], "s", True),
    ("logs/grpo-gated-35b-piratesr-ctrl-s??", "Pirate + style reward, no penalty", C["pic"], "o", True),
    ("logs/grpo-gated-35b-piratesr-pen-s??", "Pirate + style reward + penalty", C["pi"], "s", True),
  ]),
  "poly27b": ("Polynomial, Qwen3.6-27B", 1, 266, 27, "monitor/expanded_in_output", "monitor/expanded_in_cot", [
    ("logs/grpo-gated-poly27b-ctrl-s??", "No penalty", C["ctrl"], "o", True),
    ("logs/grpo-gated-poly27b-pen-s??", "Penalty, no-SFT", C["pen"], "s", True),
    ("logs/grpo-gated-poly27b-rt-s??", "Reward targeting", C["rt"], "D", True),
    ("logs/grpo-gated-poly27b-piglatinsr-ctrl-s??", "Pig-Latin + style reward, no penalty", C["plc"], "o", True),
    ("logs/grpo-gated-poly27b-piglatinsr-pen-s??", "Pig-Latin + style reward + penalty", C["pl"], "s", True),
    ("logs/grpo-gated-poly27b-piratesr-ctrl-s??", "Pirate + style reward, no penalty", C["pic"], "o", True),
    ("logs/grpo-gated-poly27b-piratesr-pen-s??", "Pirate + style reward + penalty", C["pi"], "s", True),
  ]),
  "term8b": ("Terminal (LLM judge), Qwen3-8B", 0.75, 400, 40, "monitor/cheat_in_output", "monitor/cheat_in_cot", [
    ("logs/grpo-termgated-8b-ctrl-s??", "No penalty", C["ctrl"], "o", True),
    ("logs/grpo-termgated-8b-pen-s??", "Penalty, no-SFT", C["pen"], "s", True),
    ("logs/grpo-termgated-8b-rt-s??", "Reward targeting", C["rt"], "D", True),
    ("logs/grpo-termgated-8b-mf-s??", "Mind & Face", C["mf"], "^", True),
    ("logs/grpo-termgated-8b-tmf-s??", "Targeted M&F", C["tmf"], "P", True),
    ("logs/grpo-termgated-8b-piglatinsr-ctrl-s??", "Pig-Latin + style reward, no penalty", C["plc"], "o", True),
    ("logs/grpo-termgated-8b-piglatinsr-pen-s??", "Pig-Latin + style reward + penalty", C["pl"], "s", True),
    ("logs/grpo-termgated-8b-piratesr-ctrl-s??", "Pirate + style reward, no penalty", C["pic"], "o", True),
    ("logs/grpo-termgated-8b-piratesr-pen-s??", "Pirate + style reward + penalty", C["pi"], "s", True),
  ]),
}


def load(pat, lam, n_expected, last, ko, kc):
    pts = []
    for d in sorted(glob.glob(pat)):
        ms = {}
        for ln in open(f"{d}/metrics.jsonl"):
            x = json.loads(ln)
            ms[x["step"]] = x
        steps = sorted(ms)
        if len(steps) < n_expected:
            continue
        tail = [ms[s] for s in steps[-last:]]
        task = np.mean([x["reward/correct"] for x in tail]); out = np.mean([x[ko] for x in tail]); cot = np.mean([x[kc] for x in tail])
        pts.append((cot, task - lam * out, task, out))
    return np.array(pts)


def main():
    fig, axes = plt.subplots(2, 3, figsize=(22, 13))
    axes = axes.ravel()
    summary = {}
    for ax, (key, (title, lam, n_exp, last, ko, kc, arms)) in zip(axes, PANELS.items()):
        summary[key] = {}
        for pat, label, color, marker, filled in arms:
            pts = load(pat, lam, n_exp, last, ko, kc)
            if not len(pts):
                continue
            x, y, n = pts[:, 0], pts[:, 1], len(pts)
            face = color if filled else "none"
            if marker == "x":
                ax.scatter(x, y, color=color, marker=marker, s=40, alpha=0.6)
            else:
                ax.scatter(x, y, facecolors=face, edgecolors=color, marker=marker, s=40, alpha=0.35 if filled else 0.6, linewidths=1)
            ci = lambda v: 1.96 * v.std(ddof=1) / np.sqrt(n) if n > 1 else 0  # noqa: E731
            ax.errorbar(x.mean(), y.mean(), xerr=ci(x), yerr=ci(y), color=color, marker=marker, markersize=11, markerfacecolor=face,
                        markeredgecolor="black" if filled else color, capsize=3, linewidth=1.3, label=f"{label} (n={n})", zorder=5)
            ax.annotate(f"{x.mean():.2f}", (x.mean(), y.mean()), textcoords="offset points", xytext=(0, 10 if filled else -16), ha="center", fontsize=9, color=color)
            summary[key][label] = {"n": n, "cot": round(float(x.mean()), 3), "cot_sd": round(float(x.std(ddof=1)), 3) if n > 1 else 0.0,
                                   "train_reward": round(float(y.mean()), 3), "task": round(float(pts[:, 2].mean()), 3), "m_out": round(float(pts[:, 3].mean()), 3)}
        ax.set_title(title, fontsize=13)
        ax.set_xlabel("CoT monitor detection rate", fontsize=11)
        ax.set_ylabel(f"Training reward = task − {lam}·M_out", fontsize=11)
        ax.set_xlim(0, 1.05); ax.set_ylim(-1.05, 1.1)
        ax.axhline(0, color="#bbbbbb", linewidth=0.8); ax.grid(axis="y", alpha=0.25)
        ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
        ax.legend(fontsize=7.5, loc="lower left", frameon=False)
    axes[-1].axis("off")
    axes[-1].text(0.02, 0.95, "Protocol: GRPO, GPT-4.1 hint judge (QA), regex expanded-form monitor (poly), gpt-4.1-mini verifier judge (terminal).\n"
                  "Every arm except the 8B no-penalty control, RT, M&F and the two hollow 8B references runs with the GPT-4.1 explanation gate\n"
                  "(task reward only for a coherent, on-topic explanation). Style arms add a group-normalized style reward so the style stays at 1.00.\n"
                  "QA/poly: 3200 episodes (last 27 steps); terminal: 12800 episodes (last 40). Dots = seeds; markers = mean ± 95% CI;\n"
                  "hollow = style not rewarded (drifts) or no gate (bare outputs). λ: QA 2, poly 1, terminal 0.75.",
                  transform=axes[-1].transAxes, va="top", fontsize=11, family="sans-serif")
    plt.tight_layout()
    plt.savefig("plots/gated_pareto_all.png", dpi=170); plt.savefig("plots/gated_pareto_all.pdf")
    json.dump(summary, open("plots/gated_pareto_all.json", "w"), indent=1)
    for k, arms in summary.items():
        print(f"== {PANELS[k][0]}")
        for label, v in arms.items():
            print(f"   {label:46s} n={v['n']:2d}  CoT {v['cot']:.2f}±{v['cot_sd']:.2f}  reward {v['train_reward']:.2f}  task {v['task']:.2f}  M_out {v['m_out']:.2f}")


if __name__ == "__main__":
    main()
