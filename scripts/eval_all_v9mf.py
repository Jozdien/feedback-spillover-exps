"""Launch Mind & Face evaluations on all v9 M&F-family GRPO checkpoints.

Covers grpo-v9{mf,tmf,mfpirate,tmfpirate}-* QA runs. Pairs mind/face
checkpoints by name from each run's mind/ and face/ checkpoints.jsonl,
skips already-evaluated checkpoints. Poly M&F runs are excluded (poly
results come from training rollouts, no generation eval needed).

Usage:
    uv run scripts/eval_all_v9mf.py --max-concurrent 4 [--dry-run] [--size 32b]
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

PREFIXES = ["grpo-v9mf-", "grpo-v9tmf-", "grpo-v9mfpirate-", "grpo-v9tmfpirate-"]
FINALS_ONLY = False


def load_ckpts(path):
    out = {}
    if not path.exists():
        return out
    for line in open(path):
        line = line.strip()
        if line:
            d = json.loads(line)
            out[d["name"]] = d
    return out


def get_eval_tasks(output_base: Path, size_filter, prefixes, max_cot_tokens):
    tasks = []
    for d in sorted(Path("logs").iterdir()):
        if not d.is_dir() or not any(d.name.startswith(p) for p in prefixes):
            continue
        if size_filter and f"-{size_filter}-" not in d.name:
            continue
        model = "Qwen/Qwen3-32B" if "-32b-" in d.name else "Qwen/Qwen3-8B"
        mind = load_ckpts(d / "mind" / "checkpoints.jsonl")
        face = load_ckpts(d / "face" / "checkpoints.jsonl")
        eval_dir = output_base / d.name
        for name in sorted(set(mind) & set(face)):
            if FINALS_ONLY and name != "final":
                continue
            eval_name = "001000" if name == "final" else name
            # eval_grpo_mind_face writes {model_slug}_mf_{ckpt_name}.jsonl itself
            out_file = eval_dir / f"{model.replace('/', '_')}_mf_{name}.jsonl"
            if out_file.exists() and out_file.stat().st_size > 0:
                continue
            tasks.append({
                "run_name": d.name, "ckpt_name": name, "eval_name": eval_name,
                "model": model,
                "mind": mind[name]["state_path"], "face": face[name]["state_path"],
                "output_dir": str(eval_dir), "max_cot_tokens": max_cot_tokens,
            })
    return tasks


def _load_env():
    env = dict(os.environ)
    if Path(".env").exists():
        for line in open(".env"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = _load_env()


def run_eval(task):
    Path(task["output_dir"]).mkdir(parents=True, exist_ok=True)
    cmd = [
        "uv", "run", "python", "scripts/eval_grpo_mind_face.py",
        "--model", task["model"],
        "--mind-checkpoint", task["mind"],
        "--face-checkpoint", task["face"],
        "--output-dir", task["output_dir"],
        "--batch-size", "50",
        "--max-cot-tokens", str(task["max_cot_tokens"]),
    ]
    label = f"{task['run_name']}/{task['ckpt_name']}"
    t0 = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, env=ENV)
        elapsed = time.time() - t0
        if result.returncode == 0:
            return label, "OK", elapsed
        return label, f"FAIL (rc={result.returncode}): {(result.stderr or 'no stderr')[-300:]}", elapsed
    except subprocess.TimeoutExpired:
        return label, "TIMEOUT", time.time() - t0
    except Exception as e:
        return label, f"ERROR: {e}", time.time() - t0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-concurrent", type=int, default=4)
    parser.add_argument("--output-base", default="logs/eval-penalty-v9mf")
    parser.add_argument("--size", default=None, choices=[None, "8b", "32b"])
    parser.add_argument("--prefixes", nargs="+", default=PREFIXES,
                        help="run-name prefixes to match (default: v9 M&F family)")
    parser.add_argument("--max-cot-tokens", type=int, default=4096,
                        help="MUST match the runs' training budget (v9=4096, t300=300)")
    parser.add_argument("--finals-only", action="store_true",
                        help="only evaluate the final checkpoint of each run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    global FINALS_ONLY
    FINALS_ONLY = args.finals_only
    output_base = Path(args.output_base)
    output_base.mkdir(parents=True, exist_ok=True)
    tasks = get_eval_tasks(output_base, args.size, args.prefixes, args.max_cot_tokens)
    print(f"Found {len(tasks)} M&F evals to run (max concurrent: {args.max_concurrent})")
    if args.dry_run:
        for t in tasks[:15]:
            print(f"  {t['run_name']}/{t['ckpt_name']}")
        return

    done = failed = 0
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.max_concurrent) as pool:
        futures = {pool.submit(run_eval, t): t for t in tasks}
        for fut in as_completed(futures):
            label, status, elapsed = fut.result()
            done += "OK" in status
            failed += "OK" not in status
            rate = (done + failed) / (time.time() - t0) * 3600
            print(f"[{done+failed}/{len(tasks)}] {label}: {status} ({elapsed:.0f}s) [{done} ok, {failed} fail, {rate:.0f}/hr]", flush=True)

    print(f"\nDone: {done} ok, {failed} failed out of {len(tasks)} total")


if __name__ == "__main__":
    main()
