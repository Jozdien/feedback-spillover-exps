# Check-in — feedback spillover experiments

*Last updated: 2026-06-12 ~23:30 UTC. (Detailed version for Claudes: HANDOFF.md)*

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
