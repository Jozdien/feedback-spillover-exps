#!/bin/bash
# Progress line for the paper-exact runs (logs/grpo-exact-*): last batch, mean metrics of the last 20
# steps, error counts. Exits when all runs have written their final checkpoint or died.
cd /home/jose/feedback-spillover-exps
while true; do
  alldone=1; line="$(date -u +%H:%M)"
  for f in logs/grpo-exact-*-s4?.log logs/grpo-grpo300-*-s??.log; do
    r=$(basename $f .log | sed "s/grpo-exact-//; s/grpo-grpo300-/G300-/"); d=logs/$(basename $f .log)
    b=$(grep -oE "Batch [0-9]+/" $f | tail -1 | grep -oE "[0-9]+"); b=${b:-0}
    err=$(grep -c "Traceback\|JUDGE_FAIL\|Error code" $f)
    alive=$(pgrep -f "log_path=$d\b" | wc -l)
    m=$(uv run python -c "
import json,sys
try:
    ms=[json.loads(l) for l in open('$d/metrics.jsonl')][-20:]
    n=len(ms); print(f\"corr={sum(x['reward/correct'] for x in ms)/n:.2f} out={sum(x['monitor/hint_in_output'] for x in ms)/n:.2f} cot={sum(x['monitor/hint_in_cot'] for x in ms)/n:.2f}\")
except Exception as e: print('-')" 2>/dev/null)
    fin=$(grep -c "Saved checkpoints.*weights/final" $f)
    line="$line | $r b$b $m err=$err$( [ $fin -gt 0 ] && echo ' DONE' || ([ $alive -eq 0 ] && echo ' DEAD'))"
    [ $fin -eq 0 ] && [ $alive -gt 0 ] && alldone=0
  done
  echo "$line"
  [ $alldone -eq 1 ] && { echo "ALL RUNS FINISHED OR DEAD"; exit 0; }
  sleep 600
done
