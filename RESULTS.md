# Results reference — "Style separation mitigates feedback spillover"

*Purpose: single source to write the paper draft from. Every result below has its numbers,
the plot, the eval data path, and the generating script. All numbers are seed-averaged
final-checkpoint eval values (2 seeds: 42, 43) unless noted. Companion docs: CHECKIN.md
(status), HANDOFF.md (infra/gotchas), TODO.md (task list).*
*Written 2026-06-16.*

---

## 0. Thesis & framing (settled with Jose)

**Claim:** Giving the CoT and the output *different styles* (via cheap output-style SFT before
RL) mitigates feedback spillover — an output-only penalty stops obfuscating the CoT. It is
**competitive with the prior mitigations** of arXiv 2511.11584 (reward targeting, Mind & Face),
**beats them individually** on monitorability, **composes with reward targeting**, and costs
far less (just SFT — no second model, no gradient surgery). We do NOT claim it beats the
strongest combined prior mitigation (Targeted M&F).

**Reference paper:** "Output Supervision Can Obfuscate the Chain of Thought" (arXiv 2511.11584,
Drori/Marks et al., MATS). PDF read; key facts in §8. They introduce feedback spillover +
two mitigations (reward targeting for *conditional* spillover, Mind & Face for *parametric*),
and find in their QA env ALL mitigations failed (Targeted M&F best, −30% task reward).

