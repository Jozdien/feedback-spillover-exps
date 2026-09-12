#!/bin/bash
# Terminal env mitigations under the replication protocol (regex penalty lambda=1.25, effective batch 32,
# lr 5e-6, 3200 episodes, T=128/256, Qwen3-8B). rt = reward targeting; pirate-pen/ctrl = pirate-output SFT
# init. (Mind & Face is not implemented for the multi-turn trainer.) Baselines: logs/grpo-term-regex-*.
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
PIRATE="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
COMMON="monitor=regex group_size=4 batch_size=32 num_episodes=3200 learning_rate=5e-6 max_thinking_tokens=128 max_output_tokens=256 max_turns=4 temperature=1.0 save_every=25 model_name=Qwen/Qwen3-8B"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo_terminal $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
for s in 42 43 44 45 46; do
  launch termmit-rt-8b-s$s          penalty_weight=-1.25 seed=$s reward_target=true
  launch termmit-pirate-pen-8b-s$s  penalty_weight=-1.25 seed=$s checkpoint=$PIRATE
  launch termmit-pirate-ctrl-8b-s$s penalty_weight=0     seed=$s checkpoint=$PIRATE
done
