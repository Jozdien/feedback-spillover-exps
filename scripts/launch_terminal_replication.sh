#!/bin/bash
# Multi-turn terminal env, Drori et al. App. C.3.1 regex-penalty setup adapted to GRPO: effective batch
# 32 (group 4 x 8 problems), lr 5e-6, 3200 episodes (100 steps), lambda=1.25 on the "ground truth"
# regex count, thinking 128 / output 256, Qwen3-8B, max 4 turns. penalty x5 seeds, control x5 seeds.
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
COMMON="monitor=regex group_size=4 batch_size=32 num_episodes=3200 learning_rate=5e-6 max_thinking_tokens=128 max_output_tokens=256 max_turns=4 temperature=1.0 save_every=25 model_name=Qwen/Qwen3-8B"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo_terminal $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
for s in 42 43 44 45 46; do
  launch term-regex-pen-8b-s$s  penalty_weight=-1.25 seed=$s
  launch term-regex-ctrl-8b-s$s penalty_weight=0     seed=$s
done
