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

**Checkpoints:** HuggingFace `Jozdien/feedback-spillover-*` (private, 55 LoRA adapters — pirate
SFTs, all QA finals, poly suite). Local sampler archives: `checkpoint_archives/` (one per run).

**Dashboard:** https://feedback-spillover.pages.dev — Sample Browser has eval finals
(v6–v9) + sampled training rollouts (rollouts/<run>, 6 batch-snapshots each) + plots.
STALE: M&F transcripts there are the wrong-budget 300 ones + t300 data not yet added; rebuild
`scripts/build_dashboard.py` + redeploy to refresh (see HANDOFF for deploy steps).

**Reproduction config:** GRPO group_size 4 × 3 prompts, 1000 batches × 12 rollouts, lr 1e-5,
LoRA rank 32, temp 1.0, save_every 100, no_answer_penalty −1 (QA only), max_output_tokens 600.
Models: Qwen3-8B, Qwen3-32B (deprecated 6/15), Qwen3.6-35B-A3B, Nemotron-3-Super-120B.
Pirate SFT checkpoints: 8B `tinker://e970f303-…/weights/final`, 32B
`tinker://707d82b5-…/weights/final`.

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
