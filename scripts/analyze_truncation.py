"""Analyze CoT truncation rates across eval runs.

The CoT was sampled with max_tokens=300 and stop='</think>'.
If cot_text does NOT end with '</think>', it was likely truncated by the token limit.
"""

import json
import os
import re
from pathlib import Path
from collections import defaultdict

EVAL_DIR = Path("/home/jose/feedback-spillover-exps/logs/eval-penalty")


def parse_run_name(run_name: str):
    """Parse run directory name into components.
    Format: grpo-{size}-{condition}-{source}-s{seed}
    Conditions can be multi-word like 'pirate-cot' or 'pirate-output'.
    """
    # Pattern: grpo-{size}-{condition}-{source}-s{seed}
    m = re.match(r"grpo-(\w+)-(.*?)-(haiku|qwen)-s(\d+)", run_name)
    if not m:
        return None
    size, condition, source, seed = m.groups()
    return {
        "size": size,
        "condition": condition,
        "source": source,
        "seed": seed,
    }


def is_truncated(cot_text: str) -> bool:
    """Check if CoT text was truncated (didn't end with </think>)."""
    if cot_text is None:
        return False
    # Strip whitespace and check if it ends with </think>
    stripped = cot_text.strip()
    return not stripped.endswith("</think>")


def get_step_from_filename(filename: str) -> str:
    """Extract step number from filename like Qwen_Qwen3-32B_000100.jsonl"""
    m = re.search(r"_(\d+|final)\.jsonl$", filename)
    if m:
        return m.group(1)
    return "unknown"


