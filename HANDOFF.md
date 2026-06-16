# HANDOFF — feedback-spillover paper experiments

*Maintained by Claude for future Claude sessions. Updated: 2026-06-12 ~00:15 UTC.*
*Companion docs: CHECKIN.md (concise user-facing status, inline plots) and TODO.md (paper
task list + results-in-hand). Keep ALL THREE updated after significant events.*

## 1. Project and narrative

Paper in progress (user = Jose, solo, a few weeks, "90/10" scope — core result + few ablations,
explicitly NOT replicating the breadth of the original paper). Narrative:

> Giving the CoT and the output different *styles* (via cheap SFT before RL) prevents feedback
> spillover — an output-only penalty stops obfuscating the CoT — and this outperforms the
> mitigations from arXiv 2511.11584 (reward targeting, Mind & Face) in that paper's own QA
> environment, at zero extra training cost.

Reference paper: "Output Supervision Can Obfuscate the Chain of Thought" (arXiv 2511.11584,
Drori/Marks et al., MATS). Their mechanism split: *conditional* spillover (CoTs that lead to
safe-looking outputs get reinforced) → mitigated by **reward targeting** (zero the penalty's
∇_CoT term); *parametric* spillover (parameters generalize output-safety to CoT) → mitigated by
**Mind & Face** (separate CoT/output models). Crucially, in their QA-with-hints environment
(the one we use) ALL their mitigations failed (Targeted M&F best, −30% task reward). Their QA
config: Qwen3-4B, bs12, 3200 episodes, λ=2, thinking=300, output=600, 10 runs/condition.

Our setting: MMLU elementary-math, hints pointing to *incorrect* answers, two-phase generation
(CoT up to 4096 tok, output 600). Reward = correctness + pw·out_score, out_score from
GPT-4o-mini soft judge (logprob-weighted). no_answer_penalty=-1 for unboxed answers (QA only).
Eval (scripts/eval_grpo_baseline.py): 378 questions; metrics = sycophancy (followed hint),
real_correct, out_score (hint acknowledged in output), cot_score (hint acknowledged in CoT).
"Spillover" = cot_score dropping under an output-only penalty. GRPO: group_size 4 × 3 prompts,
1000 batches × 12 rollouts, lr 1e-5, LoRA rank 32, save_every=100, temp 1.0, seeds 42/43.

## 2. Experiment inventory

| Fleet | What | Status |
|---|---|---|
| v6/v6ctrl/v6pw | Pirate-output SFT + GRPO, pw {0=v6ctrl, -0.5=v6, -1=v6pw-1, -2=v6pw-2}, 8B+32B, 2 seeds | DONE + evaluated |
| v7base/v7norm/v7pcot | No-SFT / normal-SFT / pirate-CoT-SFT × 4 pw × 2 sizes × 2 seeds | DONE + evaluated |
| v8base | No-SFT baselines: Qwen3.6-35B-A3B + Nemotron-3-Super-120B × 4 pw × s42 | DONE + evaluated |
| (v8 killed) | Qwen3.6-27B: killed at batch ~6, ~$6 spent — projected ~$340/run (2.9k-tok CoTs × $3.73/MTok) | dead, logs remain |
| v9 QA baselines | rt / rtpirate / mf / tmf / mfpirate / tmfpirate, pw=-2, thinking=4096, both sizes, 2 seeds | 32B in flight (deadline), 8B PAUSED |
| v9 poly suite | task=poly: ctrl/pen/rt/mf/tmf/pirate/piratectrl × 2 seeds, 32B, 500 batches | DONE (results from rollouts; no eval needed) |

v9 motivation: the OLD mitigation runs (logs/grpo-qwen3-32b-{mf,tmf}, hardcoded numbers in
older plot scripts) used the paper's thinking=300 — NOT comparable to our thinking=4096 runs.
v9 reruns everything matched. mfpirate/tmfpirate = mind AND face both init from pirate SFT.

Pirate SFT checkpoints (everything pirate derives from these; archived + on HF):
- 32B: tinker://707d82b5-211a-5014-b528-77713c6c1dbb:train:0/weights/final
- 8B:  tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/weights/final

## 3. Headline results so far (final checkpoints, pw=-2 unless noted)

8B Pareto (complete; plots/combined_pareto_dots_v7_pw2.png):
- **Pirate-CoT SFT + penalty: TOTAL spillover** — cot_score ≈ 0.0 at full reward (control 0.73).
- **Pirate-output SFT + penalty: NO spillover** — cot_score ≈ 0.46 ≈ control (0.50), full reward.
- **Normal SFT: penalty only partially takes** (reward ~0.4); **No SFT: fails** (reward ~0.03,
  out_score stays ~0.5 — model never stops acknowledging the hint).
