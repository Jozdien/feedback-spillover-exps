#!/bin/bash
# thinking=300 base case: no-SFT QA, penalty vs no-penalty, 8B, 2 seeds = 4 runs.
# Matches v7base-8b config EXACTLY except max_thinking_tokens (4096 -> 300), to test
# whether a short CoT budget restores the strong baseline spillover seen in the paper
# (Qwen3-4B, thinking=300) but weak in our 32B/4096 runs.

set -a && source .env && set +a

COMMON="task=qa no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=300"
DELAY=30

launch() {
    local tag=$1 seed=$2 pw=$3
    local log_dir="logs/grpo-t300base-8b-${tag}-s${seed}"
    echo "Launching $log_dir (pw=$pw, thinking=300) ..."
    nohup uv run python -m src.spillover.train_grpo \
        model_name=Qwen/Qwen3-8B seed="$seed" \
        log_path="$log_dir" penalty_weight="$pw" $COMMON \
        > "${log_dir}.log" 2>&1 &
    echo "  PID: $!"
    sleep $DELAY
}

echo "=== Launching 4 thinking=300 base-case runs ==="
for seed in 42 43; do
    launch "pw0" "$seed" 0
    launch "pw-2" "$seed" -2
done
echo "=== Done ==="
