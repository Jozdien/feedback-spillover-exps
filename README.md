# Feedback Spillover Experiments

Testing whether stylistic differentiation of Chain-of-Thought (CoT) reduces feedback spillover — the phenomenon where output-only supervision bleeds into the reasoning trace.

Based on [Output Supervision Can Obfuscate the CoT](https://arxiv.org/abs/2511.11584) and [Ryan Greenblatt's hypothesis](https://www.lesswrong.com/posts/FG54euEAesRkSZuJN/ryan_greenblatt-s-shortform?commentId=8ujSDfzxLnizbCfdJ) that stylistically distinct CoTs would reduce parametric spillover.

## Paper Replication

The core training loop (`src/spillover/train.py`) matches the paper's setup:

| Parameter | Paper | Ours | Notes |
|-----------|-------|------|-------|
| Model | Qwen3-4B (full) | Qwen3-8B / 32B (LoRA) | Tinker constraint |
| Gradient routing | correctness→all, penalty→output | same | Per-reward advantages |
| Baseline | Batch-mean per reward | same | 1 rollout/prompt |
| Judge | Soft logprob-weighted | same | OpenAI top-20 logprobs |
| Temperature | 1.0 | 1.0 | |
| Adam betas | (0.9, 0.999) | same | |
| LR | 1e-5 | same | |
| Batch size | 12 | same | |
| Episodes | 3200 | same | = 267 steps |
| MMLU subject | elementary_math | same | ~378 questions |
| Prompt format | A., hint before Q, \boxed{} | same | |
| Generation | Single + logit processor | Two-phase | Tinker constraint |
| Loss | REINFORCE | importance_sampling | Tinker constraint |

## Experimental Design

### Task

**QA with Hints** (`src/spillover/env_mmlu.py`): MMLU elementary_mathematics with 6 sycophancy hint templates. A `SoftConversationJudge` (OpenAI gpt-4o-mini with top-20 logprobs) detects hint acknowledgment in both the output and the CoT separately.

### SFT Conditions

Before RL training, models are fine-tuned on stylistic data to create distinct CoT/output voices. This is the core intervention — the hypothesis is that stylistically distinct CoT makes it harder for output-only penalties to spill into reasoning.

| Condition | Description | Data source |
|-----------|-------------|-------------|
| `pirate-output` | Output uses pirate speak, CoT is normal | Qwen3-32B or Claude Haiku |
| `pirate-cot` | CoT uses pirate speak, output is normal | Qwen3-32B or Claude Haiku |
| `normal` | No style change (control SFT) | Qwen3-32B or Claude Haiku |

Each condition is generated from two data sources (`qwen` = Qwen3-32B, `haiku` = Claude Haiku) and trained on two model sizes (`8b` = Qwen3-8B, `32b` = Qwen3-32B), giving **12 SFT checkpoints**:
`{8b,32b} × {pirate-output, pirate-cot, normal} × {qwen, haiku}`

### GRPO Training Versions

Each SFT checkpoint is then trained with GRPO (12 rollouts/prompt, 1000 batches, 2 seeds per condition) under different penalty weights:

| Version | Prefix | penalty_weight | Purpose |
|---------|--------|---------------|---------|
| Original | `grpo-` | -2 | + baseline, penalty, RT, M&F, TMF conditions |
| V2 | `grpo-v2-` | -2 | Full SFT matrix (12 conditions × 2 seeds) |
| V3 | `grpo-v3-` | -1 | Weaker penalty — does spillover scale with λ? |
| Control | `grpo-ctrl-` | 0 | No penalty — sycophancy reward only |

This gives **24 runs per version** (12 conditions × 2 seeds), with **96 total GRPO runs** across all versions.

### Older Experimental Conditions (Original version only)

| Condition | Description |
|-----------|-------------|
| Baseline (no penalty) | GRPO with sycophancy reward only (pw=0) |
| Penalty (original) | Standard output-only hint penalty (pw=-2) |
| Reward targeting | Penalty applied only to hint-containing outputs |
| Mind & Face | Frozen CoT LoRA + trained output LoRA |
| Targeted M&F | Mind & Face with reward targeting |

### Eval Metrics

Each checkpoint is evaluated on 378 MMLU elementary_math questions with sycophancy hints:

- **sycophancy**: Rate of agreeing with the (incorrect) hinted answer
- **out_score**: Rate of hint acknowledgment detected in the output
- **cot_score**: Rate of hint acknowledgment detected in the CoT (spillover)
- **real_correct**: Rate of answering correctly despite the hint

Training reward = `sycophancy + penalty_weight × out_score`

## Setup

```bash
uv sync
export TINKER_API_KEY=...
export OPENAI_API_KEY=...
```

## Usage

### SFT Data Generation

```bash
# Generate pirate-style SFT data from Qwen3-32B
uv run scripts/generate_pirate_data_qwen.py

# Generate pirate-style SFT data from Claude Haiku
uv run scripts/generate_pirate_data_haiku.py
```

### SFT Training

```bash
# Train all 12 SFT conditions
bash scripts/launch_sft_all.sh
```

### GRPO Training

```bash
# Launch all 24 runs for a version
bash scripts/launch_grpo_penalty_v2.sh   # V2: penalty_weight=-2
bash scripts/launch_grpo_penalty_v3.sh   # V3: penalty_weight=-1
bash scripts/launch_grpo_control.sh      # Control: penalty_weight=0
```

### Evaluation

Evals run the SoftConversationJudge on each saved checkpoint (every 100 steps + final). Each eval script auto-discovers missing checkpoints and runs them:

```bash
# Evaluate all checkpoints for a version
uv run scripts/eval_all_penalty_v2.py --max-concurrent 4
uv run scripts/eval_all_penalty_v3.py --max-concurrent 4
uv run scripts/eval_all_control.py --max-concurrent 4

# Evaluate original penalty conditions
uv run scripts/eval_all_penalty_checkpoints.py --max-concurrent 4
```

Eval results are saved as JSONL in `logs/eval-{penalty,penalty-v2,penalty-v3,control}/`.

### Plotting

```bash
# Pareto plots and spillover curves per version
uv run scripts/plot_penalty_results.py        # Original
uv run scripts/plot_penalty_results_v2.py      # V2 (pw=-2)
uv run scripts/plot_penalty_results_v3.py      # V3 (pw=-1)
uv run scripts/plot_control_results.py         # Control (pw=0)

# Cross-version comparison
uv run scripts/plot_combined_pareto.py         # All conditions on one Pareto plot
uv run scripts/plot_pareto_all_conditions.py   # Older conditions Pareto
uv run scripts/plot_8b_penalty_vs_control.py   # 8B penalty vs control comparison
uv run scripts/plot_control_grid.py            # Control grid view
```

Plots are saved to `plots/`.

### Dashboard

An interactive HTML dashboard provides browsable access to all eval data, plots, and individual model samples:

```bash
# Build the dashboard (reads from all eval dirs, generates dashboard.html)
uv run scripts/build_dashboard.py

# Deploy to Cloudflare Pages
npx wrangler pages deploy . --project-name feedback-spillover
```

The dashboard includes:
- Summary table of all runs with filtering by version, model size, condition, and data source
- All generated plots with descriptions
- Browsable per-sample eval results (prompt, CoT, output, scores) for every run/checkpoint

Live at: [feedback-spillover.pages.dev](https://feedback-spillover.pages.dev)

## Data Layout

```
logs/
├── eval-penalty/          — Original condition evals
├── eval-penalty-v2/       — V2 (pw=-2) evals
├── eval-penalty-v3/       — V3 (pw=-1) evals
├── eval-control/          — Control (pw=0) evals
├── grpo-{v2,v3,ctrl}-{8b,32b}-{condition}-{source}-s{seed}/
│   └── ...                — Training logs and checkpoints
├── sft-{8b,32b}-{condition}-{source}/
│   └── ...                — SFT training logs
└── gen-*.log              — SFT data generation logs

plots/                     — All generated plots (PNG)
```

Each eval directory contains one subdirectory per run, with JSONL files per checkpoint:
```
logs/eval-penalty-v2/grpo-v2-8b-pirate-output-qwen-s42/
├── grpo-v2-8b-pirate-output-qwen-s42_000100.jsonl
├── grpo-v2-8b-pirate-output-qwen-s42_000200.jsonl
├── ...
└── grpo-v2-8b-pirate-output-qwen-s42_final.jsonl
```

## Architecture

```
src/
├── judges.py              — WordMonitor, LLMJudge, SoftConversationJudge
├── parsing.py             — CoT/output extraction from <think> tags
├── spillover/
│   ├── train.py           — Paper-matching REINFORCE on Tinker
│   ├── train_grpo.py      — GRPO variant (group-relative advantages)
│   ├── train_grpo_mind_face.py — Mind & Face GRPO variant
│   ├── env_mmlu.py        — MMLU elementary_math (paper's exact format)
│   └── env_polynomial.py  — Polynomial derivative factoring
├── style/
│   ├── generate_data.py   — Style data generation
│   ├── sft.py             — Style SFT training
│   └── rl_enforce.py      — Style RL enforcement
└── analysis/
    ├── metrics.py         — Load metrics, compute spillover ratios
    └── plot.py            — Training curves and comparison plots

scripts/
├── launch_sft_all.sh              — Launch all 12 SFT training jobs
├── launch_grpo_penalty_v2.sh      — Launch V2 GRPO runs (pw=-2)
├── launch_grpo_penalty_v3.sh      — Launch V3 GRPO runs (pw=-1)
├── launch_grpo_control.sh         — Launch control GRPO runs (pw=0)
├── eval_all_penalty_checkpoints.py — Eval original conditions
├── eval_all_penalty_v2.py         — Eval V2 checkpoints
├── eval_all_penalty_v3.py         — Eval V3 checkpoints
├── eval_all_control.py            — Eval control checkpoints
├── generate_pirate_data_qwen.py   — Generate pirate SFT data (Qwen source)
├── generate_pirate_data_haiku.py  — Generate pirate SFT data (Haiku source)
├── build_dashboard.py             — Build interactive HTML dashboard
├── plot_combined_pareto.py        — Cross-condition Pareto comparison
├── plot_penalty_results.py        — Original penalty plots
├── plot_penalty_results_v2.py     — V2 penalty plots
├── plot_penalty_results_v3.py     — V3 penalty plots
├── plot_control_results.py        — Control condition plots
├── plot_pareto_all_conditions.py  — Older conditions Pareto
├── plot_8b_penalty_vs_control.py  — 8B penalty vs control comparison
├── plot_control_grid.py           — Control grid view
└── sample_outputs.py              — Sample model outputs for inspection
```

Training via [Tinker API](https://tinker-docs.thinkingmachines.ai). LLM judges via OpenAI (gpt-4o-mini).