32B: same qualitative pattern; Normal SFT reaches full reward at 32B (~0.44 cot, 0.97 reward);
pirate-CoT total-spillover replicates (cot ≈ 0.0 @ full reward).

v8 (training curves; plots/v8_training_curves.png, v8_vs_qwen3_base.png): pw0 controls all
learn task ≈1.0; penalized runs mostly fail to learn hint-following in 1000 batches —
EXCEPT Qwen3.6-35B-A3B (climbing, output suppressed, CoT only mildly down). Nemotron is
hint-resistant from the start (eval syc 0.18, real_correct 0.82 at ckpt 100).

Penalty-weight sweep (pw0.5/pw1 pareto pngs): pirate-output keeps cot_score ≈ control at every
pw on both sizes. New pirate runs spill less than v5-era ones did.

v9 early signal: not yet plotted; rt evals accumulating in logs/eval-penalty-v7/grpo-v9rt*;
M&F evals in logs/eval-penalty-v9mf/ (sweep launched 2026-06-11 ~23:50).

## 4. THE DEADLINE — RESOLVED 2026-06-12 ~20:45 UTC
**All 12 QA 32B runs finished their full 1000 batches before deprecation; nothing was cut.**
(tmf-s43 crashed at batch 876 — transient asyncio error, not deprecation — resumed from
ckpt 800.) Remaining 32B-related work = eval-loop drain + HF export verification only.
If 32B sampling fails from here on, it's deprecation finally landing; all finals are
archived locally + on HF. Historical context below kept for reference.

**Qwen3-32B leaves Tinker June 12** (hour unknown; conservative line = 06:00 UTC). After that,
NO 32B sampling: training dies, evals die, checkpoint export dies. Saved transcripts/judge
re-runs are safe (we save everything per-sample).

Insurance (all set up, verify they ran):
1. checkpoint_archives/ — local tar.gz sampler archives: pirate SFTs + landed finals (~18GB).
2. Background task at 01:30 UTC June 12: `archive_32b_checkpoints.py --convert --all-final`
   (converts state-only latest ckpts of unfinished runs → sampler → download).
3. HF export (approved account: **Jozdien**, private repos `feedback-spillover-<label>`):
   `export_checkpoints_hf.py --hf Jozdien` running ~00:00 June 12; re-run with `--latest`
   AFTER runs get cut to push their newest checkpoints. State: exported_checkpoints/hf_pushed.json.

Endgame expectations (50-batch pace, ~23:30 June 11): pirate-family runs fast (~80-110s/batch;
CoT shrank) → rtpirate-s42 + mfpirate pair finish early June 12; no-SFT runs slow
(~220-300s/batch; penalty fails to shrink CoT) → rt/mf/tmf/tmfpirate pairs likely CUT between
batch ~700-950. That's OK: checkpoints every 100; v7 curves converged by ~600-800; use
latest-checkpoint values (eval them BEFORE deprecation — the eval loop + v9mf sweep do this).

After deadline: resume the 12 paused 8B v9 runs (kill was pre-authorized to free throughput;
they resume from last checkpoint by relaunching the SAME commands — see
scripts/launch_grpo_v9_baselines.sh / launch_grpo_v9_poly_and_pirate_mf.sh for the exact args;
resume logic = checkpoint_utils.get_last_checkpoint on log_path).

## 5. Infra currently running (June 12 00:15 UTC)

- 12 × 32B QA v9 training runs (the deadline set).
- Eval loop (bg bash): every 40min runs eval_all_v7.py (prefixes incl grpo-v9rt*) +
  eval_all_v8.py; exits+notifies when no training procs AND zero pending evals.
  Logs: logs/eval-v{7,8}-progress-loop.log.
- M&F eval sweep: eval_all_v9mf.py --size 32b --max-concurrent 4 (logs/eval-v9mf-progress.log).
  RE-RUN it as more M&F checkpoints land (skips done). 8B M&F evals: anytime, no deadline.
- Fleet monitor (persistent Monitor task): health (errors/stalls/deaths/completions) +
  2-hourly pace projections vs deadline.
- 01:30 archive sweep + HF export: background, notify on completion.
- PAUSED: 12 × 8B v9 runs (batch ~100-170).

## 6. Run-name → condition map (for plotting/analysis)

