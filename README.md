# Feedback Spillover Experiments

Testing whether stylistic differentiation of Chain-of-Thought (CoT) reduces feedback spillover — the phenomenon where output-only supervision bleeds into the reasoning trace.

Based on [Output Supervision Can Obfuscate the CoT](https://arxiv.org/abs/2511.11584) and [Ryan Greenblatt's hypothesis](https://www.lesswrong.com/posts/FG54euEAesRkSZuJN/ryan_greenblatt-s-shortform?commentId=8ujSDfzxLnizbCfdJ) that stylistically distinct CoTs would reduce parametric spillover.

## Approach

1. **Style induction**: Train Qwen3-8B to reason in Chinese (or pirate speak, etc.) via prompting → SFT → RL
2. **Spillover experiment**: RL on QA-with-hints where output mentions of the hint are penalized. Measure whether the CoT also suppresses hint mentions.
3. **Compare**: Baseline vs styled CoT vs known mitigations (Mind & Face, Reward Targeting)

## Setup

```bash
uv sync
uv pip install -e /path/to/tinker-cookbook
export TINKER_API_KEY=...
export OPENAI_API_KEY=...
```

## Usage

```bash
# Verify style prompting works
uv run python scripts/verify_style_prompting.py --style chinese

# Run style induction pipeline
uv run python scripts/run_style_induction.py --config configs/style_chinese.yaml

# Run spillover experiment
uv run python scripts/run_spillover.py --config configs/spillover_baseline.yaml
```

## Conditions

| Condition | Description |
|-----------|-------------|
| Baseline | Vanilla Qwen3-8B, standard CoT |
| Chinese CoT | Model trained to reason in Chinese |
| Pirate CoT | Model trained to reason in pirate speak |
| Mind & Face | Frozen "mind" generates CoT, trained "face" generates output |
| Reward Targeting | Per-token advantages: CoT gets task-only reward, output gets full reward |

## Architecture

- `src/judges.py` — Unified judge interface (`WordMonitor`, `LLMJudge`, `LanguageJudge`)
- `src/rewards.py` — Declarative reward composition via `RewardSpec`
- `src/parsing.py` — CoT/output extraction from `<think>` tags
- `src/style/` — Style induction pipeline (data gen, SFT, RL)
- `src/spillover/` — Spillover experiments (env, training variants)
- `src/analysis/` — Metrics and plotting

## Multi-Benchmark Evaluation

Evaluate any checkpoint across 7 benchmarks (GSM8K, MATH, MMLU, GPQA, MBPP, APPS, IFEval), measuring both correctness and style transfer:

```bash
# Evaluate base + all SFT checkpoints
uv run python scripts/eval_benchmarks.py --checkpoints base chinese_sft pirate_sft cross_model_sft

# Custom eval (specific benchmarks, sample count)
uv run python scripts/eval_benchmarks.py --checkpoints base --benchmarks gsm8k math --n 100

# Generate comparison plots
uv run python scripts/plot_benchmarks.py --input /tmp/spillover-exps/eval_all_results.json
```

## Multi-Task RL

Enforce style + correctness simultaneously across multiple benchmarks via round-robin RL:

```bash
uv run python scripts/rl_multi_task.py --style_name chinese --load_checkpoint_path <sft_checkpoint> \
    --tasks gsm8k math mmlu gpqa --style_weight 0.5
```

Training via [Tinker API](https://tinker-docs.thinkingmachines.ai). LLM judges via GPT-4o.

## Paper Replication: "Output Supervision Can Obfuscate the CoT"

Two additional environments replicate the core experiments from [arxiv 2511.11584](https://arxiv.org/abs/2511.11584):

### QA with Hints (`env_mmlu.py`)
MMLU + hard TriviaQA questions with misleading authority hints (6 templates). LLM judge (GPT-4o) detects hint references in output and CoT. Reward: `correct - 2.0 * hint_in_output`.

### Polynomial Derivative Factoring (`env_polynomial.py`)
Random degree 4-8 polynomials with factorable derivatives. Model must output factored form; penalty for showing expanded form. String matching with unicode normalization. Reward: `correct - 1.0 * expanded_in_output`.

```bash
# Run paper replication experiments
uv run python scripts/run_paper_replication.py --task qa --condition baseline
uv run python scripts/run_paper_replication.py --task qa --condition control
uv run python scripts/run_paper_replication.py --task polynomial --condition baseline
uv run python scripts/run_paper_replication.py --task polynomial --condition control
```
