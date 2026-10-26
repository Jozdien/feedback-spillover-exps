# Paper draft — Style Separation: Distinct reasoning and output styles can mitigate feedback spillover

LaTeX draft in the NeurIPS 2026 preprint style (`neurips_2026.sty` is in this folder).

## Build
```
cd paper
latexmk -pdf -interaction=nonstopmode main.tex
# or: pdflatex main && bibtex main && pdflatex main && pdflatex main
```

## Structure
1 Introduction (Figure 1 is the schematic) · 2 Related Work · 3 Methods · 4 Results: 4.1 style
separation in the main setting (Fig 2) · 4.2 combined with the prior mitigations (Fig 3) · 4.3
Qwen3.6-27B in QA and polynomial factoring (Fig 4, Table 1), closing on the other models ·
5 Discussion and Limitations · Appendices, each answering one question a reader of the body has:
A full results for the main settings (Table 2: CoT hint detection for every QA condition on both
models, laid out like Figure 3's table; Fig 5: every seed of the QA mitigation runs in Figure 3's
layout; Fig 6: every polynomial seed on Qwen3.6-27B; four highlights the body does not discuss),
B unstyled SFT and styled CoTs (Fig 7, a dumbbell of each starting model with and without the
penalty), C results on other models and environments (Fig 8 screen; C.1 mitigations on other Qwen
models, Fig 9; C.2 polynomial factoring on Qwen3-8B; C.3 the terminal environment, Fig 10), D the
explanation check and the style reward (Table 3), then E to I reference material (training
details, reward and mitigations, environments, SFT data, judge prompts). 25 pages; the body ends at
the top of page 8.

## Where the numbers come from
Figures 2–4 come from the training logs via `make_paper_figures.py`, which also writes
`figures/paper_numbers.json` (every per-seed and mean value behind them). Every appendix figure is
drawn from that file by `make_appendix_figures.py`, and Table 2 is filled from it too. Table 3 (the
explanation check) comes from `../RESULTS.md`. Tables give the sample standard deviation over seeds;
figures give 95% t intervals over seeds or show the seeds.

## Figures
```
cd paper && uv run make_paper_figures.py      # reads ../logs/, writes the body figures + paper_numbers.json
cd paper && uv run make_appendix_figures.py   # reads figures/paper_numbers.json only
```
The body uses `main_scatter_nolegend` (Fig 2, with its inline table; `\maintabletrue`),
`compose_8b` (Fig 3) and `envs_pareto2` (Fig 4); `figure_1` is drawn by hand. The appendix uses
`qa_all_seeds` (Fig 5), `poly_seeds` (Fig 6), `sft_dumbbell` (Fig 7), `screen` (Fig 8),
`other_qwen` (Fig 9) and `terminal_bars` (Fig 10). Seeds marked by hand from the run audits (the
collapsed pirate-CoT seeds, the terminal seeds that stopped reading the verifier) are listed at the top
of `make_appendix_figures.py`. The other PDFs in `figures/` and `make_figures.py` belong to earlier
drafts and are no longer referenced. Palette: grays for the controls, cool colors (squares) for the
prior mitigations, warm colors (diamonds) for the three styles, mid gray for unstyled SFT and purple
for the pirate CoT; a color means the same condition in every figure. Fonts: Inter.

## Conventions
- The paper names no scripts, files, config fields or code constants, and does not narrate
  how the experiments or the draft changed over time. It states what was run and what was
  found.
- The claim is about stylistic separation between output and CoT: it can mitigate feedback
  spillover. Style separation is the SFT pass plus the style reward that keeps the style in
  place during RL. The paper does not present "only while the style is maintained" as a
  finding or attach it to the headline claim as a caveat; that is the intervention being in
  place. The runs without the style reward are explained briefly because they are plotted.
- Condition names are fixed in Methods (plain penalty, explanation check, style reward) and
  used unchanged in the text, captions and figure labels.
- Body captions open with a bold sentence stating the finding, then say how to read the
  display, what the error bars are and how many seeds. Appendix captions are plain.
- Claims are scoped to the runs behind them (seeds, model, CoT budget).

## Status (2026-10-26)
Appendix pass on Jose's brief: every appendix element kept only if it answers a question a reader of
the body has. Cut: the unstyled SFT on other prompts, the per-seed table, the three per-model tables
and two per-model figures (now one figure), the screen table, the reward/genuine/style columns, the
SFT-cleaning minutiae and the redundant reward formulas. The style-reward ablation moved to Appendix D
(why the reward has its two added terms; the Pig Latin sequence 0.57 / 0.36 / 0.56). Body captions of
Figures 1-4 and Table 1 rewritten; `envs_pareto2` redrawn from paper_numbers.json with the CoT
intervals clipped to [0, 1] (the same change is in `make_paper_figures.py`, via `cot_err`). The 4.3
sentence on the other models now says the 16 models ran in QA (two also in polynomial factoring) and
only the two main models in the terminal environment.

Numbers still to confirm from the logs (added 2026-10-26):
- Figure 8 labels DeepSeek-V3.1 "stops explaining under the penalty" (its genuine-explanation rate
  under the penalty is 0.36, and its task reward after the check 0.13); check its raw hint-following
  in the rollouts.

## Status (2026-10-25)
Jose's pass over Methods and Results 4.1 to 4.2, with his inline comments addressed: the style
term is introduced in the style-separation paragraph rather than the displayed reward (lambda
stays a symbol because it is 2 in QA, 1 in polynomial factoring and 0.75 in terminal); the old
4.4 on styling the CoT is folded into 4.1 as one paragraph, with its figure; the
parametric/conditional-spillover account of style separation sits in Methods, and 4.2 tests its
prediction (stacks with reward targeting and Targeted M&F, not with Mind & Face); 4.3 rewritten
in the same register. The body's
unstyled SFT control is now the prompt-matched one (0.31). Follow-up: the intro states the
Mind & Face analogy in plain prose; 4.1 explains the pirate-CoT result by the same account (the
rewritten CoTs are a model's output text) plus the separate effect of training on CoTs the
model would not have written; Methods says the unstyled SFT control covers the off-policyness the SFT pipeline itself
introduces (fixed data, not on-policy SFT). Later: the styled-CoT models and the account's
prediction for them moved into Methods, and the styled-CoT result is its own subsection again (4.4). Then (2026-10-26) the styled-CoT results moved to
Appendix B, mentioned in the body in one sentence in Methods and one in the Discussion. Then Jose rewrote the intro,
contributions and Discussion, and a references pass added 41 verified citations (new Related Work
paragraph on personas and generalization; Drori et al. now cited as ICLR 2026). Jose will edit the intro and discussion.

Previous pass (2026-10-24): concision and structure pass on Jose's brief (paper-editor `.editing-notes/EDIT_BRIEF_2026-10-24.md`):
Methods in four paragraphs, each results subsection cut to its claim, 4.3 led by Qwen3.6-27B,
appendices consolidated. Removed: the long-CoT-budget appendix and its table, the no-spillover
per-seed table, the cross-environment table, the unfiltered pirate data. The old figure files
(`envs_bars`, `compose_vertical`, `envs_pareto`, `cotstyle`, previews) are unused.

Numbers still to confirm from the logs:
- Explanation-check table: the Pig Latin control's genuine-explanation rate (0.93), and the plain
  penalty's 72%, which is judged on seeds 42–49 only.
- The share of CoTs cut off at the 300-token limit (the paper says 85–90%).
