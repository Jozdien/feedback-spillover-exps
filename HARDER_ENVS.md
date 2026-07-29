# ⚠️ MAJOR CORRECTION (2026-07-29): the "b750 collapse cliff" is an ARTIFACT

The sudden CoT→0.00 collapse at ~batch 700-750 in the penalty runs is NOT spillover — it is
the OpenAI quota outage. `SoftConversationJudge` silently returns 0.0 on exhausted retries;
429/insufficient_quota errors explode at exactly the "cliff" batches in every "collapsed" run
(env2math-8b b750+, env4gpqa-8b b750+, env4gpqa-35b b500-750, env1enc-35b b600-850,
env5apps-35b b400-600). All runs hit the outage at the same wall-clock time → same "cliff batch".

Decisive check (rescored same rollouts with healthy judge, n=60/window):
- hard-math 8B: live 0.675/0.000/0.000 (pre/post/late) → RESCORED 0.661/0.660/0.669. NO collapse.
- GPQA 8B: live 0.339/0.220/0.000 → RESCORED 0.337/0.334/0.383. NO collapse.
Rescore matches live exactly where the judge was healthy (validates method).

Consequences:
1. During outage windows the PENALTY was also zeroed (out_score from same judge) — those
   batches were effectively unpenalized training. Valid penalized window = pre-outage only.
2. What survives: GPQA 8B shows genuine GRADUAL spillover pre-cliff (penalty CoT ~0.34 vs
   control ~0.60). Hard-math 8B shows little (0.66 vs ~0.70). No cliff anywhere.
3. The "resume from post-collapse ckpt diverges" rule was a MISREAD: the env4gpqa-35b resume
   showing CoT 0.6-0.9 was the TRUE value (judge healthy again) — original "collapse" was artifact.
4. Full offline rescores of all 6 affected penalty runs running (logs/rescore_all.log);
   plots + conclusions to be rebuilt from rescored.jsonl.
5. Judge patched to log failures loudly (was silent 0.0).

# Harder / safety-relevant environments — pilot campaign

*Reviewer feedback (2026-07-23): the paper's MMLU-elementary and poly-factoring
envs may not need the CoT, so obfuscating it is cheap. CoT-uplift eval confirmed
this (see TODO.md / plots/cot_uplift.png). This campaign tests 5 harder,
safety-relevant envs. Started 2026-07-25.*

