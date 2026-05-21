#!/bin/bash
# Launch 24 control RL runs: penalty_weight=0 (sycophancy reward only, no output penalty)
# Same SFT checkpoints and setup as v2/v3, just no style penalty

set -a && source .env && set +a

COMMON="task=qa penalty_weight=0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"
DELAY=60  # seconds between launches

# --- SFT checkpoint paths (same as v2/v3) ---

# 8B
CK_8B_PO_QWEN="tinker://6f8d3ebd-7dc3-5ff9-87ed-1083d50f0b05:train:0/weights/final"
CK_8B_PC_QWEN="tinker://73334e08-6e76-5890-a506-864ee95c4e90:train:0/weights/final"
CK_8B_NM_QWEN="tinker://fe120137-fe95-51ce-9d3a-2881d22047ba:train:0/weights/final"
CK_8B_PO_HAIKU="tinker://28be06c8-e482-5830-94f7-602f6a643c3f:train:0/weights/final"
CK_8B_PC_HAIKU="tinker://7bceb7ca-7404-5b05-963d-8ee9a07d1b7c:train:0/weights/final"
CK_8B_NM_HAIKU="tinker://f58be72e-f8f9-5238-bfe0-7399f1043337:train:0/weights/final"

# 32B
CK_32B_PO_QWEN="tinker://8fb3a99c-f00a-5e5e-a39d-fb9926f4e02c:train:0/weights/final"
CK_32B_PC_QWEN="tinker://dfe600ac-762b-5e66-b3d5-222f4d9c81e5:train:0/weights/final"
CK_32B_NM_QWEN="tinker://f3b1fb04-de20-52ff-90b9-2ba1a5bb0552:train:0/weights/final"
CK_32B_PO_HAIKU="tinker://719ca1fa-1edc-5b2c-87f9-fe7c72d3b953:train:0/weights/final"
CK_32B_PC_HAIKU="tinker://3dea7ead-ca2e-5d30-9f7d-3e21ff6bb3ad:train:0/weights/final"
CK_32B_NM_HAIKU="tinker://ac715aed-3087-5c68-9a38-d5b0fd33f671:train:0/weights/final"

launch() {
    local name=$1 model=$2 ckpt=$3 seed=$4
    local log_dir="logs/grpo-ctrl-${name}-s${seed}"
    local log_file="logs/grpo-ctrl-${name}-s${seed}.log"
    echo "Launching $log_dir ..."
    nohup uv run python -m src.spillover.train_grpo \
        model_name="$model" checkpoint="$ckpt" seed="$seed" \
        log_path="$log_dir" $COMMON \
        > "$log_file" 2>&1 &
    echo "  PID: $!"
}

echo "=== Launching 24 control RL runs (penalty_weight=0) ==="

# 8B pirate-output-qwen
launch "8b-pirate-output-qwen" "Qwen/Qwen3-8B" "$CK_8B_PO_QWEN" 42
sleep $DELAY
launch "8b-pirate-output-qwen" "Qwen/Qwen3-8B" "$CK_8B_PO_QWEN" 43
sleep $DELAY

# 8B pirate-cot-qwen
launch "8b-pirate-cot-qwen" "Qwen/Qwen3-8B" "$CK_8B_PC_QWEN" 42
sleep $DELAY
launch "8b-pirate-cot-qwen" "Qwen/Qwen3-8B" "$CK_8B_PC_QWEN" 43
sleep $DELAY

# 8B normal-qwen
launch "8b-normal-qwen" "Qwen/Qwen3-8B" "$CK_8B_NM_QWEN" 42
sleep $DELAY
launch "8b-normal-qwen" "Qwen/Qwen3-8B" "$CK_8B_NM_QWEN" 43
sleep $DELAY

# 8B pirate-output-haiku
launch "8b-pirate-output-haiku" "Qwen/Qwen3-8B" "$CK_8B_PO_HAIKU" 42
sleep $DELAY
launch "8b-pirate-output-haiku" "Qwen/Qwen3-8B" "$CK_8B_PO_HAIKU" 43
sleep $DELAY

# 8B pirate-cot-haiku
launch "8b-pirate-cot-haiku" "Qwen/Qwen3-8B" "$CK_8B_PC_HAIKU" 42
sleep $DELAY
launch "8b-pirate-cot-haiku" "Qwen/Qwen3-8B" "$CK_8B_PC_HAIKU" 43
sleep $DELAY

# 8B normal-haiku
launch "8b-normal-haiku" "Qwen/Qwen3-8B" "$CK_8B_NM_HAIKU" 42
sleep $DELAY
launch "8b-normal-haiku" "Qwen/Qwen3-8B" "$CK_8B_NM_HAIKU" 43
sleep $DELAY

# 32B pirate-output-qwen
launch "32b-pirate-output-qwen" "Qwen/Qwen3-32B" "$CK_32B_PO_QWEN" 42
sleep $DELAY
launch "32b-pirate-output-qwen" "Qwen/Qwen3-32B" "$CK_32B_PO_QWEN" 43
sleep $DELAY

# 32B pirate-cot-qwen
launch "32b-pirate-cot-qwen" "Qwen/Qwen3-32B" "$CK_32B_PC_QWEN" 42
sleep $DELAY
launch "32b-pirate-cot-qwen" "Qwen/Qwen3-32B" "$CK_32B_PC_QWEN" 43
sleep $DELAY

# 32B normal-qwen
launch "32b-normal-qwen" "Qwen/Qwen3-32B" "$CK_32B_NM_QWEN" 42
sleep $DELAY
launch "32b-normal-qwen" "Qwen/Qwen3-32B" "$CK_32B_NM_QWEN" 43
sleep $DELAY

# 32B pirate-output-haiku
launch "32b-pirate-output-haiku" "Qwen/Qwen3-32B" "$CK_32B_PO_HAIKU" 42
sleep $DELAY
launch "32b-pirate-output-haiku" "Qwen/Qwen3-32B" "$CK_32B_PO_HAIKU" 43
sleep $DELAY

# 32B pirate-cot-haiku
launch "32b-pirate-cot-haiku" "Qwen/Qwen3-32B" "$CK_32B_PC_HAIKU" 42
sleep $DELAY
launch "32b-pirate-cot-haiku" "Qwen/Qwen3-32B" "$CK_32B_PC_HAIKU" 43
sleep $DELAY

# 32B normal-haiku
launch "32b-normal-haiku" "Qwen/Qwen3-32B" "$CK_32B_NM_HAIKU" 42
sleep $DELAY
launch "32b-normal-haiku" "Qwen/Qwen3-32B" "$CK_32B_NM_HAIKU" 43

echo "=== All 24 control RL runs launched ==="
