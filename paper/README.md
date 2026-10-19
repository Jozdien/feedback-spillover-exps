# Paper draft — Style Separation: A distinct output style can mitigate feedback spillover

LaTeX draft in the NeurIPS 2026 preprint style (`neurips_2026.sty` is in this folder).

## Build
```
cd paper
latexmk -pdf -interaction=nonstopmode main.tex
# or: pdflatex main && bibtex main && pdflatex main && pdflatex main
```

## Structure
1 Introduction (Figure 1 is the schematic) · 2 Related Work · 3 Methods ·
4 Results: 4.1 style separation in the main setting (Fig 2) · 4.2 combined with the prior
mitigations (Fig 3) · 4.3 other environments and models: where spillover appears (Fig 4) and the
mitigations where it does (Fig 5) · 4.4 styling the CoT · 5 Discussion and Limitations ·
Appendices A–H, results first (full numbers, the explanation check, the long CoT budget), then
reference material (training details, reward, environments, SFT data, judge prompts).

## Where the numbers come from
Figures 2–5 and Tables 1–2 come from the training logs via `make_paper_figures.py`, which also
writes `figures/paper_numbers.json` (every per-seed and mean value behind them). Other tables come
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

## Status (2026-10-19)
Plot and text pass: means-only main figure with bars (or a table), vertical composition bars, a
spillover screen over every model and environment, and per-seed bars for the other spillover
settings. The section on the reward without the explanation check, its figure, and the
output–CoT coupling appendix figure were removed; the check is described in Methods with a short
appendix. Claims in Section 4.3 are stated against reward targeting, Targeted M&F, the plain penalty
and the no-penalty control. Mitigations were not run on the three Qwen3.5 models that spill.

Numbers still to confirm from the logs:
- Explanation-check table: the Pig Latin control's genuine-explanation rate (0.93), and the plain
  penalty's 72%, which is judged on seeds 42–49 only.
- The share of CoTs cut off at the 300-token limit (the paper says 85–90%).
- Whether the pirate-CoT models' CoTs stayed in pirate-speak through RL.
