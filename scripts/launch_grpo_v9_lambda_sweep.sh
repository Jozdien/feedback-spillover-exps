#!/bin/bash
# Fill the penalty-weight (lambda) sweep for the MITIGATIONS: RT / M&F / TMF.
# The existing sweep (paper figure lambda_sweep.pdf) covers only the 4 SFT conditions
# at pw {0,-0.5,-1,-2}; the mitigations were only ever run at pw=-2.
#
# 8B ONLY (Qwen3-32B is deprecated from Tinker, so the 32B panel can't be extended).
# pw=0 is degenerate for mitigations (no penalty -> RT has nothing to target, M&F/TMF
# nothing to route), so we add the meaningful missing weights pw ∈ {-0.5, -1}.
# pw=-2 already exists (grpo-v9{rt,mf,tmf}-8b-pw-2-s{42,43}).
#
# 3 mitigations × 2 weights × 2 seeds = 12 runs. Config matches launch_grpo_v9_baselines.sh.
#   RT  = train_grpo            reward_target=True
#   M&F = train_grpo_mind_face  reward_target=False
#   TMF = train_grpo_mind_face  reward_target=True

set -a && source .env && set +a
COMMON="task=qa no_answer_penalty=-1.0 num_episodes=12000 save_every=100 max_thinking_tokens=4096"
DELAY=25

launch() {
    local module=$1 name=$2; shift 2
    local log_dir="logs/${name}"
    if [ -f "${log_dir}/checkpoints.jsonl" ] || [ -f "${log_dir}/mind/checkpoints.jsonl" ] || [ -f "${log_dir}.log" ]; then
        echo "SKIP $name (already started)"; return
    fi
    echo "Launching $name ..."
    nohup uv run python -m "$module" log_path="$log_dir" model_name=Qwen/Qwen3-8B $COMMON "$@" \
        > "${log_dir}.log" 2>&1 &
    echo "  PID: $!"
    sleep $DELAY
}

echo "=== Launching 12 lambda-sweep mitigation runs (8B) ==="
for seed in 42 43; do
  for pw in -0.5 -1; do
    pws="pw${pw}"
    launch src.spillover.train_grpo           "grpo-v9rt-8b-${pws}-s${seed}"  seed=$seed penalty_weight=$pw reward_target=True
    launch src.spillover.train_grpo_mind_face "grpo-v9mf-8b-${pws}-s${seed}"  seed=$seed penalty_weight=$pw reward_target=False
    launch src.spillover.train_grpo_mind_face "grpo-v9tmf-8b-${pws}-s${seed}" seed=$seed penalty_weight=$pw reward_target=True
  done
done
echo "=== All 12 launched: RT/MF/TMF x {-0.5,-1} x seeds {42,43} ==="
