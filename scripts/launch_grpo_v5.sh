#!/bin/bash
# Launch 4 V5 runs: pirate-output-qwen only, with no_answer_penalty=-1.0
# Same as V4 (penalty_weight=-0.5) but adds penalty for empty/no-answer outputs

set -a && source .env && set +a

COMMON="task=qa penalty_weight=-0.5 no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"
DELAY=60

# SFT checkpoint paths (pirate-output-qwen only)
CK_8B_PO_QWEN="tinker://6f8d3ebd-7dc3-5ff9-87ed-1083d50f0b05:train:0/weights/final"
CK_32B_PO_QWEN="tinker://8fb3a99c-f00a-5e5e-a39d-fb9926f4e02c:train:0/weights/final"

launch() {
    local name=$1 model=$2 ckpt=$3 seed=$4
    local log_dir="logs/grpo-v5-${name}-s${seed}"
    local log_file="logs/grpo-v5-${name}-s${seed}.log"
    echo "Launching $log_dir ..."
    nohup uv run python -m src.spillover.train_grpo \
        model_name="$model" checkpoint="$ckpt" seed="$seed" \
        log_path="$log_dir" $COMMON \
        > "$log_file" 2>&1 &
    echo "  PID: $!"
}

echo "=== Launching 4 V5 runs (penalty_weight=-0.5, no_answer_penalty=-1.0) ==="

launch "8b-pirate-output-qwen" "Qwen/Qwen3-8B" "$CK_8B_PO_QWEN" 42
sleep $DELAY
launch "8b-pirate-output-qwen" "Qwen/Qwen3-8B" "$CK_8B_PO_QWEN" 43
sleep $DELAY
launch "32b-pirate-output-qwen" "Qwen/Qwen3-32B" "$CK_32B_PO_QWEN" 42
sleep $DELAY
launch "32b-pirate-output-qwen" "Qwen/Qwen3-32B" "$CK_32B_PO_QWEN" 43

echo "=== All 4 V5 runs launched ==="
