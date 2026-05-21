#!/usr/bin/env python3
"""Build a self-contained HTML dashboard for viewing RL spillover eval results.

Reads all eval JSONL files and plot PNGs, embeds everything as base64/JSON
into a single dashboard.html file.
"""

import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLOTS_DIR = ROOT / "plots"
OUTPUT_HTML = ROOT / "dashboard.html"

EVAL_DIRS = {
    "original": ROOT / "logs" / "eval-penalty",
    "v2": ROOT / "logs" / "eval-penalty-v2",
    "v3": ROOT / "logs" / "eval-penalty-v3",
    "control": ROOT / "logs" / "eval-control",
}

PLOT_NAMES = [
    "combined_pareto_dots",
    "v2_pareto_cot_vs_output",
    "v2_spillover_curves",
    "v3_pareto_cot_vs_output",
    "v3_spillover_curves",
    "ctrl_pareto_cot_vs_output",
    "ctrl_spillover_curves",
    "pareto_all_conditions",
    "spillover_curves",
    "spillover_by_source",
    "pareto_cot_vs_output",
    "final_comparison",
    "correctness_curves",
]

STEP_ORDER = ["000000", "000100", "000200", "000300", "000400",
              "000500", "000600", "000700", "000800", "000900", "001000", "final"]
STEP_LABELS = {
    "000000": "0", "000100": "100", "000200": "200", "000300": "300",
    "000400": "400", "000500": "500", "000600": "600", "000700": "700",
    "000800": "800", "000900": "900", "001000": "1000", "final": "1000",
}


def encode_plot(name: str) -> str | None:
    path = PLOTS_DIR / f"{name}.png"
    if not path.exists():
        print(f"  WARNING: plot {path} not found, skipping")
        return None
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


def parse_run_name(dirname: str, version: str = "original"):
    """Parse run directory name, handling v2/v3/ctrl prefixes."""
    m = re.match(
        r"grpo-(?:v[23]-|ctrl-)?(8b|32b)-(pirate-output|pirate-cot|normal)-(\w+)-s(\d+)",
        dirname,
    )
    if not m:
        return None
    return {
        "size": m.group(1),
        "condition": m.group(2),
        "source": m.group(3),
        "seed": int(m.group(4)),
        "version": version,
    }


def load_jsonl(path: Path):
    """Load a JSONL eval file, returning (summary, samples)."""
    summary = None
    samples = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("type") == "metadata":
                continue
            elif obj.get("type") == "summary":
                summary = {
                    "n": obj.get("n", 0),
                    "sycophancy": obj.get("sycophancy", 0),
                    "real_correct": obj.get("real_correct", 0),
                    "hint_in_output": obj.get("hint_in_output", 0),
                    "hint_in_cot": obj.get("hint_in_cot", 0),
                }
            elif obj.get("type") == "result":
                samples.append({
                    "question": obj.get("question", ""),
                    "target": obj.get("target", ""),
                    "correct_answer": obj.get("correct_answer", ""),
                    "cot_text": obj.get("cot_text", ""),
                    "out_text": obj.get("out_text", ""),
                    "sycophancy": obj.get("sycophancy", 0),
                    "real_correct": obj.get("real_correct", 0),
                    "out_score": obj.get("out_score", 0),
                    "cot_score": obj.get("cot_score", 0),
                })
    # Compute summary from samples if not present
    if summary is None and samples:
        n = len(samples)
        summary = {
            "n": n,
            "sycophancy": sum(s["sycophancy"] for s in samples) / n,
            "real_correct": sum(s["real_correct"] for s in samples) / n,
            "hint_in_output": sum(s["out_score"] for s in samples) / n,
            "hint_in_cot": sum(s["cot_score"] for s in samples) / n,
        }
    return summary, samples


def find_jsonl_files(run_dir: Path):
    """Find all JSONL files in a run dir, return dict of step -> path."""
    steps = {}
    for f in sorted(run_dir.glob("*.jsonl")):
        for step_key in STEP_ORDER:
            if step_key in f.stem:
                steps[step_key] = f
                break
    return steps


SAMPLES_DIR = ROOT / "dashboard_data"


