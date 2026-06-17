# Paper TODO — style separation mitigates feedback spillover

*Scope per Jose: 90/10 — a solid core paper with a few ablations, not the original paper's
breadth. Narrative: CoT/output style separation mitigates feedback spillover, outperforming
the prior mitigations (reward targeting, Mind & Face) in their own QA environment.*
*Last updated: 2026-06-12 ~01:30 UTC.*

## Currently running (no action, just don't break it)
- [x] ~~12 × v9 QA 32B mitigation runs~~ **ALL DONE 2026-06-12 ~20:45, zero cut.**
- [ ] 12 × v9 QA 8B mitigation runs — resumed from checkpoints ~21:00 June 12.
- [ ] Eval loops sweeping the new 32B finals (regular + M&F); HF export pass 2 pushing them.

## Deadline aftermath
- [x] Pre-deadline archive sweeps (54+ archives, 0 failed); pruned to one per run (73GB).
- [x] Resume the 12 paused 8B v9 runs.
- [ ] Verify final-checkpoint eval coverage for all 12 QA 32B runs once loops drain.
- [ ] Final archive prune + HF export verification after finals are confirmed pushed.
- [x] ~~Cut-run salvage decisions~~ — moot, nothing was cut.

## To launch (approved or requested)
- [~] **thinking=300 QA runs** (Jose):
      - [x] Base case (grpo-t300base-8b-pw{0,-2}-s{42,43}): DONE. CONFIRMED budget effect —
            penalty drives hint_in_cot 0.41→0.001 (total) at 300 vs 0.66→0.21 (partial) at 4096.
            Plot: plots/t300_vs_4096_spillover.png. NOTE: at 300 the penalty run reward-hacks
            (babble output, full task reward); at 4096 it stays low task reward — not a perfectly
            clean apples-to-apples, mention in writeup.
      - [~] Mitigation suite (grpo-t300{rt,pirate,mf,tmf}-8b-pw-2-s{42,43}, 8 runs): LAUNCHED
            2026-06-14. No pw0 controls (deferred — see below). RT/pirate=train_grpo,
            mf/tmf=train_grpo_mind_face.
      - EVAL all t300 runs with --max-cot-tokens 300 (NOT default 4096) to match training
        budget. Standard eval_all_v7 won't pick them up (prefix + cot-budget) — needs a custom
        pass. M&F t300 evals need eval_all_v9mf-style mind/face pairing at 300.
- [ ] (Deferred, Jose 2026-06-14) pw0 controls for the t300 mitigation conditions (maybe).
- [x] ~~8B M&F evals~~ DONE (all 12 8B v9 finals evaluated; one needed a re-run after a
      concurrent-eval collision left a 50-row partial — see gotcha below).

## Deferred (Jose's call)
- [PUNTED 2026-06-17] Style-generality ablation — not running for now, and REMOVED from the
  paper (no longer mentioned in limitations/future-work). Revisit only if a reviewer asks.
- [ ] (On hold per Jose) Seed 43 for v8 (~$525).

## Analysis & plotting (no training needed)
- [DEPRIORITIZED] Mechanism analysis (style-presence judge over rollouts). Jose's call
      2026-06-13: NOT a clean test. Hypothesis = pirate installs persona-level output/CoT
      separation → less spillover. But that's consistent with the style curve going EITHER way
      (persists = separation held; fades = separation worked until it eroded), so measuring
      style-over-time discriminates nothing. For a 90/10 paper, state the persona-separation
      mechanism as a one-line discussion claim; don't run an experiment that can't fail.
      (Only revisit if a reviewer demands mechanistic evidence — and then design a test that
      can actually distinguish hypotheses, e.g. timing: does spillover ONSET coincide with
      style erosion within a run.)
- [x] Pareto with v9 mitigation dots — DONE. Clean focused figures in plots/:
      pareto_sft.png (core SFT, 8B+32B, with no-penalty CoT reference lines),
      pareto_mitigations.png (pirate vs RT/M&F/TMF, 8B), pareto_stacking.png (8B).
      Script: plot_pareto_clean.py. NOTE on stacking: only pirate+RT improves on pirate
      alone (0.47→0.60); pirate+M&F/TMF are ~equal-or-lower → frame stacking around RT.
      (Old busy combined_pareto_dots_v7_pw2.png kept as-is per Jose.)
