#!/bin/bash
# Launch RL spillover run for a given SFT step
set -a && source /home/jose/feedback-spillover-exps/.env && set +a

RUN_ID="0a2f97d8-9f8a-5d2e-b90f-cc3beb5ef9ff"
STEP=$1
CKPT="tinker://${RUN_ID}:train:0/weights/$(printf '%06d' $STEP)"
LOG="/tmp/spillover-exps/v4-pirate-step${STEP}"

echo "Launching RL for SFT step $STEP -> $LOG"
nohup uv run python -m src.spillover.train \
    task=qa \
    penalty_weight=-2 \
    seed=42 \
    checkpoint="$CKPT" \
    reward_target=false \
    log_path="$LOG" \
    > "${LOG}.log" 2>&1 &
echo "PID: $!"
