#!/bin/bash
# Scenario B: penalty RL (pw=-2) on intermediate pirate-output SFT checkpoints.
# Waits for the SFT rerun to finish, then launches RL from each selected checkpoint
# (persona depth sweep), 2 seeds = 14 runs. 8B only (Qwen3-32B deprecated from Tinker).

set -a && source .env && set +a
CKPT_JSONL="logs/sft-8b-pirate-output-rerun/checkpoints.jsonl"
COMMON="task=qa penalty_weight=-2 no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"
TARGETS="000005 000025 000050 000100 000150 000200 final"

echo "Waiting for SFT rerun to finish..."
until grep -q '"name": "final"' "$CKPT_JSONL" 2>/dev/null; do sleep 60; done
echo "SFT done. Launching Scenario B RL runs."

get_path() {  # $1 = checkpoint name -> its state_path
    python3 -c "
import json,sys
for l in open('$CKPT_JSONL'):
    d=json.loads(l)
    if d['name']=='$1': print(d['state_path']); break
"
}

DELAY=20
for step in $TARGETS; do
    sp=$(get_path "$step")
    if [ -z "$sp" ]; then echo "  MISSING checkpoint $step, skipping"; continue; fi
    label=$([ "$step" = "final" ] && echo "final" || echo "$((10#$step))")
    for seed in 42 43; do
        name="grpo-scenB-step${label}-8b-pw-2-s${seed}"
        echo "Launching $name (from SFT $step) ..."
        nohup uv run python -m src.spillover.train_grpo \
            model_name=Qwen/Qwen3-8B seed=$seed checkpoint="$sp" \
            log_path="logs/${name}" $COMMON > "logs/${name}.log" 2>&1 &
        echo "  PID: $!"
        sleep $DELAY
    done
done
echo "=== All Scenario B RL runs launched ==="
