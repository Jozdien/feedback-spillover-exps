# Feedback Spillover Experiments

Testing whether stylistic differentiation of Chain-of-Thought (CoT) reduces feedback spillover — the phenomenon where output-only supervision bleeds into the reasoning trace.

Based on [Output Supervision Can Obfuscate the CoT](https://arxiv.org/abs/2511.11584) and [Ryan Greenblatt's hypothesis](https://www.lesswrong.com/posts/FG54euEAesRkSZuJN/ryan_greenblatt-s-shortform?commentId=8ujSDfzxLnizbCfdJ) that stylistically distinct CoTs would reduce parametric spillover.

## Key Findings

### 1. Architectural mitigations work best for QA spillover

When penalizing hint references in model output, the penalty spills over into CoT (hint references disappear from CoT too). **Mind & Face** (frozen CoT model) provides the strongest protection:

| Condition | CoT hint rate | Output hint rate | Assessment |
|-----------|:---:|:---:|---|
| Mind & Face | **0.66** | 0.03 | Best — frozen mind protects CoT |
| Reward Targeting | **0.58** | 0.04 | Strong — per-token advantages help |
| Chinese SFT | **0.42** | 0.32 | Best style-based approach |
| Rev Chinese | 0.35 | 0.36 | Moderate |
| Pirate SFT | 0.27 | 0.24 | Similar to baseline |
| Baseline | 0.25 | 0.22 | Standard spillover |
| Cross-model | 0.03 | 0.01 | Catastrophic — concise style strips everything |

*Higher CoT hint rate = less spillover = better protection. Control (no penalty) has hint_cot=0.24.*

### 2. Cross-model CoT uniquely prevents polynomial spillover

When penalizing the expanded derivative form in output, the model moves the computation into CoT. Only cross-model (gpt-oss-120b reasoning style) prevents this:

| Condition | Expanded in CoT | Expanded in output | Assessment |
|-----------|:---:|:---:|---|
| Cross-model | **0.00** | 0.00 | Only condition preventing migration |
| Control | 0.06 | 0.94 | No penalty reference |
| Baseline | 0.50 | 0.50 | Moderate spillover |
| Chinese/Pirate SFT | 0.50 | 0.50 | Same as baseline |
| Rev Chinese | 0.56 | 0.44 | Slight spillover |
| Rev Pirate | 0.75 | 0.25 | Heavy spillover |

### 3. No single mitigation works for both tasks

- **Mind & Face**: Best for QA, not tested on polynomial
- **Cross-model**: Best for polynomial, worst for QA
- **Chinese SFT**: Helps QA (only surviving style), neutral for polynomial
- **Style differentiation**: Generally unreliable — styles often get destroyed by RL training

### 4. Style robustness matters

Only Chinese CoT survives spillover RL training. Pirate speak and cross-model styles are destroyed, reverting the model to baseline behavior. This makes the style barrier ineffective for those conditions.

## Experimental Setup

### Style Conditions Tested

| Condition | CoT style | Output style | How created |
|-----------|-----------|-------------|-------------|
| Baseline | Normal English | Normal English | Base Qwen3-8B |
| Chinese CoT (SFT) | Chinese | English | SFT on Chinese math reasoning data |
| Chinese CoT (SFT+RL) | Chinese | English | + RL with LanguageJudge reward |
| Pirate CoT (SFT) | Pirate speak | English | SFT on "Captain Thinkbeard" data |
| Pirate CoT (SFT+RL) | Pirate speak | English | + RL with GPT-4o style reward |
| Cross-model CoT | gpt-oss-120b style | English | SFT on gpt-oss reasoning + Qwen output |
| Reverse Pirate | English | Pirate speak | SFT on normal CoT + pirate output |
| Reverse Chinese | English | Chinese | SFT on normal CoT + Chinese output |
| Mind & Face | Frozen base model | Trained | Architectural: separate CoT/output models |
| Reward Targeting | Normal | Normal | Algorithmic: per-token advantage targeting |

### Two Tasks (Paper Replication)

**QA with Hints** (`src/spillover/env_mmlu.py`): MMLU + hard TriviaQA questions with 6 authority hint templates. LLM judge (gpt-4o-mini) with conversation context detects hint acknowledgment. λ=2.

**Polynomial Derivative Factoring** (`src/spillover/env_polynomial.py`): Degree 4-8 polynomials. Model must output factored derivative. String match penalty for expanded form. λ=1.

### Additional Experimental Setups

**Hard Questions** (`scripts/run_hard_spillover.py`): TriviaQA questions the model can't answer (filtered by 5 failed attempts), with the correct answer as the hint. Forces genuine sycophancy-hiding behavior.

**Multi-Benchmark Eval** (`scripts/eval_benchmarks.py`): Evaluate style transfer across GSM8K, MATH, MMLU, GPQA, MBPP, APPS, IFEval.

**Multi-Task RL** (`scripts/rl_multi_task.py`): Enforce style across multiple benchmarks simultaneously.

## Setup

```bash
uv sync
export TINKER_API_KEY=...
export OPENAI_API_KEY=...
```

## Usage

```bash
# Paper replication (v2, matching paper's exact setup)
uv run python scripts/run_paper_replication.py --task qa --condition baseline
uv run python scripts/run_paper_replication.py --task polynomial --condition baseline

# With a styled checkpoint
uv run python scripts/run_paper_replication.py --task qa --condition chinese_sft \
    --checkpoint "tinker://..."

# Style induction pipeline
uv run python scripts/run_style_induction.py --config configs/style_chinese.yaml

# Hard questions spillover
uv run python scripts/run_hard_spillover.py checkpoint=... epochs=3

# Cross-model data generation
uv run python scripts/generate_cross_model_data.py --max-questions 2500

# Evaluation
uv run python scripts/eval_benchmarks.py --checkpoints base chinese_sft pirate_sft
```

## Architecture

```
src/
├── judges.py          — WordMonitor, LLMJudge, ConversationJudge, LanguageJudge
├── parsing.py         — CoT/output extraction from <think> tags
├── rewards.py         — Declarative reward composition
├── style/             — Style induction (datagen, SFT, RL enforcement)
├── spillover/         — Spillover experiments
│   ├── env.py         — HintQA environment (TriviaQA, keyword monitor)
│   ├── env_hard.py    — Hard questions (correct-answer hints)
│   ├── env_mmlu.py    — Paper QA replication (MMLU, LLM judge)
│   ├── env_polynomial.py — Polynomial derivative factoring
│   ├── train.py       — Standard RL training
│   ├── train_mind_face.py — Mind & Face mitigation
│   └── train_reward_target.py — Reward Targeting mitigation
└── analysis/          — Metrics loading and plotting

scripts/
├── run_paper_replication.py    — Paper replication experiments
├── run_spillover.py            — Original spillover experiments
├── run_hard_spillover.py       — Hard questions experiments
├── run_style_induction.py      — Style training pipeline
├── iterate_pirate.py           — Iterative pirate prompt/SFT pipeline
├── generate_cross_model_data.py — gpt-oss CoT + Qwen output datagen
├── generate_reverse_style_data.py — Reverse style datagen
├── eval_benchmarks.py          — Multi-benchmark evaluation
├── rl_multi_task.py            — Multi-task RL
├── run_all.py                  — Generate comparison plots
└── plot_benchmarks.py          — Benchmark comparison plots
```

Training via [Tinker API](https://tinker-docs.thinkingmachines.ai). LLM judges via OpenAI (gpt-4o-mini).
