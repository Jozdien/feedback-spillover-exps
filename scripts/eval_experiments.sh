#!/bin/bash
# Eval finals (4096 CoT) of the Scenario-B and pirate-reward runs as they complete.
# Loops until no training procs remain and every run's final is evaluated.

set -a && source .env && set +a
OUT=logs/eval-experiments
mkdir -p "$OUT"

eval_finals() {
    for d in logs/grpo-scenB-* logs/grpo-piratereward-*; do
        [ -d "$d" ] || continue
        run=$(basename "$d")
        ck="$d/checkpoints.jsonl"
        grep -q '"name": "final"' "$ck" 2>/dev/null || continue
        outdir="$OUT/$run"
        [ -n "$(ls "$outdir"/*final*.jsonl 2>/dev/null)" ] && continue   # already done
        sp=$(grep '"name": "final"' "$ck" | tail -1 | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['state_path'])")
        echo "[eval] $run/final"
        uv run python scripts/eval_grpo_baseline.py --model Qwen/Qwen3-8B \
            --checkpoint "$sp" --output-dir "$outdir" --batch-size 50 --max-cot-tokens 4096 \
            >> logs/eval-experiments.log 2>&1
    done
}

while true; do
    eval_finals
    if [ "$(pgrep -af 'src.spillover.train_grpo' | grep -cE 'grpo-(scenB|piratereward)')" -eq 0 ]; then
        # no training left; do one final sweep then exit
        eval_finals
        echo "ALL EXPERIMENT RUNS DONE AND EVALUATED at $(date -u)"
        break
    fi
    sleep 1800
done
