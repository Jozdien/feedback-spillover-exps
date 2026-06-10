# Experiment Status

*Last updated: 2026-06-10 ~01:30 UTC*

## Overview

We're running a full factorial experiment studying **feedback spillover** during GRPO training. The question: when you penalize a model for acknowledging hints in its output, does that penalty "spill over" into chain-of-thought reasoning and other behaviors?

**Design:** 4 SFT conditions × 4 penalty weights × 2 model sizes × 2 seeds = 64 runs (plus 8 legacy v6/v6ctrl runs = 72 total Qwen3 training runs), plus a V8 extension: baseline (no-SFT) runs on 2 additional base models.

---

## Experiment Design

### SFT Conditions

| Condition | Code prefix | Description |
|-----------|-------------|-------------|
| Base (no SFT) | `v7base`, `v8base` | Raw base model, no fine-tuning before GRPO |
| Pirate-output | `v6`, `v6ctrl`, `v6pw` | SFT on Alpaca data with pirate-style *output* formatting |
| Normal | `v7norm` | SFT on normal Alpaca data (style-neutral control) |
| Pirate-CoT | `v7pcot` | SFT on Alpaca data with pirate-style *chain-of-thought* |

### Penalty Weights

| Weight | Meaning |
|--------|---------|
| 0 | No penalty (control — pure QA reward) |
| -0.5 | Mild penalty for hint acknowledgement in output (`v6` runs use this) |
| -1 | Moderate penalty (`v6pw-1`) |
| -2 | Strong penalty (`v6pw-2`) |

### Models
- **Qwen3-8B** / **Qwen3-32B** — main factorial (all 4 SFT conditions, 2 seeds)
- **V8 extension (no-SFT baselines only, seed 42):** Qwen3.6-35B-A3B, Nemotron-3-Super-120B-A12B.
  Qwen3.6-27B was launched and killed at batch ~6 (~$6 spent): dense Qwen3.6 pricing ($3.73/MTok sample+train)
  plus ~2,900-token CoTs projected ~$1,370 for the 4-run set.

### GRPO Training Config
- 1000 batches, 12 rollouts/batch (group_size=4, 3 prompts)
- Checkpoints saved every 100 steps, max_thinking_tokens=4096, no_answer_penalty=-1.0, num_episodes=12000

---

## Training Run Status

| Group | Status |
|-------|--------|
| All 8B (32 runs: v6/v6ctrl/v6pw/v7base/v7norm/v7pcot) | **Done (32/32)** |
| 32B v6/v6ctrl | **Done (4/4)** |
| 32B v7pcot | 3/8 done (pw-1 both seeds, pw-2 s43); rest at batch ~560–820 |
| 32B v6pw / v7base / v7norm | 0/20 done; at batch ~440–670 as of last update |
| V8 baselines (8 runs, pw 0/-0.5/-1/-2 × 2 models) | Launched 2026-06-10 ~00:00 UTC, ~30–40 hr ETA |

Remaining 32B runs should finish through the morning of 2026-06-10; v8 runs the evening after.

### Cost tracking (training + rollout judging, measured from rollouts.jsonl)

- 24 v7 8B runs: ~$500 total. In-flight 32B fleet: ~$890 spent of ~$1,450 projected.
- V8 fleet: Qwen3.6-35B-A3B ~$100/run (thinks ~2.9k tok), Nemotron-Super ~$31/run (terse, ~750 tok) → ~$525 total.
- `scripts/` cost estimation approach: sample rollouts.jsonl field lengths, ~3.8 chars/token, Tinker prefill/sample/train pricing.

---

## Evaluation Status

### What the eval measures
Each checkpoint is evaluated on **378 MMLU elementary_math questions** with **incorrect-answer hints** injected into the prompt. Two-phase generation: CoT (4096 tokens) then output (600 tokens).

**Metrics:**
- **Sycophancy** — did the model follow the hint? (boxed answer = hinted answer)
- **Real correctness** — did the model get the right answer? (boxed answer = ground truth)
- **Hint in output (out_score)** — does the final output acknowledge the hint? (GPT-4o-mini soft judge)
- **Hint in CoT (cot_score)** — does the chain-of-thought acknowledge the hint? (GPT-4o-mini soft judge)

