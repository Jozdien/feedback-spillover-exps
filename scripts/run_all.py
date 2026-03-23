"""Run all spillover conditions and generate analysis plots."""

import argparse
import logging

from src.analysis.metrics import load_metrics, spillover_ratio
from src.analysis.plot import (
    plot_spillover_bar,
    plot_spillover_curves,
    plot_style_persistence,
    plot_task_performance,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_LOG_PATHS = {
    "baseline": "/tmp/spillover-exps/spillover-baseline",
    "chinese": "/tmp/spillover-exps/spillover-chinese",
    "pirate": "/tmp/spillover-exps/spillover-pirate",
    "mind_face": "/tmp/spillover-exps/spillover-mind-face",
    "reward_targeting": "/tmp/spillover-exps/spillover-reward-target",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--conditions", nargs="*", default=list(DEFAULT_LOG_PATHS.keys()),
        help="Which conditions to analyze",
    )
    parser.add_argument("--output-dir", default=".", help="Where to save plots")
    args = parser.parse_args()

    runs = []
    for cond in args.conditions:
        log_path = DEFAULT_LOG_PATHS.get(cond, f"/tmp/spillover-exps/spillover-{cond}")
        try:
            run = load_metrics(log_path, cond)
            runs.append(run)
            ratio = spillover_ratio(run)
            logger.info(f"{cond}: spillover_ratio={ratio:.3f}, steps={len(run.steps)}")
        except FileNotFoundError:
            logger.warning(f"No metrics found for {cond} at {log_path}, skipping")

    if not runs:
        logger.error("No runs found. Run experiments first.")
        return

    prefix = f"{args.output_dir}/"
    plot_spillover_curves(runs, f"{prefix}spillover_curves.png")
    plot_spillover_bar(runs, f"{prefix}spillover_ratios.png")
    plot_style_persistence(runs, f"{prefix}style_persistence.png")
    plot_task_performance(runs, f"{prefix}task_performance.png")
    logger.info(f"Plots saved to {args.output_dir}/")


if __name__ == "__main__":
    main()