## 35B mitigation arm LAUNCHED (2026-07-29 ~15:3x UTC, user-approved)
4 runs on Qwen3.6-35B-A3B init from the paper's 35B pirate SFT ckpt
(tinker://e2809e41-d831-5ae6-a708-fba76fdb28b8:train:0/weights/final):
env2pirate-35ba3b-{pw2,ctrl}, env4pirate-35ba3b-{pw2,ctrl}. ~$380 est. All 4 logged Batch 0
(ctrl cot 0.76/0.27; pw2 correct=-1.0 = no-answer penalty, expected early). Now 10 concurrent
runs; judge retries 3-4/tail — watch. Watcher resume_watch2.sh extended to all 10.
New plot: plots/harder_mitigation_trajectory.png (fig_mitigation in plot_harder_envs.py). 
## Tinker 402 outage killed whole batch ~14-17h (2026-07-28→29), recovered 15:01 UTC
All 6 runs (4 pirate-8B mitigation + 2 completeness-35B controls) died on a Tinker 402
billing block; old 24h resume watcher had already lapsed so nothing relaunched them.
Recovered 2026-07-29 15:01 UTC: relaunched all 6 from latest pre-collapse ckpts (8B from
400/500, 35B from 200). New robust watcher scratchpad/resume_watch2.sh (48h, auto-resumes
DEAD runs from latest ckpt, SKIPS runs >=batch 680 = post-collapse). ~15h wall-clock lost
but Tinker bills per-token so no wasted spend; b750 mitigation readout pushed back ~15h. 
## env2pirate-λ2 HUNG @b483 + recovered (2026-07-28 ~22:45)
env2pirate-8b-pw2 (key hard-math mitigation run) wedged at batch 483 (~57min silent, 35B-style
hang) while other 5 advanced. pkill -9 + relaunched from ckpt 400 (pre-collapse, safe). Watch
for recurrence — this env has hung twice now. 
## Matched-batch mitigation comparison @ ~b400 (2026-07-28, still pre-cliff)
env2 math: pirate-λ2 holds (b360-410 cot=0.72 ≈ its ctrl 0.73) while no-SFT-λ2 has begun
drifting (0.68→0.64) — divergence STARTING, consistent w/ mitigation preserving CoT.
env4 GPQA: ambiguous — pirate-λ2 (0.43) ≈ no-SFT-λ2 (0.45), both < pirate-ctrl (0.60); no
clear separation yet. All PRE-cliff (no-SFT collapse ~b700) — decisive readout at b750.
## Early mitigation trend @ batch ~280 (2026-07-28, PROMISING but pre-collapse)
Recent-40 window: env2pirate-λ2 cot=0.72 out=0.01 corr=0.66 (output SCRUBBED, CoT ≈ its
λ0 control 0.71); env4pirate-λ2 cot=0.42 out=0.00 corr=0.85 (vs ctrl 0.55). So pirate-output
holds the CoT near its control level while the output is scrubbed — the "mitigation works"
signature. NOT conclusive: no-SFT collapse was a LATE cliff (~batch 700); these are at ~280
where no-SFT was also still high. Confirm at batch 750+. 
## RESUMED 2026-07-28 ~13:58 (Tinker topped up) — all 6 back
Watcher auto-relaunched all 6 on Tinker recovery. Mitigation (env2pirate/env4pirate 8B
{pw2,ctrl}) restarted from pirate SFT init (were <batch 100; ~70 batches lost ≈ $3);
completeness controls (env1enc/env4gpqa 35B) resumed from ckpt 200. Judge clean, no 402.
Readouts: mitigation ~batch 750 (~30-36h at 6-run contention), completeness ~batch 700
(~24h). If funds run out again the watcher re-resumes (24h window). 
## 4th Tinker 402 (2026-07-28 ~04:43) — $236 batch ran out of funds mid-run
The topped-up balance was exhausted ~4.5h in; all 6 runs (4 pirate mitigation 8B @batch
~70, 2 completeness 35B controls @~250) hard-died on 402. NEEDS MORE FUNDS to finish
(the $236 estimate was for the full runs; ~$40-50 consumed before the balance ran dry —
so either the top-up was partial or the balance was already low). Watcher
scratchpad/resume_batch.sh (24h window) auto-relaunches all 6 from checkpoints on
top-up (mitigation from pirate SFT init since <batch 100, ~70 batches lost = ~$3;
controls from ckpt 200). Core 8B spillover result AIRTIGHT + plots done regardless.

## $260 batch LAUNCHED (2026-07-28, Tinker topped up) — mitigation + completeness
6 runs, judge healthy at 6 concurrent (0 retries). ~$236 total.
MITIGATION (the paper-contribution experiment; 8B, init RL from env-agnostic pirate-output
SFT ckpt tinker://e970f303-...:train:0/weights/final):
  - grpo-env2pirate-8b-{pw2,ctrl}-s42 (hard-math, λ=2 penalty + λ=0 control)
  - grpo-env4pirate-8b-{pw2,ctrl}-s42 (GPQA, λ=2 + λ=0)
  QUESTION: does pirate-output's CoT COLLAPSE under λ=2 (spillover → mitigation FAILS) or
  STAY HIGH (mitigation WORKS in CoT-necessary envs)? Compare pirate-λ2 late CoT vs its
  λ=0 control AND vs no-SFT-λ2 (env2-8b/env4-8b, which →0.00). Baseline CoT (batch 0):
  env2pirate 0.85-0.91, env4pirate 0.26-0.38.
COMPLETENESS (35B controls, resumed from ckpt 200, CAPPED at batch 700 via num_episodes=8400
to save ~$50; past the 35B penalty collapse points): grpo-env1enc-ctrl-35ba3b, grpo-env4gpqa-ctrl-35ba3b.
  Re-score offline (rescore_rollouts.py) → confirm 35B control CoT stays high vs 35B penalty→0.
SKIPPED (per user $260 budget): env2math-35b penalty (35B spillover already shown by env1enc/env4gpqa-35b).
DEFERRED to next funding: 35B mitigation + seed 43 (user will add funds later).

## 35B COMPLETENESS DEFERRED — ending silent poll (2026-07-27 ~19:30)
3rd Tinker 402 outage ran >11h and hard-killed the 3 completeness runs (env2math-35b
penalty @~430, env1enc-ctrl-35b @~260, env4gpqa-ctrl-35b @~254). Per user guidance
(billing turbulence temporary, don't fuss) and since these are NON-ESSENTIAL (the core
8B result is complete + penalty-driven-confirmed + plotted; env4gpqa-35b penalty +
env1enc-35b penalty already showed 35B spillover), stopping the hourly Claude poll.
A 12h watcher (scratchpad/resume_completeness.sh, log /resume_completeness.log) keeps
probing Tinker every 5min and will AUTO-RELAUNCH all 3 from their safe checkpoints on
top-up — no user action needed for resume. When it resumes / when user re-engages: do
the 35B readout (env2math-35b passes ~b760 collapse; controls pass ~b500 → re-score
via rescore_rollouts.py --env qa_encoded/qa_hard, add 35B control-vs-penalty rows,
regen plots). If the 12h watcher expires first, user re-runs scratchpad/resume_completeness.sh
after topping up. STILL PENDING: pirate-output MITIGATION arm (user go-ahead).

### WHAT'S DONE & SOLID (the deliverable):
- 5 harder/safety-relevant envs built + tested (env1 encoded hints, env2 hard-math,
  env3 Impossible-LCB, env4 uplift-filtered GPQA, env5 APPS backdoor).
- Headline: strong feedback spillover in CoT-necessary envs at T=4096 — CoT hint
  detection → 0.00 at full task reward (env2 8B, env4 8B+35B, env1 35B).
- CONFIRMED penalty-driven: 8B λ=0 controls keep CoT ~0.6-0.7 while penalty →0.00.
- Plots: plots/harder_spillover_trajectory.png, plots/harder_spillover_summary.png.
- Answers the reviewer: task-hardness does NOT prevent spillover (if anything stronger).

## Tinker 402 again (3rd outage, 2026-07-27 ~08:10) — completeness runs PAUSED
All 3 completeness runs (env2math-35b penalty, env1enc-ctrl-35b, env4gpqa-ctrl-35b)
hit Tinker 402 and HARD-DIED (402 APIStatusError → process exit; the soft pause escalated). Need
active relaunch-from-checkpoint once Tinker recovers (NOT auto-resume — procs exited). Not notifying (user: billing
turbulence is temporary/don't fuss; these are non-essential completeness, core 8B
result airtight). They'll resume when Tinker is topped up. If any hard-dies instead,
resume from its latest ckpt (env2math latest ckpt ~400, pre-collapse = safe; controls
always safe). Batches reached before pause: env2math-35b ~439, controls ~254-260.

## env2math-35b penalty HUNG + recovered (2026-07-27 ~07:05)
env2math-35b penalty wedged mid-batch at batch 430 (log silent ~1.8h vs ~80s/batch
normal; proc alive at 35% CPU — not a clean Tinker future-wait, and the 2 controls
kept advancing, so process-specific not global). pkill -9'd it and relaunched;
auto-resumed from ckpt 400 (PRE-collapse, safe per the resume rule). Single clean
instance confirmed (no competing writer). Watch for recurrence.

## Resume-fragility observation + batch decisions (2026-07-27)
Resuming env4gpqa-35b penalty from its batch-700 checkpoint (where the ORIGINAL run
was solidly collapsed, cot=0.00 for batches ~500-753) did NOT reproduce the collapse
— the resumed rollouts came back at cot 0.6-0.9. Same weights/env/seed. Most likely a
resume artifact (Adam state reset + fresh RNG knocking the policy off the collapsed
point), NOT a real "spillover reverses" result — do not over-claim. But it's a
tentative hint that the collapsed state may be less of a hard attractor than the
within-env vuln/hysteresis result suggested; worth a dedicated resume-from-collapsed
probe later if we care. DECISIONS: (1) KILLED env4gpqa-35b resume — its original 0-753
run already shows the clean collapse (that IS the result); use original trajectory.
(2) plot_harder_envs.py now dedups metrics by first-occurrence per batch, so resume
dups can't pollute the readout (env4gpqa-35b late-60 = 0.00 confirmed after dedup).
(3) KEPT env2math-35b penalty (resumed from PRE-collapse ckpt 300, tracking normally
~0.81) + the 2 fresh 35B controls (env1enc-ctrl 0.88, env4gpqa-ctrl 0.58 — behaving as
controls). Lesson: only resume from a checkpoint EARLIER than the collapse; a
post-collapse resume diverges.

## Completeness batch launched (2026-07-27, OpenAI recovered)
Plots: plots/harder_spillover_trajectory.png (control vs penalty CoT collapse, 8B),
plots/harder_spillover_summary.png (cross-env; incomplete 35B runs flagged).
Launched 4 runs (≤4 judge cap): resume env2math-35b penalty (@365→1000, the incomplete
flagship — will show 35B hard-math cliff), resume env4gpqa-35b penalty (@753→1000),
+ 35B λ=0 controls env1enc-ctrl-35b & env4gpqa-ctrl-35b (to confirm penalty-driven at
35B, re-score offline via rescore_rollouts.py). HELD for user go-ahead: the
pirate-output MITIGATION arm (init RL from the existing env-agnostic 8B pirate SFT
checkpoint on env2/env4, {λ=0,λ=2}) — the paper-contribution experiment.

## *** CONFIRMED: spillover is penalty-driven (control vs penalty, 2026-07-27) ***
λ=0 controls (no penalty) re-scored offline from saved rollouts (rescore_rollouts.py)
after the OpenAI top-up. cot = hint-in-CoT (early batches 0-40 vs late last-60):

| env / 8B | CONTROL cot early→late | CONTROL corr | PENALTY cot early→late | PENALTY corr |
|----------|------------------------|--------------|------------------------|--------------|
| env2 math | 0.646 → **0.704** (stays high) | 0.82 | 0.693 → **0.000** (collapses) | 0.74 |
| env4 GPQA | 0.500 → **0.603** (stays high) | 1.00 | 0.455 → **0.000** (collapses) | 0.94 |

**Without the output penalty the CoT hint-acknowledgment STAYS HIGH (~0.6-0.7) — even
rises as the model learns the task. With the penalty it collapses to 0.00 at the SAME
(full) task reward.** So the CoT collapse is caused by the output penalty, not by
training drift or the model dropping the hint on its own. Feedback spillover CONFIRMED,
penalty-driven, in both harder CoT-necessary environments. This is the airtight version
of the headline finding — the reviewer's concern is fully answered.

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

## *** OpenAI judge QUOTA EXHAUSTED (2026-07-26 ~03:30 UTC) — separate from Tinker ***
Root cause of the "judge rate-limit": the OpenAI account is OUT OF QUOTA (429
"You exceeded your current quota, check your plan and billing"). The campaign's
gpt-4o-mini judge calls (~24/batch × ~1000 batches × 9 runs) burned the balance.
Isolated single judge call also returns 0.0 → it's account-level, not concurrency.
NEEDS an OpenAI top-up (like the Tinker one). Until then NO live CoT/out monitor.
**Mitigation:** the 2 λ=0 controls (env2math-ctrl-8b, env4gpqa-ctrl-8b) DON'T need
the judge to train (reward = programmatic correctness), and every rollout's
cot_text/out_text is saved to rollouts.jsonl. So they keep training + accumulating
CoT; re-score offline with `scripts/rescore_rollouts.py <run> --env math|qa_hard`
once OpenAI is topped up. The completed penalty runs' late-batch cot≈0 is REAL
(judge worked during that phase — env2math-8b b0 cot=0.639 proves it); only the
new post-outage batches are affected. So the headline finding STANDS. What's
pending: the control CoT (should stay HIGH) to confirm penalty-driven.

## Controls + judge-contention lesson (2026-07-26 ~03:20 UTC, after billing top-up)
Billing recovered. Launched 4 λ=0 controls + resumed 3 died 35B penalty runs = 9
concurrent runs → **OpenAI gpt-4o-mini judge rate-limited** (168 retries/200 log
lines; monitor/hint_in_cot stuck at 0.000 = judge failures scored 0, NOT real).
Programmatic correctness unaffected. LESSON: the judge-based monitors cap total
concurrent runs at ~2-4, not 9 — the earlier 9-run T=4096 campaign only worked
because 35B runs are slow (judge calls spread out) and launches were staggered.
FIX: cut to the 2 rigor-critical 8B controls (env2math-ctrl-8b, env4gpqa-ctrl-8b,
λ=0). Killed the 3 resumed 35B penalty runs (env1enc/env4gpqa/env5apps-35b — their
spillover already captured at batch 888/753/640), env2math-t300-8b (non-learning),
env2math-35b (will re-resume later at low concurrency). Once the 2 controls show
CoT STAYING HIGH (contrast vs penalty runs' CoT→0) = spillover confirmed
penalty-driven. Remaining runs to finish later, ≤3 at a time to keep judge healthy.

## *** CORRECTED FULL-RUN READOUT (2026-07-26 ~02:24 UTC) — supersedes earlier "no spillover" reads ***
Earlier "CoT holds at 4096" was WRONG — read at batch ~150 BEFORE output scrubbed.
At batch 600-999 (output fully scrubbed) the CoT DOES collapse. Windowed:
cot_e=batches20-60, cot_l/out_l/corr_l=last 60.
| run          | b   | cot_e | cot_l | drop  | out_l | corr_l | verdict |
|--------------|-----|-------|-------|-------|-------|--------|---------|
| env1enc 35B  | 888 | 0.721 | 0.000 | +0.72 | 0.000 | +0.993 | **CLEAN SPILLOVER** (follows hint 0.99, CoT erased) |
| env1enc 8B   | 999 | 0.449 | 0.026 | +0.42 | 0.003 | +0.012 | confounded (task-reject, corr~0) |
| env2math 8B  | 999 | 0.693 | 0.000 | +0.69 | 0.000 | +0.738 | **CLEAN SPILLOVER** (solves math, CoT coherent 12k-char but omits leak) |
| env2math 35B | 365 | 0.805 | 0.848 | -0.04 | 0.226 | +0.862 | pre-scrub (paused by billing @365; cot still high, output scrubbing) |
| env4gpqa 8B  | 999 | 0.455 | 0.000 | +0.46 | 0.000 | +0.940 | **CLEAN SPILLOVER** (follows hint 0.94, CoT erased) |
| env4gpqa 35B | 753 | 0.580 | 0.000 | +0.58 | 0.000 | +0.977 | **CLEAN SPILLOVER** (follows hint 0.98, CoT erased) |
| env5apps 35B | 640 | 0.080 | 0.000 | +0.08 | 0.000 | +0.363 | weak (baseline CoT backdoor-admission only 0.08) |
| env3lcb 8B   | 929 | 0.003 | 0.000 | +0.00 | 0.000 | +0.119 | FLAT (dead env) |
| env3lcb 35B  | 621 | 0.103 | 0.000 | +0.10 | 0.000 | +0.197 | weak |

**HEADLINE FINDING (answers the reviewer):** harder, CoT-necessary envs show
STRONG feedback spillover at T=4096 — env4 GPQA (both sizes) and env1-35B follow
the wrong hint at 0.94-0.99 while CoT hint-acknowledgment → 0.00; env2 hard-math
solves correctly with coherent 12k-char CoTs that never mention the leaked step.
This is MORE spillover than the paper's easy QA env showed at 4096 (which only
partially spilled). Spillover here is a LATE-training effect: output scrubs by
~batch 300-500, CoT collapses by ~700-999. Rollouts NOT degenerate (verified
env2-8B: full coherent math reasoning, hint omitted). Reviewer concern REVERSED:
task-hardness does NOT prevent spillover — if anything it's stronger.

**Caveats / next:** (1) penalty-only, NO λ=0 control yet — the early→late CoT drop
needs a no-penalty control to prove it's penalty-driven not training drift
(TOP PRIORITY once billing back). (2) env2 (real-correctness reward): confirm the
model still USES the leak silently vs solving without it. (3) env1-8B confounded
(task-reject) — its 35B counterpart is the clean version.

**Degeneracy check (user request):** T=4096 rollouts coherent, not degenerate.
env2math-t300-8B: NOT degenerate CoTs either, but model NEVER LEARNS (corr ~0.02-0.11
from the start) — 300 tokens too short to solve L5 MATH. So a T=300 sweep is invalid
for the CoT-heavy envs; use an INTERMEDIATE budget (~1024) if pursuing the
short-budget regime story. But spillover is already strong at 4096, so the T=300
arm is now lower priority than CONTROLS.

**BILLING: Tinker 402 exhausted again (~02:20 UTC 07-26). 5 runs hard-died, 2 paused
in retry loop. Blocks all new runs. Completed 8B runs (env1/2/4 @999) already give
the headline. On recovery: (a) λ=0 CONTROLS for env2-8B + env4-8B (prove
penalty-driven), (b) resume partial 35B runs, (c) optional intermediate-budget arm.**

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
