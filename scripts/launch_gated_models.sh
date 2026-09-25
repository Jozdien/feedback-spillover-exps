#!/bin/bash
# Gated + style-rewarded protocol (RESULTS §16d) on other base models / styles. Same recipe as
# launch_explanation_judged.sh: T=300/600, GRPO 4x3, lr 1e-5, 3200 episodes, lambda=2, GPT-4.1 hint judge,
# GPT-4.1 explanation gate, style reward weight 1 on styled arms.
# Usage: MODEL=Qwen/Qwen3.6-27B TAG=27b [PIRATE=tinker://...] [PIGLATIN=tinker://...] [CHINESE=tinker://...] \
#        [SEEDS="42 43 44 45 46"] bash scripts/launch_gated_models.sh [arms...]
# Arms: nosft-ctrl nosft-pen rt piratesr-ctrl piratesr-pen piglatinsr-ctrl piglatinsr-pen chinesesr-ctrl chinesesr-pen
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
MODEL=${MODEL:-Qwen/Qwen3-8B}; TAG=${TAG:-8b}
COMMON="task=qa group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=300 max_output_tokens=600 temperature=1.0 judge_model=gpt-4.1 judge_binary=true no_answer_penalty=0 explanation_judge=true explanation_judge_model=gpt-4.1 save_every=50 model_name=$MODEL"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name (exists)"; return; }
  setsid bash -c "exec uv run python -m src.spillover.${MOD:-train_grpo} $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
need () { [ -n "$1" ] || { echo "missing checkpoint for $2 on $MODEL; skipping"; return 1; }; }
for s in ${SEEDS:-42 43 44 45 46}; do
  for arm in "$@"; do
    case $arm in
      nosft-ctrl)    launch gated-$TAG-nosft-ctrl-s$s    penalty_weight=0  seed=$s ;;
      nosft-pen)     launch gated-$TAG-nosft-pen-s$s     penalty_weight=-2 seed=$s ;;
      rt)            launch gated-$TAG-rt-s$s            penalty_weight=-2 seed=$s reward_target=true ;;
      mf)   MOD=train_grpo_mind_face launch gated-$TAG-mf-s$s   penalty_weight=-2 seed=$s reward_target=false ;;
      tmf)  MOD=train_grpo_mind_face launch gated-$TAG-tmf-s$s  penalty_weight=-2 seed=$s reward_target=true ;;
      piratesr-ctrl) need "$PIRATE" pirate && launch gated-$TAG-piratesr-ctrl-s$s penalty_weight=0  seed=$s checkpoint=$PIRATE style_monitor=true style_desc=pirate pirate_reward_weight=1 ;;
      piratesr-pen)  need "$PIRATE" pirate && launch gated-$TAG-piratesr-pen-s$s  penalty_weight=-2 seed=$s checkpoint=$PIRATE style_monitor=true style_desc=pirate pirate_reward_weight=1 ;;
      piglatinsr-ctrl) need "$PIGLATIN" piglatin && launch gated-$TAG-piglatinsr-ctrl-s$s penalty_weight=0  seed=$s checkpoint=$PIGLATIN style_monitor=true style_desc=piglatin pirate_reward_weight=1 ;;
      piglatinsr-pen)  need "$PIGLATIN" piglatin && launch gated-$TAG-piglatinsr-pen-s$s  penalty_weight=-2 seed=$s checkpoint=$PIGLATIN style_monitor=true style_desc=piglatin pirate_reward_weight=1 ;;
      chinesesr-ctrl)  need "$CHINESE" chinese && launch gated-$TAG-chinesesr-ctrl-s$s penalty_weight=0  seed=$s checkpoint=$CHINESE style_monitor=true style_desc=chinese pirate_reward_weight=1 ;;
      chinesesr-pen)   need "$CHINESE" chinese && launch gated-$TAG-chinesesr-pen-s$s  penalty_weight=-2 seed=$s checkpoint=$CHINESE style_monitor=true style_desc=chinese pirate_reward_weight=1 ;;
    esac
  done
done
