#!/bin/bash
# Explanation-required reruns (RESULTS §16 follow-up): identical to the T=300 protocol of
# grpo300 / mit300 / style300 (GRPO 4x3, lr 1e-5, 3200 episodes, lambda=2, GPT-4.1 binary judge,
# no no-answer penalty) plus min_explanation_words=20: an output whose "### Explanation" section
# has <20 words gets task reward 0 instead of 1, so a bare \boxed{X} can no longer collect the task
# reward. Arms = every arm whose outputs degenerated under the output penalty (pirate / Chinese /
# Pig-Latin SFT penalty, targeted Mind & Face, no-SFT penalty) plus the controls needed to read them.
# RT and plain M&F keep real explanations (>99% >=10 words) and are NOT rerun. Seeds 42-46, sync.
# Usage: bash scripts/launch_explanation_required.sh [arms...]
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
PIRATE="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
CHINESE="tinker://8defc206-fb5c-5855-8b90-79051204da20:train:0/weights/final"
PIGLATIN="tinker://a0ed9ddb-9a6d-515c-b0e9-3f4ebab4e44e:train:0/weights/final"
COMMON="task=qa group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=300 max_output_tokens=600 temperature=1.0 judge_model=gpt-4.1 judge_binary=true no_answer_penalty=0 min_explanation_words=20 save_every=50 model_name=Qwen/Qwen3-8B"
ARMS=${@:-nosft-pen pirate-pen pirate-ctrl tmf chinese-pen chinese-ctrl piglatin-pen}
launch () {  # module, name, extra args
  local mod=$1 name=$2; shift 2
  [ -d logs/grpo-$name ] && { echo "skip $name (exists)"; return; }
  setsid bash -c "exec uv run python -m src.spillover.$mod $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null &
  echo "launched $name"
}
for s in 42 43 44 45 46; do
  for arm in $ARMS; do
    case $arm in
      nosft-pen)    launch train_grpo expl300-nosft-pen-8b-s$s     penalty_weight=-2 seed=$s ;;
      pirate-pen)   launch train_grpo expl300-pirate-pen-8b-s$s    penalty_weight=-2 seed=$s checkpoint=$PIRATE ;;
      pirate-ctrl)  launch train_grpo expl300-pirate-ctrl-8b-s$s   penalty_weight=0  seed=$s checkpoint=$PIRATE ;;
      tmf)          launch train_grpo_mind_face expl300-tmf-8b-s$s penalty_weight=-2 seed=$s reward_target=true ;;
      chinese-pen)  launch train_grpo expl300-chinese-pen-8b-s$s   penalty_weight=-2 seed=$s checkpoint=$CHINESE  style_monitor=true style_desc=chinese ;;
      chinese-ctrl) launch train_grpo expl300-chinese-ctrl-8b-s$s  penalty_weight=0  seed=$s checkpoint=$CHINESE  style_monitor=true style_desc=chinese ;;
      piglatin-pen) launch train_grpo expl300-piglatin-pen-8b-s$s  penalty_weight=-2 seed=$s checkpoint=$PIGLATIN style_monitor=true style_desc=piglatin ;;
    esac
  done
done