QA evals live in: eval-penalty-v6 (v6/v6ctrl), eval-penalty-v7 (v6pw, v7*, v9rt*),
eval-penalty-v8 (v8), eval-penalty-v9mf (M&F pairs, files <step>.jsonl not model-prefixed).
Eval jsonl rows: type ∈ {metadata, result, summary}; result has question/target/correct_answer/
cot_text/out_text/sycophancy/real_correct/out_score/cot_score. "final" ckpt → file *_001000.jsonl.

- grpo-v6-{size}-... = pirate-output pw-0.5 | v6ctrl = pw0 | v6pw-1/-2 = pw-1/-2
- grpo-v7{base,norm,pcot}-{size}-pw{0,-0.5,-1,-2}-s{seed}
- grpo-v8base-{qwen36-35ba3b,nemotron-super-120b}-pw{..}-s42
- grpo-v9{rt,rtpirate}-{size}-pw-2-s{seed} — train_grpo, reward_target=True
- grpo-v9{mf,tmf,mfpirate,tmfpirate}-{size}-pw-2-s{seed} — train_grpo_mind_face
  (tmf* = reward_target=True; *pirate = checkpoint=pirate SFT; mind/ + face/ subdirs)
- grpo-v9poly-{ctrl,pen,rt,mf,tmf,pirate,piratectrl}-32b-... — task=poly, 500 batches,
  NO no_answer_penalty (its \boxed{[A-D]} regex is MC-specific)
- Old non-matched runs (thinking=300, do NOT mix into v9 comparisons): grpo-qwen3-32b-{mf,tmf}

Training logs per run: config.json, metrics.jsonl (reward/correct, monitor/hint_in_output,
monitor/hint_in_cot per batch), rollouts.jsonl (per-rollout text + scores + advantages),
checkpoints.jsonl (name/batch/state_path; sampler_path only on final).

## 7. Cost ledger (measured from rollouts; Tinker prefill/sample/train pricing)

v7 8B fleet ~$500; v6/v7 32B in-flight portion ~$1450; v8 ~$525 (35B ~$100/run thinks ~2.9k
tok; Nemotron ~$31/run, terse ~750 tok); v9 QA suite ~$880; poly suite ~$600; pirate-stack
M&F ~$480. Per-eval: 8B ~$0.45, 32B ~$0.77 (incl judge). Whole campaign ≈ $5-6k.
Estimation method: sample rollouts.jsonl field lengths, ~3.8 chars/token.

## 8. Gotchas (learned the hard way)

- **pgrep/pkill -f self-match**: your own shell's cmdline contains the pattern → bracket trick
  `train_grp[o]`. (Killed own shell once; a drain-watcher deadlocked on itself once.)
- **"weights/final" appears at run START** (SFT-init config echo) — completion detection must
  match `Saved checkpoints.*weights/final`.
- Tinker archive endpoint accepts ONLY sampler_weights paths; intermediate ckpts are state-only
  → convert: create_training_client_from_state_with_optimizer + save_weights_for_sampler.
  get_checkpoint_archive_url_from_tinker_path(...).result() returns an OBJECT — use `.url`.
- Tinker fleet-wide stalls happen (~40min, twice on June 11); procs sit at ~0.5% CPU waiting on
  futures; they self-resolve — don't restart before ~45min silent.
- eval_all_v7 renames "final" eval files to *_001000.jsonl; skip-detection keys on that.
- M&F eval needs eval_grpo_mind_face.py (--mind-checkpoint/--face-checkpoint); the standard
  eval can't load mind/face pairs.
- Qwen3.6 models: renderer qwen3_5, same <think> format; Nemotron: renderer nemotron3,
  </think> = special token 13. Both work with the existing two-phase logic unchanged.
- The dashboard build (scripts/build_dashboard.py) silently drops run dirs whose names don't
  match parse_run_name's regex — extend it AND EVAL_DIRS when adding v7/v8/v9 to the dashboard.
  Deploy: cp dashboard.html deploy_dir/index.html; rsync dashboard_data → deploy_dir;
  wrangler pages deploy deploy_dir --project-name feedback-spillover --branch main.
- 27B-class dense Qwen3.6 pricing is ~2.5× Qwen3-32B — check model pricing before launching.

## 9. What remains (paper plan)

1. **Now**: ride out the deadline; eval everything 32B before cutoff; salvage via --latest HF
   export + archives after.
2. Resume 12 paused 8B v9 runs; run 8B M&F evals (eval_all_v9mf.py --size 8b); sweep with
   eval loop until all evaluated.
