"""Evaluate SFT checkpoints as step-0 baselines for v3 runs (penalty_weight=-1).

Same 12 SFT checkpoints, but with results placed in v3 directories.
Results go to logs/eval-penalty-v3/grpo-v3-{run}/Qwen_Qwen3-{size}_000000.jsonl
"""

import json
import os
import subprocess
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed


SFT_CHECKPOINTS = {
    "8b-pirate-output-qwen": ("Qwen/Qwen3-8B", "tinker://6f8d3ebd-7dc3-5ff9-87ed-1083d50f0b05:train:0/weights/final"),
    "8b-pirate-cot-qwen": ("Qwen/Qwen3-8B", "tinker://73334e08-6e76-5890-a506-864ee95c4e90:train:0/weights/final"),
    "8b-normal-qwen": ("Qwen/Qwen3-8B", "tinker://fe120137-fe95-51ce-9d3a-2881d22047ba:train:0/weights/final"),
    "8b-pirate-output-haiku": ("Qwen/Qwen3-8B", "tinker://28be06c8-e482-5830-94f7-602f6a643c3f:train:0/weights/final"),
    "8b-pirate-cot-haiku": ("Qwen/Qwen3-8B", "tinker://7bceb7ca-7404-5b05-963d-8ee9a07d1b7c:train:0/weights/final"),
    "8b-normal-haiku": ("Qwen/Qwen3-8B", "tinker://f58be72e-f8f9-5238-bfe0-7399f1043337:train:0/weights/final"),
    "32b-pirate-output-qwen": ("Qwen/Qwen3-32B", "tinker://8fb3a99c-f00a-5e5e-a39d-fb9926f4e02c:train:0/weights/final"),
    "32b-pirate-cot-qwen": ("Qwen/Qwen3-32B", "tinker://dfe600ac-762b-5e66-b3d5-222f4d9c81e5:train:0/weights/final"),
    "32b-normal-qwen": ("Qwen/Qwen3-32B", "tinker://f3b1fb04-de20-52ff-90b9-2ba1a5bb0552:train:0/weights/final"),
    "32b-pirate-output-haiku": ("Qwen/Qwen3-32B", "tinker://719ca1fa-1edc-5b2c-87f9-fe7c72d3b953:train:0/weights/final"),
    "32b-pirate-cot-haiku": ("Qwen/Qwen3-32B", "tinker://3dea7ead-ca2e-5d30-9f7d-3e21ff6bb3ad:train:0/weights/final"),
    "32b-normal-haiku": ("Qwen/Qwen3-32B", "tinker://ac715aed-3087-5c68-9a38-d5b0fd33f671:train:0/weights/final"),
}


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
        "--checkpoint", task["checkpoint"],
        "--output-dir", task["output_dir"],
        "--batch-size", "50",
        "--max-cot-tokens", "4096",
    ]
    label = task["label"]
    t0 = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, env=ENV)
        elapsed = time.time() - t0
        if result.returncode == 0:
            return label, "OK", elapsed
        else:
            err = result.stderr[-500:] if result.stderr else "no stderr"
            return label, f"FAIL: {err}", elapsed
    except subprocess.TimeoutExpired:
        return label, "TIMEOUT", time.time() - t0
    except Exception as e:
        return label, f"ERROR: {e}", time.time() - t0


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-concurrent", type=int, default=2)
    args = parser.parse_args()

    output_base = Path("logs/eval-penalty-v3")

    tasks = []
    for cond_name, (model, ckpt) in SFT_CHECKPOINTS.items():
        for seed in [42, 43]:
            run_name = f"grpo-v3-{cond_name}-s{seed}"
            eval_dir = output_base / run_name
            model_slug = model.replace("/", "_")
            out_file = eval_dir / f"{model_slug}_000000.jsonl"
            if out_file.exists() and out_file.stat().st_size > 0:
                continue
            tasks.append({
                "label": f"{run_name}/000000",
                "model": model,
                "checkpoint": ckpt,
                "output_dir": str(eval_dir),
            })

    # Deduplicate: same SFT checkpoint for both seeds, just copy results after
    seen = {}
    unique_tasks = []
    copy_map = []
    for t in tasks:
        key = (t["model"], t["checkpoint"])
        if key not in seen:
            seen[key] = t
            unique_tasks.append(t)
        else:
            copy_map.append((seen[key]["output_dir"], t["output_dir"], t["model"]))

    print(f"Found {len(unique_tasks)} unique SFT evals to run, {len(copy_map)} to copy (max concurrent: {args.max_concurrent})")

    if not unique_tasks:
        print("All baselines already evaluated.")
    else:
        done = failed = 0
        with ProcessPoolExecutor(max_workers=args.max_concurrent) as pool:
            futures = {pool.submit(run_eval, t): t for t in unique_tasks}
            for future in as_completed(futures):
                label, status, elapsed = future.result()
                if "OK" in status:
                    done += 1
                else:
                    failed += 1
                print(f"[{done+failed}/{len(unique_tasks)}] {label}: {status} ({elapsed:.0f}s)")

        print(f"\nDone: {done} ok, {failed} failed")

    # Copy results for duplicate seeds
    import shutil
    for src_dir, dst_dir, model in copy_map:
        model_slug = model.replace("/", "_")
        src_file = Path(src_dir) / f"{model_slug}_000000.jsonl"
        dst_path = Path(dst_dir)
        dst_path.mkdir(parents=True, exist_ok=True)
        dst_file = dst_path / f"{model_slug}_000000.jsonl"
        if src_file.exists() and not dst_file.exists():
            shutil.copy2(src_file, dst_file)
            print(f"Copied {src_file} -> {dst_file}")


if __name__ == "__main__":
    main()
