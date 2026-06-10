#!/bin/bash
# Launch 8 V6 GRPO runs on Alpaca pirate-output SFT checkpoints
# V5 (penalty_weight=-0.5) + V5ctrl (penalty_weight=0), both with no_answer_penalty=-1.0
# 2 model sizes × 2 seeds × 2 reward versions = 8 runs

set -a && source .env && set +a

COMMON="task=qa no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"
DELAY=60

# Alpaca pirate-output SFT checkpoints
CK_8B="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
CK_32B="tinker://707d82b5-211a-5014-b528-77713c6c1dbb:train:0/weights/final"

launch() {
    local version=$1 name=$2 model=$3 ckpt=$4 seed=$5 pw=$6
    local log_dir="logs/grpo-${version}-${name}-s${seed}"
    local log_file="logs/grpo-${version}-${name}-s${seed}.log"
    echo "Launching $log_dir (penalty_weight=$pw) ..."
    nohup uv run python -m src.spillover.train_grpo \
        model_name="$model" checkpoint="$ckpt" seed="$seed" \
        log_path="$log_dir" penalty_weight="$pw" $COMMON \
        > "$log_file" 2>&1 &
    echo "  PID: $!"
}

echo "=== Launching 8 V6 runs (Alpaca pirate-output) ==="

# V5: penalty_weight=-0.5
launch "v6" "8b-pirate-output-alpaca-qwen" "Qwen/Qwen3-8B" "$CK_8B" 42 -0.5
sleep $DELAY
launch "v6" "8b-pirate-output-alpaca-qwen" "Qwen/Qwen3-8B" "$CK_8B" 43 -0.5
sleep $DELAY
launch "v6" "32b-pirate-output-alpaca-qwen" "Qwen/Qwen3-32B" "$CK_32B" 42 -0.5
sleep $DELAY
launch "v6" "32b-pirate-output-alpaca-qwen" "Qwen/Qwen3-32B" "$CK_32B" 43 -0.5
sleep $DELAY

# V5ctrl: penalty_weight=0
launch "v6ctrl" "8b-pirate-output-alpaca-qwen" "Qwen/Qwen3-8B" "$CK_8B" 42 0
sleep $DELAY
launch "v6ctrl" "8b-pirate-output-alpaca-qwen" "Qwen/Qwen3-8B" "$CK_8B" 43 0
sleep $DELAY
launch "v6ctrl" "32b-pirate-output-alpaca-qwen" "Qwen/Qwen3-32B" "$CK_32B" 42 0
sleep $DELAY
launch "v6ctrl" "32b-pirate-output-alpaca-qwen" "Qwen/Qwen3-32B" "$CK_32B" 43 0

echo "=== All 8 V6 runs launched ==="
