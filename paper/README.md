# Paper draft — Style Separation Cheaply Mitigates Feedback Spillover

Working LaTeX draft. Self-contained: `main.tex` compiles with a generic article
preamble approximating NeurIPS margins, so no external `.sty` is required to build.

## Build
```
cd paper
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

## To switch to a real conference style
Replace the marked preamble block at the top of `main.tex` with
`\usepackage{neurips_2025}` (or `iclr2025_conference`) and drop in that style file.

## Status
Real, seed-averaged final-checkpoint numbers are in for every table and figure. `\todo{}`
marks (red in PDF) flag remaining writing/decisions, not missing results — the main ones:
- author affiliation;
- the SFT-data description (size / how the pirate rewriting was produced / an example);
- the explicit list of differences from Drori et al. (LoRA, two-phase sampling, etc.);
- the style-generality ablation (not yet run — the one recommended new experiment);
- the cross-model section is no-SFT-only on the new models (decide scope);
- verify the prior-work comparison numbers (Table, appendix) against their PDF;
- appendix expansion (penalty sweep, full numbers, eval-budget bug, transcripts).

## Figures
`figures/` holds the paper figures as **titleless vector PDFs** with one semantic palette
reused across the paper (per the writing-papers skill — the LaTeX `\caption` carries the
takeaway, so the figures have no on-figure title). Regenerate all of them with:
```
cd paper && uv run make_figures.py   # reads ../logs/eval-penalty-*, writes figures/*.pdf
```
`make_figures.py` is self-contained (palette + matplotlib style in `figstyle.py`); it is the
paper-figure analog of the working/dashboard plots in `../scripts/plot_*.py`. Figures:
pareto_sft · pareto_mitigations · pareto_stacking · pareto_mitigations_t300 ·
t300_vs_4096_spillover · v9_poly_32b · v8_vs_qwen3_base.

## Where the numbers come from
See `../RESULTS.md` — the full results reference (every claim with its numbers, plot,
eval-data path, and generating script). This draft is built from it section-for-section.

## Structure
1 Intro · 2 Background/Related · 3 Setup · 4 Core result (style separation, Fig 1 + Tab 1)
· 5 Mitigation comparison + composition (Fig 2 + Tab 2) · 6 Regime-dependence (Fig 3) ·
7 CoT-style induces spillover · 8 Generality (poly + cross-model) · 9 Discussion
(mechanism, output-minimization nuance, limitations, future work) · Appendix.
