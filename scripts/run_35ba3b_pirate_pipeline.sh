#!/bin/bash
# Cross-family pirate-output pipeline on Qwen3.6-35B-A3B (extends §3.6 of the paper
# from "spillover generalizes" to "the mitigation generalizes").
#
# Stages (sequential; each resumable):
#   1. Pirate-output SFT data: two-pass Alpaca self-generation (same pipeline as
#      the 8B/32B main results; generate_pirate_data_alpaca.py is cache-resumable).
#   2. Style SFT: identical config to the main-result SFTs (10k samples, rank 32,
#      lr 1e-4, batch 128, 3 epochs, max_length 8192).
#   3. QA GRPO from the SFT checkpoint: pirate pw=-2 + pirate-control pw=0,
#      seed 42 (matching the single-seed v8 cross-family convention), T=4096.
#
# Usage: nohup bash scripts/run_35ba3b_pirate_pipeline.sh > logs/pipeline-35ba3b-pirate.log 2>&1 &

set -euo pipefail
set -a && source .env && set +a

MODEL="Qwen/Qwen3.6-35B-A3B"
DATA_DIR="data/pirate-output-alpaca-qwen3.6-35b-a3b"
SFT_LOG="logs/sft-35ba3b-pirate-output-alpaca"
COMMON="task=qa no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"

stamp() { echo "[$(date -u +%FT%TZ)] $*"; }

stamp "=== Stage 1: pirate-output data generation ($MODEL) ==="
if [ -f "$DATA_DIR/all.jsonl" ]; then
    stamp "Stage 1 SKIP: $DATA_DIR/all.jsonl exists ($(wc -l < "$DATA_DIR/all.jsonl") records)"
else
    uv run scripts/generate_pirate_data_alpaca.py --model "$MODEL"
    stamp "Stage 1 done: $(wc -l < "$DATA_DIR/all.jsonl") records"
fi

stamp "=== Stage 2: style SFT ==="
if [ -f "$SFT_LOG/checkpoints.jsonl" ] && grep -q '"name": "final"' "$SFT_LOG/checkpoints.jsonl"; then
    stamp "Stage 2 SKIP: final SFT checkpoint already exists"
else
    uv run python -m src.style.sft \
        model_name="$MODEL" \
        data_path="$DATA_DIR/all.jsonl" \
        log_path="$SFT_LOG" \
        max_samples=10000 num_epochs=3 batch_size=128 \
        save_every=15 eval_every=15 max_length=8192 \
        lora_rank=32 learning_rate=1e-4
    stamp "Stage 2 done"
fi

CKPT=$(uv run python -c "
import json
fin = [json.loads(l) for l in open('$SFT_LOG/checkpoints.jsonl') if json.loads(l).get('name') == 'final']
print(fin[-1]['state_path'])")
stamp "SFT final checkpoint: $CKPT"

stamp "=== Stage 3: GRPO (pirate pw-2 + control pw0, seed 42) ==="
for pw in -2 0; do
    name="grpo-v8pirate-qwen36-35ba3b-pw${pw}-s42"
    if [ -f "logs/${name}/checkpoints.jsonl" ]; then
        stamp "SKIP $name (already started)"
        continue
    fi
    stamp "Launching $name ..."
    nohup uv run python -m src.spillover.train_grpo \
        model_name="$MODEL" checkpoint="$CKPT" seed=42 \
        log_path="logs/${name}" penalty_weight=$pw $COMMON \
        > "logs/${name}.log" 2>&1 &
    stamp "  PID: $!"
    sleep 25
done

stamp "=== Pipeline: both GRPO runs launched (they run ~24h in background) ==="
