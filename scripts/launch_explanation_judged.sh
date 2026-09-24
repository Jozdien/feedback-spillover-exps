#!/bin/bash
# Explanation-JUDGED reruns (RESULTS §16b follow-up, 2026-09-24): §12b protocol (T=300/600, GRPO 4x3,
# lr 1e-5, 3200 episodes, lambda=2, GPT-4.1 binary hint judge, no no-answer penalty) plus a semantic gate:
# a GPT-4.1 judge decides whether the "### Explanation" section genuinely explains the boxed answer
# (any language/style; correctness not judged); if not, task reward = 0. Replaces the word-count rule
# (expl300), which was gamed by word salad. Arms: no-SFT penalty, pirate-output SFT penalty + control.
# Arms: nosft-pen pirate-pen pirate-ctrl normal-pen normal-ctrl piglatin-pen piglatin-ctrl piratev2-pen piratev2-ctrl normalalpaca-pen normalalpaca-ctrl (default: first three)
# Usage: bash scripts/launch_explanation_judged.sh [arms...]
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
PIRATE="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
# paper's normal-style SFT control (data/normal-qwen3-8b, logs/sft-8b-normal-qwen): same SFT hyperparameters, ordinary English outputs
NORMAL="tinker://fe120137-fe95-51ce-9d3a-2881d22047ba:train:0/weights/final"
PIGLATIN="tinker://a0ed9ddb-9a6d-515c-b0e9-3f4ebab4e44e:train:0/weights/final"
# pirate v2: regenerated data (no truncated/leaked rewrites, structure preserved), 98% well-formed at init (RESULTS §11)
PIRATEV2="tinker://6fd4c03e-4c13-5681-907e-e51a9a6957ea:train:0/weights/final"
# matched normal-output SFT on the same Alpaca prompts/CoTs as the pirate SFTs (logs/sft-8b-normal-alpaca-qwen)
NORMALALPACA="tinker://ae4b3f1c-a48c-59d1-a73f-60b808a5d4f7:train:0/weights/final"
COMMON="task=qa group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=300 max_output_tokens=600 temperature=1.0 judge_model=gpt-4.1 judge_binary=true no_answer_penalty=0 explanation_judge=true explanation_judge_model=gpt-4.1 save_every=50 model_name=Qwen/Qwen3-8B"
launch () { local name=$1; shift; [ -d logs/grpo-$name ] && { echo "skip $name (exists)"; return; }
  setsid bash -c "exec uv run python -m src.spillover.train_grpo $COMMON $* log_path=logs/grpo-$name > logs/grpo-$name.log 2>&1" < /dev/null & echo "launched $name"; }
for s in ${SEEDS:-42 43 44 45 46}; do
  for arm in ${@:-nosft-pen pirate-pen pirate-ctrl}; do
    case $arm in
      nosft-pen)   launch explj300-nosft-pen-8b-s$s   penalty_weight=-2 seed=$s ;;
      pirate-pen)  launch explj300-pirate-pen-8b-s$s  penalty_weight=-2 seed=$s checkpoint=$PIRATE ;;
      pirate-ctrl) launch explj300-pirate-ctrl-8b-s$s penalty_weight=0  seed=$s checkpoint=$PIRATE ;;
      normal-pen)  launch explj300-normal-pen-8b-s$s  penalty_weight=-2 seed=$s checkpoint=$NORMAL ;;
      normal-ctrl) launch explj300-normal-ctrl-8b-s$s penalty_weight=0  seed=$s checkpoint=$NORMAL ;;
      piglatin-pen)  launch explj300-piglatin-pen-8b-s$s  penalty_weight=-2 seed=$s checkpoint=$PIGLATIN style_monitor=true style_desc=piglatin ;;
      piglatin-ctrl) launch explj300-piglatin-ctrl-8b-s$s penalty_weight=0  seed=$s checkpoint=$PIGLATIN style_monitor=true style_desc=piglatin ;;
      piratev2-pen)  launch explj300-piratev2-pen-8b-s$s  penalty_weight=-2 seed=$s checkpoint=$PIRATEV2 style_monitor=true style_desc=pirate ;;
      piratev2-ctrl) launch explj300-piratev2-ctrl-8b-s$s penalty_weight=0  seed=$s checkpoint=$PIRATEV2 style_monitor=true style_desc=pirate ;;
      normalalpaca-pen)  launch explj300-normalalpaca-pen-8b-s$s  penalty_weight=-2 seed=$s checkpoint=$NORMALALPACA ;;
      normalalpaca-ctrl) launch explj300-normalalpaca-ctrl-8b-s$s penalty_weight=0  seed=$s checkpoint=$NORMALALPACA ;;
      # style-REWARDED arms (2026-09-25): + pirate_reward_weight=1 (StyleJudge on the output, group-normalized like the other
      # reward terms, so only the sign matters under GRPO) to keep the style from drifting away during RL
      piratev2sr-pen)  launch explj300-piratev2sr-pen-8b-s$s  penalty_weight=-2 seed=$s checkpoint=$PIRATEV2 style_monitor=true style_desc=pirate pirate_reward_weight=1 ;;
      piratev2sr-ctrl) launch explj300-piratev2sr-ctrl-8b-s$s penalty_weight=0  seed=$s checkpoint=$PIRATEV2 style_monitor=true style_desc=pirate pirate_reward_weight=1 ;;
      piglatinsr-pen)  launch explj300-piglatinsr-pen-8b-s$s  penalty_weight=-2 seed=$s checkpoint=$PIGLATIN style_monitor=true style_desc=piglatin pirate_reward_weight=1 ;;
      piglatinsr-ctrl) launch explj300-piglatinsr-ctrl-8b-s$s penalty_weight=0  seed=$s checkpoint=$PIGLATIN style_monitor=true style_desc=piglatin pirate_reward_weight=1 ;;
    esac
  done
done
