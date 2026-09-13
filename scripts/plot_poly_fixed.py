"""Regenerate the paper's v9_poly_32b figure with the Correctness panel recomputed
using the FIXED task-correctness checker, instead of the legacy (buggy) checker's
values baked into metrics.jsonl's "reward/correct".

Background (see RESULTS.md §14): env_polynomial._check_correctness (legacy version
now called _check_correctness_legacy) couldn't parse factored boxed answers like
"2x^3(x+5)" and fell back to rewarding ANY output containing the EXPANDED derivative
-- i.e. it rewarded exactly the behaviour the penalty is supposed to suppress. The
paper's v9poly 32B runs (paper/figures/v9_poly_32b.pdf, via fig_poly() in
paper/make_figures.py) were trained and plotted with that buggy checker.

This script:
  - recomputes per-batch correctness from each run's logs/.../rollouts.jsonl with the
    FIXED checker (env_polynomial._check_correctness), via a multiprocessing Pool
    (sympy parsing is slow -- see scripts/rescore_poly.py, whose per-row methodology
    this mirrors exactly: problem dict = {"deriv_sympy": parse(target), "factored_str":
    "", "expanded_norm": target}, rows whose target fails to parse are excluded);
  - dedupes rollout rows by (batch, rollout), keeping the LAST occurrence (resumed
    runs append duplicate rows for the same step);
  - leaves the other two panels (expanded form in output / in CoT) untouched, read
    from metrics.jsonl exactly as paper/make_figures.py:fig_poly() does -- those
    monitors are simple string-match judges, unaffected by the task-reward bug;
  - uses the same run names, condition labels, colours (from paper/make_figures.py's
    `C` palette) and smoothing (25-batch moving average, seeds 42/43 averaged) as
    fig_poly().

Does NOT modify anything under paper/ (reads paper/figstyle.py only, for the shared
matplotlib style / figsize helper -- that module has no import-time side effects).

Usage: uv run scripts/plot_poly_fixed.py
Writes: plots/v9_poly_32b_fixed.png, plots/v9_poly_32b_fixed.pdf,
        plots/v9_poly_32b_fixed.json
"""

import json
import multiprocessing as mp
import os
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "paper"))

from figstyle import figsize, set_paper_style  # noqa: E402
from src.spillover.env_polynomial import _check_correctness, _poly_to_sympy  # noqa: E402

LOGS = ROOT / "logs"
PLOTS = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)

set_paper_style()
plt.rcParams.update({"grid.alpha": 0.3, "lines.linewidth": 1.4})  # matches fig_poly()'s tweak in make_figures.py

# --- Same palette as paper/make_figures.py's `C` (verbatim) ----------------
C = {
    "no_sft":     ("#868e96", "o"),   # gray  — no intervention / baseline
    "normal":     ("#0c8599", "^"),   # teal  — normal SFT (SFT-not-style control)
    "pirate":     ("#e8590c", "s"),   # orange — pirate output (ours)
    "pirate_cot": ("#c2255c", "D"),   # raspberry — pirate CoT
    "rt":         ("#1c7ed6", "D"),   # blue   — reward targeting
    "mf":         ("#2f9e44", "^"),   # green  — Mind & Face
    "tmf":        ("#7048e8", "v"),   # violet — Targeted M&F
    "penalty":    ("#e03131", "o"),   # red    — plain penalty (poly)
    "pirate_ctrl":("#ffa94d", "s"),   # light orange — pirate, no penalty (poly)
}

# Same conditions / run-name bases / labels / colours as fig_poly()
CONDS = [
    ("Penalty",          C["penalty"][0],     "grpo-v9poly-pen-32b-pw-2"),
    ("Control (pw=0)",   C["no_sft"][0],      "grpo-v9poly-ctrl-32b-pw0"),
    ("Reward targeting", C["rt"][0],          "grpo-v9poly-rt-32b-pw-2"),
    ("Mind & Face",      C["mf"][0],          "grpo-v9poly-mf-32b-pw-2"),
    ("Targeted M&F",     C["tmf"][0],         "grpo-v9poly-tmf-32b-pw-2"),
    ("Pirate output",    C["pirate"][0],      "grpo-v9poly-pirate-32b-pw-2"),
    ("Pirate (pw=0)",    C["pirate_ctrl"][0], "grpo-v9poly-piratectrl-32b-pw0"),
]
SEEDS = (42, 43)
SMOOTH_W = 25   # fig_poly()'s curve() default window
LAST_N = 50     # "last 10%" of 500 batches -- matches scripts/rescore_poly.py / RESULTS.md §14


# ===================== helpers copied from paper/make_figures.py =====================
# (kept byte-for-byte so the two untouched panels reproduce fig_poly() exactly)
def curve(run_dir, key, w=SMOOTH_W):
    p = LOGS / run_dir / "metrics.jsonl"
    if not p.exists():
        return None
    vals = [json.loads(ln)[key] for ln in open(p) if key in json.loads(ln)]
    if not vals:
        return None
    a = np.asarray(vals, float)
    return a if len(a) < w else np.convolve(a, np.ones(w) / w, "valid")


