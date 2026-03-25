"""Plot benchmark evaluation results across checkpoints."""

import argparse
import json

import matplotlib.pyplot as plt
import numpy as np


def load_results(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def plot_correctness(results: dict, output_path: str):
    benchmarks = ["gsm8k", "math", "mmlu", "gpqa"]
    checkpoints = list(results.keys())
    x = np.arange(len(benchmarks))
    width = 0.8 / len(checkpoints)

    fig, ax = plt.subplots(figsize=(12, 5))
    for i, ckpt in enumerate(checkpoints):
        vals = []
        for b in benchmarks:
            c = results[ckpt].get(b, {}).get("correctness", 0)
            vals.append(c if c == c else 0)  # handle NaN
        ax.bar(x + i * width, vals, width, label=ckpt)

    ax.set_ylabel("Correctness")
    ax.set_title("Benchmark Correctness by Checkpoint")
    ax.set_xticks(x + width * (len(checkpoints) - 1) / 2)
    ax.set_xticklabels(benchmarks)
    ax.set_ylim(0, 1.1)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved {output_path}")


def plot_style_transfer(results: dict, style_name: str, output_path: str):
    benchmarks = ["gsm8k", "math", "mmlu", "gpqa", "mbpp", "ifeval"]
    checkpoints = list(results.keys())
    x = np.arange(len(benchmarks))
    width = 0.8 / len(checkpoints)

    fig, ax = plt.subplots(figsize=(12, 5))
    for i, ckpt in enumerate(checkpoints):
        vals = [
            results[ckpt].get(b, {}).get("style_scores", {}).get(style_name, 0)
            for b in benchmarks
        ]
        ax.bar(x + i * width, vals, width, label=ckpt)

    ax.set_ylabel(f"{style_name.title()} Style Score")
    ax.set_title(f"{style_name.title()} Style Transfer Across Benchmarks")
    ax.set_xticks(x + width * (len(checkpoints) - 1) / 2)
    ax.set_xticklabels(benchmarks)
    ax.set_ylim(0, 1.1)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved {output_path}")


def plot_performance_vs_style(results: dict, output_path: str):
    """Scatter: x=style score, y=correctness. One point per (checkpoint, benchmark)."""
    benchmarks = ["gsm8k", "math", "mmlu", "gpqa"]
    styles = ["chinese", "pirate"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, style in zip(axes, styles):
        for ckpt, color in zip(results.keys(), plt.cm.tab10.colors):
            for b in benchmarks:
                r = results[ckpt].get(b, {})
                c = r.get("correctness", 0)
                s = r.get("style_scores", {}).get(style, 0)
                if c != c:
                    continue
                ax.scatter(s, c, color=color, s=60, alpha=0.8)
                ax.annotate(b, (s, c), fontsize=6, alpha=0.7)
        ax.set_xlabel(f"{style.title()} Style Score")
        ax.set_ylabel("Correctness")
        ax.set_title(f"Performance vs {style.title()} Style")
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(0, 1.1)
        ax.grid(alpha=0.3)
        # Manual legend
        for ckpt, color in zip(results.keys(), plt.cm.tab10.colors):
            ax.scatter([], [], color=color, label=ckpt)
        ax.legend(fontsize=7, loc="lower left")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="/tmp/spillover-exps/eval_all_results.json")
    parser.add_argument("--output-dir", default="/tmp/spillover-exps")
    args = parser.parse_args()

    results = load_results(args.input)
    d = args.output_dir

    plot_correctness(results, f"{d}/bench_correctness.png")
    plot_style_transfer(results, "chinese", f"{d}/bench_style_chinese.png")
    plot_style_transfer(results, "pirate", f"{d}/bench_style_pirate.png")
    plot_performance_vs_style(results, f"{d}/bench_perf_vs_style.png")


if __name__ == "__main__":
    main()
