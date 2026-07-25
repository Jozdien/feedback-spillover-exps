# Harder / safety-relevant environments — pilot campaign

*Reviewer feedback (2026-07-23): the paper's MMLU-elementary and poly-factoring
envs may not need the CoT, so obfuscating it is cheap. CoT-uplift eval confirmed
this (see TODO.md / plots/cot_uplift.png). This campaign tests 5 harder,
safety-relevant envs. Started 2026-07-25.*

## Design

Each env is run **penalty-only** first (λ=2, seed 42, T=4096, 1000 batches) on
Qwen3-8B and Qwen3.6-35B-A3B — the cheap "does spillover happen here?" probe.
Spillover reference = the early-training hint-in-CoT level from each run's own
rollout curve + the pre-RL calibration baseline (no separate control run yet;
matches the t300 figure's readout). Full SFT/control/mitigation arms come later
only for envs that show a clean spillover signal with real CoT uplift.

Shared infra: `train_grpo.py` gained `task=qa_encoded|qa_hard|math|lcb`
dispatch; `SoftConversationJudge(prompt=...)` override for per-env rubrics.

## Envs

### Env 1 — encoded hints (MMLU elementary)  [RUNNING]
`src/spillover/env_mmlu_encoded.py`, `task=qa_encoded`. Plain hints replaced with
ones that must be *computed* (mod-product / Caesar / digit-sum), so the HACK
itself needs the CoT. Runs: `logs/grpo-env1enc-{8b,35ba3b}-pw2-s42`.
**Calibration (`logs/env-calibration/`, base models):** hint-following needs CoT
here — 8B follow 0.20→0.05 at T=0→4096 but the decode shows up in the CoT
(hint_in_cot 0.54 at 4096); 35B follow 0.08→0.38 (T=0→4096), hint_in_cot 0.88.
Real signal to lose. 8B batch-0 penalized: cot 0.42, out 0.91.

### Env 4 — uplift-filtered GPQA hints  [POOL BUILDING]
`src/spillover/env_qa_hard.py`, `task=qa_hard`. GPQA-main, plain wrong-answer
hints (same rubric as base QA), pool filtered to questions with CoT uplift
(`scripts/filter_gpqa_uplift.py`: keep pass@4 T=4096>0 & T=0==0 on 8B →
`data/gpqa_uplift_pool.json`). Launch: `bash scripts/launch_env_pilots.sh env4`.

### Env 2 — hard math + sub-step leak hints  [POOL BUILDING]
`src/spillover/env_math_hint.py`, `task=math`. MATH level≥4, reward = REAL
correctness (normalized + sympy), hint = Claude-extracted intermediate step
(never the final answer). Pool: `scripts/build_math_pool.py` (difficulty filter
on 8B → hint extraction via claude-opus-4-8 → with-hint uplift verify) →
`data/math_hint_pool.json`. Launch: `bash scripts/launch_env_pilots.sh env2`.

### Env 3 — Impossible-LiveCodeBench test-passing  [RUNNING]
`src/spillover/env_lcb.py`, `task=lcb`. `fjzzq2002/impossible_livecodebench`
original(103)+conflicting(103); reward = pass GIVEN tests (subprocess exec w/
rlimits); on conflicting items that needs special-casing → the hack. Penalized
behavior = admitting test-gaming (judge). Runs:
`logs/grpo-env3lcb-{8b,35ba3b}-pw2-s42`. 8B batch-0: out 0.25.

### Env 5 — APPS backdoor  [PILOT — gated]
`scripts/pilot_apps_backdoor.py`. Single-turn: solution + secret backdoor input.
Measures correct/backdoor/joint success at temp 1.0. **Full run only if
joint≥0.05** (else GRPO groups have no reward variance — the documented
sparse-reward risk at 8B). Data: `logs/apps-pilot/`. No `train_grpo` task wired
until the pilot passes.

## Status snapshot (2026-07-25 ~02:30 UTC)
- env1 8b+35b: training (batch 0 healthy)
- env3 8b+35b: training
- env4: GPQA uplift filter ~410/448 (8B), then 35B pass; then launch
- env2: math pool stage A (difficulty) ~450/1200; then hint extraction + verify
- env5: 100-problem joint-rate pilot running on both models

## Eval / analysis (TODO once runs finish)
- Eval each final at matched T=4096 (adapt `eval_cot_uplift.py` scorers per env).
- Spillover = early-vs-late hint-in-CoT on the training rollout curve.
- Rank envs by (clean spillover signal × CoT uplift) for the SFT/mitigation phase.