- [ ] Poly-env figure for the paper (from rollouts; draft exists: plots/v9_poly_32b.png).
- [ ] v8 cross-model figure (draft exists: plots/v8_vs_qwen3_base.png).
- [ ] Eval-based final numbers table: all conditions × {syc, real_correct, out, cot},
      final/latest checkpoints, both sizes, seed-averaged ± range.
- [ ] Dashboard: add v7/v8/v9 to build_dashboard.py (EVAL_DIRS + parse_run_name) and redeploy.

## Writing
- [x] PAPER DRAFT written 2026-06-16: paper/ (self-contained LaTeX, compiles to 9pp PDF).
      Built from RESULTS.md section-for-section; real numbers in all tables/figures; 7 figures
      copied to paper/figures/; references.bib (11 entries). 10 \todo{} marks for remaining
      writing/decisions (affiliation, SFT-data description, diffs-from-prior-work, verify their
      Fig4 numbers, style-generality ablation, cross-model scope, appendix expansion).
      Build: cd paper && pdflatex main && bibtex main && pdflatex main && pdflatex main.
- [ ] Comparison table vs prior work (their Fig 4 QA numbers vs our matched runs).
- [ ] Framing for the regime finding: at 32B/4096-thinking, baseline spillover is weak;
      strong spillover appears at 8B, thinking=300, poly env, and pirate-CoT SFT. Position
      style separation as: free (no 2nd model/gradient surgery), works where others fail
      (8B, poly speed), and never *induces* spillover — unlike styled CoT, which does.
- [ ] Limitations: 1–2 seeds (vs paper's 10), LoRA not full FT, two-phase sampling,
      Tinker-specific setup, no-SFT 32B runs possibly cut before batch 1000.

## Decisions for Jose
- [ ] Do cut no-SFT 32B runs get finished locally, or do we report latest-checkpoint values?
- [ ] Pareto presentation: drop old thinking=300 mitigation dots entirely, or keep as
      faded reference?
- [ ] M&F+pirate for poly env (never run) — probably skip per 90/10.

---

## Results in hand (will go in the paper)

**Core result (QA env, final-checkpoint evals, both sizes, 2 seeds):**
- Pirate-output SFT + penalty: output acknowledgement → ~0, full training reward, CoT hint
  detection ≈ no-penalty control (8B: 0.46 vs 0.50; 32B: ~0.55 vs ~0.59) → **no spillover**.
- Pirate-CoT SFT + penalty: CoT detection → ~0.0 at full reward, both sizes → **total
  spillover when the penalized style lives in the CoT** (clean induced-spillover demo).
- No SFT: penalty fails at 8B (reward 0.03, output acknowledgement persists); at 32B output
  is suppressed with CoT ≈ 0.5 (weak baseline spillover at this scale/CoT budget).
- Normal SFT: intermediate (8B reward ~0.4; 32B full reward, CoT ~0.44) — SFT alone isn't
  the mitigation, style separation is.
- Full penalty-weight sweep (0/-0.5/-1/-2) for all four SFT conditions, both sizes.

**Second environment (poly, 32B, 2 seeds, training-rollout metrics):**
- Plain penalty reproduces the paper's spillover: expanded-form in CoT 1.0 → ~0.2.
- Pirate-output: CoT intact (≈1.0) AND fastest output suppression of all conditions.
- RT / M&F / TMF also hold the CoT (consistent with the paper's poly results).

**Matched mitigation baselines (QA 32B, thinking=4096, in flight):**
- Training curves: all conditions suppress output fully and reach full task reward;
  hint-in-CoT holds ~0.5–0.6 across conditions (incl. no-mitigation) — see regime framing.
- Final eval dots pending (runs finish or get cut today).

**Cross-model generality (v8, no-SFT, 4 penalty weights, seed 42):**
- Qwen3.6-35B-A3B: learns hint-following under penalty with output suppressed; CoT mildly down.
- Nemotron-3-Super-120B: barely sycophantic at baseline (syc 0.18, real_correct 0.82);
  penalized runs never adopt hint-following — interesting hint-resistance contrast.
- Qwen3.6-27B killed for cost (documented).

**Infrastructure/artifacts:** full per-sample transcripts + judge scores for every eval;
all rollouts/advantages saved; 32B LoRA finals archived locally + on HF (private);
interactive dashboard (v6 deployed; v7–v9 pending).
