#!/bin/bash
# Pirate-reward sweep: penalty RL from the existing 8B pirate-output SFT final,
# plus a reward mu*is_pirate(output). mu in {0.5,1,2} x 2 seeds = 6 runs (8B only).

set -a && source .env && set +a
PIRATE_SFT_8B="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
COMMON="task=qa penalty_weight=-2 no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"
DELAY=25

echo "=== Launching 6 pirate-reward runs ==="
for mu in 0.5 1 2; do
    for seed in 42 43; do
        name="grpo-piratereward-mu${mu}-8b-pw-2-s${seed}"
        echo "Launching $name ..."
        nohup uv run python -m src.spillover.train_grpo \
            model_name=Qwen/Qwen3-8B seed=$seed checkpoint="$PIRATE_SFT_8B" \
            pirate_reward_weight=$mu log_path="logs/${name}" $COMMON \
            > "logs/${name}.log" 2>&1 &
        echo "  PID: $!"
        sleep $DELAY
    done
done
echo "=== All 6 pirate-reward runs launched ==="
