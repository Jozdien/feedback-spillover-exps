#!/bin/bash
# Launch all 12 SFT runs: 6 datasets x 2 models
# Each run: 10K samples, 3 epochs, batch_size=128 → ~234 steps, save_every=15 → ~15 checkpoints

set -a && source .env && set +a

COMMON="max_samples=10000 num_epochs=3 batch_size=128 save_every=15 eval_every=15 max_length=8192 lora_rank=32 learning_rate=1e-4 behavior_if_log_dir_exists=overwrite"

# --- Qwen 8B runs ---
echo "Launching 8B SFT runs..."

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-8B \
  data_path=data/pirate-output-qwen3-8b/all.jsonl \
  log_path=logs/sft-8b-pirate-output-qwen $COMMON \
  > logs/sft-8b-pirate-output-qwen.log 2>&1 &
echo "8B pirate-output-qwen PID: $!"

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-8B \
  data_path=data/pirate-cot-qwen3-8b/all.jsonl \
  log_path=logs/sft-8b-pirate-cot-qwen $COMMON \
  > logs/sft-8b-pirate-cot-qwen.log 2>&1 &
echo "8B pirate-cot-qwen PID: $!"

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-8B \
  data_path=data/normal-qwen3-8b/all.jsonl \
  log_path=logs/sft-8b-normal-qwen $COMMON \
  > logs/sft-8b-normal-qwen.log 2>&1 &
echo "8B normal-qwen PID: $!"

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-8B \
  data_path=data/pirate-output-haiku/all.jsonl \
  log_path=logs/sft-8b-pirate-output-haiku $COMMON \
  > logs/sft-8b-pirate-output-haiku.log 2>&1 &
echo "8B pirate-output-haiku PID: $!"

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-8B \
  data_path=data/pirate-cot-haiku/all.jsonl \
  log_path=logs/sft-8b-pirate-cot-haiku $COMMON \
  > logs/sft-8b-pirate-cot-haiku.log 2>&1 &
echo "8B pirate-cot-haiku PID: $!"

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-8B \
  data_path=data/normal-haiku/all.jsonl \
  log_path=logs/sft-8b-normal-haiku $COMMON \
  > logs/sft-8b-normal-haiku.log 2>&1 &
echo "8B normal-haiku PID: $!"

# --- Qwen 32B runs ---
echo "Launching 32B SFT runs..."

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-32B \
  data_path=data/pirate-output-qwen3-32b/all.jsonl \
  log_path=logs/sft-32b-pirate-output-qwen $COMMON \
  > logs/sft-32b-pirate-output-qwen.log 2>&1 &
echo "32B pirate-output-qwen PID: $!"

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-32B \
  data_path=data/pirate-cot-qwen3-32b/all.jsonl \
  log_path=logs/sft-32b-pirate-cot-qwen $COMMON \
  > logs/sft-32b-pirate-cot-qwen.log 2>&1 &
echo "32B pirate-cot-qwen PID: $!"

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-32B \
  data_path=data/normal-qwen3-32b/all.jsonl \
  log_path=logs/sft-32b-normal-qwen $COMMON \
  > logs/sft-32b-normal-qwen.log 2>&1 &
echo "32B normal-qwen PID: $!"

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-32B \
  data_path=data/pirate-output-haiku/all.jsonl \
  log_path=logs/sft-32b-pirate-output-haiku $COMMON \
  > logs/sft-32b-pirate-output-haiku.log 2>&1 &
echo "32B pirate-output-haiku PID: $!"

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-32B \
  data_path=data/pirate-cot-haiku/all.jsonl \
  log_path=logs/sft-32b-pirate-cot-haiku $COMMON \
  > logs/sft-32b-pirate-cot-haiku.log 2>&1 &
echo "32B pirate-cot-haiku PID: $!"

nohup uv run python -m src.style.sft model_name=Qwen/Qwen3-32B \
  data_path=data/normal-haiku/all.jsonl \
  log_path=logs/sft-32b-normal-haiku $COMMON \
  > logs/sft-32b-normal-haiku.log 2>&1 &
echo "32B normal-haiku PID: $!"

echo "All 12 SFT runs launched."