def main():
    print("Building dashboard...")

    # 1. Encode plots
    print("Encoding plots...")
    plots = {}
    for name in PLOT_NAMES:
        encoded = encode_plot(name)
        if encoded:
            plots[name] = encoded
            print(f"  {name}: {len(encoded) // 1024}KB base64")

    # 2. Load all eval data — summaries inline, samples to separate files
    print("Loading eval data...")
    SAMPLES_DIR.mkdir(exist_ok=True)
    runs = {}
    total_samples = 0

    for version, eval_dir in EVAL_DIRS.items():
        if not eval_dir.exists():
            print(f"  Skipping {version}: {eval_dir} not found")
            continue
        run_dirs = sorted(eval_dir.iterdir())
        print(f"  Loading {version} from {eval_dir} ({len([d for d in run_dirs if d.is_dir()])} dirs)")

        for run_dir in run_dirs:
            if not run_dir.is_dir():
                continue
            info = parse_run_name(run_dir.name, version)
            if info is None:
                continue

            jsonl_files = find_jsonl_files(run_dir)
            if not jsonl_files:
                continue

            steps_data = {}
            run_samples = 0
            for step_key, path in jsonl_files.items():
                summary, samples = load_jsonl(path)
                step_label = STEP_LABELS[step_key]
                steps_data[step_label] = {"summary": summary, "n_samples": len(samples)}

                if samples:
                    sample_file = SAMPLES_DIR / f"{version}_{run_dir.name}_step{step_label}.json"
                    sample_file.write_text(json.dumps(samples, separators=(",", ":")))
                    run_samples += len(samples)

            run_key = f"{version}/{run_dir.name}"
            runs[run_key] = {
                "size": info["size"],
                "condition": info["condition"],
                "source": info["source"],
                "seed": info["seed"],
                "version": version,
                "steps": steps_data,
            }
            total_samples += run_samples
            n_steps = len(steps_data)
            print(f"    {run_dir.name}: {n_steps} steps, {run_samples} samples")

    # 3. Build the index JSON (summaries only, no samples)
    data = {"plots": plots, "runs": runs}
    data_json = json.dumps(data, separators=(",", ":"))
    print(f"Index JSON size: {len(data_json) / 1024 / 1024:.1f}MB")
    print(f"Sample files in dashboard_data/: {total_samples} samples across {len(list(SAMPLES_DIR.glob('*.json')))} files")

    # 4. Build HTML
    print("Building HTML...")
    html = build_html(data_json, len(runs))

    OUTPUT_HTML.write_text(html)
    print(f"Dashboard written to {OUTPUT_HTML}")
    print(f"File size: {OUTPUT_HTML.stat().st_size / 1024 / 1024:.1f}MB")
    print(f"\nTo view: cd {ROOT} && python3 -m http.server 8080")
    print(f"Then open http://localhost:8080/dashboard.html")


def build_html(data_json: str, n_runs: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Feedback Spillover Experiments</title>
<style>
:root {{
  --bg-primary: #1a1b2e;
  --bg-secondary: #242640;
  --bg-tertiary: #2d2f4a;
  --bg-card: #2a2c48;
  --text-primary: #e8e9f3;
  --text-secondary: #a0a3bd;
  --text-muted: #6b6f8d;
  --accent: #7c5cfc;
  --accent-hover: #9b82fd;
  --accent-dim: rgba(124, 92, 252, 0.15);
  --border: #3a3c5a;
  --green: #4ade80;
  --green-dim: rgba(74, 222, 128, 0.15);
  --red: #f87171;
  --red-dim: rgba(248, 113, 113, 0.15);
  --yellow: #fbbf24;
  --yellow-dim: rgba(251, 191, 36, 0.15);
  --blue: #60a5fa;
  --radius: 8px;
  --radius-lg: 12px;
  --shadow: 0 4px 24px rgba(0,0,0,0.3);
  --transition: 0.2s ease;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  line-height: 1.6;
  min-height: 100vh;
}}

/* Header */
.header {{
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  padding: 24px 32px;
}}
.header h1 {{
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}}
.header .subtitle {{
  color: var(--text-secondary);
  font-size: 0.875rem;
  margin-top: 4px;
}}

/* Tabs */
.tab-bar {{
  display: flex;
  gap: 0;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  padding: 0 32px;
}}
.tab-btn {{
  padding: 12px 24px;
  border: none;
  background: none;
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all var(--transition);
}}
.tab-btn:hover {{
  color: var(--text-primary);
  background: var(--bg-tertiary);
}}
.tab-btn.active {{
  color: var(--accent);
  border-bottom-color: var(--accent);
}}

/* Content */
.content {{
  padding: 24px 32px;
  max-width: 1600px;
  margin: 0 auto;
}}
.tab-panel {{
  display: none;
}}
.tab-panel.active {{
  display: block;
}}

/* Plot grid */
.plot-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(500px, 1fr));
  gap: 20px;
}}
.plot-card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: transform var(--transition), box-shadow var(--transition);
}}
.plot-card:hover {{
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}}
.plot-card img {{
  width: 100%;
  height: auto;
  display: block;
}}
.plot-card .plot-label {{
  padding: 12px 16px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  font-weight: 500;
  text-transform: capitalize;
}}

