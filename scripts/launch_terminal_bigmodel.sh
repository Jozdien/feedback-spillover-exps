#!/bin/bash
# Terminal env (LLM-judge penalty, Drori Fig 7 setting) on a larger model. Same protocol as the extended
# termllm 8B runs (gpt-4.1-mini judge, lambda=0.75, GRPO 4x8, lr 5e-6, T=128/256, max_turns 4, 12800
# episodes = 400 steps). Arms: control, penalty, reward targeting; 3 seeds.
# The trainer hand-builds the multi-turn sequence with Qwen3 structural tokens, so only models whose chat
# template passes the token-bookkeeping check (run `dry_run=true` first) are valid: Nemotron-3-Super-120B
# FAILED it on every episode (2026-09-13; runs discarded to logs/_invalid). Default model: Qwen3.6-27B.
# Usage: MODEL=Qwen/Qwen3.6-27B TAG=27b bash scripts/launch_terminal_bigmodel.sh [ctrl|pen|rt ...]
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
MODEL=${MODEL:-Qwen/Qwen3.6-27B}
TAG=${TAG:-27b}
COMMON="monitor=llm judge_model=gpt-4.1-mini group_size=4 batch_size=32 num_episodes=12800 learning_rate=5e-6 max_thinking_tokens=128 max_output_tokens=256 max_turns=4 temperature=1.0 save_every=25 model_name=$MODEL"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo_terminal $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
for s in 42 43 44; do
  for arm in ${@:-ctrl pen rt}; do
    case $arm in
      ctrl) launch termllm-$TAG-ctrl-s$s penalty_weight=0     seed=$s ;;
      pen)  launch termllm-$TAG-pen-s$s  penalty_weight=-0.75 seed=$s ;;
      rt)   launch termllm-$TAG-rt-s$s   penalty_weight=-0.75 seed=$s reward_target=true ;;
    esac
  done
done
