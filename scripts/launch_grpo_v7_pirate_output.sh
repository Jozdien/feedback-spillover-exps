#!/bin/bash
# Launch additional GRPO runs on Alpaca pirate-output SFT checkpoints
# pw={-1, -2} × 2 model sizes × 2 seeds = 8 runs (minus 1 already running)

set -a && source .env && set +a

COMMON="task=qa no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"
DELAY=30

CK_8B="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
CK_32B="tinker://707d82b5-211a-5014-b528-77713c6c1dbb:train:0/weights/final"

launch() {
    local tag=$1 model=$2 ckpt=$3 seed=$4 pw=$5
    local log_dir="logs/grpo-v6pw${pw}-${tag}-s${seed}"
    local log_file="${log_dir}.log"
    if [ -d "$log_dir" ]; then
        echo "SKIP $log_dir (already exists)"
        return
    fi
    echo "Launching $log_dir (pw=$pw) ..."
    nohup uv run python -m src.spillover.train_grpo \
        model_name="$model" checkpoint="$ckpt" seed="$seed" \
        log_path="$log_dir" penalty_weight="$pw" $COMMON \
        > "$log_file" 2>&1 &
    echo "  PID: $!"
}

echo "=== Launching pirate-output SFT GRPO runs (pw=-1, -2) ==="

for pw in -1 -2; do
    for seed in 42 43; do
        launch "8b-pirate-output-alpaca-qwen" "Qwen/Qwen3-8B" "$CK_8B" "$seed" "$pw"
        sleep $DELAY
        launch "32b-pirate-output-alpaca-qwen" "Qwen/Qwen3-32B" "$CK_32B" "$seed" "$pw"
        sleep $DELAY
    done
done

echo "=== All pirate-output SFT runs launched ==="
