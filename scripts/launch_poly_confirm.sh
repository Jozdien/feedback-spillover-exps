#!/bin/bash
# Fresh polynomial confirmation (2026-09-12): (a) Qwen3.6-27B (dense, closest current model to the
# retired Qwen3-32B) at the paper's budgets T=800/1000, lambda=1, GRPO 4x3, 3200 episodes, fixed reward;
# (b) Qwen3-8B at T=4096/1000 (the budget of the 32B runs) to separate size from budget. 3 seeds each.
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
C27="task=poly group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=800 max_output_tokens=1000 temperature=1.0 no_answer_penalty=0 save_every=50 model_name=Qwen/Qwen3.6-27B"
C8="task=poly group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=4096 max_output_tokens=1000 temperature=1.0 no_answer_penalty=0 save_every=50 model_name=Qwen/Qwen3-8B"
for s in 42 43 44; do
  launch poly800-27b-pen-s$s  $C27 penalty_weight=-1 seed=$s
  launch poly800-27b-ctrl-s$s $C27 penalty_weight=0  seed=$s
  launch poly4096-8b-pen-s$s  $C8 penalty_weight=-1 seed=$s
  launch poly4096-8b-ctrl-s$s $C8 penalty_weight=0  seed=$s
done
