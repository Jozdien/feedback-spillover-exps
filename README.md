# Feedback Spillover Experiments

Testing whether stylistic differentiation of Chain-of-Thought (CoT) reduces feedback spillover — the phenomenon where output-only supervision bleeds into the reasoning trace.

Based on [Output Supervision Can Obfuscate the CoT](https://arxiv.org/abs/2511.11584) and [Ryan Greenblatt's hypothesis](https://www.lesswrong.com/posts/FG54euEAesRkSZuJN/ryan_greenblatt-s-shortform?commentId=8ujSDfzxLnizbCfdJ) that stylistically distinct CoTs would reduce parametric spillover.

## Paper Replication

The core training loop (`src/spillover/train.py`) matches the paper's setup:

| Parameter | Paper | Ours | Notes |
|-----------|-------|------|-------|
| Model | Qwen3-4B (full) | Qwen3-8B (LoRA) | Tinker constraint |
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

## Experimental Conditions

### Paper Replication Tasks

**QA with Hints** (`src/spillover/env_mmlu.py`): MMLU elementary_mathematics with 6 sycophancy hint templates. Soft LLM judge detects hint acknowledgment. λ=2.

**Polynomial Derivative Factoring** (`src/spillover/env_polynomial.py`): Degree 5-8 polynomials. Factored derivative in output. String match penalty for expanded form. λ=1.

### Mitigation Conditions

| Condition | How to run |
|-----------|-----------|
| Baseline | `python -m src.spillover.train task=qa` |
| Styled checkpoint | `python -m src.spillover.train task=qa checkpoint=tinker://styled` |
| Mind & Face | `python -m src.spillover.train_mind_face task=qa` |
| Control (no penalty) | `python -m src.spillover.train task=qa penalty_weight=0` |

Style conditions (Chinese, Pirate, Cross-model, Reverse) are created via the style induction pipeline, then tested by passing `checkpoint=...` to `train.py`.

## Setup

```bash
uv sync
export TINKER_API_KEY=...
export OPENAI_API_KEY=...
```

## Usage

```bash
# Paper replication (QA baseline with penalty)
uv run python -m src.spillover.train task=qa penalty_weight=-2

# Paper replication (polynomial)
uv run python -m src.spillover.train task=polynomial penalty_weight=-1

# Control (no penalty)
uv run python -m src.spillover.train task=qa penalty_weight=0 log_path=/tmp/spillover-exps/control

# From styled checkpoint
uv run python -m src.spillover.train task=qa checkpoint="tinker://..." log_path=/tmp/spillover-exps/chinese

# Mind & Face mitigation
uv run python -m src.spillover.train_mind_face task=qa

# Style induction pipeline
uv run python scripts/run_style_induction.py --config configs/style_chinese.yaml
```

## Architecture

```
src/
├── judges.py              — WordMonitor, LLMJudge, SoftConversationJudge, etc.
├── parsing.py             — CoT/output extraction from <think> tags
├── spillover/
│   ├── train.py           — Paper-matching REINFORCE on Tinker
│   ├── train_mind_face.py — Frozen mind + trained face mitigation
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
├── run_style_induction.py        — End-to-end style training pipeline
├── generate_cross_model_data.py  — gpt-oss CoT + Qwen output datagen
├── generate_reverse_style_data.py — Reverse style datagen
├── eval_benchmarks.py            — Multi-benchmark evaluation
└── plot_benchmarks.py            — Benchmark comparison plots
```

Training via [Tinker API](https://tinker-docs.thinkingmachines.ai). LLM judges via OpenAI (gpt-4o-mini).
