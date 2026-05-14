"""Monitor resumed SFT and launch remaining RL runs."""

import functools
import json
import os
import subprocess
import time
from pathlib import Path

print = functools.partial(print, flush=True)

SFT_LOG = Path("/tmp/spillover-exps/pirate-haiku-sft-resume")
RESUME_RUN_ID = "67b18dea-4aa9-53c5-a765-6387b28b2950"

# resume_step -> original_step (for RL naming)
TARGETS = {59: 2625, 234: 2800, 409: 2975, 584: 3150, 759: 3325, 934: 3500}

LAUNCHED = set()


def get_step():
    ckpt_file = SFT_LOG / "checkpoints.jsonl"
    if not ckpt_file.exists():
        return 0
    lines = ckpt_file.read_text().strip().split("\n")
    last = json.loads(lines[-1])
    return int(last["state_path"].split("/")[-1])


def launch_rl(resume_step, orig_step):
    ckpt = f"tinker://{RESUME_RUN_ID}:train:0/weights/{resume_step:06d}"
    log_path = f"/tmp/spillover-exps/v4-pirate-step{orig_step}"
    if Path(f"{log_path}/metrics.jsonl").exists():
        n = sum(1 for _ in open(f"{log_path}/metrics.jsonl"))
        if n > 0:
            print(f"  Step {orig_step}: already has {n} batches, skipping")
            return
    print(f"  Launching RL for original step {orig_step} (resume step {resume_step})")
    subprocess.Popen(
        ["uv", "run", "python", "-m", "src.spillover.train",
         "task=qa", "penalty_weight=-2", "seed=42",
         f"checkpoint={ckpt}", "reward_target=false",
         f"log_path={log_path}"],
        stdout=open(f"{log_path}.log", "w"),
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )


def main():
    print(f"Monitoring resumed SFT for {len(TARGETS)} remaining checkpoints")

    while True:
        step = get_step()
        ready = {rs: os for rs, os in TARGETS.items() if rs <= step and os not in LAUNCHED}

        if ready:
            print(f"\nResume step {step}, new checkpoints: {list(ready.values())}")
            for rs, os in sorted(ready.items()):
                launch_rl(rs, os)
                LAUNCHED.add(os)

        if len(LAUNCHED) == len(TARGETS):
            print("\nAll remaining RL runs launched!")
            break

        print(f"[Resume step {step}/934] Launched {len(LAUNCHED)}/{len(TARGETS)}")
        time.sleep(60)


if __name__ == "__main__":
    main()
