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
`figures/` holds self-contained copies of the generated plots. Regenerate via scripts in
`../scripts/` (data in `../logs/eval-penalty-*`):
- `pareto_sft.png` — core SFT result, 8B+32B — `scripts/plot_pareto_clean.py`
- `pareto_mitigations.png`, `pareto_stacking.png` — `scripts/plot_pareto_clean.py`
- `pareto_mitigations_t300.png` — `scripts/plot_pareto_t300_mitigations.py`
- `t300_vs_4096_spillover.png` — `scripts/plot_t300.py`
- `v9_poly_32b.png` — `scripts/plot_v9_training_curves.py`
- `v8_vs_qwen3_base.png` — `scripts/plot_v8_training_curves.py`

## Where the numbers come from
See `../RESULTS.md` — the full results reference (every claim with its numbers, plot,
eval-data path, and generating script). This draft is built from it section-for-section.

## Structure
1 Intro · 2 Background/Related · 3 Setup · 4 Core result (style separation, Fig 1 + Tab 1)
· 5 Mitigation comparison + composition (Fig 2 + Tab 2) · 6 Regime-dependence (Fig 3) ·
7 CoT-style induces spillover · 8 Generality (poly + cross-model) · 9 Discussion
(mechanism, output-minimization nuance, limitations, future work) · Appendix.
