"""Monitor SFT progress and launch RL runs as epoch checkpoints become available."""

import functools
import json
import os
import subprocess
import time
from pathlib import Path

SFT_LOG = Path("/tmp/spillover-exps/pirate-haiku-sft")
RUN_ID = "0a2f97d8-9f8a-5d2e-b90f-cc3beb5ef9ff"
STEPS_PER_EPOCH = 175

# Epoch-end checkpoints (epochs 1-20)
TARGET_STEPS = [STEPS_PER_EPOCH * e for e in range(1, 21)]
# Also add the fractional first-epoch checkpoints
TARGET_STEPS = sorted(set([35, 58, 87] + TARGET_STEPS))

ALREADY_LAUNCHED = set()
print = functools.partial(print, flush=True)


def get_sft_step():
    ckpt_file = SFT_LOG / "checkpoints.jsonl"
    if not ckpt_file.exists():
        return 0
    lines = ckpt_file.read_text().strip().split("\n")
    if not lines:
        return 0
    last = json.loads(lines[-1])
    path = last.get("state_path", "")
    step_str = path.split("/")[-1]
    try:
        return int(step_str)
    except ValueError:
        return 0


def launch_rl(step):
    ckpt = f"tinker://{RUN_ID}:train:0/weights/{step:06d}"
    log_path = f"/tmp/spillover-exps/v4-pirate-step{step}"
    if Path(f"{log_path}/metrics.jsonl").exists():
        n = sum(1 for _ in open(f"{log_path}/metrics.jsonl"))
        if n > 0:
            print(f"  Step {step}: already has {n} batches, skipping")
            return

    env = os.environ.copy()
    print(f"  Launching RL for SFT step {step}")
    subprocess.Popen(
        ["uv", "run", "python", "-m", "src.spillover.train",
         f"task=qa", f"penalty_weight=-2", f"seed=42",
         f"checkpoint={ckpt}", f"reward_target=false",
         f"log_path={log_path}"],
        stdout=open(f"{log_path}.log", "w"),
        stderr=subprocess.STDOUT,
        env=env,
    )


def check_rl_progress():
    for step in sorted(ALREADY_LAUNCHED):
        log = f"/tmp/spillover-exps/v4-pirate-step{step}/metrics.jsonl"
        n = sum(1 for _ in open(log)) if Path(log).exists() else 0
        status = "DONE" if n >= 266 else f"{n}/266"
        print(f"  step {step}: {status}")


def main():
    print(f"Monitoring SFT and launching RL runs for {len(TARGET_STEPS)} checkpoints")
    print(f"Target steps: {TARGET_STEPS}")

    while True:
        current_step = get_sft_step()
        ready = [s for s in TARGET_STEPS if s <= current_step and s not in ALREADY_LAUNCHED]

        if ready:
            print(f"\nSFT at step {current_step}, new checkpoints ready: {ready}")
            for step in ready:
                launch_rl(step)
                ALREADY_LAUNCHED.add(step)

        if len(ALREADY_LAUNCHED) == len(TARGET_STEPS):
            print("\nAll RL runs launched!")
            break

        # Print status every check
        if ALREADY_LAUNCHED:
            print(f"\n[SFT step {current_step}/{STEPS_PER_EPOCH * 20}] "
                  f"Launched {len(ALREADY_LAUNCHED)}/{len(TARGET_STEPS)} RL runs")
            check_rl_progress()

        time.sleep(60)


if __name__ == "__main__":
    main()
