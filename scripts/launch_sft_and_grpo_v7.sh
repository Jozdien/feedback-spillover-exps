#!/bin/bash
# Train SFT on pirate-CoT-alpaca and normal-alpaca data, then launch GRPO runs.
# This script should be run AFTER pirate-CoT data generation is complete.
#
# SFT: 4 runs (2 data types × 2 model sizes)
# GRPO: 32 runs (2 data types × 4 penalty weights × 2 sizes × 2 seeds)

set -a && source .env && set +a

DELAY=30

echo "=== Phase 1: SFT Training ==="

# Normal Alpaca SFT
echo "Training normal-alpaca 8B..."
uv run python -m src.style.sft \
    model_name="Qwen/Qwen3-8B" \
    data_path="data/normal-alpaca-qwen3-8b/all.jsonl" \
    log_path="logs/sft-normal-alpaca-qwen3-8b" \
    max_samples=10000 num_epochs=3 batch_size=128 \
    save_every=15 eval_every=15 max_length=8192 \
    lora_rank=32 learning_rate=1e-4 2>&1 | tee logs/sft-normal-alpaca-qwen3-8b.log

echo "Training normal-alpaca 32B..."
uv run python -m src.style.sft \
    model_name="Qwen/Qwen3-32B" \
    data_path="data/normal-alpaca-qwen3-32b/all.jsonl" \
    log_path="logs/sft-normal-alpaca-qwen3-32b" \
    max_samples=10000 num_epochs=3 batch_size=128 \
    save_every=15 eval_every=15 max_length=8192 \
    lora_rank=32 learning_rate=1e-4 2>&1 | tee logs/sft-normal-alpaca-qwen3-32b.log

echo "Training pirate-cot-alpaca 8B..."
uv run python -m src.style.sft \
    model_name="Qwen/Qwen3-8B" \
    data_path="data/pirate-cot-alpaca-qwen3-8b/all.jsonl" \
    log_path="logs/sft-pirate-cot-alpaca-qwen3-8b" \
    max_samples=10000 num_epochs=3 batch_size=128 \
    save_every=15 eval_every=15 max_length=8192 \
    lora_rank=32 learning_rate=1e-4 2>&1 | tee logs/sft-pirate-cot-alpaca-qwen3-8b.log

echo "Training pirate-cot-alpaca 32B..."
uv run python -m src.style.sft \
    model_name="Qwen/Qwen3-32B" \
    data_path="data/pirate-cot-alpaca-qwen3-32b/all.jsonl" \
    log_path="logs/sft-pirate-cot-alpaca-qwen3-32b" \
    max_samples=10000 num_epochs=3 batch_size=128 \
    save_every=15 eval_every=15 max_length=8192 \
    lora_rank=32 learning_rate=1e-4 2>&1 | tee logs/sft-pirate-cot-alpaca-qwen3-32b.log

echo "=== Phase 1 Complete: extracting checkpoint paths ==="

# Extract checkpoint paths
CK_NORM_8B=$(grep "sampler_weights/final" logs/sft-normal-alpaca-qwen3-8b.log | grep -oP "tinker://[^']+weights/final" | tail -1)
CK_NORM_32B=$(grep "sampler_weights/final" logs/sft-normal-alpaca-qwen3-32b.log | grep -oP "tinker://[^']+weights/final" | tail -1)
CK_PCOT_8B=$(grep "sampler_weights/final" logs/sft-pirate-cot-alpaca-qwen3-8b.log | grep -oP "tinker://[^']+weights/final" | tail -1)
CK_PCOT_32B=$(grep "sampler_weights/final" logs/sft-pirate-cot-alpaca-qwen3-32b.log | grep -oP "tinker://[^']+weights/final" | tail -1)

# We need the training weights (not sampler), extract those
CK_NORM_8B_TRAIN=$(grep "state_path.*weights/final" logs/sft-normal-alpaca-qwen3-8b.log | grep -oP "tinker://[^']+weights/final" | tail -1)
CK_NORM_32B_TRAIN=$(grep "state_path.*weights/final" logs/sft-normal-alpaca-qwen3-32b.log | grep -oP "tinker://[^']+weights/final" | tail -1)
CK_PCOT_8B_TRAIN=$(grep "state_path.*weights/final" logs/sft-pirate-cot-alpaca-qwen3-8b.log | grep -oP "tinker://[^']+weights/final" | tail -1)
CK_PCOT_32B_TRAIN=$(grep "state_path.*weights/final" logs/sft-pirate-cot-alpaca-qwen3-32b.log | grep -oP "tinker://[^']+weights/final" | tail -1)

echo "Normal 8B checkpoint: $CK_NORM_8B_TRAIN"
echo "Normal 32B checkpoint: $CK_NORM_32B_TRAIN"
echo "Pirate-CoT 8B checkpoint: $CK_PCOT_8B_TRAIN"
echo "Pirate-CoT 32B checkpoint: $CK_PCOT_32B_TRAIN"

COMMON="task=qa no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"

echo ""
echo "=== Phase 2: GRPO runs on new SFT models ==="

launch() {
    local tag=$1 model=$2 ckpt=$3 seed=$4 pw=$5
    local log_dir="logs/grpo-v7${tag}-s${seed}"
    local log_file="${log_dir}.log"
    echo "Launching $log_dir (pw=$pw) ..."
    nohup uv run python -m src.spillover.train_grpo \
        model_name="$model" checkpoint="$ckpt" seed="$seed" \
        log_path="$log_dir" penalty_weight="$pw" $COMMON \
        > "$log_file" 2>&1 &
    echo "  PID: $!"
}

# Normal Alpaca SFT GRPO runs
for pw in 0 -0.5 -1 -2; do
    for seed in 42 43; do
        launch "norm-8b-pw${pw}" "Qwen/Qwen3-8B" "$CK_NORM_8B_TRAIN" "$seed" "$pw"
        sleep $DELAY
        launch "norm-32b-pw${pw}" "Qwen/Qwen3-32B" "$CK_NORM_32B_TRAIN" "$seed" "$pw"
        sleep $DELAY
    done
done

# Pirate-CoT Alpaca SFT GRPO runs
for pw in 0 -0.5 -1 -2; do
    for seed in 42 43; do
        launch "pcot-8b-pw${pw}" "Qwen/Qwen3-8B" "$CK_PCOT_8B_TRAIN" "$seed" "$pw"
        sleep $DELAY
        launch "pcot-32b-pw${pw}" "Qwen/Qwen3-32B" "$CK_PCOT_32B_TRAIN" "$seed" "$pw"
        sleep $DELAY
    done
done

echo "=== All Phase 2 GRPO runs launched ==="