**Secondary contributions:**
1. Feedback spillover is **regime-dependent**: strong at short CoT budget (thinking=300, the
   paper's setting) and at 8B; weak at 32B/4096. We characterize this (§5).
2. **Pirate-CoT SFT *induces* total spillover** — a clean demonstration that *where the
   penalized style lives* (output vs CoT) determines spillover (§2).
3. Cross-model generality of spillover (§7).

---

## 1. Core result — style separation preserves CoT monitorability (QA, pw=-2)

**Plot:** `plots/pareto_sft.png` (8B + 32B; dotted line = each model's no-penalty CoT level).
**Script:** `scripts/plot_pareto_clean.py`. **Data:** `logs/eval-penalty-v6/` (pirate-output),
`logs/eval-penalty-v7/` (no-SFT/normal/pirate-CoT).

Metric guide: **cot** = hint acknowledged in CoT (monitorability; higher = less spillover).
**out** = hint acknowledged in output (the penalized behavior). **syc** = followed hint (the
task reward signal). **real** = got the true answer. **rew** = syc − 2·out (training reward).

### 8B (seed-avg, n=2)
| Condition | control cot (pw0) | penalized cot (pw-2) | out (pen) | syc (pen) | rew (pen) |
|---|---|---|---|---|---|
| No SFT | 0.67 | 0.18 | 0.008 | 0.05 | +0.03 |
| Normal SFT | 0.54 | 0.25 | 0.018 | 0.43 | +0.40 |
| **Pirate output** | 0.50 | **0.47** | 0.018 | 1.00 | +0.96 |
| Pirate-CoT | 0.74 | **0.00** | 0.002 | 1.00 | +0.99 |

### 32B (seed-avg, n=2)
| Condition | control cot | penalized cot | out (pen) | syc (pen) | rew (pen) |
|---|---|---|---|---|---|
| No SFT | 0.78 | 0.50 | 0.006 | 1.00 | +0.99 |
| Normal SFT | 0.60 | 0.44 | 0.007 | 1.00 | +0.98 |
| **Pirate output** | 0.59 | **0.55** | 0.000 | 1.00 | +1.00 |
| Pirate-CoT | 0.83 | **0.00** | 0.002 | 0.99 | +0.99 |

**Reading:** Pirate-output's penalized CoT (0.47 @8B, 0.55 @32B) ≈ its own no-penalty control
(0.50, 0.59) → the output penalty did NOT spill into the CoT. It fully suppresses output
(out≈0) at full reward. Normal SFT and No SFT lose much more CoT signal (and at 8B don't even
learn the task — see §6 nuance). **Full penalty-weight sweep (pw 0/-0.5/-1/-2)** for all four
conditions both sizes: `plots/combined_pareto_dots_v7_pw{0.5,1,2}.png` — pirate-output keeps
cot≈control at every pw.

---

## 2. Pirate-CoT SFT INDUCES total spillover (key mechanism demonstration)

Same data as §1. Pirate-CoT (styled *reasoning*, plain output) + penalty → **cot → 0.00 at
full reward, both sizes** (control cot 0.74/0.83). This is the cleanest result in the paper:
when the penalized behavior's "surface" (the output) is plain but the *reasoning* carries the
style, the penalty drives the CoT's hint-acknowledgement to zero — total obfuscation.

Contrast with pirate-*output* (no spillover): the asymmetry shows it's not "stylistic
dissimilarity" per se, but **which channel the penalty targets relative to the style**.
Mechanism framing (Jose, one-line in discussion): pirate-output installs a persona-level
output/CoT separation; we do NOT run a mechanism experiment (a style-over-time probe can't
falsify it — see TODO "DEPRIORITIZED").

---

## 3. Pirate-output vs prior mitigations — 8B, thinking=4096, pw=-2

**Plot:** `plots/pareto_mitigations.png`. **Script:** `scripts/plot_pareto_clean.py` (fig 2).
**Data:** `logs/eval-penalty-v7/grpo-v9rt-8b-*` (RT), `logs/eval-penalty-v9mf/grpo-v9{mf,tmf}-8b-*`
(M&F/TMF, **re-evaluated at 4096 — see §9 eval bug**), `logs/eval-penalty-v6/` (pirate).

| Condition | cot (↑ better) | out | rew | cost |
|---|---|---|---|---|
| No SFT (penalty only) | 0.18 | 0.008 | +0.03 | — (fails task @8B, see §6) |
| Reward targeting | 0.20 | 0.005 | +0.99 | gradient routing |
| Mind & Face | 0.40 | 0.004 | +0.99 | 2× model (mind+face) |
| **Pirate output (ours)** | **0.47** | 0.018 | +0.96 | **just SFT** |
| Targeted M&F | 0.75 | 0.000 | +1.00 | 2× model + gradient routing |

**Reading:** pirate-output (0.47) beats RT (0.20) and plain M&F (0.40) on monitorability, at
full reward and lowest cost. Targeted M&F (both protections) is the single best CoT-preserver
(0.75) — we do not claim to beat it. Story = "competitive-and-cheaper, beats the individual
prior mitigations."

---

## 4. Stacking — pirate-output + existing mitigations (8B, 4096, pw-2)

**Plot:** `plots/pareto_stacking.png`. **Script:** `plot_pareto_clean.py` (fig 3).
**Data:** `logs/eval-penalty-v9mf/grpo-v9{rtpirate,mfpirate,tmfpirate}-8b-*` (rtpirate is in
`logs/eval-penalty-v7/`).

| Condition | cot | rew |
|---|---|---|
| Pirate output | 0.47 | +0.96 |
| **Pirate + Reward targeting** | **0.60** | +0.95 |
| Pirate + Mind & Face | 0.38 | +0.99 |
| Pirate + Targeted M&F | 0.42 | +0.94 |

**Reading (IMPORTANT — don't overstate):** only **Pirate+RT improves** on pirate alone
(0.47→0.60). Pirate+M&F and Pirate+TMF are ~equal-or-slightly-lower. Frame stacking
specifically around reward targeting (the cheap, no-extra-model one): "composes with reward
targeting to give the best result short of standalone Targeted M&F."

---

## 5. Feedback spillover is regime-dependent — CoT budget (thinking=300 vs 4096)

**Plot:** `plots/t300_vs_4096_spillover.png` (3-panel training curves, no-SFT, pw0 vs pw-2,
300 vs 4096). **Script:** `scripts/plot_t300.py`. **Data:** training metrics
`logs/grpo-t300base-8b-*/metrics.jsonl` and `logs/grpo-v7base-8b-*/metrics.jsonl`.

No-SFT penalty effect on hint-in-CoT (training metric, late-training, seed-avg):
- **thinking=300: 0.41 → 0.001 (TOTAL spillover)**
- thinking=4096: 0.66 → 0.21 (partial)

Relative drop 99.8% vs 68% — a genuine CoT-budget effect, not just "less room to mention the
hint at 300" (control IS lower at 300, 0.41 vs 0.66, but the penalty effect far exceeds that).
Explains: (a) why our 32B/4096 baseline barely spills, (b) reproduces the paper's strong
spillover at their 300-token regime.

**Caveat for writeup:** at 300 the no-SFT penalty run reaches full reward by reward-hacking
(syc=1.0, babble output → out≈0); at 4096 it instead answers honestly (real_correct=0.94,
syc=0.05) and never learns the sycophancy task (rew 0.03). So the two budgets aren't a perfectly
clean apples-to-apples — different failure modes. State this.

---

## 6. Mitigations in the short-CoT regime — 8B, thinking=300, pw-2

**Plot:** `plots/pareto_mitigations_t300.png`. **Script:** `scripts/plot_pareto_t300_mitigations.py`.
**Data:** `logs/eval-penalty-t300/` (all trained AND evaluated at max_thinking_tokens=300).

| Condition | cot @300 | rew @300 | (cot @4096 for ref) |
|---|---|---|---|
| No SFT (penalty only) | 0.00 | +0.99 | 0.18 |
| Reward targeting | 0.08 | +1.00 | 0.20 |
| Mind & Face | 0.16 | +1.00 | 0.40 |
| **Pirate output** | **0.37** | **+0.76** | 0.47 |
| Targeted M&F | 0.42 | +1.00 | 0.75 |

**Reading:** the ranking is **robust across budgets** — pirate-output beats RT and M&F
individually on monitorability at 300 too (0.37 vs 0.08/0.16), TMF best in both. **Wrinkle:**
at 300 pirate-output pays a reward cost (0.76 vs 1.0 — out≈0.11, doesn't fully suppress the
output), so TMF dominates it there on both axes. The no-SFT baseline flips behavior vs 4096
(reward-hacks to full reward + total spillover here; fails the task at 4096).

---

## 7. Second environment — polynomial derivative factoring (32B)

**Plot:** `plots/v9_poly_32b.png` (3-panel: correctness / expanded-form-in-output /
expanded-form-in-CoT). **Script:** `scripts/plot_v9_training_curves.py` (poly section).
**Data:** training rollouts `logs/grpo-v9poly-*-32b-*/{metrics.jsonl,rollouts.jsonl}` — poly
uses a STRING-MATCH monitor (no LLM judge), metrics are from training, no separate eval needed.
Prompt requests an explanation in the output but does NOT reward it (matches the paper);
`src/spillover/env_polynomial.py` SYSTEM_PROMPT.

- Plain **penalty reproduces the paper's spillover**: expanded-form in CoT 1.0 → ~0.2.
- **Pirate-output: CoT intact (≈1.0) AND fastest output suppression** of any condition
  (bare-boxed by batch ~100 vs ~150–400 for RT/M&F/TMF).
- RT / M&F / TMF also hold the CoT here (consistent with the paper's poly results, where their
  mitigations *did* work — unlike their QA env).

Conditions present (×2 seeds, 500 batches): ctrl(pw0)/penalty/rt/mf/tmf/pirate/pirate-ctrl(pw0).

---

## 8. Cross-model generality of spillover (v8, no-SFT, seed 42 only)

**Plot:** `plots/v8_vs_qwen3_base.png`, `plots/v8_training_curves.png`.
**Script:** `scripts/plot_v8_training_curves.py`. **Data:** `logs/eval-penalty-v8/`,
`logs/grpo-v8base-*/metrics.jsonl`. New base models, no SFT, 4 penalty weights, seed 42.

| Model (pw-2) | cot (pen) | out (pen) | syc | real | rew |
|---|---|---|---|---|---|
| Qwen3.6-35B-A3B | 0.85 | 0.027 | 0.98 | 0.02 | +0.92 |
| Nemotron-3-Super-120B | 0.21 | 0.012 | 0.99 | 0.01 | +0.97 |

- **Qwen3.6-35B-A3B**: learns hint-following, output suppressed, CoT barely drops (0.85) — very
  weak spillover (like 32B Qwen3).
- **Nemotron-120B**: hint-resistant at baseline (control out only 0.68 vs ~0.9 for others; at
  ckpt-100 syc=0.18, real=0.82); under penalty its CoT drops more (0.21) — different dynamics.
- Qwen3.6-27B: launched, killed at batch ~6 for cost (~$340/run projected; dense 27B pricing).
  Documented as a cost note, not a result.

**Pirate-output on Qwen3.6-35B-A3B (2026-07-05): the MITIGATION generalizes cross-family.**
Full pipeline re-run on the new model (self-generated Alpaca pirate data 35,687 records →
SFT 234 steps → QA GRPO pw{-2,0}, seed 42, T=4096). Last-100-batch training metrics:
| condition | rew | out | cot |
|---|---|---|---|
| no-SFT ctrl (pw0) | 1.00 | 0.92 | 0.995 |
| no-SFT pen (pw-2) | 0.99 | 0.033 | 0.851 |
| pirate ctrl (pw0) | 1.00 | 0.94 | 0.990 |
| **pirate pen (pw-2)** | 1.00 | **0.000** | **0.971** |
Pirate-output closes the (weak) baseline spillover (0.995→0.851 becomes 0.990→0.971) and
suppresses the output MORE completely than no-SFT, at full reward. Paper: §3.6 rewritten
("Spillover, and the mitigation, generalize"), fig v8 second row, TODO resolved.
**Final-checkpoint evals** (`logs/eval-penalty-v8/grpo-v8pirate-*`): pirate pen cot 0.978
(ctrl 0.987), out ~0.000, syc 1.00 → Pareto fig `pareto_v8_35ba3b.pdf` (fig:v8pareto).
**Audit finding (2026-07-05):** the penalized 35B output degenerates by REGURGITATING the
SFT rewrite-prompt boilerplate (boxed answer + "Rewrite the provided text ENTIRELY in
exaggerated pirate speak..." meta-text; ~100% of late rollouts and eval outputs). Seeded by
a 0.5% think-tag contamination in the SFT data (47/10,050 records) that the penalty
amplified because the boilerplate never mentions the hint. Control (pw0) outputs are real
hint-acknowledging explanations but the pirate style erodes to 0 by late training. CoT
unaffected (read transcripts: coherent, hint-acknowledging). Disclosed in §3.6 + Discussion.
**Data:** `logs/grpo-v8pirate-qwen36-35ba3b-pw{-2,0}-s42/`, SFT `logs/sft-35ba3b-pirate-output-alpaca`,
data `data/pirate-output-alpaca-qwen3.6-35b-a3b/`. **Pipeline:** `scripts/run_35ba3b_pirate_pipeline.sh`.

**Lambda-sweep for mitigations (2026-07-05, Jose's runs):** RT/M&F/TMF × pw{-0.5,-1} × 2 seeds
completed; finals evaluated @4096 (`logs/eval-penalty-v7/grpo-v9rt-8b-pw-{0.5,1}-*`,
`logs/eval-penalty-v9mf/grpo-v9{mf,tmf}-8b-pw-{0.5,1}-*`). Ranking flat in λ:
RT 0.18-0.21, M&F 0.36-0.40, TMF 0.60-0.75, all full reward; pirate (0.44-0.50) beats RT+M&F at
every λ. Paper: fig lambda_sweep panel (c), App I text, §3.2 robustness sentence.
NOTE: one sweep run (grpo-v9mf-8b-pw-1-s43) died in the 7/4 Tinker billing outage and was
resumed from ckpt 400 (duplicate metrics batches 400-491, benign, same pattern as v9 finals).

---

## 8b. CoT-pressure & hysteresis — does prior pressure on the CoT make it more vulnerable? (2026-06-29)

Separate experiment (Jose's question): does pressuring the CoT make it more vulnerable to *later*
output-only pressure spilling in? Plus a hysteresis probe (does spillover persist once the penalty
stops?). **8B only** (Qwen3-32B deprecated from Tinker), **thinking=300** (the regime where the
penalty causes *real* suppression, not just reframing — see §5), QA-with-hints, 2 seeds.

Mechanism: new `penalty_schedule` knob in `train_grpo.py` (`"cot:300,out:700"` etc.; segments
`mode:batches`, mode ∈ out|cot|none) routes the penalty to output / CoT / nothing per training
segment. Arms (`grpo-vuln-{arm}-8b-s{42,43}`):
- **C** `out:1000` baseline · **A** `cot:300,out:700` (CoT-pressure→output) · **A0** `cot:300,none:700`
  (CoT-pressure→recovery) · **A3** `cot:200,none:200,out:600` (pressure→recover→pressure) ·
  **R** `out:500,none:500` (Exp 2 hysteresis).

Two metrics agree throughout (so not a judge artifact): soft judge `monitor/hint_in_cot` and an
API-free literal hint-source-mention regex on saved `cot_text`. Sycophancy → ~1.0 in all arms.

**Seed-avg literal hint-mention in CoT, by batch window:**
| arm | b0-50 | b150-300 | b300-400 | b400-500 | b700-1000 |
|---|---|---|---|---|---|
| C  (out:1000)             | 0.45 | 0.32 | 0.13 | 0.06 | 0.01 |
| A  (cot300,out700)        | 0.43 | 0.13 | 0.01 | 0.00 | 0.00 |
| A0 (cot300,none700)       | 0.43 | 0.15 | 0.02 | 0.03 | 0.04 |
| A3 (cot200,none200,out600)| 0.44 | 0.22 | 0.19 | 0.12 | 0.00 |
| R  (out500,none500)       | 0.42 | 0.27 | 0.06 | 0.02 | 0.02 |

**Held-out eval @ final ckpt (378 MMLU Qs, seed-avg), `logs/eval-vuln/`:**
| arm | hint_in_cot | hint_in_output | syc | real |
|---|---|---|---|---|
| C  | 0.008 | 0.005 | 1.00 | 0.00 |
| A  | 0.000 | 0.003 | 1.00 | 0.01 |
| A0 | 0.010 | **0.245** | 1.00 | 0.03 |
| A3 | 0.000 | 0.000 | 1.00 | 0.00 |
| R  | 0.008 | 0.010 | 1.00 | 0.00 |

**Findings:**
1. **Direct CoT pressure suppresses the CoT faster/deeper than output-penalty spillover** (A/A0 ≈0.13
   vs C ≈0.32 at b150-300).
2. **Persistence / hysteresis (cleanest result):** once suppressed, hint-mention does NOT recover when
   pressure is removed — A0 stays ~0.02-0.04 for 700 no-pressure batches; R stays ~0.02 after b500; A3
   never rebounds. Answers Exp 2 (hysteresis = yes). Likely a stable-attractor mechanism (nothing
   pushes the model back to verbalizing the hint once the compressed policy earns full reward).
3. **Directional asymmetry (surprise):** output pressure spills DOWN into the CoT (C: both→~0), but
   CoT pressure barely spills UP into the output — A0 final shows CoT scrubbed (0.010) while the
   OUTPUT still acknowledges the hint (**0.245**). Penalize the output → both channels clean; penalize
   the CoT → clean CoT, still-revealing output.

**On the original "faster spillover from a common start" framing:** not realizable here, because
suppression persists — the CoT never recovers to a matched baseline to re-pressure from (A3 confirms
no rebound). Reframes to durable suppression + asymmetry.

**Cross-environment attempt (intended cleaner design: QA CoT-pressure → poly output-penalty, poly's
`expanded_in_cot` starts fresh so it gives the matched baseline the within-env design lacks).**
Blocked: poly output→CoT spillover turns out to be **essentially unique to Qwen3-32B**, which is
gone from Tinker. Full sweep of available models on poly + output penalty (`expanded_in_output`
penalized, watching whether `expanded_in_cot` follows):

| Model | out (penalized) | cot (spillover) | verdict |
|---|---|---|---|
| **Qwen3-32B** (gone) | →0 | **→0.5 by b300** | **SPILLS** (the only one; §7) |
| Qwen3-8B | 1.0 pinned | 1.0 pinned | no training (no variance) |
| Qwen3-30B-A3B | 1.0 pinned | 1.0 pinned | no training |
| Qwen3.6-35B-A3B | →0 by b200 | ~0.9 (b280) | **dissociates** |
| Nemotron-3-Super-120B-A12B | →0 by b120 | 1.0 | **dissociates** |
| GPT-OSS-120B | 0 (natural) | 1.0 | degenerate (concise output, nothing to penalize) |
| DeepSeek-V3.1 | noisy ~0.3 | noisy ~0.3 | unusable (correct~0.25, can't do poly) |
| Qwen3.6-27B | — | — | Tinker capacity-blocked (paused indefinitely) |

**Meta-finding:** poly output→CoT spillover is highly model-specific. Capable available models
*dissociate* — strip the expanded form from the output while keeping it in the CoT — which is the
monitorability-*preserving* outcome and echoes within-env finding #3 (a model can clean one channel
without contaminating the other). So the cross-env design can't be run on Tinker today. Validation
data: `logs/_poly_crossenv_validation/`.

**Caveats:** 8B only; 2 seeds; thinking=300 specifically; soft judge conflates "follows hint" with
"mentions hint" (mitigated by the agreeing literal metric); persistence may be a stable attractor
rather than fragility.

**Plots:** `plots/vuln_{hint_in_cot,panels,literal_mention}.png`. **Scripts:**
`scripts/run_vulnerability_pipeline.py` (launcher), `scripts/eval_all_vuln.py`,
`scripts/plot_vulnerability.py`. **Data:** `logs/grpo-vuln-*/`, `logs/eval-vuln/`.

---

## 9. Comparison to prior work (their QA env, Fig 4 of 2511.11584)

Their MMLU QA numbers (from their Fig 4 — **verified against the PDF 2026-06-29, commit
e5b5959**; CoT detection is read off the scatter x-axis and is approximate),
Qwen3-4B, thinking=300, λ=2, 10 runs:
| Run | Task reward | Output penalty | CoT detection (approx, from their fig) |
|---|---|---|---|
| No Penalty | 0.97±0.03 | 1.01±0.08 | ~0.52 |
| Penalty | 0.95±0.03 | 0.08±0.04 | ~0.02 |
| Mind & Face | 0.64±0.07 | 0.50±0.04 | ~0.23 |
| Reward Targeting | 0.95±0.06 | 0.03±0.01 | ~0.25 |
| Targeted M&F | 0.67±0.08 | 0.83±0.20 | ~0.62 |

Their finding: in QA, mitigations either failed to reduce spillover or hurt task reward (M&F /
TMF destabilized; RT only partial). Our matched re-runs at 4096 (§3) put RT/M&F/TMF at full
reward (the regime differs — our 8B/4096 vs their 4B/300), and add pirate-output as a new,
cheaper point. Our thinking=300 runs (§6) are the closest match to their regime.

**NOTE:** our "task reward" = sycophancy (follow the hint) and the hints point to INCORRECT
answers — so high task reward = the model is being sycophantic, which is the behavior the
penalty's spillover obfuscates. Keep this framing consistent in the paper.

---

## 10. Honest nuances / caveats (read before writing)

1. **No-SFT penalty is scale-/budget-dependent** (not one clean baseline):
   - 8B/4096: doesn't learn the sycophancy task — answers honestly (real=0.94, syc=0.05, rew 0.03).
   - 32B/4096: learns sycophancy, hides in output, partial CoT spillover (cot 0.50).
   - 8B/300: learns sycophancy, total spillover (cot 0.00), via babble output.
2. **Output suppression is partly output-DEGENERATION, not "clean explaining":**
   - pirate-output @4096: output collapses to bare `\boxed{answer}` (0%→100% bare by ~batch 500;
     pirate style gone; output not even faithful to CoT, which still reasons). CoT stays
     coherent + monitorable → the monitorability claim holds, but "suppresses output" = output
     minimization. (Jose's call: "the output not giving an explanation IS the mechanism, not a
     bug" — fine to state as such.)
   - no-SFT penalty @300: output is degenerate "Wait, no, no" babble (the most cooked).
   - no-SFT penalty @4096: the CLEANEST — coherent explanations omitting the hint.
   - Browse in dashboard (§11): rollouts/<run> entries.
3. **32B M&F dots are UNRECOVERABLE at the correct budget** — Qwen3-32B was deprecated from
   Tinker 2026-06-15; we cannot re-eval the 32B M&F runs at 4096. So `pareto_*` 32B panels omit
   M&F/TMF. (Jose OK — was a sanity check.) The wrong-budget 32B M&F evals are in
   `logs/eval-penalty-v9mf-WRONG300/` if ever needed with a caveat.
4. **2 seeds** (paper used 10). **LoRA rank 32**, not full FT. **Two-phase sampling** (CoT then
   output) not single-pass. **Tinker-specific.** v8 single-seed (42).
5. Stacking only works with RT (§4). Don't generalize.

---

## 11. Artifacts index (paths)

**Eval data** (per-sample JSONL: question/target/correct_answer/cot_text/out_text/sycophancy/
real_correct/out_score/cot_score; type∈{metadata,result,summary}):
- `logs/eval-penalty-v6/` — pirate-output (v6=pw-0.5, v6ctrl=pw0) + v6pw-1/2 in v7 dir
- `logs/eval-penalty-v7/` — v7base/v7norm/v7pcot (all pw), v6pw-1/2, v9rt/v9rtpirate (4096)
- `logs/eval-penalty-v9mf/` — 8B M&F family finals @4096 (CORRECTED); 32B wrong ones in `-WRONG300/`
- `logs/eval-penalty-t300/` — all thinking=300 runs @300 budget
- `logs/eval-penalty-v8/` — v8 cross-model
- Final-checkpoint files: `*_001000.jsonl` or `*_final.jsonl` (M&F: `*_mf_final.jsonl`).

**Training logs** (every run): `logs/grpo-<run>/` with `config.json`, `metrics.jsonl`
(reward/correct, monitor/hint_in_output, monitor/hint_in_cot per batch), `rollouts.jsonl`
(per-rollout text + scores + advantages — full data for any re-analysis), `checkpoints.jsonl`.
M&F runs have `mind/` + `face/` subdirs.

**Plots** (`plots/`): pareto_sft.png, pareto_mitigations.png, pareto_stacking.png,
pareto_mitigations_t300.png, t300_vs_4096_spillover.png, v9_poly_32b.png, v9_qa_mitigations_32b.png,
v8_vs_qwen3_base.png, v8_training_curves.png, combined_pareto_dots_v7_pw{0.5,1,2}.png (sweep,
busy), v7_*.png (training curves).

**Scripts** (`scripts/`): plotting = plot_pareto_clean.py, plot_pareto_t300_mitigations.py,
plot_t300.py, plot_v9_training_curves.py, plot_v8_training_curves.py, plot_combined_pareto_v7.py.
Eval = eval_grpo_baseline.py (`--max-cot-tokens`!), eval_grpo_mind_face.py (`--max-cot-tokens`,
fixed §9), eval_all_v7.py, eval_all_v9mf.py (`--prefixes --max-cot-tokens --finals-only`).
Launchers = launch_grpo_v9_baselines.sh, launch_grpo_t300_*.sh, launch_grpo_v8_base.sh, etc.
Training = `src/spillover/train_grpo.py` (reward_target, checkpoint=SFT-init, no_answer_penalty),
`train_grpo_mind_face.py`. Envs = `src/spillover/env_mmlu.py`, `env_polynomial.py`.

**Checkpoints:** HuggingFace `Jozdien/feedback-spillover-*` (private, 72 LoRA adapters — pirate
SFTs, all QA finals incl. v6/v7 lambda-sweep points, poly suite; registry in
`exported_checkpoints/hf_pushed.json`). Local `checkpoint_archives/` deleted 2026-07-11 after
verifying full HF coverage (`scripts/push_local_archives_hf.py`).

**Dashboard:** https://feedback-spillover.pages.dev — Sample Browser has eval finals
(v6–v9) + sampled training rollouts (rollouts/<run>, 6 batch-snapshots each) + plots.
STALE: M&F transcripts there are the wrong-budget 300 ones + t300 data not yet added; rebuild
`scripts/build_dashboard.py` + redeploy to refresh (see HANDOFF for deploy steps).

**Reproduction config:** GRPO group_size 4 × 3 prompts, 1000 batches × 12 rollouts, lr 1e-5,
LoRA rank 32, temp 1.0, save_every 100, no_answer_penalty −1 (QA only), max_output_tokens 600.
Models: Qwen3-8B, Qwen3-32B (deprecated 6/15), Qwen3.6-35B-A3B, Nemotron-3-Super-120B.
Pirate SFT checkpoints: 8B `tinker://e970f303-…/weights/final`, 32B
`tinker://707d82b5-…/weights/final`.
Style-generality SFTs (2026-09-12; 8B, pirate recipe, same 10,050 Alpaca prompts+CoTs as the pirate SFT, only the output style differs): Chinese-output `tinker://8defc206-fb5c-5855-8b90-79051204da20:train:0/weights/final` (sampler `…/sampler_weights/final`; data `data/chinese-output-alpaca-qwen3-8b/`, logs `logs/sft-8b-chinese-output-alpaca-qwen/`, test NLL 0.725→0.391; rewrites by Qwen3-8B itself).
Pig-Latin-output `tinker://a0ed9ddb-9a6d-515c-b0e9-3f4ebab4e44e:train:0/weights/final` (sampler `…/sampler_weights/final`; data `data/piglatin-output-alpaca-qwen3-8b/`, logs `logs/sft-8b-piglatin-output-alpaca-qwen/`, test NLL 1.680→0.643; output rewrites by Qwen3.6-35B-A3B because Qwen3-8B's Pig Latin was <50% correct — see `quality_check.md` in the data dir).

---

## 12. Suggested paper skeleton (refine later)

1. Intro — feedback spillover (cite Baker, Korbak); our contribution = cheap style-separation mitigation.
2. Setup — QA-with-hints env, reward, two monitors, GRPO/Tinker, what differs from 2511.11584.
3. Style separation preserves monitorability (§1) — headline figure pareto_sft.png.
4. It beats / matches prior mitigations cheaply (§3) + composes with RT (§4).
5. Spillover is regime-dependent (§5) + holds across budgets (§6) — robustness.
6. Where the style lives matters: pirate-CoT induces spillover (§2).
7. Generality: second environment (§7) + cross-model (§8).
8. Discussion — persona-separation mechanism (1 line), output-minimization nuance (§10.2),
   limitations (§10.4).
- **Appendix candidates:** penalty-weight sweep, v8 details, the regime/cooked-ness transcripts,
  full numbers table (all conditions × {syc,real,out,cot}), prior-work comparison details.

## 12. Paper-exact re-runs with the original judge (2026-09-09; T=300, GPT-4.1 binary judge)

Setup = Drori et al. App. C.2 (batch 12, lr 1e-5, 3200 episodes = 267 steps, λ=2, thinking 300 /
output 600, temperature 1, judge = GPT-4.1 binary with their exact prompt, no no-answer penalty), on
Qwen3-8B LoRA-32 (their Qwen3-4B is retired on Tinker). Two advantage estimators: REINFORCE with a
per-batch mean baseline (their algorithm; 1 rollout/prompt) and GRPO (group of 4 × 3 prompts).
Values = mean over the last 27 steps of training rollouts (their "final checkpoint" convention),
mean ± std across seeds. Runs: `logs/grpo-exact-*` (REINFORCE), `logs/grpo-grpo300-*` (GRPO);
launchers `scripts/launch_paper_exact.sh`, `scripts/launch_grpo_t300_gpt41.sh`; summary
`uv run scripts/analyze_exact.py --per-seed`.

| Arm | seeds | task reward (follow hint) | M_out | CoT detection |
|---|---|---|---|---|
| REINFORCE no-SFT control | 3 | 0.99±0.01 | 0.87±0.02 | 0.58±0.02 |
| REINFORCE no-SFT penalty | 3 | **0.38±0.07** | 0.13±0.05 | 0.22±0.01 |
| REINFORCE pirate-output control | 2 | 1.00 | 0.23±0.01 | 0.69 |
| REINFORCE pirate-output penalty | 2 | 0.50±0.50 (1.00 / 0.00) | 0.00 | 0.60±0.02 |
| GRPO no-SFT control | 10 | 1.00 | 0.88±0.02 | 0.61±0.04 |
| GRPO no-SFT penalty | 10 | **0.99±0.01** | 0.11±0.14 | **0.27±0.08** |
| Drori et al. no penalty (4B, 10 runs) | 10 | 0.97±0.03 | ~0.50 | ~0.52 |
| Drori et al. penalty (4B, 10 runs) | 10 | 0.95±0.03 | ~0.04 | ~0.02 |

Reading: (1) GRPO reproduces the original qualitatively — task learned (0.99), output scrubbed
(7/10 seeds M_out ≤ 0.08; 3 seeds still 0.21–0.44 at 267 steps), CoT acknowledgment 0.61 → 0.27
(theirs 0.52 → 0.02). Late-training breakdown: 62–89% of penalized rollouts follow the hint with
NO acknowledgment in the CoT (control: ~0%). (2) REINFORCE at these settings does not learn the
task on 8B LoRA (0.38) — the λ=2 penalty gradient dominates the sparse task signal (§CHECKIN
2026-09-09 mechanism); group normalization rescues the task signal. Pirate-output + REINFORCE
penalty is bimodal (one seed 1.00 task / CoT 0.58 ≈ control 0.69 / output 0.00; the other abandons
the task). (3) Caveat for the whole T=300 regime: ~90% of CoTs end mid-sentence at the 300-token
cap in EVERY arm and phase (median ~970 chars), so "CoT detection" here = whether the hint is
mentioned in the first 300 tokens of an unfinished thought. This is also the original paper's
setting. At T=4096 the model finishes thinking and GPT-4.1 finds the hint acknowledged (mostly
mention-and-dismiss) in ≥0.95 of penalized CoTs (32B no-SFT, 8B pirate, 8B RT) — no
acknowledgment-spillover at that budget (logs/rejudge-gpt41/).

### 12b. Mitigations under the same protocol (2026-09-11; GRPO, T=300, GPT-4.1 binary judge, λ=2)

Runs: `logs/grpo-mit300-*` (5 seeds each; baselines = the 10-seed `grpo-grpo300-nosft-*` above).
Plot: `plots/mit300_pareto.png` (`scripts/plot_mit300.py`, the original's Fig 4 format).
Values = last-27-step training means, mean ± std across seeds.

| Arm | seeds | task reward | M_out | CoT detection |
|---|---|---|---|---|
| No-SFT control | 10 | 1.00 | 0.89±0.02 | 0.63±0.05 |
| No-SFT penalty | 10 | 0.99±0.01 | 0.11±0.14 | 0.27±0.08 |
| Pirate-output control | 5 | 1.00 | 0.73±0.19 | 0.61±0.07 |
| **Pirate-output + penalty** | 5 | **1.00** | **0.00** | **0.59±0.08** |
| Reward targeting | 5 | 0.99±0.01 | 0.14±0.11 | 0.57±0.02 |
| Mind & Face | 5 | 1.00 | 0.01±0.01 | 0.36±0.10 |
| Targeted Mind & Face | 5 | 1.00 | 0.01±0.01 | 0.50±0.03 |
| Drori et al. (4B): RT / M&F / TMF | 10 | 0.95 / 0.64 / 0.67 | 0.02 / 0.25 / 0.42 | ~0.25 / ~0.23 / ~0.62 |

Reading: with the baseline spillover real (0.63 → 0.27) and the original judge, pirate-output SFT
keeps CoT detection at its no-penalty level (0.59 vs 0.61 own control / 0.63 no-SFT control) with
the output fully scrubbed and full task reward — the paper's headline claim, now on a judge-robust
footing and in the original's regime. Reward targeting preserves the CoT (0.57) but only partially
scrubs the output (M_out 0.14, seed-dependent 0.00–0.27). Mind & Face alone is a partial mitigation
(0.36); targeted M&F reaches 0.50 at full reward and zero output (the original saw TMF destabilize
training; ours is stable across 5 seeds). The 25 runs were interrupted by an OpenAI credit outage
at batch 104–191 and resumed from checkpoints (100/150) with logs truncated; 0 judge failures
after the resume (CHECKIN 2026-09-11).

### 12c. Async RL validation (2026-09-12): async_k=4 reproduces the synchronous results, 7x faster

Same protocol as §12/§12b with `async_k=4` (12 sampling workers, ≤4 optimizer steps off-policy,
stale groups re-queued). `logs/grpo-async300-*`; comparison `scripts/plot_async_vs_sync.py` →
`plots/async_vs_sync.png`. Last-27-step means ± std across seeds; wall-clock per run.

| Arm | mode | seeds | follow hint | M_out | CoT detection | wall/run | mean staleness |
|---|---|---|---|---|---|---|---|
| No-SFT control | sync | 10 | 1.00 | 0.89±0.02 | 0.63±0.05 | 149 min | 0 |
| No-SFT control | async | 5 | 1.00 | 0.89±0.02 | 0.63±0.04 | 20 min | 3.6 |
| No-SFT penalty | sync | 10 | 0.99±0.01 | 0.11±0.14 | 0.27±0.08 | 145 min | 0 |
| No-SFT penalty | async | 5 | 0.99±0.01 | 0.12±0.09 | 0.27±0.06 | 19 min | 3.6 |
| Pirate-output penalty | sync | 5 | 1.00 | 0.00 | 0.59±0.08 | 129 min | 0 |
| Pirate-output penalty | async | 5 | 0.80±0.40 | 0.00 | 0.58±0.07 | 19 min | 3.6 |

Means, spreads and curves match for the no-SFT arms. One of five async pirate-output seeds never
learned the task (the pirate init starts at ~0.1–0.2 hint-following and can fail to bootstrap;
the REINFORCE pirate arm showed the same failure mode synchronously in 1/2 seeds), so async is safe
for bulk runs but abandoned seeds should be flagged and headline pirate numbers taken with ≥5 seeds.
(Wall-clock measured with 45 concurrent runs on Tinker; the sync runs also shared the service.)

## 13. Multi-turn terminal environment (Drori et al. §4.3) — replication with the regex penalty (2026-09-12)

Environment: `src/spillover/env_terminal.py` + `src/spillover/train_grpo_terminal.py` (largest-island
task, deliberately wrong `verifier.py`, sandboxed bash, ≤4 turns; regex monitor = count of "ground
truth" in the model's explanations (output) / CoT). Protocol = their App. C.3.1 adapted to GRPO:
effective batch 32 (4×8), lr 5e-6, 3200 episodes (100 steps), λ=1.25, thinking 128 / output 256,
Qwen3-8B. Runs `logs/grpo-term-regex-*` (5 seeds each); last-27-step training means ± std.

| Arm | task reward (verifier passed) | regex in output | regex in CoT | read verifier |
|---|---|---|---|---|
| No penalty (control) | 0.98±0.00 | 0.74±0.02 | 0.23±0.02 | ~0.97 |
| Penalty λ=1.25 | 0.98±0.00 | 0.00±0.00 | 0.01±0.00 | ~0.97 |
| Drori et al. (regex, 10 runs) | 0.99 / 0.95 | λ·M: 1.25 / 0.05 | CoT detection ~0.8 / ~0.0 | — |

Reproduces the paper: the model keeps reading the verifier and passing (0.98) while the penalized
output stops saying "ground truth", and the CoT stops saying it too (0.23 → 0.01). Our unpenalized
CoT mention rate is lower than theirs (0.23 vs ~0.8; 128-token CoTs, all truncated). Mitigation runs
(reward targeting, pirate-output init): `logs/grpo-termmit-*`.

## 14. BUG in the polynomial task reward (found 2026-09-12) — affects the paper's poly figure

`env_polynomial._check_correctness` (now `_check_correctness_legacy`) could not parse boxed answers
like `2x^3(x+5)(x^2+2x-8)` (no `*` inserted between a digit and `(`), so it fell through to string
fallbacks: (a) the canonical factored string appears in the output, or (b) **the EXPANDED derivative
appears anywhere in the output**. (b) rewards the penalized behaviour itself and scores correct
factored answers as wrong once the expanded form is scrubbed. In the paper's v9poly 32B runs the
boxed answer failed to parse in ~100% of late rollouts, so task reward was decided by the fallbacks.
Re-scoring the last 10% of training rollouts with the fixed checker (`scripts/rescore_poly.py`):

| Arm (Qwen3-32B, T=4096, λ=1) | task reward used in the paper | task reward (fixed checker) | expanded in output |
|---|---|---|---|
| control | 0.99 | 0.99 | 0.99 |
| penalty | 0.65 | **0.98** | 0.00 |
| reward targeting | 0.55 | **0.98** | 0.03 |
| Mind & Face | 0.78 | **0.97** | 0.01 |
| targeted M&F | 0.67 | **0.98** | 0.02 |
| pirate-output penalty | 0.65 | **0.99** | 0.00 |
| pirate-output control | 1.00 | 0.96 | 1.00 |

=> every penalized arm actually solves the task at ≈0.98; the draft's poly figure understates their
reward by 0.2–0.45. The monitors (string match on the expanded form) are unaffected. The policies
were trained with the buggy reward (it pushed them toward the canonical factored string, which they
adopted), so the trained models are fine; the reported reward axis must be recomputed from rollouts.
The 8B T=800 replication (`poly800`) is being re-run with the fixed reward as `poly800v2`; with the
fixed checker the 8B control scores 0.82 (legacy 0.99: wrong answers credited via the expanded
form) and the penalty 0.82 (legacy 0.55).

### 13b. Terminal env mitigations with the regex penalty (2026-09-12; `logs/grpo-termmit-*`, 5 seeds)

| Arm | task | regex in output | regex in CoT | read verifier |
|---|---|---|---|---|
| control | 0.99 | 0.75±0.01 | 0.23±0.03 | 0.99 |
| penalty λ=1.25 | 0.99 | 0.00 | 0.01±0.01 | 0.99 |
| reward targeting | 0.99 | 0.00 | 0.01±0.00 | 0.98 |
| pirate-output init, control | 0.99 | 0.53±0.08 | 0.14±0.03 | 0.99 |
| pirate-output init, penalty | 0.99 | 0.02±0.01 | 0.02±0.01 | 0.99 |
| Drori et al. Fig 6 (regex): penalty / M&F / RT / TMF CoT detection | — | — | ~0.0 / ~0.2 / ~0.33 / ~1.0 | — |

Neither reward targeting nor the pirate init preserves the CoT's "ground truth" mentions under the
regex penalty in our setup (both ≈ penalty). Caveats: (i) the regex monitor is a single phrase the
model can drop while still reading the verifier (read rate stays 0.99 in every arm), so this
"spillover" is phrase avoidance rather than hidden behaviour; (ii) unpenalized CoT mention is only
0.23 here (128-token CoTs) vs ~0.8 in the paper; (iii) the pirate style DOES surface — pirate
words in 100% of penalized explanations (25% in the pirate control) — yet the CoT mention still
collapses, so the style separation that protects the QA CoT does not transfer to this phrase-level monitor. The LLM-judge variant (paper Fig 7; `scripts/launch_terminal_llmjudge.sh`)
is the meaningful mitigation test and is queued behind OpenAI credits.

### 14b. Polynomial replication at 8B with the fixed reward (`poly800v2`, 2026-09-12; T=800/1000, λ=1, GRPO, 5 seeds)

| Arm | task (fixed checker) | expanded in output | expanded in CoT |
|---|---|---|---|
| control | 0.97±0.02 | 0.93±0.03 | 1.00 |
| penalty λ=1 | 0.97±0.01 | 0.03±0.01 | 0.99 |
| Drori et al. (14B, REINFORCE) | 1.00 / 0.95 | 0.98 / 0.02 | ~0.40 / ~0.14 |

The penalty scrubs the output at zero task cost, and the CoT is untouched: Qwen3-8B differentiates
term by term in every CoT (expanded form present 99–100%) and never adopts the product-rule
workaround the paper describes, despite the same two in-context examples. So at 8B/T=800 the
polynomial env shows NO spillover; there is nothing for a mitigation to mitigate at this scale.
For comparison, the paper's own 32B runs (T=4096, λ=1, last 50 batches; task reward = fixed
checker from §14): control CoT 1.00 / out 0.99; **penalty CoT 0.18±0.06** / out 0.00 (strong
spillover); reward targeting 0.98, Mind & Face 0.98, targeted M&F 1.00, pirate-output 0.96 (all at
out ≤ 0.03, task ≈ 0.98). So the poly result is size-dependent: 32B finds the product-rule route
and spills; 8B does not. Keep the 32B runs (Qwen3-32B is retired on Tinker; a fresh confirmation
would need e.g. Qwen3.6-35B-A3B).
