"""Launch evaluations on all v7-era GRPO checkpoints.

Covers: v6pw, v7base, v7norm, v7pcot runs.
Reads checkpoints.jsonl from each run directory,
skips already-evaluated checkpoints, and launches evals with controlled concurrency.

Usage:
    uv run scripts/eval_all_v7.py --max-concurrent 8
    uv run scripts/eval_all_v7.py --max-concurrent 8 --dry-run
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed


def discover_runs():
    """Find all v7-era run directories that have checkpoints.jsonl."""
    logs = Path("logs")
    runs = []
    for d in sorted(logs.iterdir()):
        if not d.is_dir():
            continue
        name = d.name
        if not any(name.startswith(p) for p in ["grpo-v6pw-", "grpo-v7base-", "grpo-v7norm-", "grpo-v7pcot-"]):
            continue
        if (d / "checkpoints.jsonl").exists():
            runs.append(name)
    return runs


MODEL_MAP = {
    "8b": "Qwen/Qwen3-8B",
    "32b": "Qwen/Qwen3-32B",
}


def get_eval_tasks(output_base: Path):
    tasks = []
    for run_name in discover_runs():
        run_dir = Path("logs") / run_name
        ckpt_file = run_dir / "checkpoints.jsonl"

        size = "8b" if "-8b-" in run_name or "-8b " in run_name else "32b"
        model = MODEL_MAP[size]
        eval_dir = output_base / run_name

        with open(ckpt_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ckpt = json.loads(line)
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
            cmd, capture_output=True, text=True, timeout=3600, env=ENV,
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
    parser.add_argument("--max-concurrent", type=int, default=8)
    parser.add_argument("--output-base", default="logs/eval-penalty-v7")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output_base = Path(args.output_base)
    output_base.mkdir(parents=True, exist_ok=True)

    tasks = get_eval_tasks(output_base)
    print(f"Found {len(tasks)} evals to run (max concurrent: {args.max_concurrent})")

    if args.dry_run:
        for t in tasks[:20]:
            print(f"  {t['run_name']}/{t['ckpt_name']} -> {t['output_dir']}")
        if len(tasks) > 20:
            print(f"  ... and {len(tasks) - 20} more")
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
