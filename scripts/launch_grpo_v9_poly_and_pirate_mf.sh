#!/bin/bash
# V9 extension: polynomial env 32B suite (500 batches) + pirate M&F/TMF on QA
# Poly: ctrl/pen/rt/mf/tmf/pirate/piratectrl x 2 seeds = 14 runs (32B)
# QA: mfpirate/tmfpirate x {8b,32b} x 2 seeds = 8 runs

set -a && source .env && set +a

POLY_COMMON="task=poly num_episodes=6000 save_every=100 max_thinking_tokens=4096 max_output_tokens=1000"
QA_COMMON="task=qa penalty_weight=-2 no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"
DELAY=20

PIRATE_SFT_8B="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
PIRATE_SFT_32B="tinker://707d82b5-211a-5014-b528-77713c6c1dbb:train:0/weights/final"
M32="model_name=Qwen/Qwen3-32B"

launch() {
    local module=$1 name=$2; shift 2
    echo "Launching $name ..."
    nohup uv run python -m "$module" log_path="logs/${name}" "$@" \
        > "logs/${name}.log" 2>&1 &
    echo "  PID: $!"
    sleep $DELAY
}

echo "=== Poly 32B suite (deadline-bound) ==="
for seed in 42 43; do
    launch src.spillover.train_grpo "grpo-v9poly-ctrl-32b-pw0-s${seed}" \
        $M32 seed=$seed penalty_weight=0 $POLY_COMMON
    launch src.spillover.train_grpo "grpo-v9poly-pen-32b-pw-2-s${seed}" \
        $M32 seed=$seed penalty_weight=-2 $POLY_COMMON
    launch src.spillover.train_grpo "grpo-v9poly-rt-32b-pw-2-s${seed}" \
        $M32 seed=$seed penalty_weight=-2 reward_target=True $POLY_COMMON
    launch src.spillover.train_grpo_mind_face "grpo-v9poly-mf-32b-pw-2-s${seed}" \
        $M32 seed=$seed penalty_weight=-2 reward_target=False $POLY_COMMON
    launch src.spillover.train_grpo_mind_face "grpo-v9poly-tmf-32b-pw-2-s${seed}" \
        $M32 seed=$seed penalty_weight=-2 reward_target=True $POLY_COMMON
    launch src.spillover.train_grpo "grpo-v9poly-pirate-32b-pw-2-s${seed}" \
        $M32 seed=$seed penalty_weight=-2 checkpoint="$PIRATE_SFT_32B" $POLY_COMMON
    launch src.spillover.train_grpo "grpo-v9poly-piratectrl-32b-pw0-s${seed}" \
        $M32 seed=$seed penalty_weight=0 checkpoint="$PIRATE_SFT_32B" $POLY_COMMON
done

echo "=== Pirate M&F / TMF on QA ==="
for seed in 42 43; do
    launch src.spillover.train_grpo_mind_face "grpo-v9mfpirate-32b-pw-2-s${seed}" \
        $M32 seed=$seed reward_target=False checkpoint="$PIRATE_SFT_32B" $QA_COMMON
    launch src.spillover.train_grpo_mind_face "grpo-v9tmfpirate-32b-pw-2-s${seed}" \
        $M32 seed=$seed reward_target=True checkpoint="$PIRATE_SFT_32B" $QA_COMMON
    launch src.spillover.train_grpo_mind_face "grpo-v9mfpirate-8b-pw-2-s${seed}" \
        model_name=Qwen/Qwen3-8B seed=$seed reward_target=False checkpoint="$PIRATE_SFT_8B" $QA_COMMON
    launch src.spillover.train_grpo_mind_face "grpo-v9tmfpirate-8b-pw-2-s${seed}" \
        model_name=Qwen/Qwen3-8B seed=$seed reward_target=True checkpoint="$PIRATE_SFT_8B" $QA_COMMON
done

echo "=== All 22 runs launched ==="
