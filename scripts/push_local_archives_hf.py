"""Push local-only checkpoint_archives/ tarballs to HuggingFace.

Covers the 17 archives never exported by export_checkpoints_hf.py (v7 lambda-sweep
pw-0.5/pw-1 finals, v6 base/pw-1 pirate runs, 8B pirate SFT). Each archive dir
holds a final_sampler.tar.gz (plain tar, despite the name) with the PEFT adapter.
Extracts to a staging dir, uploads, verifies file sizes via the HF API, records
in exported_checkpoints/hf_pushed.json (grpo labels get the usual -final suffix).
Re-runnable: skips labels already in the record.

Usage:
  uv run scripts/push_local_archives_hf.py --hf Jozdien
"""

import argparse
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVES = ROOT / "checkpoint_archives"
DONE = ROOT / "exported_checkpoints" / "hf_pushed.json"
STAGE = ROOT / "exported_checkpoints" / "_stage"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hf", required=True)
    p.add_argument("--public", action="store_true")
    args = p.parse_args()
    if not os.environ.get("HF_TOKEN"):
        sys.exit("Set HF_TOKEN")
    from huggingface_hub import HfApi
    api = HfApi()

    done = json.load(open(DONE)) if DONE.exists() else {}
    done_names = {k.removesuffix("-final") for k in done}
    todo = sorted(d for d in ARCHIVES.iterdir()
                  if d.is_dir() and d.name not in done_names)
    print(f"Pushing {len(todo)} local-only archives to HF ({args.hf})", flush=True)

    failures = []
    for d in todo:
        label = f"{d.name}-final" if d.name.startswith("grpo-") else d.name
        tarball = d / "final_sampler.tar.gz"
        if not tarball.exists():
            print(f"  FAIL {label}: no final_sampler.tar.gz", flush=True)
            failures.append(label)
            continue
        out = STAGE / label
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        with tarfile.open(tarball) as tf:
            tf.extractall(out)
        repo = f"{args.hf}/feedback-spillover-{label}"
        try:
            api.create_repo(repo, private=not args.public, exist_ok=True, repo_type="model")
            api.upload_folder(folder_path=str(out), repo_id=repo, repo_type="model")
            info = api.model_info(repo, files_metadata=True)
            remote = {s.rfilename: s.size for s in info.siblings}
            for f in out.iterdir():
                if remote.get(f.name) != f.stat().st_size:
                    raise RuntimeError(f"size mismatch for {f.name}: "
                                       f"local {f.stat().st_size} vs HF {remote.get(f.name)}")
            done[label] = repo
            json.dump(done, open(DONE, "w"), indent=2)
            print(f"  PUSHED {repo}", flush=True)
        except Exception as e:
            print(f"  FAIL {label}: {e}", flush=True)
            failures.append(label)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    print(f"\nDone: {len(done)} total on HF, {len(failures)} failures.", flush=True)
    if failures:
        print("Failed:", ", ".join(failures), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
