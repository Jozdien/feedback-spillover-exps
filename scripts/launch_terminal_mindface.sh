#!/bin/bash
# Terminal env, LLM-judge penalty (as launch_terminal_llmjudge.sh: gpt-4.1-mini judge on the explanations,
# lambda=0.75, GRPO 4x8, lr 5e-6, T=128/256, max_turns 4, Qwen3-8B, seeds 42-46) with the Mind & Face
# mitigations of Drori et al.; 12800 episodes = 400 steps like the extended termllm runs.
#   mf  : Mind & Face (mind_face=true): mind CoT and face output both get task + penalty
#   tmf : targeted Mind & Face (mind_face=true reward_target=true): mind gets the task reward only
# Baselines: logs/grpo-termllm-{pen,ctrl,rt}-8b-s*. Needs OpenAI credits.
# Usage: bash scripts/launch_terminal_mindface.sh [mf] [tmf]   (default: both; existing run dirs are skipped)
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
COMMON="monitor=llm judge_model=gpt-4.1-mini group_size=4 batch_size=32 num_episodes=12800 learning_rate=5e-6 max_thinking_tokens=128 max_output_tokens=256 max_turns=4 temperature=1.0 save_every=25 model_name=Qwen/Qwen3-8B"
ARMS=${@:-mf tmf}
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo_terminal $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
for s in 42 43 44 45 46; do
  for arm in $ARMS; do case $arm in
    mf)  launch termllm-mf-8b-s$s  penalty_weight=-0.75 seed=$s mind_face=true reward_target=false ;;
    tmf) launch termllm-tmf-8b-s$s penalty_weight=-0.75 seed=$s mind_face=true reward_target=true ;;
    *)   echo "unknown arm: $arm (mf|tmf)"; exit 1 ;;
  esac; done
done