def seed_curve(runs, key, w=SMOOTH_W):
    cs = [c for c in (curve(r, key, w) for r in runs) if c is not None]
    if not cs:
        return None
    n = min(len(c) for c in cs)
    return np.arange(n), np.mean([c[:n] for c in cs], axis=0)


def metrics_raw_values(run_dir, key):
    """Raw (unsmoothed) per-batch values for `key`, sorted by batch -- for the
    last-50-batch means in the JSON summary."""
    p = LOGS / run_dir / "metrics.jsonl"
    rows = [json.loads(ln) for ln in open(p)]
    rows = [r for r in rows if key in r]
    rows.sort(key=lambda r: r["progress/batch"])
    return [r[key] for r in rows]


# ===================== rollouts.jsonl loading + FIXED-checker scoring =====================
def load_rollouts_deduped(run_dir):
    """(batch, rollout) -> row, keeping the LAST occurrence (resumed runs append
    duplicate rows for the same step)."""
    rows = {}
    with open(LOGS / run_dir / "rollouts.jsonl") as f:
        for line in f:
            r = json.loads(line)
            rows[(r["batch"], r.get("rollout", 0))] = r
    return rows


_TARGET_CACHE: dict = {}  # per-worker-process cache of target-string -> parsed sympy expr (or None)


def _score_row(item):
    """Worker fn (must be top-level for pickling): (target, out_text) -> fixed-checker
    score, or None if the target polynomial itself fails to parse (excluded from the
    mean, mirroring scripts/rescore_poly.py)."""
    target, out_text = item
    if target in _TARGET_CACHE:
        dv = _TARGET_CACHE[target]
    else:
        try:
            dv = _poly_to_sympy(target)
        except Exception:
            dv = None
        _TARGET_CACHE[target] = dv
    if dv is None:
        return None
    problem = {"deriv_sympy": dv, "factored_str": "", "expanded_norm": target}
    return _check_correctness(out_text, problem)


