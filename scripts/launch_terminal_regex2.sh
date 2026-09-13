#!/bin/bash
# Terminal env, regex penalty, CORRECTED monitor (2026-09-13): the paper's monitor counts the string
# "ground truth"; the verifier spells it GROUND_TRUTH and the model mostly writes that form, so the
# literal-space pattern used in term-regex/termmit missed most mentions and the penalized model simply
# switched to the underscore form. Pattern here: ground[ _]*truth (case-insensitive), indicator
# (regex_cap=1; the paper's No-Penalty output penalty of exactly 1.25±0.00 implies saturation).
# Paper Table 5: batch 32, lr 5e-6, 3200 episodes, lambda=1.25, T=128/256. Arms: control, penalty,
# reward targeting, Mind & Face, targeted M&F (5 seeds). Usage: bash scripts/launch_terminal_regex2.sh [arms]
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
COMMON="monitor=regex regex_pattern=ground[_\ ]*truth regex_cap=1 group_size=4 batch_size=32 num_episodes=3200 learning_rate=5e-6 max_thinking_tokens=128 max_output_tokens=256 max_turns=4 temperature=1.0 save_every=25 model_name=Qwen/Qwen3-8B"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo_terminal $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
for s in 42 43 44 45 46; do
  for arm in ${@:-ctrl pen rt mf tmf}; do
    case $arm in
      ctrl) launch term-regex2-ctrl-8b-s$s penalty_weight=0     seed=$s ;;
      pen)  launch term-regex2-pen-8b-s$s  penalty_weight=-1.25 seed=$s ;;
      rt)   launch term-regex2-rt-8b-s$s   penalty_weight=-1.25 seed=$s reward_target=true ;;
      mf)   launch term-regex2-mf-8b-s$s   penalty_weight=-1.25 seed=$s mind_face=true ;;
      tmf)  launch term-regex2-tmf-8b-s$s  penalty_weight=-1.25 seed=$s mind_face=true reward_target=true ;;
    esac
  done
done
