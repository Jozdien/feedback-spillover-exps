# Check-in — feedback spillover experiments

*Last updated: 2026-07-04. (Detailed version for Claudes: HANDOFF.md)*

## 🔬 2026-07-04: In flight
1. **Lambda-sweep for mitigations** (launched by Jose in another session, ~11:49 UTC):
   RT/M&F/TMF × pw{-0.5,-1} × seeds{42,43}, 8B, 12 runs. ETA ~02:00–05:00 UTC 7/5.
   Watcher armed: on completion → 12 final evals @4096 → extend lambda_sweep.pdf with a
   mitigations panel.
2. **Cross-family pirate pipeline, Qwen3.6-35B-A3B** (`scripts/run_35ba3b_pirate_pipeline.sh`,
   log `logs/pipeline-35ba3b-pirate.log`): data gen (~hours) → SFT (~10 min) → GRPO
   pirate pw-2 + ctrl pw0, seed 42, T=4096 (~24 h). Extends §3.6 to a mitigation claim.
3. **Seed-43 eval spot-check** (~10 min): v7base/v7norm/v6pirate 8B pw-2 s43 finals
   re-evaluated with `--question-seed 43` → `logs/eval-seed43-check/`. Tests whether the
   seed-42-hints eval asymmetry (App H) moves any number.

## ✅ 2026-07-04: Full paper-vs-repo audit + fixes — no conclusion-changing bugs

