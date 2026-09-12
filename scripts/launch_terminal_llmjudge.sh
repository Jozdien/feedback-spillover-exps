#!/bin/bash
# Terminal env with the LLM-judge penalty (Drori et al. App. C.3.2: gpt-4.1-mini judge on explanations,
# lambda=0.75; their lr 1e-6 / 40k episodes adapted to GRPO lr 5e-6 / 3200 episodes like the regex runs).
# Arms: penalty, control, reward targeting, pirate-output init (+ pirate control). Needs OpenAI credits.
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
PIRATE="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
COMMON="monitor=llm judge_model=gpt-4.1-mini group_size=4 batch_size=32 num_episodes=3200 learning_rate=5e-6 max_thinking_tokens=128 max_output_tokens=256 max_turns=4 temperature=1.0 save_every=25 model_name=Qwen/Qwen3-8B"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo_terminal $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
for s in 42 43 44 45 46; do
  launch termllm-pen-8b-s$s         penalty_weight=-0.75 seed=$s
  launch termllm-ctrl-8b-s$s        penalty_weight=0     seed=$s
  launch termllm-rt-8b-s$s          penalty_weight=-0.75 seed=$s reward_target=true
  launch termllm-pirate-pen-8b-s$s  penalty_weight=-0.75 seed=$s checkpoint=$PIRATE
done