def fixed_and_legacy_curves(run_dir, pool):
    """Per-batch arrays (index = batch number) of mean correctness under the FIXED
    and legacy checkers, using ALL rollouts after (batch, rollout) de-dup. The legacy
    value is read straight from rollouts.jsonl's "correct" field (verified to exactly
    reproduce metrics.jsonl's reward/correct), so only the fixed checker needs sympy."""
    rows = list(load_rollouts_deduped(run_dir).values())
    if not rows:
        return None, None, []
    items = [(r["target"], r["out_text"]) for r in rows]
    n_workers = pool._processes if hasattr(pool, "_processes") else 8
    chunksize = max(1, len(items) // (n_workers * 4))
    scores = pool.map(_score_row, items, chunksize=chunksize)

    max_batch = max(r["batch"] for r in rows)
    fixed_by_batch = defaultdict(list)
    legacy_by_batch = defaultdict(list)
    for r, s in zip(rows, scores):
        b = r["batch"]
        legacy_by_batch[b].append(float(r["correct"] == 1))
        if s is not None:
            fixed_by_batch[b].append(s)

    fixed_arr = np.full(max_batch + 1, np.nan)
    legacy_arr = np.full(max_batch + 1, np.nan)
    for b, vals in fixed_by_batch.items():
        fixed_arr[b] = np.mean(vals)
    for b, vals in legacy_by_batch.items():
        legacy_arr[b] = np.mean(vals)
    n_unparsed = sum(1 for s in scores if s is None)
    if n_unparsed:
        print(f"  [{run_dir}] WARNING: {n_unparsed}/{len(scores)} rows excluded (target failed to parse)")
    if np.isnan(fixed_arr).any() or np.isnan(legacy_arr).any():
        print(f"  [{run_dir}] WARNING: missing batches in correctness arrays (gaps in rollouts.jsonl?)")
    return fixed_arr, legacy_arr, rows


def smooth(a, w=SMOOTH_W):
    a = np.asarray(a, float)
    return a if len(a) < w else np.convolve(a, np.ones(w) / w, "valid")


def seed_average(arrays, w=SMOOTH_W):
    cs = [smooth(a, w) for a in arrays if a is not None]
    if not cs:
        return None
    n = min(len(c) for c in cs)
    return np.arange(n), np.mean([c[:n] for c in cs], axis=0)


def last_n_mean(arr, n=LAST_N):
    return float(np.mean(arr[-n:]))


# ===================== main =====================
def main():
    n_workers = min(32, os.cpu_count() or 4)
    print(f"Using a multiprocessing Pool of {n_workers} workers for FIXED-checker rescoring...")

    results = {}
    fixed_curve_by_cond = {}

    with mp.Pool(n_workers) as pool:
        for label, color, base in CONDS:
            per_seed = {"legacy_correct": [], "fixed_correct": [],
                        "expanded_in_output": [], "expanded_in_cot": [], "n_rows": []}
            fixed_raw_arrays = []
            for s in SEEDS:
                run_dir = f"{base}-s{s}"
                fixed_arr, legacy_arr, rows = fixed_and_legacy_curves(run_dir, pool)
                if fixed_arr is None:
                    print(f"  [{run_dir}] MISSING rollouts.jsonl -- skipped")
                    continue
                fixed_raw_arrays.append(fixed_arr)

                leg_m, fix_m = last_n_mean(legacy_arr), last_n_mean(fixed_arr)
                out_vals = metrics_raw_values(run_dir, "monitor/expanded_in_output")
                cot_vals = metrics_raw_values(run_dir, "monitor/expanded_in_cot")
                out_m, cot_m = last_n_mean(np.asarray(out_vals)), last_n_mean(np.asarray(cot_vals))

                per_seed["legacy_correct"].append(leg_m)
                per_seed["fixed_correct"].append(fix_m)
                per_seed["expanded_in_output"].append(out_m)
                per_seed["expanded_in_cot"].append(cot_m)
                per_seed["n_rows"].append(len(rows))
                print(f"  [{run_dir}] last-{LAST_N}-batch: legacy={leg_m:.3f} fixed={fix_m:.3f} "
                      f"out={out_m:.3f} cot={cot_m:.3f} (n_rows={len(rows)})")

            fixed_curve_by_cond[label] = seed_average(fixed_raw_arrays)
            results[label] = {
                "run_base": base,
                "legacy_correct": float(np.mean(per_seed["legacy_correct"])) if per_seed["legacy_correct"] else None,
                "fixed_correct": float(np.mean(per_seed["fixed_correct"])) if per_seed["fixed_correct"] else None,
                "expanded_in_output": float(np.mean(per_seed["expanded_in_output"])) if per_seed["expanded_in_output"] else None,
                "expanded_in_cot": float(np.mean(per_seed["expanded_in_cot"])) if per_seed["expanded_in_cot"] else None,
                "n_seeds": len(per_seed["legacy_correct"]),
                "per_seed": {
                    str(s): {
                        "legacy_correct": per_seed["legacy_correct"][i],
                        "fixed_correct": per_seed["fixed_correct"][i],
                        "expanded_in_output": per_seed["expanded_in_output"][i],
                        "expanded_in_cot": per_seed["expanded_in_cot"][i],
                        "n_rows": per_seed["n_rows"][i],
                    }
                    for i, s in enumerate(SEEDS) if i < len(per_seed["legacy_correct"])
                },
            }

    # ---- figure: same 3 panels, same labels/colours/smoothing as fig_poly() ----
    fig, axes = plt.subplots(1, 3, figsize=figsize(1.0, 0.34))

    ax = axes[0]
    for label, color, base in CONDS:
        d = fixed_curve_by_cond.get(label)
        if d:
            ax.plot(d[0], d[1], color=color, lw=1.6, label=label)
    ax.set_title("Correctness (fixed checker)", fontsize=9)
    ax.set_xlabel("Batch")
    ax.set_ylim(-0.05, 1.05)

    for ax, (key, lab) in zip(axes[1:], [("monitor/expanded_in_output", "Expanded form in output"),
                                          ("monitor/expanded_in_cot", "Expanded form in CoT")]):
        for label, color, base in CONDS:
            d = seed_curve([f"{base}-s{s}" for s in SEEDS], key)
            if d:
                ax.plot(d[0], d[1], color=color, lw=1.6, label=label)
        ax.set_title(lab, fontsize=9)
        ax.set_xlabel("Batch")
        ax.set_ylim(-0.05, 1.05)

    axes[0].legend(fontsize=7, loc="best")
    fig.tight_layout()
    fig.savefig(PLOTS / "v9_poly_32b_fixed.png", dpi=200)
    fig.savefig(PLOTS / "v9_poly_32b_fixed.pdf")
    plt.close(fig)
    print(f"Saved {PLOTS / 'v9_poly_32b_fixed.png'} and .pdf")

    out_json = {
        "_meta": {
            "seeds": list(SEEDS),
            "last_n_batches": LAST_N,
            "smoothing_window": SMOOTH_W,
            "fixed_checker": "src.spillover.env_polynomial._check_correctness",
            "legacy_checker": "rollouts.jsonl 'correct' field (= _check_correctness_legacy at train time; "
                               "verified to exactly match metrics.jsonl's reward/correct)",
            "source_script": "scripts/plot_poly_fixed.py",
        },
        "conditions": results,
    }
    json_path = PLOTS / "v9_poly_32b_fixed.json"
    json_path.write_text(json.dumps(out_json, indent=2))
    print(f"Saved {json_path}")

    print(f"\n{'condition':20s} {'legacy':>8s} {'fixed':>8s} {'exp_out':>8s} {'exp_cot':>8s}")
    for label, _, _ in CONDS:
        r = results[label]
        print(f"{label:20s} {r['legacy_correct']:8.3f} {r['fixed_correct']:8.3f} "
              f"{r['expanded_in_output']:8.3f} {r['expanded_in_cot']:8.3f}")


if __name__ == "__main__":
    main()
