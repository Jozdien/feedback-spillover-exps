"""Launch evaluations on all v5ctrl RL checkpoints (penalty_weight=0, no_answer_penalty=-1.0).

Reads checkpoints.jsonl from each grpo-v5ctrl-* run directory, skips already-evaluated
checkpoints, and launches evals with controlled concurrency.

Usage:
    uv run python scripts/eval_all_v5ctrl.py --max-concurrent 4
    uv run python scripts/eval_all_v5ctrl.py --max-concurrent 4 --dry-run
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed


CTRL_RUNS = [
    f"grpo-v5ctrl-{size}-{cond}-{src}-s{seed}"
    for size in ["8b", "32b"]
    for cond in ["pirate-output", "pirate-cot", "normal"]
    for src in ["qwen", "haiku"]
    for seed in [42, 43]
]

MODEL_MAP = {
    "8b": "Qwen/Qwen3-8B",
    "32b": "Qwen/Qwen3-32B",
}


def get_eval_tasks(output_base: Path):
    tasks = []
    for run_name in CTRL_RUNS:
        run_dir = Path("logs") / run_name
        ckpt_file = run_dir / "checkpoints.jsonl"
        if not ckpt_file.exists():
            continue

        size = "8b" if "8b" in run_name else "32b"
        model = MODEL_MAP[size]
        eval_dir = output_base / run_name

        with open(ckpt_file) as f:
            for line in f:
                ckpt = json.loads(line.strip())
                name = ckpt["name"]
                state_path = ckpt["state_path"]
                eval_name = "001000" if name == "final" else name

                model_slug = model.replace("/", "_")
                out_file = eval_dir / f"{model_slug}_{eval_name}.jsonl"
                if out_file.exists() and out_file.stat().st_size > 0:
                    continue

                tasks.append({
                    "run_name": run_name,
                    "ckpt_name": name,
                    "eval_name": eval_name,
                    "model": model,
                    "state_path": state_path,
                    "output_dir": str(eval_dir),
                })
    return tasks


def _load_env():
    env = dict(os.environ)
    if Path(".env").exists():
        with open(".env") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


ENV = _load_env()


def run_eval(task):
    cmd = [
        "uv", "run", "python", "scripts/eval_grpo_baseline.py",
        "--model", task["model"],
        "--checkpoint", task["state_path"],
        "--output-dir", task["output_dir"],
        "--batch-size", "50",
        "--max-cot-tokens", "4096",
    ]
    label = f"{task['run_name']}/{task['ckpt_name']}"
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=1800, env=ENV,
        )
        elapsed = time.time() - t0
        if result.returncode == 0:
            if task.get("eval_name") and task["eval_name"] != task["ckpt_name"]:
                model_slug = task["model"].replace("/", "_")
                src = Path(task["output_dir"]) / f"{model_slug}_{task['ckpt_name']}.jsonl"
                dst = Path(task["output_dir"]) / f"{model_slug}_{task['eval_name']}.jsonl"
                if src.exists() and not dst.exists():
                    src.rename(dst)
            return label, "OK", elapsed
        else:
            err = result.stderr[-500:] if result.stderr else "no stderr"
            return label, f"FAIL (rc={result.returncode}): {err}", elapsed
    except subprocess.TimeoutExpired:
        return label, "TIMEOUT", time.time() - t0
    except Exception as e:
        return label, f"ERROR: {e}", time.time() - t0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-concurrent", type=int, default=4)
    parser.add_argument("--output-base", default="logs/eval-penalty-v5ctrl")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output_base = Path(args.output_base)
    output_base.mkdir(parents=True, exist_ok=True)

    tasks = get_eval_tasks(output_base)
    print(f"Found {len(tasks)} evals to run (max concurrent: {args.max_concurrent})")

    if args.dry_run:
        for t in tasks[:10]:
            print(f"  {t['run_name']}/{t['ckpt_name']} -> {t['output_dir']}")
        if len(tasks) > 10:
            print(f"  ... and {len(tasks) - 10} more")
        return

    done = failed = 0
    t_start = time.time()

    with ProcessPoolExecutor(max_workers=args.max_concurrent) as pool:
        futures = {pool.submit(run_eval, t): t for t in tasks}
        for future in as_completed(futures):
            label, status, elapsed = future.result()
            if "OK" in status:
                done += 1
            else:
                failed += 1
            total = done + failed
            rate = total / (time.time() - t_start) * 3600
            print(
                f"[{total}/{len(tasks)}] {label}: {status} ({elapsed:.0f}s) "
                f"[{done} ok, {failed} fail, {rate:.0f}/hr]",
                flush=True,
            )

    print(f"\nDone: {done} ok, {failed} failed out of {len(tasks)} total")


if __name__ == "__main__":
    main()
