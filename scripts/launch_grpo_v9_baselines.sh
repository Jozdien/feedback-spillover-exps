#!/bin/bash
# V9: matched-config mitigation baselines at pw=-2, thinking=4096
# RT / MF / TMF (no SFT) + RT-on-pirate-output, both sizes, seeds 42/43 = 16 runs

set -a && source .env && set +a

COMMON="task=qa penalty_weight=-2 no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"
DELAY=30

PIRATE_SFT_8B="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
PIRATE_SFT_32B="tinker://707d82b5-211a-5014-b528-77713c6c1dbb:train:0/weights/final"

launch() {
    local module=$1 name=$2; shift 2
    local log_dir="logs/${name}"
    echo "Launching $name ..."
    nohup uv run python -m "$module" log_path="$log_dir" $COMMON "$@" \
        > "${log_dir}.log" 2>&1 &
    echo "  PID: $!"
    sleep $DELAY
}

echo "=== Launching 16 v9 baseline runs (32B first for deprecation deadline) ==="

for seed in 42 43; do
    # 32B first
    launch src.spillover.train_grpo "grpo-v9rt-32b-pw-2-s${seed}" \
        model_name=Qwen/Qwen3-32B seed=$seed reward_target=True
    launch src.spillover.train_grpo "grpo-v9rtpirate-32b-pw-2-s${seed}" \
        model_name=Qwen/Qwen3-32B seed=$seed reward_target=True checkpoint="$PIRATE_SFT_32B"
    launch src.spillover.train_grpo_mind_face "grpo-v9mf-32b-pw-2-s${seed}" \
        model_name=Qwen/Qwen3-32B seed=$seed reward_target=False
    launch src.spillover.train_grpo_mind_face "grpo-v9tmf-32b-pw-2-s${seed}" \
        model_name=Qwen/Qwen3-32B seed=$seed reward_target=True
done

for seed in 42 43; do
    launch src.spillover.train_grpo "grpo-v9rt-8b-pw-2-s${seed}" \
        model_name=Qwen/Qwen3-8B seed=$seed reward_target=True
    launch src.spillover.train_grpo "grpo-v9rtpirate-8b-pw-2-s${seed}" \
        model_name=Qwen/Qwen3-8B seed=$seed reward_target=True checkpoint="$PIRATE_SFT_8B"
    launch src.spillover.train_grpo_mind_face "grpo-v9mf-8b-pw-2-s${seed}" \
        model_name=Qwen/Qwen3-8B seed=$seed reward_target=False
    launch src.spillover.train_grpo_mind_face "grpo-v9tmf-8b-pw-2-s${seed}" \
        model_name=Qwen/Qwen3-8B seed=$seed reward_target=True
done

echo "=== All 16 v9 baseline runs launched ==="
