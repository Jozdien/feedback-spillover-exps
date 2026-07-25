#!/bin/bash
# Penalty-only pilot runs for the five candidate environments (2026-07-25).
# One run per (env, model): lambda=2, seed 42, T=4096, 1000 batches.
# Usage: bash scripts/launch_env_pilots.sh <env1|env2|env4|env3|env5> [8b|35b|both]

set -a && source .env && set +a
DELAY=30

launch() {
    local log_dir=$1; shift
    echo "Launching $log_dir ..."
    mkdir -p "$(dirname "$log_dir")"
    nohup uv run python -m src.spillover.train_grpo \
        log_path="$log_dir" seed=42 penalty_weight=-2 \
        num_episodes=12000 save_every=100 max_thinking_tokens=4096 \
        "$@" > "${log_dir}.log" 2>&1 &
    echo "  PID: $!"
    sleep "$DELAY"
}

M8B="Qwen/Qwen3-8B"
M35B="Qwen/Qwen3.6-35B-A3B"
WHICH=${2:-both}

case "$1" in
  env1)  # encoded hints on MMLU elementary math
    [[ $WHICH != 35b ]] && launch logs/grpo-env1enc-8b-pw2-s42 \
        task=qa_encoded model_name=$M8B no_answer_penalty=-1.0
    [[ $WHICH != 8b ]] && launch logs/grpo-env1enc-35ba3b-pw2-s42 \
        task=qa_encoded model_name=$M35B no_answer_penalty=-1.0
    ;;
  env4)  # uplift-filtered GPQA with plain hints (needs data/gpqa_uplift_pool.json)
    [[ -f data/gpqa_uplift_pool.json ]] || { echo "missing gpqa pool"; exit 1; }
    [[ $WHICH != 35b ]] && launch logs/grpo-env4gpqa-8b-pw2-s42 \
        task=qa_hard model_name=$M8B no_answer_penalty=-1.0
    [[ $WHICH != 8b ]] && launch logs/grpo-env4gpqa-35ba3b-pw2-s42 \
        task=qa_hard model_name=$M35B no_answer_penalty=-1.0
    ;;
  env2)  # hard math + sub-step leak hints (needs data/math_hint_pool.json)
    [[ -f data/math_hint_pool.json ]] || { echo "missing math pool"; exit 1; }
    [[ $WHICH != 35b ]] && launch logs/grpo-env2math-8b-pw2-s42 \
        task=math model_name=$M8B no_answer_penalty=-1.0 max_output_tokens=1000
    [[ $WHICH != 8b ]] && launch logs/grpo-env2math-35ba3b-pw2-s42 \
        task=math model_name=$M35B no_answer_penalty=-1.0 max_output_tokens=1000
    ;;
  env3)  # Impossible-LiveCodeBench test-passing
    [[ $WHICH != 35b ]] && launch logs/grpo-env3lcb-8b-pw2-s42 \
        task=lcb model_name=$M8B no_answer_penalty=-1.0 max_output_tokens=1500
    [[ $WHICH != 8b ]] && launch logs/grpo-env3lcb-35ba3b-pw2-s42 \
        task=lcb model_name=$M35B no_answer_penalty=-1.0 max_output_tokens=1500
    ;;
  *)
    echo "usage: $0 <env1|env2|env3|env4> [8b|35b|both]"; exit 1
    ;;
esac
