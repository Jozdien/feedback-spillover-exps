"""Monitor v5 (Qwen-generated) SFT and launch RL runs as checkpoints become available."""

import functools
import json
import os
import subprocess
import time
from pathlib import Path

print = functools.partial(print, flush=True)

SFT_LOG = Path("/tmp/spillover-exps/pirate-qwen-sft")
STEPS_PER_EPOCH = 127

TARGET_STEPS = [STEPS_PER_EPOCH * e for e in range(1, 21)]
TARGET_STEPS = sorted(set([25, 41, 63] + TARGET_STEPS))

LAUNCHED = set()


def get_run_id():
    cfg = json.loads((SFT_LOG / "config.json").read_text())
    log = SFT_LOG / "logs.log"
    for line in open(log):
        if "run_id" in line.lower() or "training_client" in line.lower():
            pass
    ckpt = json.loads(open(SFT_LOG / "checkpoints.jsonl").readline())
    # tinker://RUN_ID:train:0/weights/000001
    return ckpt["state_path"].split("://")[1].split(":")[0]


def get_step():
    ckpt_file = SFT_LOG / "checkpoints.jsonl"
    if not ckpt_file.exists():
        return 0
    lines = ckpt_file.read_text().strip().split("\n")
    if not lines:
        return 0
    last = json.loads(lines[-1])
    path = last.get("state_path", "")
    step_str = path.split("/")[-1]
    if step_str == "final":
        return 999999
    try:
        return int(step_str)
    except ValueError:
        return 0


def launch_rl(run_id, step):
    ckpt = f"tinker://{run_id}:train:0/weights/{step:06d}"
    log_path = f"/tmp/spillover-exps/v5-pirate-step{step}"
    if Path(f"{log_path}/metrics.jsonl").exists():
        n = sum(1 for _ in open(f"{log_path}/metrics.jsonl"))
        if n > 0:
            print(f"  Step {step}: already has {n} batches, skipping")
            return
    print(f"  Launching RL for SFT step {step}")
    subprocess.Popen(
        ["uv", "run", "python", "-m", "src.spillover.train",
         "task=qa", "penalty_weight=-2", "seed=42",
         f"checkpoint={ckpt}", "reward_target=false",
         f"log_path={log_path}"],
        stdout=open(f"{log_path}.log", "w"),
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )


def check_rl_progress():
    for step in sorted(LAUNCHED):
        log = f"/tmp/spillover-exps/v5-pirate-step{step}/metrics.jsonl"
        n = sum(1 for _ in open(log)) if Path(log).exists() else 0
        status = "DONE" if n >= 266 else f"{n}/266"
        print(f"  step {step}: {status}")


def main():
    print(f"Monitoring v5 SFT for {len(TARGET_STEPS)} checkpoints")
    print(f"Target steps: {TARGET_STEPS}")

    # Wait for first checkpoint so we can get run_id
    while not (SFT_LOG / "checkpoints.jsonl").exists():
        print("Waiting for first checkpoint...")
        time.sleep(30)

    run_id = get_run_id()
    print(f"Run ID: {run_id}")

    while True:
        current_step = get_step()
        ready = [s for s in TARGET_STEPS if s <= current_step and s not in LAUNCHED]

        if ready:
            print(f"\nSFT at step {current_step}, new checkpoints ready: {ready}")
            for step in ready:
                launch_rl(run_id, step)
                LAUNCHED.add(step)

        if len(LAUNCHED) == len(TARGET_STEPS):
            print("\nAll RL runs launched!")
            break

        if LAUNCHED:
            print(f"\n[SFT step {current_step}/{STEPS_PER_EPOCH * 20}] "
                  f"Launched {len(LAUNCHED)}/{len(TARGET_STEPS)} RL runs")
            check_rl_progress()

        time.sleep(60)


if __name__ == "__main__":
    main()
