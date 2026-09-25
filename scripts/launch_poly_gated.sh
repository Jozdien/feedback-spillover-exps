#!/bin/bash
# Polynomial env with the new rewards (2026-09-26): explanation gate (GPT-4.1) on every arm + style reward
# on styled arms. Paper budgets T=800/1000, lambda=1, GRPO 4x3, 3200 episodes, fixed checker. Default model
# Qwen3.6-27B (the only current model with poly spillover: RESULTS §14c/14e). 3 seeds.
# Usage: MODEL=Qwen/Qwen3.6-27B TAG=poly27b [PIRATE=...] [PIGLATIN=...] [SEEDS="42 43 44"] bash scripts/launch_poly_gated.sh [arms...]
# Arms: ctrl pen rt piratesr-ctrl piratesr-pen piglatinsr-ctrl piglatinsr-pen
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
MODEL=${MODEL:-Qwen/Qwen3.6-27B}; TAG=${TAG:-poly27b}
COMMON="task=poly group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=800 max_output_tokens=1000 temperature=1.0 no_answer_penalty=0 explanation_judge=true explanation_judge_model=gpt-4.1 judge_model=gpt-4.1 save_every=50 model_name=$MODEL"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name (exists)"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
need () { [ -n "$1" ] || { echo "missing checkpoint for $2; skipping"; return 1; }; }
for s in ${SEEDS:-42 43 44}; do
  for arm in "$@"; do
    case $arm in
      ctrl) launch gated-$TAG-ctrl-s$s penalty_weight=0  seed=$s ;;
      pen)  launch gated-$TAG-pen-s$s  penalty_weight=-1 seed=$s ;;
      rt)   launch gated-$TAG-rt-s$s   penalty_weight=-1 seed=$s reward_target=true ;;
      piratesr-ctrl) need "$PIRATE" pirate && launch gated-$TAG-piratesr-ctrl-s$s penalty_weight=0  seed=$s checkpoint=$PIRATE style_monitor=true style_desc=pirate pirate_reward_weight=1 ;;
      piratesr-pen)  need "$PIRATE" pirate && launch gated-$TAG-piratesr-pen-s$s  penalty_weight=-1 seed=$s checkpoint=$PIRATE style_monitor=true style_desc=pirate pirate_reward_weight=1 ;;
      piglatinsr-ctrl) need "$PIGLATIN" piglatin && launch gated-$TAG-piglatinsr-ctrl-s$s penalty_weight=0  seed=$s checkpoint=$PIGLATIN style_monitor=true style_desc=piglatin pirate_reward_weight=1 ;;
      piglatinsr-pen)  need "$PIGLATIN" piglatin && launch gated-$TAG-piglatinsr-pen-s$s  penalty_weight=-1 seed=$s checkpoint=$PIGLATIN style_monitor=true style_desc=piglatin pirate_reward_weight=1 ;;
    esac
  done
done
