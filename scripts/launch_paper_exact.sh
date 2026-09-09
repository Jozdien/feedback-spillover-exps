#!/bin/bash
# Re-runs of the QA env with the ORIGINAL paper's setup (Drori et al. 2511.11584, App. C.2):
#   REINFORCE with per-batch mean baseline (1 rollout/prompt), batch 12, lr 1e-5, 3200 episodes
#   (267 steps), lambda=2, thinking 300 / output 600 tokens, temperature 1, judge = GPT-4.1 binary
#   with their exact prompt, no no-answer penalty. Unavoidable deviations: Qwen3-8B (their
#   Qwen3-4B is retired on Tinker), LoRA rank 32 (Tinker), importance-sampling loss.
# Usage: bash scripts/launch_paper_exact.sh   (runs detached; logs/grpo-exact-*)
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
PIRATE="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"   # paper's 8B pirate-output SFT
COMMON="task=qa advantage_mode=reinforce group_size=1 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=300 max_output_tokens=600 temperature=1.0 judge_model=gpt-4.1 judge_binary=true no_answer_penalty=0 save_every=50 model_name=Qwen/Qwen3-8B"
launch () {  # name, extra args
  local name=$1; shift
  [ -d logs/grpo-$name ] && { echo "skip $name (exists)"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null &
  echo "launched $name"
}
for s in 42 43 44; do
  launch exact-nosft-pen-8b-s$s  penalty_weight=-2 seed=$s
  launch exact-nosft-ctrl-8b-s$s penalty_weight=0  seed=$s
done
for s in 42 43; do
  launch exact-pirate-pen-8b-s$s  penalty_weight=-2 seed=$s checkpoint=$PIRATE
  launch exact-pirate-ctrl-8b-s$s penalty_weight=0  seed=$s checkpoint=$PIRATE
done
