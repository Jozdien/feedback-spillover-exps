# Paper draft — Style Separation: A maintained output style can mitigate feedback spillover

LaTeX draft in the NeurIPS 2026 preprint style (`neurips_2026.sty` is in this folder).

## Build
```
cd paper
latexmk -pdf -interaction=nonstopmode main.tex
# or: pdflatex main && bibtex main && pdflatex main && pdflatex main
```

## Structure
1 Introduction (Figure 1 is the schematic) · 2 Related Work · 3 Methods ·
4 Results: 4.1 maintained styles under the explanation gate (Fig 2, Tab 1) ·
4.2 the plain reward, where the styled models stop explaining (Fig 3) ·
4.3 other environments and models (Fig 4) · 4.4 styling the CoT ·
5 Discussion and Limitations · Appendices A–I, results first (full numbers, what the
penalized outputs contain, coupling at initialization, the long CoT budget), then reference
material (training details, reward, environments, SFT data, judge prompts).

## Where the numbers come from
`../RESULTS.md` and `../plots/gated_pareto_all.json`. The tables give the sample standard
deviation over seeds, from the JSON. Several ± values in `RESULTS.md` are population
standard deviations, so the two differ slightly.

## Figures
The draft uses `figure_1`, `pareto_gated_8b`, `gate_bars`, `pareto_envs_models` and
`coupling_bars`. The other PDFs in `figures/` belong to earlier drafts and are no longer
referenced. All but `figure_1` are written by
```
cd paper && uv run make_figures.py   # reads ../logs/, writes figures/*.pdf
```
Figures are titleless vector PDFs; the `\caption` carries the takeaway.

## Conventions
- The paper names no scripts, files, config fields or code constants, and does not narrate
  how the experiments or the draft changed over time. It states what was run and what was
  found.
- Condition names are fixed in Methods (plain reward, plain penalty, explanation gate, style
  reward, maintained) and used unchanged in the text, captions and figure labels.
- Body captions open with a bold sentence stating the finding, then say how to read the
  display, what the error bars are and how many seeds. Appendix captions are plain.
- Claims are scoped to the runs behind them (seeds, model, CoT budget).

## Status (2026-09-28)
The draft was restructured and edited on this date. Results added to `RESULTS.md` since
then (§16h, the spillover test on 14 more models) are not in the paper.

Figures to regenerate:
- `coupling_bars`: tick labels "v1 data" / "v2 data" should read unfiltered / filtered; the
  hatch for short outputs does not show; the Chinese bar's split counts space-separated
  words, which undercounts Chinese.
- `gate_bars`: labels "no gate", "word-count gate", "judge gate", "No SFT" should use the
  paper's terms (plain reward, 20-word minimum, explanation gate, plain penalty); the fill
  patterns need a legend.
- `pareto_gated_8b`: relabel or drop the "no gate" cross; the legend is crossed by the zero
  line; the styled models' own no-penalty controls and the normal SFT control are not
  plotted; error bars extend past a reward of 1.
- `pareto_envs_models`: error bars run past the axes and several markers overlap.
- All four: error bars are 1.96 standard errors at 3 and 5 seeds (a t interval is wider);
  the figures are drawn 6.5 in wide for a 5.5 in text block, so their text prints small.

Numbers to confirm from the logs:
- Output table: the Pig Latin control's genuine-explanation rate (0.93).
- Terminal table: the Chinese rows' "read" and "genuine" values, and how episodes that do
  not read the verifier earn task reward (pirate: task 0.28 at a read rate of 0.01).
- The plain penalty's 72% genuine-explanation rate is judged on seeds 42–49 only.
- The share of CoTs cut off at the 300-token limit (the paper says 85–90%).
- Per-seed values for Chinese in the terminal environment, Targeted M&F on Qwen3.6-27B,
  and Pig Latin on Qwen3.6-35B-A3B; sample standard deviations for the styled models'
  no-penalty controls on Qwen3-8B.
- Whether the pirate-CoT models' CoTs stayed in pirate-speak through RL.
- Six table cells sit on a rounding boundary in the JSON, which stores three decimals:
  Table 1 reward targeting reward (0.575), Mind & Face "out" (0.045), normal SFT reward
  (0.655); Table 2 Targeted M&F on Qwen3.6-27B (0.855) and the polynomial Pig Latin standard
  deviation (0.005); Table 4 Pig Latin no-penalty task (0.995).
