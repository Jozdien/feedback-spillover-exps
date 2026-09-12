#!/bin/bash
# Async-RL validation: same protocol as logs/grpo-grpo300-* (T=300, GRPO 4x3, 3200 episodes, lr 1e-5,
# lambda=2, GPT-4.1 binary judge, no no-answer penalty) but async_k=4 (12 sampling workers, <=4 steps
# off-policy). Arms: no-SFT penalty/control x5 seeds, pirate-output penalty x5 seeds -> compare to the
# synchronous runs (grpo300-nosft-*, mit300-pirate-pen-*).
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
PIRATE="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
COMMON="task=qa group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=300 max_output_tokens=600 temperature=1.0 judge_model=gpt-4.1 judge_binary=true no_answer_penalty=0 save_every=50 model_name=Qwen/Qwen3-8B async_k=4"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
for s in 42 43 44 45 46; do
  launch async300-nosft-pen-8b-s$s  penalty_weight=-2 seed=$s
  launch async300-nosft-ctrl-8b-s$s penalty_weight=0  seed=$s
  launch async300-pirate-pen-8b-s$s penalty_weight=-2 seed=$s checkpoint=$PIRATE
done
