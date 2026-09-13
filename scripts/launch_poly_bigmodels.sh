#!/bin/bash
# Polynomial env on larger models (2026-09-13), to extend the size-dependence result (8B none, 27B partial,
# 32B strong): NVIDIA Nemotron-3-Super-120B-A12B (used in the paper's cross-family appendix) and
# Qwen3.5-397B-A17B (largest Qwen on Tinker). Paper budgets T=800/1000, lambda=1, GRPO 4x3, 3200 episodes,
# fixed reward, 3 seeds. Usage: bash scripts/launch_poly_bigmodels.sh [nemotron|qwen397 ...]
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
COMMON="task=poly group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=800 max_output_tokens=1000 temperature=1.0 no_answer_penalty=0 save_every=50"
declare -A MODEL
MODEL[nemotron]="nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16"
MODEL[qwen397]="Qwen/Qwen3.5-397B-A17B"
for m in ${@:-nemotron qwen397}; do
  for s in 42 43 44; do
    launch poly800-$m-pen-s$s  $COMMON model_name=${MODEL[$m]} penalty_weight=-1 seed=$s
    launch poly800-$m-ctrl-s$s $COMMON model_name=${MODEL[$m]} penalty_weight=0  seed=$s
  done
done