def main():
    # Collect results: {run_name: {step: (truncated, total)}}
    run_results = {}

    for run_dir in sorted(EVAL_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        run_name = run_dir.name
        meta = parse_run_name(run_name)
        if meta is None:
            print(f"WARNING: Could not parse run name: {run_name}")
            continue

        run_results[run_name] = {"meta": meta, "steps": {}}

        for jsonl_file in sorted(run_dir.glob("*.jsonl")):
            step = get_step_from_filename(jsonl_file.name)
            truncated = 0
            total = 0

            with open(jsonl_file) as f:
                for line in f:
                    record = json.loads(line)
                    if record.get("type") != "result":
                        continue
                    cot_text = record.get("cot_text", "")
                    if cot_text is None:
                        continue
                    total += 1
                    if is_truncated(cot_text):
                        truncated += 1

            if total > 0:
                run_results[run_name]["steps"][step] = {
                    "truncated": truncated,
                    "total": total,
                    "rate": truncated / total,
                }

    # === Report 1: Per-run truncation rate (averaged across steps) ===
    print("=" * 80)
    print("TRUNCATION RATE PER RUN (averaged across steps)")
    print("=" * 80)
    print(f"{'Run':<45} {'Avg Rate':>10} {'Min':>8} {'Max':>8} {'Steps':>6}")
    print("-" * 80)

    # Group by condition+size for summary
    condition_size_rates = defaultdict(list)
    condition_rates = defaultdict(list)
    size_rates = defaultdict(list)
    source_rates = defaultdict(list)

    for run_name in sorted(run_results.keys()):
        data = run_results[run_name]
        meta = data["meta"]
        steps = data["steps"]
        if not steps:
            continue

        rates = [s["rate"] for s in steps.values()]
        avg_rate = sum(rates) / len(rates)
        min_rate = min(rates)
        max_rate = max(rates)

        print(f"{run_name:<45} {avg_rate:>9.1%} {min_rate:>7.1%} {max_rate:>7.1%} {len(rates):>6}")

        key = f"{meta['size']}-{meta['condition']}"
        condition_size_rates[key].append(avg_rate)
        condition_rates[meta["condition"]].append(avg_rate)
        size_rates[meta["size"]].append(avg_rate)
        source_rates[meta["source"]].append(avg_rate)

    # === Report 2: Summary by condition+size ===
    print("\n" + "=" * 80)
    print("TRUNCATION RATE BY CONDITION + SIZE (averaged across runs)")
    print("=" * 80)
    print(f"{'Condition+Size':<30} {'Avg Rate':>10} {'Num Runs':>10}")
    print("-" * 50)
    for key in sorted(condition_size_rates.keys()):
        rates = condition_size_rates[key]
        avg = sum(rates) / len(rates)
        print(f"{key:<30} {avg:>9.1%} {len(rates):>10}")

    # === Report 3: Summary by condition ===
    print("\n" + "=" * 80)
    print("TRUNCATION RATE BY CONDITION (averaged across runs)")
    print("=" * 80)
    print(f"{'Condition':<20} {'Avg Rate':>10} {'Num Runs':>10}")
    print("-" * 40)
    for key in sorted(condition_rates.keys()):
        rates = condition_rates[key]
        avg = sum(rates) / len(rates)
        print(f"{key:<20} {avg:>9.1%} {len(rates):>10}")

    # === Report 4: Summary by size ===
    print("\n" + "=" * 80)
    print("TRUNCATION RATE BY SIZE (averaged across runs)")
    print("=" * 80)
    print(f"{'Size':<20} {'Avg Rate':>10} {'Num Runs':>10}")
    print("-" * 40)
    for key in sorted(size_rates.keys()):
        rates = size_rates[key]
        avg = sum(rates) / len(rates)
        print(f"{key:<20} {avg:>9.1%} {len(rates):>10}")

    # === Report 5: Summary by source ===
    print("\n" + "=" * 80)
    print("TRUNCATION RATE BY SOURCE (averaged across runs)")
    print("=" * 80)
    print(f"{'Source':<20} {'Avg Rate':>10} {'Num Runs':>10}")
    print("-" * 40)
    for key in sorted(source_rates.keys()):
        rates = source_rates[key]
        avg = sum(rates) / len(rates)
        print(f"{key:<20} {avg:>9.1%} {len(rates):>10}")

    # === Report 6: Per-step truncation rate (averaged across all runs) ===
    print("\n" + "=" * 80)
    print("TRUNCATION RATE PER STEP (averaged across all runs)")
    print("=" * 80)

    step_rates = defaultdict(list)
    for run_name, data in run_results.items():
        for step, step_data in data["steps"].items():
            step_rates[step].append(step_data["rate"])

    print(f"{'Step':<15} {'Avg Rate':>10} {'Min':>8} {'Max':>8} {'Num Runs':>10}")
    print("-" * 55)
    for step in sorted(step_rates.keys(), key=lambda x: x if x == "final" else x.zfill(10)):
        rates = step_rates[step]
        avg = sum(rates) / len(rates)
        print(f"{step:<15} {avg:>9.1%} {min(rates):>7.1%} {max(rates):>7.1%} {len(rates):>10}")

    # === Report 7: Per-step breakdown by condition ===
    print("\n" + "=" * 80)
    print("TRUNCATION RATE PER STEP BY CONDITION")
    print("=" * 80)

    # Collect: {condition: {step: [rates]}}
    cond_step_rates = defaultdict(lambda: defaultdict(list))
    for run_name, data in run_results.items():
        meta = data["meta"]
        condition = meta["condition"]
        for step, step_data in data["steps"].items():
            cond_step_rates[condition][step].append(step_data["rate"])

    for condition in sorted(cond_step_rates.keys()):
        print(f"\n  Condition: {condition}")
        print(f"  {'Step':<15} {'Avg Rate':>10} {'Num Runs':>10}")
        print(f"  {'-' * 40}")
        for step in sorted(cond_step_rates[condition].keys(), key=lambda x: x if x == "final" else x.zfill(10)):
            rates = cond_step_rates[condition][step]
            avg = sum(rates) / len(rates)
            print(f"  {step:<15} {avg:>9.1%} {len(rates):>10}")

    # === Report 8: Example truncated CoTs (lengths) ===
    print("\n" + "=" * 80)
    print("COT LENGTH DISTRIBUTION (chars) FOR TRUNCATED vs NON-TRUNCATED")
    print("=" * 80)

    trunc_lengths = []
    non_trunc_lengths = []

    # Sample from a few runs
    for run_dir in sorted(EVAL_DIR.iterdir())[:6]:
        if not run_dir.is_dir():
            continue
        for jsonl_file in sorted(run_dir.glob("*.jsonl"))[:3]:
            with open(jsonl_file) as f:
                for line in f:
                    record = json.loads(line)
                    if record.get("type") != "result":
                        continue
                    cot_text = record.get("cot_text", "")
                    if cot_text is None:
                        continue
                    if is_truncated(cot_text):
                        trunc_lengths.append(len(cot_text))
                    else:
                        non_trunc_lengths.append(len(cot_text))

    if trunc_lengths:
        trunc_lengths.sort()
        print(f"\n  Truncated CoTs (n={len(trunc_lengths)}):")
        print(f"    Mean length: {sum(trunc_lengths)/len(trunc_lengths):.0f} chars")
        print(f"    Median length: {trunc_lengths[len(trunc_lengths)//2]:.0f} chars")
        print(f"    Min: {min(trunc_lengths)}, Max: {max(trunc_lengths)}")
        p25 = trunc_lengths[len(trunc_lengths)//4]
        p75 = trunc_lengths[3*len(trunc_lengths)//4]
        print(f"    25th percentile: {p25}, 75th percentile: {p75}")

    if non_trunc_lengths:
        non_trunc_lengths.sort()
        print(f"\n  Non-truncated CoTs (n={len(non_trunc_lengths)}):")
        print(f"    Mean length: {sum(non_trunc_lengths)/len(non_trunc_lengths):.0f} chars")
        print(f"    Median length: {non_trunc_lengths[len(non_trunc_lengths)//2]:.0f} chars")
        print(f"    Min: {min(non_trunc_lengths)}, Max: {max(non_trunc_lengths)}")
        p25 = non_trunc_lengths[len(non_trunc_lengths)//4]
        p75 = non_trunc_lengths[3*len(non_trunc_lengths)//4]
        print(f"    25th percentile: {p25}, 75th percentile: {p75}")


if __name__ == "__main__":
    main()
