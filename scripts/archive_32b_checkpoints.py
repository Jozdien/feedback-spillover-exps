"""Download LoRA checkpoint archives for Qwen3-32B runs before Tinker deprecation.

For each live/completed 32B run dir given (or auto-discovered v9 32B runs),
downloads the latest checkpoint's sampler (and optionally state) archive to
checkpoint_archives/<run>/<ckpt>_<kind>.tar.gz. Skips files that already exist,
so it can be re-run as new checkpoints land.

Usage:
    uv run scripts/archive_32b_checkpoints.py            # v9 32B runs + pirate SFT
    uv run scripts/archive_32b_checkpoints.py --all-final # also final ckpts of all v6/v7 32B runs
"""

import argparse
import json
import subprocess
from pathlib import Path

import tinker

ARCHIVE_DIR = Path("checkpoint_archives")

PIRATE_SFT = {
    "sft-pirate-output-32b": "tinker://707d82b5-211a-5014-b528-77713c6c1dbb:train:0/sampler_weights/final",
    "sft-pirate-output-8b": "tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/sampler_weights/final",
}


def download(rc, run_name, ckpt_name, kind, tinker_path):
    out_dir = ARCHIVE_DIR / run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{ckpt_name}_{kind}.tar.gz"
    if out_file.exists() and out_file.stat().st_size > 0:
        return "skip"
    try:
        url = rc.get_checkpoint_archive_url_from_tinker_path(tinker_path).result().url
    except Exception as e:
        print(f"  ERROR getting URL for {run_name}/{ckpt_name} ({kind}): {e}")
        return "fail"
    r = subprocess.run(["curl", "-sfL", "-o", str(out_file), str(url)])
    if r.returncode != 0:
        out_file.unlink(missing_ok=True)
        print(f"  ERROR downloading {run_name}/{ckpt_name} ({kind})")
        return "fail"
    print(f"  {run_name}/{ckpt_name} ({kind}): {out_file.stat().st_size / 1e6:.0f}MB")
    return "ok"


def latest_checkpoint(run_dir: Path):
    f = run_dir / "checkpoints.jsonl"
    if not f.exists():
        return None
    last = None
    for line in open(f):
        line = line.strip()
        if line:
            last = json.loads(line)
    return last


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-final", action="store_true",
                        help="also archive final checkpoints of completed v6/v7 32B runs")
    parser.add_argument("--convert", action="store_true",
                        help="convert state-only checkpoints to sampler weights (slow)")
    args = parser.parse_args()

    sc = tinker.ServiceClient()
    rc = sc.create_rest_client()
    counts = {"ok": 0, "skip": 0, "fail": 0}

    print("=== Pirate SFT checkpoints ===")
    for name, path in PIRATE_SFT.items():
        counts[download(rc, name, "final", "sampler", path)] += 1

    print("=== Latest checkpoints of v9 32B runs ===")
    for run_dir in sorted(Path("logs").glob("grpo-v9*32b*")):
        if not run_dir.is_dir():
            continue
        # M&F runs keep checkpoints in mind/ and face/ subdirs
        subdirs = [d for d in [run_dir / "mind", run_dir / "face"] if d.exists()] or [run_dir]
        for sub in subdirs:
            ckpt = latest_checkpoint(sub)
            if ckpt is None:
                continue
            label = run_dir.name if sub == run_dir else f"{run_dir.name}-{sub.name}"
            # archive endpoint supports sampler weights only; intermediate
            # checkpoints save state only, so convert when requested
            if ckpt.get("sampler_path"):
                counts[download(rc, label, ckpt["name"], "sampler", ckpt["sampler_path"])] += 1
            elif args.convert and ckpt.get("state_path"):
                out_file = ARCHIVE_DIR / label / f"{ckpt['name']}_sampler.tar.gz"
                if out_file.exists() and out_file.stat().st_size > 0:
                    counts["skip"] += 1
                    continue
                try:
                    tc = sc.create_training_client_from_state_with_optimizer(ckpt["state_path"])
                    sampler_path = tc.save_weights_for_sampler(name=f"archive_{ckpt['name']}").result().path
                    counts[download(rc, label, ckpt["name"], "sampler", sampler_path)] += 1
                except Exception as e:
                    print(f"  ERROR converting {label}/{ckpt['name']}: {e}")
                    counts["fail"] += 1

    if args.all_final:
        print("=== Final checkpoints of completed v6/v7 32B runs ===")
        for run_dir in sorted(Path("logs").glob("grpo-v[67]*32b*")) + sorted(Path("logs").glob("grpo-v6-32b*")) + sorted(Path("logs").glob("grpo-v6ctrl-32b*")):
            if not run_dir.is_dir():
                continue
            ckpt = latest_checkpoint(run_dir)
            if ckpt is None or ckpt.get("name") != "final":
                continue
            if ckpt.get("sampler_path"):
                counts[download(rc, run_dir.name, "final", "sampler", ckpt["sampler_path"])] += 1

    print(f"\nDone: {counts['ok']} downloaded, {counts['skip']} skipped, {counts['fail']} failed")


if __name__ == "__main__":
    main()
