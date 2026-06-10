#!/bin/bash
# Launch 12 GRPO baseline runs on new base models (no SFT)
# 3 models × 4 penalty weights × 1 seed (42) = 12 runs

set -a && source .env && set +a

COMMON="task=qa no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"
DELAY=30

launch() {
    local tag=$1 model=$2 seed=$3 pw=$4
    local log_dir="logs/grpo-v8base-${tag}-pw${pw}-s${seed}"
    local log_file="${log_dir}.log"
    echo "Launching $log_dir (pw=$pw) ..."
    nohup uv run python -m src.spillover.train_grpo \
        model_name="$model" seed="$seed" \
        log_path="$log_dir" penalty_weight="$pw" $COMMON \
        > "$log_file" 2>&1 &
    echo "  PID: $!"
}

echo "=== Launching 12 v8 base-model GRPO runs ==="

for pw in 0 -0.5 -1 -2; do
    launch "qwen36-27b" "Qwen/Qwen3.6-27B" 42 "$pw"
    sleep $DELAY
    launch "qwen36-35ba3b" "Qwen/Qwen3.6-35B-A3B" 42 "$pw"
    sleep $DELAY
    launch "nemotron-super-120b" "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16" 42 "$pw"
    sleep $DELAY
done

echo "=== All 12 v8 base-model runs launched ==="
