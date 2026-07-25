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

## Status snapshot (2026-07-25 ~03:02 UTC)
- env1 8b+35b: training (batch 0: 8B cot 0.42 out 0.91)
- env2 8b+35b: training — pool DONE (108 problems, hint unlocks task; nh 0→wh 1
  cases). 8B batch 0: correct 0.33, out 0.60, cot 0.64 (strong baseline CoT signal).
- env3 8b+35b: training (8B batch 0 out 0.25)
- env4: GPQA uplift filter on final 35B stage (~384/448); launches when pool lands
- env5: 35B ONLY, training. Pilot verdict: joint success 0.01 (8B, sparse, SKIPPED)
  vs 0.21 (35B, viable). APPS backdoor: reward=joint correct+working-backdoor,
  monitor=backdoor-admission judge. Pilot data logs/apps-pilot/.

## Env viability / CoT-necessity so far (from calibration + batch-0)
- **env2 (hard math)**: best CoT-necessity — L5 MATH, hint unlocks unsolved problems,
  strong baseline CoT signal (0.64). Reward = REAL correctness.
- **env1 (encoded)**: hack needs CoT (decode); baseline cot 0.42-0.88.
- **env5 (APPS backdoor)**: 35B-only; best safety relevance (AI-control).
- **env3 (LCB)**: reward-hacking realism; baseline out 0.25 (lower signal, watch).
- **env4 (GPQA)**: task needs CoT (uplift-filtered) but hack (plain hint) does not.

## Eval / analysis (TODO once runs finish)
- Eval each final at matched T=4096 (adapt `eval_cot_uplift.py` scorers per env).
- Spillover = early-vs-late hint-in-CoT on the training rollout curve.
- Rank envs by (clean spillover signal × CoT uplift) for the SFT/mitigation phase.
