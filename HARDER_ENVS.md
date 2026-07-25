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
- env4 8b+35b: training. GPQA uplift pool = 84/448 problems (CoT necessary: 8B
  solves w/ CoT at T=4096, fails at T=0; 77 also 35B-solvable). ALL 9 RUNS LIVE.
- env5: 35B ONLY, training. Pilot verdict: joint success 0.01 (8B, sparse, SKIPPED)
  vs 0.21 (35B, viable). APPS backdoor: reward=joint correct+working-backdoor,
  monitor=backdoor-admission judge. Pilot data logs/apps-pilot/.

## Early training snapshot (2026-07-25 ~03:25 UTC, all 9 alive, no crashes)
Batch N/1000, penalized (correct=task reward, out/cot=hint-in-channel):
- env1enc  8B b55: correct .08 out .16 cot .09 | 35B b30: .50 / 1.00 / .99
- env2math 8B b12: correct .75 out .18 cot .61 | 35B b8:  .67 / .31 / .87
- env3lcb  8B b33: correct -.08 out .00 cot .00 | 35B b25: .08 / .00 / .00 (flat)
- env4gpqa 8B b9:  correct .67 out .41 cot .66 | 35B b6:  .83 / .17 / .73
- env5apps 35B b13: correct -.25 out .23 cot .00
Reading: env2/env4 already show output scrubbed while CoT stays high (the
spillover-test setup — watch whether CoT falls by late training). env1-8B CoT
already low (possible early spillover, but task reward also low — watch). env5 CoT
backdoor-admission ~0 even early (model may not verbalize backdoor planning).

## Throughput & revised readout target (2026-07-25 ~03:56 UTC)
Per-batch wall time (typical): 8B QA/math ~40-75s; 35B QA/math ~100-175s; 35B
code-exec (env3/env5) ~130-285s with 600-730s spikes (code-execution timeouts).
=> 1000 batches is 10-20h (8B) to 30-55h (35B code). **Spillover develops in the
first few hundred batches** (cf. paper t300 regime study), so the pilot readout
targets **batch ~300-400**, not 1000. Runs keep going + checkpoint every 100;
read whatever batch they've reached. Full 1000-batch completion only if an env's
~300-batch signal is worth the extra compute.

Confound to remember: env1-8B early CoT drop (0.45→0.31 windowed) comes with task
reward ~0.05 — the model REJECTS the hint rather than learning it (the paper's
8B/4096 no-SFT failure mode), so that drop is not clean spillover. Judge
early-vs-late CoT only at maintained/high task reward.

## Partial trend @ batch ~70-130 (2026-07-25 ~04:49 UTC, 8B runs only)
cot_early = mean hint_in_cot batches 20-60; cot_now = last 20; corr_now = task reward.
| run              | b   | cot_early | cot_now | drop  | out_now | corr_now |
|------------------|-----|-----------|---------|-------|---------|----------|
| env1enc (encoded)| 130 | 0.449     | 0.376   | +0.073| 0.431   | +0.036   |
| env2math (math)  | 70  | 0.693     | 0.649   | +0.045| 0.230   | +0.476   |
| env3lcb (LCB)    | 82  | 0.003     | 0.000   | +0.003| 0.038   | +0.000   |
| env4gpqa (GPQA)  | 71  | 0.455     | 0.448   | +0.008| 0.310   | +0.710   |
**Too early to call spillover.** In the task-learning envs (env2/env4) the OUTPUT
isn't fully scrubbed yet (out 0.23-0.31) — the precondition for a CoT-spillover
read — and CoT has barely moved. env1's larger CoT drop is the confounded
task-rejection case (corr≈0). env3 flat-dead. Need batch ~300 (output scrubbed to
~0) before the early-vs-late CoT comparison is meaningful. 9 concurrent runs
contend for Tinker/judge capacity (~55-66s/batch effective on 8B), so batch 300 is
~2h out on 8B, many hours on 35B.

