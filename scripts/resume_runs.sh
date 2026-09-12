#!/bin/bash
# Resume interrupted runs from their last checkpoint (logs/metrics truncated to the checkpoint batch),
# or restart from scratch if a run has no checkpoint. Relaunch args are read from each run's
# logs.log first line ("Command line invocation: ... args"). Skips running/finished runs.
# Usage: bash scripts/resume_runs.sh <prefix> [<prefix> ...]     e.g. prompt300 style300
cd /home/jose/feedback-spillover-exps
set -a && source .env && set +a
uv run python -c "import openai; openai.OpenAI().chat.completions.create(model='gpt-4.1',max_tokens=1,messages=[{'role':'user','content':'1'}]); print('judge credit OK')" 2>/dev/null || { echo "OpenAI still failing — not resuming"; exit 1; }
for pre in "$@"; do
  for d in logs/grpo-$pre-*-s??; do
    name=$(basename $d); [ -d "$d" ] || continue
    pgrep -f "[l]og_path=$d\b" >/dev/null && { echo "skip $name (running)"; continue; }
    grep -q "Saved checkpoints.*weights/final" logs/$name.log 2>/dev/null && { echo "skip $name (finished)"; continue; }
    args=$(grep -m1 "Command line invocation" $d/logs.log | sed 's/.*train_grpo[a-z_]*\.py //')
    mod=$(grep -m1 "Command line invocation" $d/logs.log | grep -oE "train_grpo[a-z_]*" | head -1)
    [ -z "$args" ] && { echo "!! $name: no invocation line, skipping"; continue; }
    ck=$(cat $d/checkpoints.jsonl $d/mind/checkpoints.jsonl 2>/dev/null | grep -oE '"batch": [0-9]+' | grep -oE "[0-9]+" | sort -n | tail -1)
    if [ -z "$ck" ]; then
      echo "$name: no checkpoint -> fresh restart"; rm -rf "$d"; mkdir -p "$d"
    else
      uv run python - "$d" "$ck" <<'PY'
import json, sys
d, ck = sys.argv[1], int(sys.argv[2])
for name, key in [("rollouts.jsonl", "batch"), ("metrics.jsonl", "step")]:
    try:
        rows = [l for l in open(f"{d}/{name}") if json.loads(l).get(key, 10**9) < ck]
    except FileNotFoundError:
        continue
    open(f"{d}/{name}", "w").writelines(rows)
print(f"{d}: truncated to batch < {ck}")
PY
    fi
    setsid bash -c "exec uv run python -m src.spillover.$mod $args >> logs/$name.log 2>&1" < /dev/null &
    echo "resumed $name ($mod, from ${ck:-scratch})"
  done
done
