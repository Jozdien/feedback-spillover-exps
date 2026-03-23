"""Load experiment metrics and compute spillover ratios."""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class RunMetrics:
    condition: str
    steps: list[int]
    correct: list[float]
    hint_in_output: list[float]
    hint_in_cot: list[float]
    style_score: list[float] | None = None


def load_metrics(log_path: str, condition: str) -> RunMetrics:
    """Load metrics from a tinker-cookbook metrics.jsonl log."""
    metrics_file = Path(log_path) / "metrics.jsonl"
    steps, correct, hint_out, hint_cot, style = [], [], [], [], []

    with open(metrics_file) as f:
        for line in f:
            m = json.loads(line)
            step = m.get("progress/batch", m.get("step", len(steps)))
            steps.append(int(step))
            correct.append(m.get("reward/correct", m.get("correct", 0.0)))
            hint_out.append(m.get("monitor/hint_in_output", m.get("hint_in_output", 0.0)))
            hint_cot.append(m.get("monitor/hint_in_cot", m.get("hint_in_cot", 0.0)))
            if "style_score" in m:
                style.append(m["style_score"])

    return RunMetrics(
        condition=condition,
        steps=steps,
        correct=correct,
        hint_in_output=hint_out,
        hint_in_cot=hint_cot,
        style_score=style if style else None,
    )


def spillover_ratio(run: RunMetrics, window: int = 5) -> float:
    """Compute spillover ratio: delta(cot_hint) / delta(output_hint).

    Uses first and last `window` steps to compute deltas.
    Returns ratio in [0, inf). Lower = less spillover.
    """
    if len(run.hint_in_output) < 2 * window:
        return float("nan")

    early_out = np.mean(run.hint_in_output[:window])
    late_out = np.mean(run.hint_in_output[-window:])
    early_cot = np.mean(run.hint_in_cot[:window])
    late_cot = np.mean(run.hint_in_cot[-window:])

    delta_out = early_out - late_out
    delta_cot = early_cot - late_cot

    if abs(delta_out) < 1e-6:
        return float("nan")
    return delta_cot / delta_out


def smooth(values: list[float], window: int = 5) -> list[float]:
    """Simple moving average smoothing."""
    if len(values) < window:
        return values
    kernel = np.ones(window) / window
    padded = np.pad(values, (window // 2, window - 1 - window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid").tolist()