/* Lightbox */
.lightbox {{
  display: none;
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.85);
  z-index: 1000;
  justify-content: center;
  align-items: center;
  cursor: pointer;
}}
.lightbox.open {{
  display: flex;
}}
.lightbox img {{
  max-width: 95vw;
  max-height: 95vh;
  border-radius: var(--radius);
}}

/* Tables */
.table-controls {{
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
  align-items: center;
}}
.filter-select {{
  padding: 8px 12px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 0.8rem;
  cursor: pointer;
}}
.filter-select:focus {{
  outline: none;
  border-color: var(--accent);
}}

table {{
  width: 100%;
  border-collapse: collapse;
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  overflow: hidden;
  font-size: 0.85rem;
}}
thead th {{
  background: var(--bg-tertiary);
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  border-bottom: 1px solid var(--border);
}}
thead th:hover {{
  color: var(--text-primary);
}}
thead th .sort-arrow {{
  margin-left: 4px;
  opacity: 0.4;
}}
thead th.sorted .sort-arrow {{
  opacity: 1;
  color: var(--accent);
}}
tbody td {{
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
}}
tbody tr:hover {{
  background: var(--accent-dim);
}}
tbody tr:last-child td {{
  border-bottom: none;
}}

/* Score cells */
.score-cell {{
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  border-radius: 4px;
  padding: 2px 8px;
  display: inline-block;
  min-width: 60px;
  text-align: center;
}}

/* Training curves tab */
.run-selector {{
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  align-items: center;
  flex-wrap: wrap;
}}
.run-selector label {{
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-weight: 500;
}}

/* Sample browser */
.sample-controls {{
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  align-items: center;
  flex-wrap: wrap;
}}
.sample-nav {{
  display: flex;
  gap: 8px;
  align-items: center;
}}
.nav-btn {{
  padding: 8px 16px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 0.85rem;
  transition: all var(--transition);
}}
.nav-btn:hover:not(:disabled) {{
  background: var(--accent);
  border-color: var(--accent);
}}
.nav-btn:disabled {{
  opacity: 0.4;
  cursor: not-allowed;
}}
.sample-counter {{
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
  min-width: 100px;
  text-align: center;
}}

.sample-card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}}
.sample-section {{
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}}
.sample-section:last-child {{
  border-bottom: none;
}}
.sample-section-label {{
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 8px;
}}
.sample-question {{
  white-space: pre-wrap;
  font-size: 0.85rem;
  line-height: 1.7;
}}
.sample-text {{
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 0.8rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--bg-primary);
  padding: 16px;
  border-radius: var(--radius);
  max-height: none;
}}
.sample-cot {{
  border-left: 3px solid var(--accent);
}}
.sample-output {{
  border-left: 3px solid var(--green);
}}
.sample-scores {{
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}}
.score-badge {{
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 16px;
  background: var(--bg-primary);
  border-radius: var(--radius);
  min-width: 100px;
}}
.score-badge .score-label {{
  font-size: 0.7rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 4px;
}}
.score-badge .score-value {{
  font-size: 1.1rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}}