## READOUT @ batch 77-291 (2026-07-25 ~06:43 UTC) — classified
cot_e=hint_in_cot batches 20-60; cot_l/out_l/corr_l = last-40 means.
| run             | b   | cot_e | cot_l | drop  | out_l | corr_l | class |
|-----------------|-----|-------|-------|-------|-------|--------|-------|
| env1enc 8B      | 291 | 0.449 | 0.028 | +0.421| 0.004 | +0.006 | CONFOUNDED (task-rejection) |
| env1enc 35B     | 121 | 0.721 | 0.654 | +0.067| 0.571 | +0.299 | pre-scrub |
| env2math 8B     | 148 | 0.693 | 0.710 | -0.017| 0.252 | +0.494 | pre-scrub, CoT up, task learned |
| env2math 35B    | 77  | 0.805 | 0.831 | -0.026| 0.378 | +0.634 | pre-scrub, CoT up, task learned |
| env3lcb 8B      | 149 | 0.003 | 0.002 | +0.001| 0.033 | +0.081 | FLAT |
| env3lcb 35B     | 100 | 0.103 | 0.056 | +0.046| 0.016 | +0.159 | CoT holds (weak baseline) |
| env4gpqa 8B     | 157 | 0.455 | 0.452 | +0.003| 0.335 | +0.717 | pre-scrub, CoT holds, task learned |
| **env4gpqa 35B**| 84  | 0.580 | 0.587 | -0.006| 0.161 | +0.549 | **CoT HOLDS (output scrubbed, task learned) — cleanest no-spillover** |
| env5apps 35B    | 83  | 0.080 | 0.086 | -0.006| 0.492 | +0.102 | pre-scrub (weak CoT baseline) |

**Result (holding across the board):** every case where the task is LEARNED and the
output is (nearly) scrubbed shows the CoT HOLDING — no spillover at T=4096. The only
large CoT drop (env1-8B) is task-rejection, not spillover. This matches the paper's
weak-spillover-at-long-budget regime: **task hardness does NOT induce spillover at
4096; the CoT budget dominates.**

**T=300 contrast launched (2026-07-25 06:43):** `logs/grpo-env2math-t300-8b-pw2-s42`
(env2 hard-math, 8B, 300-tok CoT). Tests whether the harder env DOES spill at the
short budget (paper's total-spillover regime). If yes: env2 cleanly shows
budget-gated spillover in a genuinely CoT-necessary task — the strongest reviewer
response. 300-tok runs are ~3-5x faster/batch than 4096.

## Sharper trend @ batch 111-205 (2026-07-25 ~05:46 UTC, 8B; late window = last 40)
| run          | b   | cot_early | cot_late | drop  | out_late | corr_late | read |
|--------------|-----|-----------|----------|-------|----------|-----------|------|
| env1 encoded | 205 | 0.449     | 0.115    | +0.334| 0.064    | +0.002    | CONFOUNDED: output scrubbed but model REJECTS hint (corr≈0) → both channels drop; = paper 8B/4096 task-rejection, not spillover |
| env2 math    | 111 | 0.693     | 0.650    | +0.043| 0.256    | +0.396    | task learned, output scrubbing, CoT HOLDS → no spillover yet |
| env4 GPQA    | 116 | 0.455     | 0.454    | +0.002| 0.289    | +0.681    | task learned, output scrubbing, CoT HOLDS → no spillover yet |
| env3 LCB     | 117 | 0.003     | 0.002    | +0.001| 0.015    | +0.006    | flat-dead |

**Emerging (tentative) finding:** at T=4096 on 8B, where the task is genuinely
learned (env2/env4), the CoT does NOT spill — same weak-spillover regime as the
paper's original envs. env1's big CoT drop is task-rejection, not spillover. This
supports the paper's thesis that the CoT BUDGET (300 vs 4096), not task hardness,
drives spillover strength — harder tasks don't spontaneously induce spillover at
4096. NEEDS confirming at fuller batch counts (env2/env4 output not fully scrubbed
yet) and ideally a T=300 arm on the best env (env2) to show these DO spill at the
short budget like the QA env did.

## Env viability / CoT-necessity so far (from calibration + batch-0)
- **env2 (hard math)**: best CoT-necessity — L5 MATH, hint unlocks unsolved problems,
  strong baseline CoT signal (0.64). Reward = REAL correctness.
- **env1 (encoded)**: hack needs CoT (decode); baseline cot 0.42-0.88.
- **env5 (APPS backdoor)**: 35B-only; best safety relevance (AI-control).
- **env3 (LCB)**: WEAK — batch ~20 both models cot≈0.00, out≈0.00, correct negative
  (no-answer penalty firing). LCB-hard is too hard: models rarely pass the
  conflicting tests, so there's little test-gaming to acknowledge → little CoT
  signal to lose. Likely ranks last; if pursued, swap to LCB easy/medium problems.
- **env4 (GPQA)**: task needs CoT (uplift-filtered) but hack (plain hint) does not.

## Eval / analysis (TODO once runs finish)
- Eval each final at matched T=4096 (adapt `eval_cot_uplift.py` scorers per env).
- Spillover = early-vs-late hint-in-CoT on the training rollout curve.
- Rank envs by (clean spillover signal × CoT uplift) for the SFT/mitigation phase.
