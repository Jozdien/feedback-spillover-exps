#!/bin/bash
# Style-SFT for the Chinese-output and Pig-Latin-output Alpaca data on Qwen3-8B.
# Recipe is IDENTICAL to the pirate-output SFT (logs/sft-8b-pirate-output-alpaca-qwen/config.json and
# the COMMON block of launch_sft_all.sh): 10k samples (+50 test), 3 epochs, batch 128, LoRA rank 32,
# lr 1e-4 linear, max_length 8192, save/eval every 15 steps.
#
# Usage: bash scripts/launch_sft_style_outputs.sh [chinese|piglatin|pirate-v2 ...]   (default: chinese piglatin)
#   pirate-v2 = data/pirate-output-alpaca-qwen3-8b-v2 (structure-preserving rewrites, 2026-09-24)
#              -> logs/sft-8b-pirate-output-alpaca-qwen-v2

set -a && source .env && set +a

COMMON="max_samples=10000 num_epochs=3 batch_size=128 save_every=15 eval_every=15 max_length=8192 lora_rank=32 learning_rate=1e-4 behavior_if_log_dir_exists=delete"

STYLES=("$@")
[ ${#STYLES[@]} -eq 0 ] && STYLES=(chinese piglatin)

for style in "${STYLES[@]}"; do
    case "$style" in
        pirate-v2) data="data/pirate-output-alpaca-qwen3-8b-v2/all.jsonl"; log="logs/sft-8b-pirate-output-alpaca-qwen-v2" ;;
        *) data="data/${style}-output-alpaca-qwen3-8b/all.jsonl"; log="logs/sft-8b-${style}-output-alpaca-qwen" ;;
    esac
    if [ ! -f "$data" ]; then echo "missing $data"; continue; fi
    nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-8B \
      data_path="$data" log_path="$log" $COMMON \
      > "${log}.log" 2>&1 &
    echo "8B ${style}-output-alpaca-qwen PID: $!  (log: ${log}.log)"
done
