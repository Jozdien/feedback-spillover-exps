#!/bin/bash
# thinking=300 mitigation suite: RT / M&F / TMF / pirate-output, 8B, pw=-2, 2 seeds = 8 runs.
# Matched to the t300 base case (thinking=300) so spillover & mitigations can be compared
# in the paper's short-CoT regime. No pw0 controls (deferred). Eval LATER with
# --max-cot-tokens 300 to match training budget.

set -a && source .env && set +a

COMMON="task=qa penalty_weight=-2 no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=300"
DELAY=30
PIRATE_SFT_8B="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"

launch() {
    local module=$1 name=$2; shift 2
    echo "Launching $name ..."
    nohup uv run python -m "$module" log_path="logs/${name}" model_name=Qwen/Qwen3-8B $COMMON "$@" \
        > "logs/${name}.log" 2>&1 &
    echo "  PID: $!"
    sleep $DELAY
}

echo "=== Launching 8 t300 mitigation runs ==="
for seed in 42 43; do
    launch src.spillover.train_grpo "grpo-t300rt-8b-pw-2-s${seed}" \
        seed=$seed reward_target=True
    launch src.spillover.train_grpo "grpo-t300pirate-8b-pw-2-s${seed}" \
        seed=$seed checkpoint="$PIRATE_SFT_8B"
    launch src.spillover.train_grpo_mind_face "grpo-t300mf-8b-pw-2-s${seed}" \
        seed=$seed reward_target=False
    launch src.spillover.train_grpo_mind_face "grpo-t300tmf-8b-pw-2-s${seed}" \
        seed=$seed reward_target=True
done
echo "=== All 8 t300 mitigation runs launched ==="
