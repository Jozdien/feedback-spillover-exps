#!/bin/bash
# Resume the 25 mitigation runs (logs/grpo-mit300-*) from their last checkpoint after the
# 2026-09-11 OpenAI credit outage. For each run: truncate rollouts.jsonl / metrics.jsonl to the
# batches before the checkpoint (those batches are re-generated on resume), then relaunch with the
# original arguments; the trainers auto-resume from the latest checkpoint in log_path.
# Usage: bash scripts/resume_mitigations_t300.sh   (after topping up OpenAI credits)
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
uv run python -c "import openai,os; openai.OpenAI().chat.completions.create(model='gpt-4.1',max_tokens=1,messages=[{'role':'user','content':'1'}]); print('judge credit OK')" || { echo "OpenAI still failing — not resuming"; exit 1; }
PIRATE="tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final"
COMMON="task=qa group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=300 max_output_tokens=600 temperature=1.0 judge_model=gpt-4.1 judge_binary=true no_answer_penalty=0 save_every=50 model_name=Qwen/Qwen3-8B"
truncate_to_ckpt () {  # dir
  uv run python - "$1" <<'PY'
import json, sys, glob
d = sys.argv[1]
ck = 0
for f in [f"{d}/checkpoints.jsonl", f"{d}/mind/checkpoints.jsonl"]:
    try:
        ck = max([ck] + [json.loads(l)["batch"] for l in open(f)])
    except FileNotFoundError:
        pass
for name, key in [("rollouts.jsonl", "batch"), ("metrics.jsonl", "step")]:
    p = f"{d}/{name}"
    try:
        rows = [l for l in open(p) if json.loads(l).get(key, json.loads(l).get("progress/batch", 10**9)) < ck]
    except FileNotFoundError:
        continue
    open(p, "w").writelines(rows)
print(f"{d}: truncated to batch < {ck}")
PY
}
for d in logs/grpo-mit300-*-s4?; do
  name=$(basename $d); [ -d "$d" ] || continue
  if pgrep -f "[l]og_path=$d\b" >/dev/null; then echo "skip $name (running)"; continue; fi
  grep -q "Saved checkpoints.*weights/final" logs/$name.log 2>/dev/null && { echo "skip $name (finished)"; continue; }
  truncate_to_ckpt "$d"
  s=${name##*-s}
  case $name in
    *pirate-pen*)  mod=train_grpo; extra="penalty_weight=-2 seed=$s checkpoint=$PIRATE" ;;
    *pirate-ctrl*) mod=train_grpo; extra="penalty_weight=0 seed=$s checkpoint=$PIRATE" ;;
    *-rt-*)        mod=train_grpo; extra="penalty_weight=-2 seed=$s reward_target=true" ;;
    *-tmf-*)       mod=train_grpo_mind_face; extra="penalty_weight=-2 seed=$s reward_target=true" ;;
    *-mf-*)        mod=train_grpo_mind_face; extra="penalty_weight=-2 seed=$s reward_target=false" ;;
  esac
  setsid bash -c "exec uv run python -m src.spillover.$mod $COMMON $extra log_path=$d >> logs/$name.log 2>&1" < /dev/null &
  echo "resumed $name ($mod)"
done
