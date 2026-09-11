#!/bin/bash
# Mitigation arms under the paper-exact protocol (T=300/600, GRPO 4x3, lr 1e-5, 3200 episodes, lambda=2,
# GPT-4.1 binary judge, no no-answer penalty), Qwen3-8B, seeds 42-46. Baselines: logs/grpo-grpo300-nosft-*.
#   pirate-pen / pirate-ctrl : pirate-output SFT init (train_grpo)
#   rt                       : reward targeting (train_grpo reward_target=true)
#   mf / tmf                 : Mind & Face / targeted M&F (train_grpo_mind_face, reward_target=false/true)
# Usage: bash scripts/launch_mitigations_t300.sh [arms...]   (default: all five)
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
PIRATE="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
COMMON="task=qa group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=300 max_output_tokens=600 temperature=1.0 judge_model=gpt-4.1 judge_binary=true no_answer_penalty=0 save_every=50 model_name=Qwen/Qwen3-8B"
ARMS=${@:-pirate-pen pirate-ctrl rt mf tmf}
launch () {  # module, name, extra args
  local mod=$1 name=$2; shift 2
  [ -d logs/grpo-$name ] && { echo "skip $name (exists)"; return; }
  setsid bash -c "exec uv run python -m src.spillover.$mod $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null &
  echo "launched $name"
}
for s in 42 43 44 45 46; do
  for arm in $ARMS; do
    case $arm in
      pirate-pen)  launch train_grpo mit300-pirate-pen-8b-s$s  penalty_weight=-2 seed=$s checkpoint=$PIRATE ;;
      pirate-ctrl) launch train_grpo mit300-pirate-ctrl-8b-s$s penalty_weight=0  seed=$s checkpoint=$PIRATE ;;
      rt)          launch train_grpo mit300-rt-8b-s$s          penalty_weight=-2 seed=$s reward_target=true ;;
      mf)          launch train_grpo_mind_face mit300-mf-8b-s$s  penalty_weight=-2 seed=$s reward_target=false ;;
      tmf)         launch train_grpo_mind_face mit300-tmf-8b-s$s penalty_weight=-2 seed=$s reward_target=true ;;
    esac
  done
done