.highlight-target {{
  background: var(--red-dim);
  color: var(--red);
  padding: 1px 4px;
  border-radius: 3px;
  font-weight: 600;
}}
.highlight-correct {{
  background: var(--green-dim);
  color: var(--green);
  padding: 1px 4px;
  border-radius: 3px;
  font-weight: 600;
}}

.empty-state {{
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
  font-size: 0.9rem;
}}

/* Scrollbar */
::-webkit-scrollbar {{
  width: 8px;
  height: 8px;
}}
::-webkit-scrollbar-track {{
  background: var(--bg-primary);
}}
::-webkit-scrollbar-thumb {{
  background: var(--border);
  border-radius: 4px;
}}
::-webkit-scrollbar-thumb:hover {{
  background: var(--text-muted);
}}

/* Responsive */
@media (max-width: 768px) {{
  .content {{ padding: 16px; }}
  .plot-grid {{ grid-template-columns: 1fr; }}
  .tab-btn {{ padding: 10px 14px; font-size: 0.8rem; }}
}}
</style>
</head>
<body>

<div class="header">
  <h1>Feedback Spillover Experiments</h1>
  <div class="subtitle" id="header-subtitle">Loading...</div>
</div>

<div class="tab-bar">
  <button class="tab-btn active" data-tab="plots">Plots</button>
  <button class="tab-btn" data-tab="summary">Summary Table</button>
  <button class="tab-btn" data-tab="curves">Training Curves</button>
  <button class="tab-btn" data-tab="samples">Sample Browser</button>
</div>

<div class="content">
  <!-- Plots Tab -->
  <div class="tab-panel active" id="tab-plots">
    <div class="plot-grid" id="plot-grid"></div>
  </div>

  <!-- Summary Table Tab -->
  <div class="tab-panel" id="tab-summary">
    <div class="table-controls" id="summary-filters"></div>
    <div style="overflow-x: auto;">
      <table id="summary-table">
        <thead><tr id="summary-thead"></tr></thead>
        <tbody id="summary-tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- Training Curves Tab -->
  <div class="tab-panel" id="tab-curves">
    <div class="run-selector">
      <label>Select run:</label>
      <select class="filter-select" id="curves-run-select"></select>
    </div>
    <div style="overflow-x: auto;">
      <table id="curves-table">
        <thead>
          <tr>
            <th>Step</th>
            <th>N</th>
            <th>Sycophancy</th>
            <th>Real Correct</th>
            <th>Hint in Output</th>
            <th>Hint in CoT</th>
          </tr>
        </thead>
        <tbody id="curves-tbody"></tbody>
      </table>
    </div>
    <div class="empty-state" id="curves-empty">Select a run to view training curves</div>
  </div>

  <!-- Sample Browser Tab -->
  <div class="tab-panel" id="tab-samples">
    <div class="sample-controls">
      <label style="color: var(--text-secondary); font-size: 0.85rem; font-weight: 500;">Run:</label>
      <select class="filter-select" id="sample-run-select"></select>
      <label style="color: var(--text-secondary); font-size: 0.85rem; font-weight: 500;">Step:</label>
      <select class="filter-select" id="sample-step-select"></select>
      <div class="sample-nav">
        <button class="nav-btn" id="sample-prev" disabled>&larr; Prev</button>
        <span class="sample-counter" id="sample-counter">0 / 0</span>
        <button class="nav-btn" id="sample-next" disabled>Next &rarr;</button>
      </div>
    </div>
    <div id="sample-display">
      <div class="empty-state" id="sample-empty">Select a run and step to browse samples</div>
    </div>
  </div>
</div>

<!-- Lightbox -->
<div class="lightbox" id="lightbox">
  <img id="lightbox-img" src="" alt="">
</div>

<script>
// Embedded data
const DATA = {data_json};

// ---- Tab switching ----
const tabBtns = document.querySelectorAll('.tab-btn');
const tabPanels = document.querySelectorAll('.tab-panel');
tabBtns.forEach(btn => {{
  btn.addEventListener('click', () => {{
    tabBtns.forEach(b => b.classList.remove('active'));
    tabPanels.forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  }});
}});

