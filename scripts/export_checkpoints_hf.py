"""Push paper-relevant Qwen3-32B LoRA finals to HuggingFace before deprecation.

For each checkpoint: use the final's sampler weights (convert from state if
absent), download the PEFT adapter via tinker CLI, upload to HF, delete the
local copy. Skips already-pushed labels (exported_checkpoints/hf_pushed.json),
so it can be re-run as more v9 runs finish.

Curated set: pirate SFT 32B + QA finals at pw0/pw-2 for all SFT conditions +
all v9 32B finals (QA mitigations incl. mind/face pairs, poly suite).
--latest also exports the newest checkpoint of *unfinished* v9 32B runs
(post-deadline salvage).

Usage:
  uv run scripts/export_checkpoints_hf.py --hf Jozdien [--public] [--latest]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import tinker

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "exported_checkpoints"
DONE = STAGE / "hf_pushed.json"

PIRATE_SFT_32B = "tinker://707d82b5-211a-5014-b528-77713c6c1dbb:train:0/sampler_weights/final"

QA_FINAL_RUNS = (
    [f"grpo-v7{c}-32b-{pw}-s{s}" for c in ["base", "norm", "pcot"]
     for pw in ["pw0", "pw-2"] for s in [42, 43]]
    + [f"grpo-v6ctrl-32b-pirate-output-alpaca-qwen-s{s}" for s in [42, 43]]
    + [f"grpo-v6pw-2-32b-pirate-output-alpaca-qwen-s{s}" for s in [42, 43]]
)


def ckpt_entries(run_dir: Path):
    f = run_dir / "checkpoints.jsonl"
    if not f.exists():
        return []
    return [json.loads(line) for line in open(f) if line.strip()]


def gather(latest: bool):
    """Yield (label, sampler_path_or_None, state_path_or_None)."""
    items = [("sft-pirate-output-32b", PIRATE_SFT_32B, None)]

    def add_run(run_dir: Path, label: str):
        entries = ckpt_entries(run_dir)
        if not entries:
            return
        final = next((e for e in entries if e["name"] == "final"), None)
        if final:
            items.append((f"{label}-final", final.get("sampler_path"), final.get("state_path")))
        elif latest:
            e = entries[-1]
            items.append((f"{label}-{e['name']}", e.get("sampler_path"), e.get("state_path")))

    for name in QA_FINAL_RUNS:
        add_run(ROOT / "logs" / name, name)

    for run_dir in sorted((ROOT / "logs").glob("grpo-v9*32b*")):
        if not run_dir.is_dir():
            continue
        if (run_dir / "mind").exists():
            add_run(run_dir / "mind", f"{run_dir.name}-mind")
            add_run(run_dir / "face", f"{run_dir.name}-face")
        else:
            add_run(run_dir, run_dir.name)
    return items


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hf", required=True)
    p.add_argument("--public", action="store_true")
    p.add_argument("--latest", action="store_true")
    args = p.parse_args()
    if not os.environ.get("HF_TOKEN"):
        sys.exit("Set HF_TOKEN")
    from huggingface_hub import HfApi
    api = HfApi()

    STAGE.mkdir(exist_ok=True)
    done = json.load(open(DONE)) if DONE.exists() else {}
    items = gather(args.latest)
    service = tinker.ServiceClient()
    print(f"Exporting {len(items)} checkpoints to HF ({args.hf})")

    for label, sampler, state in items:
        if done.get(label):
            print(f"  skip {label} (done)", flush=True)
            continue
        if sampler is None:
            if state is None:
                print(f"  FAIL {label}: no paths")
                continue
            try:
                tc = service.create_training_client_from_state_with_optimizer(state)
                sampler = tc.save_weights_for_sampler(name="hf-export").result().path
            except Exception as e:
                print(f"  FAIL convert {label}: {e}", flush=True)
                continue
        out = STAGE / label
        if not out.exists():
            r = subprocess.run([sys.executable, "-m", "tinker.cli", "checkpoint", "download",
                                sampler, "--output", str(out)], cwd=ROOT,
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"  FAIL download {label}: {(r.stderr or '')[-200:]}", flush=True)
                continue
        subs = [s for s in out.iterdir() if s.is_dir()]
        adir = subs[0] if subs else out
        repo = f"{args.hf}/feedback-spillover-{label}"
        try:
            api.create_repo(repo, private=not args.public, exist_ok=True, repo_type="model")
            api.upload_folder(folder_path=str(adir), repo_id=repo, repo_type="model")
            done[label] = repo
            json.dump(done, open(DONE, "w"), indent=2)
            print(f"  PUSHED {repo}", flush=True)
        except Exception as e:
            print(f"  FAIL upload {label}: {e}", flush=True)
            continue
        shutil.rmtree(out, ignore_errors=True)
    print(f"\nDone: {len(done)} on HF.")


if __name__ == "__main__":
    main()
