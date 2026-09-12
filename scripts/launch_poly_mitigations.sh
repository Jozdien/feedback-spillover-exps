#!/bin/bash
# Polynomial env mitigations under the replication protocol (T=800/1000, GRPO 4x3, 3200 episodes,
# lr 1e-5, lambda=1, string-match monitor), Qwen3-8B, seeds 42-46. Baselines: logs/grpo-poly800-*.
#   pirate-pen : pirate-output SFT init (8B)   rt : reward targeting   mf / tmf : Mind & Face / targeted
# Usage: bash scripts/launch_poly_mitigations.sh [arms...]
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
PIRATE="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
COMMON="task=poly group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=800 max_output_tokens=1000 temperature=1.0 no_answer_penalty=0 save_every=50 model_name=Qwen/Qwen3-8B"
ARMS=${@:-pirate-pen pirate-ctrl rt mf tmf}
launch () { local mod=$1 name=$2; shift 2; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.$mod $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
for s in 42 43 44 45 46; do
  for arm in $ARMS; do case $arm in
    pirate-pen)  launch train_grpo polymit800-pirate-pen-8b-s$s  penalty_weight=-1 seed=$s checkpoint=$PIRATE ;;
    pirate-ctrl) launch train_grpo polymit800-pirate-ctrl-8b-s$s penalty_weight=0  seed=$s checkpoint=$PIRATE ;;
    rt)          launch train_grpo polymit800-rt-8b-s$s          penalty_weight=-1 seed=$s reward_target=true ;;
    mf)          launch train_grpo_mind_face polymit800-mf-8b-s$s  penalty_weight=-1 seed=$s reward_target=false ;;
    tmf)         launch train_grpo_mind_face polymit800-tmf-8b-s$s penalty_weight=-1 seed=$s reward_target=true ;;
  esac; done
done