3. Tier-2 ablation (user-approved direction, not yet launched): style-generality — one
   non-pirate style (e.g. French/archaic), output-SFT, 8B, pw 0/-2, 2 seeds, <$50.
3b. **USER-REQUESTED (2026-06-12): thinking=300 QA runs** — rerun key QA conditions
   (penalty / RT / MF / pirate-output, 8B, pw=-2 + pw0 control) at max_thinking_tokens=300
   to (a) match the original paper's regime, (b) test whether CoT budget modulates baseline
   spillover (32B/4096 curves show almost no baseline spillover; paper's 4B/300 showed
   heavy spillover), (c) deconfound the old-vs-new mitigation comparison at 8B.
4. Mechanism analysis (no training): style-presence judge over saved rollouts — show pirate
   runs' CoT stays unpirated while output is pirated; ~$20-40 GPT-4o-mini.
5. Final plots: add v9 mitigation dots (incl. M&F from eval-penalty-v9mf) to the combined
   pareto; poly-env figure from rollouts; v8 figure.
6. Dashboard refresh + redeploy with v7/v8/v9.
7. Writing: compare-to-prior-work table (their Fig 4 numbers vs ours), mechanism framing
   (style separation ≈ parametric mitigation without a second model).
8. Open user decisions: seed 43 for v8 (~$525, on hold); M&F+pirate for poly env (not run);
   second non-QA environment is DONE (poly) — terminal env ruled out (days of eng, 40k episodes).

## 10. User preferences (this project)

- Monitor autonomously w/ event-driven watchers; brief acks for routine events.
- Pre-authorized: pausing 8B runs for deadline throughput (done once); eval re-runs; plot refreshes.
- NOT pre-authorized: new training spend (ask w/ cost estimate first), external publishes
  (HF account Jozdien now approved; Cloudflare deploy approved per-instance).
- Cost estimates BEFORE launching anything new; measure from real rollout data when possible.
- Keep HANDOFF.md (this, for Claudes) + CHECKIN.md (user-facing, concise, inline plots) updated.

## Addendum (2026-06-14) — M&F EVAL BUG (affects headline numbers)
eval_grpo_mind_face.py HARDCODED cot max_tokens=300 (now a --max-cot-tokens flag, default
4096). All earlier v9 M&F/TMF evals (8b+32b, trained at thinking=4096) were thus evaluated
with the CoT truncated to 300 tokens — NOT comparable to RT/pirate/no-SFT (evaluated at 4096).
So the M&F/TMF Pareto dots (M&F 0.28/TMF 0.45 @8B; M&F 0.33 @32B) and the "M&F worst /
scale-flip" framing are SUSPECT until re-eval. Wrong evals moved to
logs/eval-penalty-v9mf-WRONG300/. Re-running finals at 4096 (eval_all_v9mf --finals-only
--max-cot-tokens 4096) 2026-06-14; regenerate pareto after. For t300 runs, 300 IS the correct
budget. LESSON: eval CoT budget must match each run's training max_thinking_tokens.

## Addendum (2026-06-13)
- ALL TRAINING COMPLETE: 118 runs, 0 lost. 8B v9 fleet finished + evaluated.
- Concurrent-eval hazard: two eval loops (or a manual run + a sleeping loop) can evaluate the
  same checkpoint at once and clobber the output file (left tmf-8b-s43 with 50/378 rows).
  Fixed by killing redundant loops + re-running. TODO: add a .lock/.inprogress marker in the
  eval orchestrators so the same (run,ckpt) can't launch twice.
- thinking=300 base case launched (grpo-t300base-8b-pw{0,-2}-s{42,43}). Eval with
  --max-cot-tokens 300 to match training budget, NOT the default 4096.
- Key result: matched 8B mitigation Pareto done. Pirate-output (CoT 0.47) > all 3 prior
  mitigations (RT 0.20, MF 0.28, TMF 0.45); pirate+RT best (0.60). RT is scale-unstable
  (0.20 @ 8B vs 0.62 @ 32B); pirate-output is scale-stable (0.47→0.55). 2 seeds; sanity-check
  RT rollouts before relying on the scale-flip.

## Addendum (2026-06-12 ~22:00)
- eval_grpo_mind_face.py writes its own output names ({model_slug}_mf_{ckpt}.jsonl incl
  "_mf_final"); eval_all_v9mf.py skip-detection fixed to match (was re-evaluating everything
  each sweep — duplicate evals were overwritten harmlessly).
- M&F 32B eval coverage COMPLETE: 8 runs × 10 checkpoints incl finals, 0 failures.
