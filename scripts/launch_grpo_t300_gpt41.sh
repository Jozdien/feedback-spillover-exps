#!/bin/bash
# GRPO counterpart of scripts/launch_paper_exact.sh: same environment, episode budget (3200), lr,
# T=300/600, lambda=2, GPT-4.1 binary judge, no no-answer penalty — but GRPO advantages
# (group_size 4 x 3 prompts = 12 rollouts/step, 267 steps). 10 seeds x {penalty, control}.
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
COMMON="task=qa advantage_mode=grpo group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=300 max_output_tokens=600 temperature=1.0 judge_model=gpt-4.1 judge_binary=true no_answer_penalty=0 save_every=50 model_name=Qwen/Qwen3-8B"
launch () {
  local name=$1; shift
  [ -d logs/grpo-$name ] && { echo "skip $name (exists)"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null &
  echo "launched $name"
}
for s in 42 43 44 45 46 47 48 49 50 51; do
  launch grpo300-nosft-pen-8b-s$s  penalty_weight=-2 seed=$s
  launch grpo300-nosft-ctrl-8b-s$s penalty_weight=0  seed=$s
done