// ---- Header ----
const runNames = Object.keys(DATA.runs);
const totalEvals = runNames.reduce((sum, r) => {{
  return sum + Object.keys(DATA.runs[r].steps).reduce((s2, step) => {{
    return s2 + (DATA.runs[r].steps[step].samples ? DATA.runs[r].steps[step].samples.length : 0);
  }}, 0);
}}, 0);
document.getElementById('header-subtitle').textContent =
  `${{runNames.length}} runs | ${{totalEvals.toLocaleString()}} eval samples loaded`;

// ---- Plots Tab ----
const plotGrid = document.getElementById('plot-grid');
const plotLabels = {{
  combined_pareto_dots: "Combined Pareto (All Conditions)",
  v2_pareto_cot_vs_output: "V2 (pw=-2) Pareto",
  v2_spillover_curves: "V2 (pw=-2) Spillover Curves",
  v3_pareto_cot_vs_output: "V3 (pw=-1) Pareto",
  v3_spillover_curves: "V3 (pw=-1) Spillover Curves",
  ctrl_pareto_cot_vs_output: "Control (pw=0) Pareto",
  ctrl_spillover_curves: "Control (pw=0) Spillover Curves",
  pareto_all_conditions: "Pareto: All Conditions (Older)",
  spillover_curves: "Spillover Curves (Original)",
  spillover_by_source: "Spillover by Source",
  pareto_cot_vs_output: "Pareto: CoT vs Output (Original)",
  final_comparison: "Final Comparison",
  correctness_curves: "Correctness Curves",
}};
Object.entries(DATA.plots).forEach(([name, src]) => {{
  const card = document.createElement('div');
  card.className = 'plot-card';
  card.innerHTML = `<img src="${{src}}" alt="${{name}}" loading="lazy"><div class="plot-label">${{plotLabels[name] || name.replace(/_/g, ' ')}}</div>`;
  card.addEventListener('click', () => {{
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox').classList.add('open');
  }});
  plotGrid.appendChild(card);
}});

// Lightbox close
document.getElementById('lightbox').addEventListener('click', () => {{
  document.getElementById('lightbox').classList.remove('open');
}});
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') document.getElementById('lightbox').classList.remove('open');
}});

// ---- Summary Table ----
const summaryColumns = [
  {{ key: 'name', label: 'Run', numeric: false }},
  {{ key: 'version', label: 'Version', numeric: false }},
  {{ key: 'size', label: 'Size', numeric: false }},
  {{ key: 'condition', label: 'Condition', numeric: false }},
  {{ key: 'source', label: 'Source', numeric: false }},
  {{ key: 'seed', label: 'Seed', numeric: true }},
  {{ key: 'sycophancy', label: 'Sycophancy', numeric: true }},
  {{ key: 'real_correct', label: 'Real Correct', numeric: true }},
  {{ key: 'hint_in_output', label: 'Hint in Output', numeric: true }},
  {{ key: 'hint_in_cot', label: 'Hint in CoT', numeric: true }},
];

function buildSummaryData() {{
  const rows = [];
  for (const [name, run] of Object.entries(DATA.runs)) {{
    // Use latest available step
    const allSteps = Object.keys(run.steps).map(Number).filter(n => !isNaN(n)).sort((a,b) => a-b);
    const lastStep = allSteps.length > 0 ? String(allSteps[allSteps.length - 1]) : null;
    if (!lastStep) continue;
    const final = run.steps[lastStep];
    if (!final || !final.summary) continue;
    rows.push({{
      name,
      version: run.version || 'original',
      size: run.size,
      condition: run.condition,
      source: run.source,
      seed: run.seed,
      sycophancy: final.summary.sycophancy,
      real_correct: final.summary.real_correct,
      hint_in_output: final.summary.hint_in_output,
      hint_in_cot: final.summary.hint_in_cot,
    }});
  }}
  return rows;
}}

let summaryData = buildSummaryData();
let summarySort = {{ key: 'name', asc: true }};
let summaryFilters = {{ version: '', size: '', condition: '', source: '' }};

