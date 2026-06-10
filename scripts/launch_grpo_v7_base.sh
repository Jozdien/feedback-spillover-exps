#!/bin/bash
# Launch 16 GRPO runs on base Qwen models (no SFT)
# 4 penalty weights × 2 model sizes × 2 seeds = 16 runs

set -a && source .env && set +a

COMMON="task=qa no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"
DELAY=30

launch() {
    local tag=$1 model=$2 seed=$3 pw=$4
    local log_dir="logs/grpo-v7base-${tag}-s${seed}"
    local log_file="${log_dir}.log"
    echo "Launching $log_dir (pw=$pw) ..."
    nohup uv run python -m src.spillover.train_grpo \
        model_name="$model" seed="$seed" \
        log_path="$log_dir" penalty_weight="$pw" $COMMON \
        > "$log_file" 2>&1 &
    echo "  PID: $!"
}

echo "=== Launching 16 base-model GRPO runs ==="

for pw in 0 -0.5 -1 -2; do
    for seed in 42 43; do
        launch "8b-pw${pw}" "Qwen/Qwen3-8B" "$seed" "$pw"
        sleep $DELAY
        launch "32b-pw${pw}" "Qwen/Qwen3-32B" "$seed" "$pw"
        sleep $DELAY
    done
done

echo "=== All 16 base-model runs launched ==="
