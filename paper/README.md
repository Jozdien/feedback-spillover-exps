# Paper draft — Style Separation: A distinct output style can mitigate feedback spillover

LaTeX draft in the NeurIPS 2026 preprint style (`neurips_2026.sty` is in this folder).

## Build
```
cd paper
latexmk -pdf -interaction=nonstopmode main.tex
# or: pdflatex main && bibtex main && pdflatex main && pdflatex main
```

## Structure
1 Introduction (Figure 1 is the schematic) · 2 Related Work · 3 Methods (four paragraphs) ·
4 Results: 4.1 style separation in the main setting, with the unstyled SFT control (Fig 2) ·
4.2 combined with the prior mitigations, testing the parametric/conditional account in Methods
(Fig 3) · 4.3 Qwen3.6-27B in QA and polynomial factoring, closing on the other models (Fig 4) ·
5 Discussion and Limitations · Appendices: A full results for the main settings, B styling the
CoT (the pirate-CoT result, its explanation, the 27B runs), C results on other models (the
spillover screen first), D the terminal environment, E the explanation check, then F to J
reference material (training details, reward, environments, SFT data, judge prompts). The body
ends on page 7.

## Where the numbers come from
Figures 2–5 come from the training logs via `make_paper_figures.py`, which also writes
`figures/paper_numbers.json` (every per-seed and mean value behind them); the appendix bar
figures are drawn from that file by `make_appendix_figures.py`. Other tables come
from `../RESULTS.md` and `../plots/gated_pareto_all.json`. Tables give the sample standard deviation
over seeds; figure error bars are 95% t intervals over seeds.

## Figures
```
cd paper && uv run make_paper_figures.py   # reads ../logs/, writes the body figures + paper_numbers.json
```
writes `main_scatter_bars` (Fig 2, default), `main_scatter_nolegend` (Fig 2 with the table, the
alternative layout: set `\maintabletrue` in the preamble), `compose_vertical` (Fig 3),
`spillover_screen` (Fig 4) and `envs_bars` (Fig 5). `figure_1` is drawn by hand. The other PDFs in
`figures/` and `make_figures.py` belong to earlier drafts and are no longer referenced.
Palette: grays for the controls, cool colors (squares) for the prior mitigations, warm colors
(diamonds) for the three styles; a color means the same condition in every figure.

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
Appendix B, mentioned in the body in one sentence in Methods and one in the Discussion. Jose will edit the intro and discussion.

Previous pass (2026-10-24): concision and structure pass on Jose's brief (paper-editor `.editing-notes/EDIT_BRIEF_2026-10-24.md`):
Methods in four paragraphs, each results subsection cut to its claim, 4.3 led by Qwen3.6-27B,
appendices consolidated. Removed: the long-CoT-budget appendix and its table, the no-spillover
per-seed table, the cross-environment table, the unfiltered pirate data. The old figure files
(`envs_bars`, `compose_vertical`, `envs_pareto`, `cotstyle`, previews) are unused.

Numbers still to confirm from the logs:
- Explanation-check table: the Pig Latin control's genuine-explanation rate (0.93), and the plain
  penalty's 72%, which is judged on seeds 42–49 only.
- The share of CoTs cut off at the 300-token limit (the paper says 85–90%).