function colorScore(value, type) {{
  // type: 'hint' (red=high bad), 'correct' (green=high good), 'syc' (red=high bad)
  const v = parseFloat(value);
  let bg, color;
  if (type === 'correct') {{
    if (v >= 0.7) {{ bg = 'var(--green-dim)'; color = 'var(--green)'; }}
    else if (v >= 0.4) {{ bg = 'var(--yellow-dim)'; color = 'var(--yellow)'; }}
    else {{ bg = 'var(--red-dim)'; color = 'var(--red)'; }}
  }} else {{
    // hint or sycophancy: low is good
    if (v <= 0.2) {{ bg = 'var(--green-dim)'; color = 'var(--green)'; }}
    else if (v <= 0.5) {{ bg = 'var(--yellow-dim)'; color = 'var(--yellow)'; }}
    else {{ bg = 'var(--red-dim)'; color = 'var(--red)'; }}
  }}
  return `<span class="score-cell" style="background:${{bg}};color:${{color}}">${{v.toFixed(3)}}</span>`;
}}

function renderSummaryTable() {{
  let rows = [...summaryData];

  // Apply filters
  if (summaryFilters.version) rows = rows.filter(r => r.version === summaryFilters.version);
  if (summaryFilters.size) rows = rows.filter(r => r.size === summaryFilters.size);
  if (summaryFilters.condition) rows = rows.filter(r => r.condition === summaryFilters.condition);
  if (summaryFilters.source) rows = rows.filter(r => r.source === summaryFilters.source);

  // Sort
  rows.sort((a, b) => {{
    let va = a[summarySort.key], vb = b[summarySort.key];
    if (typeof va === 'number' && typeof vb === 'number') {{
      return summarySort.asc ? va - vb : vb - va;
    }}
    va = String(va); vb = String(vb);
    return summarySort.asc ? va.localeCompare(vb) : vb.localeCompare(va);
  }});

  // Header
  const thead = document.getElementById('summary-thead');
  thead.innerHTML = summaryColumns.map(col => {{
    const sorted = summarySort.key === col.key;
    const arrow = sorted ? (summarySort.asc ? '\\u25B2' : '\\u25BC') : '\\u25B4';
    return `<th class="${{sorted ? 'sorted' : ''}}" data-sort="${{col.key}}">${{col.label}} <span class="sort-arrow">${{arrow}}</span></th>`;
  }}).join('');

  // Body
  const tbody = document.getElementById('summary-tbody');
  tbody.innerHTML = rows.map(r => `<tr>
    <td style="font-weight:500;font-size:0.8rem">${{r.name}}</td>
    <td>${{r.version}}</td>
    <td>${{r.size.toUpperCase()}}</td>
    <td>${{r.condition}}</td>
    <td>${{r.source}}</td>
    <td>${{r.seed}}</td>
    <td>${{colorScore(r.sycophancy, 'syc')}}</td>
    <td>${{colorScore(r.real_correct, 'correct')}}</td>
    <td>${{colorScore(r.hint_in_output, 'hint')}}</td>
    <td>${{colorScore(r.hint_in_cot, 'hint')}}</td>
  </tr>`).join('');

  // Attach sort handlers
  thead.querySelectorAll('th').forEach(th => {{
    th.addEventListener('click', () => {{
      const key = th.dataset.sort;
      if (summarySort.key === key) summarySort.asc = !summarySort.asc;
      else {{ summarySort.key = key; summarySort.asc = true; }}
      renderSummaryTable();
    }});
  }});
}}

// Build filter dropdowns
function buildFilters() {{
  const container = document.getElementById('summary-filters');
  const versions = [...new Set(summaryData.map(r => r.version))].sort();
  const sizes = [...new Set(summaryData.map(r => r.size))].sort();
  const conditions = [...new Set(summaryData.map(r => r.condition))].sort();
  const sources = [...new Set(summaryData.map(r => r.source))].sort();

  function makeFilter(label, key, options) {{
    const select = document.createElement('select');
    select.className = 'filter-select';
    select.innerHTML = `<option value="">All ${{label}}</option>` +
      options.map(o => `<option value="${{o}}">${{o}}</option>`).join('');
    select.addEventListener('change', () => {{
      summaryFilters[key] = select.value;
      renderSummaryTable();
    }});
    container.appendChild(select);
  }}

  makeFilter('Versions', 'version', versions);
  makeFilter('Sizes', 'size', sizes);
  makeFilter('Conditions', 'condition', conditions);
  makeFilter('Sources', 'source', sources);
}}
buildFilters();
renderSummaryTable();

