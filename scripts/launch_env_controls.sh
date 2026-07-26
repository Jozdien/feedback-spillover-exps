#!/bin/bash
# λ=0 no-penalty CONTROLS for the spillover-showing envs, to prove the CoT drop is
# penalty-driven (not training drift). Same config as the penalty pilots but
# penalty_weight=0 and no no_answer_penalty (nothing to evade). If the CoT stays
# high here while it collapsed under the penalty, spillover is confirmed.
# Usage: bash scripts/launch_env_controls.sh
set -a && source .env && set +a
DELAY=30
launch() { local log_dir=$1; shift; echo "Launching $log_dir ..."
  nohup uv run python -m src.spillover.train_grpo log_path="$log_dir" seed=42 \
    penalty_weight=0 num_episodes=12000 save_every=100 max_thinking_tokens=4096 "$@" \
    > "${log_dir}.log" 2>&1 & echo "  PID: $!"; sleep "$DELAY"; }
M8B="Qwen/Qwen3-8B"; M35B="Qwen/Qwen3.6-35B-A3B"
# Priority: the clean spillover envs on 8B (cheapest), then 35B.
launch logs/grpo-env2math-ctrl-8b-s42    task=math    model_name=$M8B  max_output_tokens=1000
launch logs/grpo-env4gpqa-ctrl-8b-s42    task=qa_hard model_name=$M8B
launch logs/grpo-env1enc-ctrl-35ba3b-s42 task=qa_encoded model_name=$M35B
launch logs/grpo-env4gpqa-ctrl-35ba3b-s42 task=qa_hard  model_name=$M35B
