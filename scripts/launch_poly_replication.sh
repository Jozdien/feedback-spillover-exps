#!/bin/bash
# Polynomial derivative factoring, Drori et al. App. C.1 setup adapted to GRPO: thinking 800 / output
# 1000 tokens, lr 1e-5, lambda=1 (string-match expanded-form monitor, no LLM judge), 3200 episodes
# (267 steps of 12 rollouts; theirs: 1600 episodes of 3x2). Qwen3-8B (their Qwen3-14B is not on
# Tinker). penalty x5 seeds, control x5 seeds.
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
COMMON="task=poly group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=800 max_output_tokens=1000 temperature=1.0 no_answer_penalty=0 save_every=50 model_name=Qwen/Qwen3-8B"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
for s in 42 43 44 45 46; do
  launch poly800-pen-8b-s$s  penalty_weight=-1 seed=$s
  launch poly800-ctrl-8b-s$s penalty_weight=0  seed=$s
done