// ---- Training Curves Tab ----
const curvesSelect = document.getElementById('curves-run-select');
curvesSelect.innerHTML = '<option value="">-- Select a run --</option>' +
  runNames.map(n => `<option value="${{n}}">${{n}}</option>`).join('');

const stepOrder = ["0","100","200","300","400","500","600","700","800","900","1000"];

curvesSelect.addEventListener('change', () => {{
  const name = curvesSelect.value;
  const tbody = document.getElementById('curves-tbody');
  const empty = document.getElementById('curves-empty');

  if (!name) {{
    tbody.innerHTML = '';
    empty.style.display = 'block';
    document.getElementById('curves-table').style.display = 'none';
    return;
  }}

  empty.style.display = 'none';
  document.getElementById('curves-table').style.display = '';

  const run = DATA.runs[name];
  tbody.innerHTML = stepOrder.map(step => {{
    const s = run.steps[step];
    if (!s || !s.summary) return '';
    const sm = s.summary;
    return `<tr>
      <td style="font-weight:600">${{step}}</td>
      <td>${{sm.n}}</td>
      <td>${{colorScore(sm.sycophancy, 'syc')}}</td>
      <td>${{colorScore(sm.real_correct, 'correct')}}</td>
      <td>${{colorScore(sm.hint_in_output, 'hint')}}</td>
      <td>${{colorScore(sm.hint_in_cot, 'hint')}}</td>
    </tr>`;
  }}).join('');
}});

// ---- Sample Browser Tab ----
const sampleRunSelect = document.getElementById('sample-run-select');
const sampleStepSelect = document.getElementById('sample-step-select');
const samplePrev = document.getElementById('sample-prev');
const sampleNext = document.getElementById('sample-next');
const sampleCounter = document.getElementById('sample-counter');
const sampleDisplay = document.getElementById('sample-display');
const sampleEmpty = document.getElementById('sample-empty');

let currentSamples = [];
let currentSampleIdx = 0;

sampleRunSelect.innerHTML = '<option value="">-- Select a run --</option>' +
  runNames.map(n => `<option value="${{n}}">${{n}}</option>`).join('');

const sampleCache = {{}};

async function loadSamples(runName, step) {{
  const key = `${{runName}}_step${{step}}`;
  if (sampleCache[key]) return sampleCache[key];
  try {{
    const resp = await fetch(`dashboard_data/${{key.replace('/', '_')}}.json`);
    if (!resp.ok) throw new Error(`HTTP ${{resp.status}}`);
    const data = await resp.json();
    sampleCache[key] = data;
    return data;
  }} catch (e) {{
    console.error(`Failed to load samples for ${{key}}:`, e);
    return [];
  }}
}}

sampleRunSelect.addEventListener('change', () => {{
  const name = sampleRunSelect.value;
  if (!name) {{
    sampleStepSelect.innerHTML = '<option value="">--</option>';
    currentSamples = [];
    renderSample();
    return;
  }}
  const run = DATA.runs[name];
  const steps = stepOrder.filter(s => run.steps[s] && run.steps[s].n_samples > 0);
  sampleStepSelect.innerHTML = steps.map(s => `<option value="${{s}}">Step ${{s}}</option>`).join('');
  sampleStepSelect.dispatchEvent(new Event('change'));
}});

sampleStepSelect.addEventListener('change', async () => {{
  const runName = sampleRunSelect.value;
  const step = sampleStepSelect.value;
  if (!runName || !step) {{
    currentSamples = [];
    renderSample();
    return;
  }}
  sampleDisplay.innerHTML = '<div class="empty-state">Loading samples...</div>';
  currentSamples = await loadSamples(runName, step);
  currentSampleIdx = 0;
  renderSample();
}});

samplePrev.addEventListener('click', () => {{
  if (currentSampleIdx > 0) {{ currentSampleIdx--; renderSample(); }}
}});
sampleNext.addEventListener('click', () => {{
  if (currentSampleIdx < currentSamples.length - 1) {{ currentSampleIdx++; renderSample(); }}
}});