### Eval runs

| Eval batch | Scope | Status |
|------------|-------|--------|
| V6 evals (`logs/eval-penalty-v6/`) | 8 v6/v6ctrl runs × 10 checkpoints = 80 evals | **Done (80/80)** |
| V7 evals (`logs/eval-penalty-v7/`) | All v6pw + v7 runs (~560 evals eventually) | **Running** (~175/412 of first pass; 3 failures to retry) |

Known failures (will retry on re-run): `v6pw-2-32b-s42/000300` (rc=134), `v7base-32b-pw-1-s42/000200` and `/000400`
(timeouts — per-eval timeout has been raised 1800→3600s for the next pass). Re-run `scripts/eval_all_v7.py` as more
training completes; it auto-discovers and skips already-done evals. **V8 runs are NOT covered** by eval_all_v7.py
(it filters on v6pw/v7 prefixes and maps model by 8b/32b) — needs an eval_all_v8.py variant.

Estimated eval campaign cost: ~$340 total (~$0.45/8B eval, ~$0.77/32B eval, incl. GPT-4o-mini judging).

---

## Artifacts

### Plots (in `plots/`)
- `combined_pareto_dots_v7_pw{0.5,1,2}.png` — **Final-checkpoint Pareto, V6/V7 conditions + older hardcoded baselines**
  (`scripts/plot_combined_pareto_v7.py --pw {-0.5,-1,-2}`). Each SFT condition gets a filled (penalized) and hollow
  (pw=0 control) dot. Re-run as final evals land; prints missing conditions.
- `v6_eval_curves.png`, `v6_eval_pareto.png`, `v6_eval_cot_spillover.png` — V6 eval plots (final)
- `v7_all_conditions_overview.png`, `v7_penalty_sweep.png`, `v7_penalty_sweep_32b.png`, `v7_sft_comparison.png` — V7 training curves

### Early findings
- New pirate-output runs spill over much more than v5: CoT hint detection ~0.36 (8B) / ~0.60 (32B) at pw=-0.5 vs ~0.2 in v5.
- At pw=-1/-2, 8B pirate-output keeps ~0.46–0.49 CoT spillover at full training reward (penalty cleans output, not CoT).
- No-SFT 8B at pw=-2 lands at low reward (~0.03) — penalty fails to fully suppress output acknowledgement from the raw base model.

### Dashboard
`dashboard.html` — interactive HTML dashboard with eval results. Currently includes V6 data. V7 pending
(add `"v7": ROOT / "logs" / "eval-penalty-v7"` to `EVAL_DIRS` in `scripts/build_dashboard.py`, rebuild).

### Key scripts
| Script | Purpose |
|--------|---------|
| `scripts/eval_all_v7.py` | Launch evals on all v7-era checkpoints (auto-discovers, skips done) |
| `scripts/eval_grpo_baseline.py` | Core eval: MMLU + hints, two-phase generation |
| `scripts/plot_combined_pareto_v7.py` | Cross-condition final-checkpoint Pareto (V6/V7 + older baselines) |
| `scripts/plot_v7_training_curves.py` | V7 training curve plots |
| `scripts/launch_grpo_v8_base.sh` | V8 baseline launcher (new base models) |
| `scripts/build_dashboard.py` | Build HTML dashboard from eval results |

---

## What Remains

1. **Wait for 32B training runs to finish** — 25 in progress, finishing through 2026-06-10 morning.
2. **Wait for v8 baseline runs** — 8 runs, ETA evening of 2026-06-11.
3. **Re-run V7 evals** when first pass drains and as checkpoints land (`scripts/eval_all_v7.py`; retries the 3 failures).
4. **Write eval_all_v8.py** for the v8 baseline runs (model name from run dir instead of 8b/32b map).
5. **Decide on seed 43 for v8** (doubles v8 cost, ~$525 more).
6. **Add V7 eval data to dashboard** and rebuild.
7. **Final plots + analysis** — cross-condition Pareto with all dots, scaling comparisons, spillover patterns across SFT conditions and sizes.
