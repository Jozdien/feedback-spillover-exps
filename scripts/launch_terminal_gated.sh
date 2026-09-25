#!/bin/bash
# Terminal env, gated protocol: LLM-judge penalty (gpt-4.1-mini verifier judge on the explanations,
# lambda=0.75, as launch_terminal_llmjudge.sh) + GPT-4.1 explanation gate on every arm (task reward only
# for episodes whose per-turn explanations are genuine) + style reward (weight 1) on the style-SFT arms.
# GRPO 4x8 (32 episodes/step), lr 5e-6, T=128/256, max_turns 4, 12800 episodes = 400 steps, seeds 42-46.
# Usage: [MODEL=Qwen/Qwen3-8B] [TAG=8b] [PIRATE=tinker://...] [PIGLATIN=tinker://...] [SEEDS="42 43 44 45 46"] \
#        bash scripts/launch_terminal_gated.sh [arms...]
# Arms: ctrl pen rt mf tmf piratesr-ctrl piratesr-pen piglatinsr-ctrl piglatinsr-pen (default: all)
# Runs go to logs/grpo-termgated-<TAG>-<arm>-s<seed>.
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
MODEL=${MODEL:-Qwen/Qwen3-8B}; TAG=${TAG:-8b}
PIRATE=${PIRATE:-}; PIGLATIN=${PIGLATIN:-}
ARMS=${@:-ctrl pen rt mf tmf piratesr-ctrl piratesr-pen piglatinsr-ctrl piglatinsr-pen}
COMMON="monitor=llm judge_model=gpt-4.1-mini explanation_judge=true explanation_judge_model=gpt-4.1 group_size=4 batch_size=32 num_episodes=12800 learning_rate=5e-6 max_thinking_tokens=128 max_output_tokens=256 max_turns=4 temperature=1.0 save_every=25 model_name=$MODEL"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name (exists)"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo_terminal $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
need () { [ -n "$1" ] || { echo "missing checkpoint for $2 on $MODEL; skipping"; return 1; }; }
for s in ${SEEDS:-42 43 44 45 46}; do
  for arm in $ARMS; do
    case $arm in
      ctrl) launch termgated-$TAG-ctrl-s$s penalty_weight=0     seed=$s ;;
      pen)  launch termgated-$TAG-pen-s$s  penalty_weight=-0.75 seed=$s ;;
      rt)   launch termgated-$TAG-rt-s$s   penalty_weight=-0.75 seed=$s reward_target=true ;;
      mf)   launch termgated-$TAG-mf-s$s   penalty_weight=-0.75 seed=$s mind_face=true ;;
      tmf)  launch termgated-$TAG-tmf-s$s  penalty_weight=-0.75 seed=$s mind_face=true reward_target=true ;;
      piratesr-ctrl)   need "$PIRATE" pirate     && launch termgated-$TAG-piratesr-ctrl-s$s   penalty_weight=0     seed=$s checkpoint=$PIRATE   style_monitor=true style_desc=pirate   pirate_reward_weight=1 ;;
      piratesr-pen)    need "$PIRATE" pirate     && launch termgated-$TAG-piratesr-pen-s$s    penalty_weight=-0.75 seed=$s checkpoint=$PIRATE   style_monitor=true style_desc=pirate   pirate_reward_weight=1 ;;
      piglatinsr-ctrl) need "$PIGLATIN" piglatin && launch termgated-$TAG-piglatinsr-ctrl-s$s penalty_weight=0     seed=$s checkpoint=$PIGLATIN style_monitor=true style_desc=piglatin pirate_reward_weight=1 ;;
      piglatinsr-pen)  need "$PIGLATIN" piglatin && launch termgated-$TAG-piglatinsr-pen-s$s  penalty_weight=-0.75 seed=$s checkpoint=$PIGLATIN style_monitor=true style_desc=piglatin pirate_reward_weight=1 ;;
      *) echo "unknown arm $arm" ;;
    esac
  done
done