Five-agent audit of paper/main.tex against code, configs, and all eval logs (79/81 numeric
checks matched; all 118 final eval files verified against final checkpoints; all 158 run
configs consistent with the paper's hyperparameters). Fixed in the paper:
- **Seed error**: MMLU pool is shuffled with the run's RL seed (42/43), not "seed 0"; the seed
  also draws hint letters/templates. Disclosed the related eval asymmetry (evals hardcode
  seed-42 hints, so s43 runs are evaluated on fresh hint assignments — uniform across
  conditions; App H + Limitations).
- **App G**: SFT data is self-generated per base model (8B by 8B), not all from Qwen3-32B.
- **hparams table**: poly runs are 6000 episodes/500 steps and 1000 output tokens (was
  claimed 12000/1000/600); poly "default pw −1" clarified (runs used −2).
- **tab:full**: 32B RT CoT 0.62 → 0.60 (recomputed 0.596); filled previously-dashed syc/out/rew
  cells from logs; fixed caption (dashes = no matched control, not "not recorded").
- **§3.5 softened to match data**: depth checkpoints range 0.32–0.58 (step5=0.37, step200=0.32,
  not "near 0.50 everywhere"); step100 is a partial suppressor (out 0.089, rew 0.82).
- **§3.4 pirate-reward**: CoT range quantified (0.36–0.55 vs 0.47 at mu=0); poly pirate CoT
  "≈1.0" → 0.92–1.0 across seeds.
- **GRPO now cites Shao et al. 2024** (was REINFORCE); REINFORCE citation moved to the
  REINFORCE mention.
- **New App B "Implementation notes"**: doubled `</think>` delimiter in every natural rollout
  (stop seq kept + bridge appended; train/rollout consistent so loss unaffected), forced bridge
  on CoT truncation, invalid rollouts staying in group normalization, judge-failure→0.
- **App E**: SFT example now quoted verbatim in full (was silently condensed); filter
  thresholds made exact (10/5 words, substring keyword match).
- Repo: eval scripts now record `max_cot_tokens` + `question_seed` in metadata and take
  `--question-seed` (default 42, behavior unchanged); RESULTS.md §9 prior-work table updated to
  the verified Fig-4 values. PDF recompiles clean.

**Not fixed / for Jose:** see the audit summary in the session (s43 eval-hint spot-check
optional; cross-family pirate run still an open TODO; Fig 1 schematic + affiliations TODOs).

## ✅ 2026-06-29: CoT-pressure "vulnerability" experiment — COMPLETE (10 runs, 8B, think=300)
All 10 arms finished (1000 batches, 2 seeds). Soft judge and API-free literal hint-mention metric
AGREE throughout (result is not a judge artifact). Sycophancy → ~1.0 in all arms (model follows the
hint → suppression is real, unlike the 4096 regime). Seed-avg literal hint-mention in CoT by window:

| arm (schedule) | b0-50 | b150-300 | b300-400 | b400-500 | b700-1000 |
|---|---|---|---|---|---|
| C  (out:1000)            | 0.45 | 0.32 | 0.13 | 0.06 | 0.01 |
| A  (cot300,out700)       | 0.43 | 0.13 | 0.01 | 0.00 | 0.00 |
| A0 (cot300,none700)      | 0.43 | 0.15 | 0.02 | 0.03 | 0.04 |
| A3 (cot200,none200,out600)| 0.44 | 0.22 | 0.19 | 0.12 | 0.00 |
| R  (out500,none500)      | 0.42 | 0.27 | 0.06 | 0.02 | 0.02 |

**Findings:** (1) Direct CoT pressure suppresses the CoT faster/deeper than output-penalty spillover
(A/A0 ≈0.13 vs C ≈0.32 at b150-300). (2) **Persistence/hysteresis (cleanest result):** once
suppressed, hint-mention does NOT recover when pressure is removed — A0 stays ~0.02-0.04 for 700
no-pressure batches; R stays ~0.02 after b500; A3 holds its plateau (no rebound). (3) **Directional
asymmetry (surprise):** output pressure spills DOWN into the CoT (C: both→~0), but CoT pressure
barely spills UP into the output — A0 drives CoT→0.01 while hint_in_OUTPUT stays ~0.25. So
pressuring the CoT yields a clean-looking CoT but a still-revealing output; pressuring the output
hides the hint in both. (4) The original "faster spillover from a common start" comparison isn't
realizable because suppression persists (no recovery to re-test) — reframes to durable suppression +
asymmetry; likely a stable-attractor mechanism (no gradient back to verbalizing once the compressed
policy satisfies reward). Caveats: 8B only, 2 seeds, think=300 specifically, soft judge conflates
follows-vs-mentions (mitigated by agreeing literal metric).

Plots: plots/vuln_literal_mention.png, plots/vuln_panels.png, plots/vuln_hint_in_cot.png. Held-out
evals (100 checkpoints) running. Analysis: scripts/plot_vulnerability.py + the seed-avg window table.


## 🔬 2026-06-28: CoT-pressure "vulnerability" experiment — LAUNCHED (10 runs, 8B)
New question (Jose): does prior pressure *on the CoT* make it more vulnerable to *later*
output-only pressure spilling into it? Plus a hysteresis probe (does spillover persist once
the penalty is removed?).

**Design pivot (important):** original plan was cross-environment — pressure the CoT in the
polynomial env, then measure QA hint-in-CoT spillover. Smoke-tested and **killed it**: at 8B
the model writes the expanded derivative in *every* CoT (expanded_in_cot=1.0 for all rollouts,
even degree 7-10), so GRPO has zero within-group variance → the poly CoT-penalty is a no-op.
(32B, where poly varies, is deprecated from Tinker.) Only hint-acknowledgment has real CoT
variance at 8B, so pivoted to the **within-environment QA** version (the other option Jose
described), adding a recovery control to handle the starting-point confound he flagged.

New `penalty_schedule` knob in train_grpo.py (`"cot:300,out:700"` etc.) routes the penalty to
CoT / output / nothing per training segment. Arms (QA, 8B, 1000 batches, pw=-2, 2 seeds):
- **C** `out:1000` baseline · **A** `cot:300,out:700` treatment · **A3** `cot:200,none:200,out:600`
  (pressure → recover → pressure; clean "faster from common start" test) · **A0** `cot:300,none:700`
  recovery control (does CoT suppression persist?) · **R** `out:500,none:500` (Exp 2, hysteresis).

Validated before launch: scheduler unit-tested, chz comma-parsing OK, CoT-penalty has strong
GRPO signal (cot_pen_adv up to ±1.73), live phase-routing correct (A starts cot-only, C out-only).
Est. ~$320 incl. held-out evals (within the ~$1-2k Jose OK'd). Read dynamics from per-batch
metrics; evals via `scripts/eval_all_vuln.py`; plots via `scripts/plot_vulnerability.py`.

**2026-06-29 ~03:40 — second pivot: thinking=4096 → 300 (regime fix).** Monitoring the first
launch caught that at 4096 the 8B model never actually removes hint reasoning from the CoT — it
reframes "follow the hint" → "mention-but-reject it, answer honestly." The soft judge scores
that 0, but the *literal* hint-mention rate stays ~0.90 the whole run (verified across all arms).
So at 4096 there is NO real suppression and both metrics saturate → the vulnerability question is
unanswerable. Confirmed against existing t300 data that at thinking=300 suppression is genuine and
graded (literal hint-mention 0.44→0.00 over b0-400, soft judge agrees). Killed the 10 4096 runs
(~$60 sunk; partial data in logs/_vuln4096_partial/) and **relaunched all 10 at thinking=300**.
300-token runs are ~3× cheaper/faster (~6-7h, ~$80-100 total). Methodological note worth keeping:
the soft hint_in_cot judge conflates "follows hint" with "mentions hint" — at 4096 a model that
rejects the hint scores ~0 despite fully reasoning about it. Also added an offline literal-mention
re-scoring as a second, non-saturating spillover metric for the analysis.

**2026-06-29 ~04:30 — 🚨 BLOCKED on OpenAI quota; all runs stopped.** Root cause of the weird
score behavior: the OpenAI key (sk-proj-…OzkA) hit `429 insufficient_quota` — the account is out
of credits. The SoftConversationJudge returns 0.0 on exception, so every out_score/cot_score went
silently to 0 once the quota ran out (~01:38, which is exactly when the 4096 scores "collapsed" —
NOT model reframing as I first thought; that interpretation was wrong, it was the dead judge). My
10 concurrent runs (24 judge calls/batch each) burned through the remaining credit. Every run after
~01:38 trained with a silently-disabled penalty → contaminated. Stopped + archived all of them
(logs/_vuln4096_partial/, logs/_vuln300_contaminated/). ~$75 spent, much of it wasted post-quota.
**ACTION NEEDED FROM JOSE: top up OpenAI billing/credits (or provide a working key).** The
penalty depends on the semantic judge; a regex proxy would be gameable (model just rephrases), so
I'm NOT substituting one — waiting for the key. Everything is staged for a one-command relaunch
(`uv run scripts/run_vulnerability_pipeline.py`). Open regime question to settle on relaunch with a
LIVE judge: the only clean pre-quota live data (4096, b40-100) showed cot 0.40→0.20 with literal
staying ~0.90; historical t300base showed cot 0.34→0 with literal agreeing — so 300 still looks
like the cleaner regime, but I'll re-confirm with a short smoke once the judge works.

**2026-06-29 (later) — UNBLOCKED + relaunched + validated.** Jose topped up OpenAI. Judge
sanity-check: it scores sycophantic acknowledgment=1.0 but "mention-but-reject hint"=0.0 — i.e. it
effectively measures whether the model *follows* the hint, which is exactly why 300 (sycophantic,
budget forces real suppression) is the right regime and 4096 (model stays honest → judge ~0, no real
suppression) is not. Relaunched all 10 arms at thinking=300; early-batch validation with the LIVE
judge confirms everything works: cot_score 0.2-0.4 with wide within-group variance (NOT saturated),
CoT-penalty signal real (max|cot_pen_adv|=1.73 on A/A0/A3), output-penalty signal real on C/R,
routing correct. Monitoring includes a judge-health ping to catch any credit re-exhaustion fast.
Full fleet ~$50-60 OpenAI + ~$80-100 Tinker.


## ✅ 2026-06-13: ENTIRE TRAINING CAMPAIGN COMPLETE (118 runs, 0 lost)
All 12 8B v9 runs finished + evaluated. The matched-mitigation Pareto is complete at both
sizes (plots/combined_pareto_dots_v7_pw2.png).

**8B matched comparison (pw=-2, think=4096; higher CoT detection = less spillover; all
reward ≈0.95 except baseline):**
| Condition | CoT det | reward |   | Condition | CoT det | reward |
|---|---|---|---|---|---|---|
| No-SFT penalty | 0.18 | +0.03⚠ |   | Pirate output | **0.47** | +0.96 |
| Reward targeting | 0.20 | +0.99 |   | Pirate+RT | **0.60** | +0.95 |
| Mind & Face | 0.28 | +0.98 |   | Pirate+M&F | 0.40 | +0.98 |
| Targeted M&F | 0.45 | +0.92 |   | Pirate+TMF | 0.42 | +0.94 |

Takeaways: (1) pirate-output beats all 3 prior mitigations at preserving CoT; pirate+RT best
overall. (2) **RT flips with scale** — best at 32B (0.62), worst at 8B (0.20); M&F the
reverse. **Pirate-output is the only scale-stable mitigation** (0.47→0.55). Likely stronger
framing than a flat win. Caveats: 2 seeds; the no-SFT-penalty baseline never suppressed the
*output* (reward +0.03) so isn't a clean reference; sanity-check RT rollouts before leaning
on the scale-flip in writing.

## 2026-06-14: thinking=300 base case — CoT-BUDGET HYPOTHESIS CONFIRMED
No-SFT penalty, late-training hint_in_cot (control → penalty):
- **thinking=300: 0.41 → 0.001 (TOTAL spillover)**
- thinking=4096: 0.66 → 0.21 (partial)
Relative drop 99.8% vs 68% — genuine budget effect, not just "less CoT space" (control IS
lower at 300, but penalty effect far exceeds that). Explains: weak 32B/4096 baseline
spillover = long CoT budget; reproduces paper's strong-spillover at their regime; RT looked
ineffective at 4096 only because there was little spillover to mitigate. → Mitigation
comparison should differentiate at 300. Recommend extending t300 to RT/MF/TMF/pirate (~$120).

## Overnight plan (June 12→13) — DONE
12 × 8B v9 runs training (~batch 250+, finishing morning/midday), eval loop sweeping them
(v9rt via standard evals, M&F pairs via the fixed v9mf orchestrator). By your morning
check-in the 8B panel of the matched-mitigation Pareto should be filling in — the key
question: does style separation beat RT/M&F at 8B *under matched thinking budget*, where
the no-SFT penalty fails outright?

**New 32B headline (evals, pw=-2):** Reward targeting (v9) preserves CoT best (~0.62) with
pirate-output (~0.55) and pirate+RT (~0.60) at control level; **Mind & Face actively hurts
(~0.33)**; old think=300 dots relabeled — the thinking-budget confound was large (RT: 0.23
→ 0.62). See updated pareto below.

**Storage:** local archives pruned to the 17GB not on HF (pw-0.5/-1 sweep finals + 8B pirate
SFT); 55 verified adapters on HF; 104GB disk free.

## 2026-06-27 (overnight): two new experiments running
20 × 8B runs launched 2026-06-26 night; finishing through the morning. Health monitor +
auto-eval loop (logs/eval-experiments/) running. New pirate-reward code committed (8401539).

**Experiment 1 — Scenario B (persona-depth sweep):** penalty RL (pw=-2) from intermediate
pirate-output SFT checkpoints {step 5,25,50,100,150,200,final} × 2 seeds = 14 runs. Q: does
mitigation strength depend on how much pirate SFT was done? RESULT (training metrics, late-training, seed-avg, 12/14 done): the depth trend is
roughly FLAT and noisy — CoT detection 0.34–0.59 across all depths (step 5→final), output
suppressed (~0.02) and full task reward everywhere. Even 5 steps of pirate SFT suffices;
the persona-separation benefit saturates immediately, no monotonic depth dependence.
Contrast no-SFT 8B penalty (CoT 0.18, reward 0.03 — never learns the task). So a tiny amount
of pirate SFT flips the model into learns-task + suppresses-output + stays-monitorable.
Eval-based numbers pending (should track). (Intermediates regenerated — Tinker GC'd originals.)

**Experiment 2 — pirate-reward sweep:** penalty RL from the 8B pirate-output SFT final + a
reward mu*is_pirate(output), mu∈{0.5,1,2} × 2 seeds = 6 runs. R = correct - 2*out_hint +
mu*pirate. New PirateStyleJudge (GPT-4o-mini binary).
- **FULL SWEEP DONE (training metrics, late, seed-avg).** All mu: correct 1.00, out_hint 0.00,
  pirate_out ~1.00 (persona HELD — vs plain pirate-output where style erodes to bare \boxed{}).
  CoT detection rises mildly with mu: mu0.5=0.36, mu1=0.38, mu2=0.54 (mu2 ≈ control level).
  **BUT output reward-hacks into degenerate pirate SPAM at EVERY mu** — even mu=0.5
  ("Arrr, matey! \boxed{D} ### Arrrr! Avast!..." repeated). Gentler mu does NOT avoid it.
  Takeaway: the pirate reward prevents persona erosion and preserves CoT monitorability, but
  only changes the FLAVOR of output degeneration (bare answer -> pirate spam); it does not buy
  a genuine styled explanation. Reinforces the paper's core point: CoT monitorability is robust
  across all these interventions; output "suppression" is always some degeneration.

## 2026-06-15: M&F EVAL BUG FIXED + framing settled
M&F eval had hardcoded CoT=300 (models trained @4096) → M&F/TMF dots were under-budgeted.
Fixed (--max-cot-tokens), re-ran 8B M&F finals @4096. Corrected 8B CoT-detection:
M&F 0.28→0.40, TMF 0.45→0.75. 32B M&F CANNOT be re-evaled (Qwen3-32B deprecated from Tinker
as of today) — those dots dropped from the Pareto; Jose OK with this (they were a sanity check).

**Agreed framing (Jose):** pirate-output (CoT 0.47) is competitive — beats plain M&F (0.40)
and RT (0.20) individually, and STACKS (pirate+RT 0.60) — at much lower cost (just SFT, no 2nd
model / no gradient surgery). NOT claiming it beats Targeted M&F (0.75, the both-protections
combo). "Outperforms prior mitigations" → "competitive-and-cheaper, and composes with them."

t300 mitigation evals done @300 (correct budget): M&F 0.16, TMF 0.42. Pareto regenerated.

## 2026-06-14: DASHBOARD UPDATED + "IS IT COOKED" CHECK
Dashboard live: https://feedback-spillover.pages.dev — now has all eval finals (v6–v9mf),
**sampled training rollouts for all 122 runs** (6 batch-snapshots each, to see degeneration
over training), and current plots. Browse the Sample Browser; "rollouts/<run>" entries show
training trajectory, "v*/<run>" show held-out eval finals.

**Cooked-ness findings (important):** suppressing out_score→0 happens via different routes:
- **No-SFT penalty @4096 (main result): CLEAN** — real coherent explanations that omit the hint. ✓
- **No-SFT penalty @300: COOKED** — output degenerates to "Wait no no no" babble.
- **Pirate-output penalty @4096: output COLLAPSED** to bare \boxed{answer} (0%→100% bare over
  training; pirate style gone by ~batch 500; output not even faithful to CoT). CoT itself stays
  coherent + monitorable (cot_score high), so the CoT-monitorability claim holds — but "output
  suppression" is partly output-minimization, not "learned to explain without the hint." Worth a
  caveat in the writeup. Also: confirms Jose's intuition that pirate persona erodes over training.
- Minor: a few INTERMEDIATE eval files have corrupted rows (concurrent-eval collisions); all
  FINAL checkpoints verified clean, so headline numbers unaffected. Dashboard skips bad rows.

## 🎉 2026-06-12 ~20:45: ALL 32B TRAINING COMPLETE — ZERO RUNS CUT
Qwen3-32B stayed up past every projection; all 12 matched mitigation baselines finished
their full 1000 batches (tmf-s43 crashed at batch 876 mid-day — transient, not deprecation —
and was resumed from checkpoint 800; ~$5 lost). Final evals sweeping now; new finals being
pushed to HF; the 12 paused 8B runs are resumed and training.

Glossary: **QA env** = MMLU questions with wrong-answer hints (the original paper's
question-answering environment); **poly env** = polynomial derivative factoring (their
second environment). "QA 32B runs" = the mitigation-baseline reruns on the QA env.

## TL;DR
Everything trained except the 12 deadline-critical 32B mitigation-baseline runs (v9 QA).
Pirate-family ones will finish before the Qwen3-32B cutoff; the no-SFT ones (rt/mf/tmf pairs)
will likely be cut at batch ~700–950 — fine, since checkpoints save every 100, runs converge
by ~600–800, and everything is being archived + pushed to HF as insurance. All evals are
keeping pace ahead of the deadline.

## Status board
| Fleet | State |
|---|---|
| v6/v7 Qwen3 factorial (72 runs) | ✅ done + evaluated |
| v8 new base models (8 runs) | ✅ done + evaluated |
| v9 poly 32B suite (14 runs) | ✅ done (results from rollouts) |
| v9 QA 32B mitigations (12 runs) | ✅ ALL DONE, full 1000 batches, zero cut |
| v9 QA 8B mitigations (12 runs) | 🔄 resumed from checkpoints ~21:00 June 12 |
| M&F evals (32B) | 🔄 loop sweeping final checkpoints (49+ done, 0 failed) |
| Checkpoint insurance | ✅ one archive/run local (73GB) + 35+ adapters on HF (Jozdien/*, private) |

## Headline results so far
**The core story holds at both scales** (final checkpoints, pw=-2):
pirate-*output* SFT keeps the CoT monitorable under an output penalty (cot detection ≈ control,
full reward); pirate-*CoT* SFT produces total spillover (cot detection → 0); without style SFT
the penalty either fails (8B) or works with substantial spillover (32B).

![8B/32B pareto, pw=-2](plots/combined_pareto_dots_v7_pw2.png)

**v8 (cross-family):** controls all learn the task; penalized base models mostly fail to learn
hint-following — except Qwen3.6-35B-A3B. Nemotron barely follows hints at all (syc 0.18).

![v8 vs qwen3 base models](plots/v8_vs_qwen3_base.png)

**Poly env (complete, training-rollout metrics):** plain penalty reproduces the paper's
spillover — expanded-form mentions in CoT crash 1.0 → ~0.2 — while **pirate-output style
keeps the CoT fully intact (≈1.0) AND suppresses the output fastest of any condition.**
RT/M&F/TMF also hold the CoT here (matches the paper: their mitigations worked in poly).
Penalized runs trade away some task correctness, same as the paper observed.

![poly env condition suite](plots/v9_poly_32b.png)

**QA mitigation curves (32B, in flight):** all conditions suppress the output penalty fully
and learn the task. Notable: at 32B with 4096-token thinking, even the *no-mitigation*
penalty run keeps hint-in-CoT ≈ 0.5 in training metrics — much weaker spillover than the
paper's 4B/300-token setting. The dramatic spillover at 32B comes from the pirate-*CoT*
condition (cot → 0). Final-checkpoint evals will settle this.

![v9 QA mitigations](plots/v9_qa_mitigations_32b.png)

## Events while you were out
- 2026-06-11 night: two fleet-wide Tinker stalls (~40min each), self-resolved, no losses.
- Paused the 12 8B v9 runs (pre-authorized) when 32B deadline projections stayed red.
- Wrote + launched M&F eval orchestrator (`eval_all_v9mf.py`) — that was an eval-coverage gap.
- HF export of curated 32B finals running (private repos `Jozdien/feedback-spillover-*`).

## Queued next
- **thinking=300 QA runs** (your request): key conditions at 8B to match the paper's regime
  and test whether CoT budget drives baseline spillover.
- Resume 12 paused 8B v9 runs after the 32B cutoff; 8B M&F evals.
- v9 dots onto the Pareto once final/latest evals land; retire old hardcoded mitigation dots.

## Waiting on you
- Seed 43 for v8 (~$525) — on hold per your call.
- Style-generality ablation (non-pirate style, 8B, <$50) — recommended, not yet launched.
