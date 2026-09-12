#!/bin/bash
# Style ablations: same protocol as mit300-pirate-* (T=300, GRPO 4x3, 3200 episodes, lr 1e-5, lambda=2,
# GPT-4.1 binary judge, no no-answer penalty), but the style-SFT init is Chinese-output or
# Pig-Latin-output instead of pirate-output. Style monitors (output + CoT) logged. Seeds 42-46.
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
declare -A CKPT
CKPT[chinese]="tinker://8defc206-fb5c-5855-8b90-79051204da20:train:0/weights/final"
CKPT[piglatin]="tinker://a0ed9ddb-9a6d-515c-b0e9-3f4ebab4e44e:train:0/weights/final"
COMMON="task=qa group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=300 max_output_tokens=600 temperature=1.0 judge_model=gpt-4.1 judge_binary=true no_answer_penalty=0 save_every=50 model_name=Qwen/Qwen3-8B style_monitor=true"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
for style in ${@:-chinese piglatin}; do
  for s in 42 43 44 45 46; do
    launch style300-$style-pen-8b-s$s  penalty_weight=-2 seed=$s checkpoint=${CKPT[$style]} style_desc=$style
    launch style300-$style-ctrl-8b-s$s penalty_weight=0  seed=$s checkpoint=${CKPT[$style]} style_desc=$style
  done
done