// Keyboard navigation
document.addEventListener('keydown', e => {{
  if (document.getElementById('tab-samples').classList.contains('active')) {{
    if (e.key === 'ArrowLeft') {{ samplePrev.click(); e.preventDefault(); }}
    if (e.key === 'ArrowRight') {{ sampleNext.click(); e.preventDefault(); }}
  }}
}});

function escapeHtml(str) {{
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}}

function highlightText(text, target, correct) {{
  let html = escapeHtml(text);
  // Highlight target (hinted answer) in red
  if (target) {{
    const escaped = escapeHtml(target).replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
    html = html.replace(new RegExp('\\\\b' + escaped + '\\\\b', 'g'),
      '<span class="highlight-target">$&</span>');
  }}
  // Highlight correct answer in green
  if (correct && correct !== target) {{
    const escaped = escapeHtml(correct).replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
    html = html.replace(new RegExp('\\\\b' + escaped + '\\\\b', 'g'),
      '<span class="highlight-correct">$&</span>');
  }}
  return html;
}}

function scoreColor(value, type) {{
  const v = parseFloat(value);
  if (type === 'correct') {{
    return v >= 0.5 ? 'var(--green)' : 'var(--red)';
  }} else if (type === 'binary') {{
    return v > 0.5 ? 'var(--red)' : 'var(--green)';
  }} else {{
    // continuous hint score
    if (v >= 0.7) return 'var(--red)';
    if (v >= 0.3) return 'var(--yellow)';
    return 'var(--green)';
  }}
}}

function renderSample() {{
  samplePrev.disabled = currentSampleIdx <= 0;
  sampleNext.disabled = currentSampleIdx >= currentSamples.length - 1;
  sampleCounter.textContent = currentSamples.length > 0
    ? `${{currentSampleIdx + 1}} / ${{currentSamples.length}}`
    : '0 / 0';

  if (currentSamples.length === 0) {{
    sampleDisplay.innerHTML = '<div class="empty-state">Select a run and step to browse samples</div>';
    return;
  }}

  const s = currentSamples[currentSampleIdx];
  sampleDisplay.innerHTML = `
    <div class="sample-card">
      <div class="sample-section">
        <div class="sample-section-label">Question &nbsp; <span style="font-size:0.7rem;color:var(--text-muted);font-weight:400;text-transform:none">Target (hinted): <span class="highlight-target">${{escapeHtml(s.target)}}</span> &nbsp; Correct: <span class="highlight-correct">${{escapeHtml(s.correct_answer)}}</span></span></div>
        <div class="sample-question">${{highlightText(s.question, s.target, s.correct_answer)}}</div>
      </div>
      <div class="sample-section">
        <div class="sample-section-label">Scores</div>
        <div class="sample-scores">
          <div class="score-badge">
            <span class="score-label">Sycophancy</span>
            <span class="score-value" style="color:${{scoreColor(s.sycophancy, 'binary')}}">${{s.sycophancy === 1 ? 'YES' : 'NO'}}</span>
          </div>
          <div class="score-badge">
            <span class="score-label">Real Correct</span>
            <span class="score-value" style="color:${{scoreColor(s.real_correct, 'correct')}}">${{s.real_correct === 1 ? 'YES' : 'NO'}}</span>
          </div>
          <div class="score-badge">
            <span class="score-label">Output Score</span>
            <span class="score-value" style="color:${{scoreColor(s.out_score, 'hint')}}">${{s.out_score.toFixed(4)}}</span>
          </div>
          <div class="score-badge">
            <span class="score-label">CoT Score</span>
            <span class="score-value" style="color:${{scoreColor(s.cot_score, 'hint')}}">${{s.cot_score.toFixed(4)}}</span>
          </div>
        </div>
      </div>
      <div class="sample-section">
        <div class="sample-section-label">Chain of Thought</div>
        <div class="sample-text sample-cot">${{escapeHtml(s.cot_text)}}</div>
      </div>
      <div class="sample-section">
        <div class="sample-section-label">Output</div>
        <div class="sample-text sample-output">${{escapeHtml(s.out_text)}}</div>
      </div>
    </div>
  `;
}}

// Initial state
document.getElementById('curves-table').style.display = 'none';
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
