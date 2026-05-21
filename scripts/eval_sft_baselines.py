"""Evaluate SFT checkpoints (step 0) to get pre-RL baselines.

12 unique SFT checkpoints, each shared by 2 seeds.
Results saved as step 000000 in each run's eval directory.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

SFT_CHECKPOINTS = {
    "8b-pirate-output-qwen": ("Qwen/Qwen3-8B", "tinker://6f8d3ebd-7dc3-5ff9-87ed-1083d50f0b05:train:0/weights/final"),
    "8b-pirate-cot-qwen":    ("Qwen/Qwen3-8B", "tinker://73334e08-6e76-5890-a506-864ee95c4e90:train:0/weights/final"),
    "8b-normal-qwen":        ("Qwen/Qwen3-8B", "tinker://fe120137-fe95-51ce-9d3a-2881d22047ba:train:0/weights/final"),
    "8b-pirate-output-haiku": ("Qwen/Qwen3-8B", "tinker://28be06c8-e482-5830-94f7-602f6a643c3f:train:0/weights/final"),
    "8b-pirate-cot-haiku":   ("Qwen/Qwen3-8B", "tinker://7bceb7ca-7404-5b05-963d-8ee9a07d1b7c:train:0/weights/final"),
    "8b-normal-haiku":       ("Qwen/Qwen3-8B", "tinker://f58be72e-f8f9-5238-bfe0-7399f1043337:train:0/weights/final"),
    "32b-pirate-output-qwen": ("Qwen/Qwen3-32B", "tinker://8fb3a99c-f00a-5e5e-a39d-fb9926f4e02c:train:0/weights/final"),
    "32b-pirate-cot-qwen":   ("Qwen/Qwen3-32B", "tinker://dfe600ac-762b-5e66-b3d5-222f4d9c81e5:train:0/weights/final"),
    "32b-normal-qwen":       ("Qwen/Qwen3-32B", "tinker://f3b1fb04-de20-52ff-90b9-2ba1a5bb0552:train:0/weights/final"),
    "32b-pirate-output-haiku": ("Qwen/Qwen3-32B", "tinker://719ca1fa-1edc-5b2c-87f9-fe7c72d3b953:train:0/weights/final"),
    "32b-pirate-cot-haiku":  ("Qwen/Qwen3-32B", "tinker://3dea7ead-ca2e-5d30-9f7d-3e21ff6bb3ad:train:0/weights/final"),
    "32b-normal-haiku":      ("Qwen/Qwen3-32B", "tinker://ac715aed-3087-5c68-9a38-d5b0fd33f671:train:0/weights/final"),
}

SEEDS = [42, 43]
EVAL_BASE = Path("logs/eval-penalty")


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
    label, model, checkpoint, output_dir = task
    cmd = [
        "uv", "run", "python", "scripts/eval_grpo_baseline.py",
        "--model", model,
        "--checkpoint", checkpoint,
        "--output-dir", output_dir,
        "--batch-size", "50",
    ]
    t0 = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, env=ENV)
        elapsed = time.time() - t0
        if result.returncode == 0:
            return label, "OK", elapsed
        else:
            err = result.stderr[-500:] if result.stderr else "no stderr"
            return label, f"FAIL (rc={result.returncode}): {err}", elapsed
    except subprocess.TimeoutExpired:
        return label, "TIMEOUT", time.time() - t0
    except Exception as e:
        return label, f"ERROR: {e}", time.time() - t0


def main():
    import shutil
    tasks = []
    copy_plan = []

    for cond_key, (model, ckpt) in SFT_CHECKPOINTS.items():
        # Eval into seed 42's directory, then copy to seed 43
        s42_dir = EVAL_BASE / f"grpo-{cond_key}-s42"
        s43_dir = EVAL_BASE / f"grpo-{cond_key}-s43"
        s42_dir.mkdir(parents=True, exist_ok=True)
        s43_dir.mkdir(parents=True, exist_ok=True)

        model_slug = model.replace("/", "_")
        out_file = s42_dir / f"{model_slug}_000000.jsonl"
        copy_dest = s43_dir / f"{model_slug}_000000.jsonl"

        if out_file.exists() and out_file.stat().st_size > 0:
            print(f"  Skipping {cond_key}: already exists")
            if not copy_dest.exists():
                copy_plan.append((out_file, copy_dest))
            continue

        tasks.append((cond_key, model, ckpt, str(s42_dir)))
        copy_plan.append((out_file, copy_dest))

    print(f"Running {len(tasks)} SFT baseline evals")

    done = failed = 0
    t_start = time.time()
    with ProcessPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(run_eval, t): t for t in tasks}
        for future in as_completed(futures):
            label, status, elapsed = future.result()
            if "OK" in status:
                done += 1
            else:
                failed += 1
            total = done + failed
            print(f"[{total}/{len(tasks)}] {label}: {status} ({elapsed:.0f}s)", flush=True)

    # Copy results to seed 43 directories
    for src, dst in copy_plan:
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            print(f"  Copied {src.name} -> {dst.parent.name}/")

    print(f"\nDone: {done} ok, {failed} failed. Copied to both seeds.")


if __name__ == "__main__":
    main()
