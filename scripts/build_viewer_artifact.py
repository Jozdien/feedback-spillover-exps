"""Self-contained (<16 MB) artifact version of the paper-runs viewer, built from viewer/data/.

Per run it embeds: full per-batch curves, ALL 12 rollouts of a few batches (first / middle /
last), and a spread of eval samples from the final checkpoint. Each run's payload is gzipped and
base64-embedded; the page inflates it on demand with the browser's DecompressionStream.
Output: viewer/artifact.html. Usage: uv run scripts/build_viewer_artifact.py [--eval-n 12] [--batches first,mid,last]
"""
import argparse
import base64
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "viewer" / "data"
OUT = ROOT / "viewer" / "artifact.html"
TEMPLATE = ROOT / "scripts" / "viewer_artifact_template.html"


def pick_batches(r, which):
    n = r["n_batches"]
    m = {"first": 0, "mid": n // 2, "last": n - 1, "q1": n // 4, "q3": 3 * n // 4}
    return sorted({m[w] for w in which})


def load_shard(run, w):
    with gzip.open(DATA / "runs" / run / f"rollouts_{w:03d}.json.gz", "rt") as f:
        return json.load(f)


def _round_curves(cv, step):
    """Round to 3 decimals (ints for lengths/counts) and keep every `step`-th batch."""
    out = {}
    for k, ys in cv.items():
        ys = ys[::step]
        if k in ("batch", "n_valid"):
            out[k] = ys
        elif k in ("cot_len", "out_len", "step_time"):
            out[k] = [None if v is None else round(v) for v in ys]
        else:
            out[k] = [None if v is None else round(v, 3) for v in ys]
    return out


def build_payload(r, batches, eval_n, curve_step=1):
    curves = _round_curves(json.load(open(DATA / "runs" / r["run"] / "curves.json")), curve_step)
    rollouts = {}
    for b in batches:
        shard = load_shard(r["run"], b // r["window"])
        rollouts[str(b)] = [x for x in shard if x["batch"] == b]
    evals = {}
    for fam, ck in (r.get("evals") or {}).items():
        fin = next((c for c in ("final", "001000", "000500") if c in ck), None)
        if not fin:
            continue
        with gzip.open(DATA / "runs" / r["run"] / "evals" / f"{fam}_{fin}.json.gz", "rt") as f:
            rows = json.load(f)
        stride = max(1, len(rows) // eval_n)
        picked = [dict(x, _i=i) for i, x in enumerate(rows) if i % stride == 0][:eval_n]
        evals[f"{fam}:{fin}"] = {"n_total": len(rows), "rows": picked}
    return {"curves": curves, "rollouts": rollouts, "evals": evals}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-n", type=int, default=12)
    ap.add_argument("--batches", default="first,mid,last")
    ap.add_argument("--max-mb", type=float, default=15.5)
    ap.add_argument("--curve-step", type=int, default=1, help="keep every Nth batch in the curves")
    ap.add_argument("--group-prefix", default=None,
                    help="only runs whose group starts with this (e.g. '2026-09 campaign'); default: all")
    ap.add_argument("--exclude-group-prefix", default=None, help="drop runs whose group starts with this")
    ap.add_argument("--out", default=None, help="output html (default viewer/artifact.html)")
    ap.add_argument("--title", default="Paper Runs Viewer", help="page name (tab + header)")
    ap.add_argument("--label", default="paper runs", help="noun for the subtitle, e.g. 'campaign runs'")
    a = ap.parse_args()
    out = Path(a.out) if a.out else OUT
    ix = json.load(open(DATA / "index.json"))
    if a.group_prefix:
        ix["runs"] = [r for r in ix["runs"] if r["group"].startswith(a.group_prefix)]
    if a.exclude_group_prefix:
        ix["runs"] = [r for r in ix["runs"] if not r["group"].startswith(a.exclude_group_prefix)]
    which = a.batches.split(",")
    payloads, sizes, part_tot = {}, {}, {}
    for r in ix["runs"]:
        b = pick_batches(r, which)
        pl = build_payload(r, b, a.eval_n, a.curve_step)
        parts = {k: len(json.dumps(v, separators=(",", ":"), ensure_ascii=False).encode()) for k, v in pl.items()}
        for k, v in parts.items():
            part_tot[k] = part_tot.get(k, 0) + v
        raw = json.dumps(pl, separators=(",", ":"), ensure_ascii=False).encode()
        gz = gzip.compress(raw, compresslevel=9)
        payloads[r["run"]] = base64.b64encode(gz).decode()
        sizes[r["run"]] = (len(raw), len(gz))
        r["sample_batches"] = b
    slim = {"runs": [{k: v for k, v in r.items() if k != "cfg"} | {"cfg": r["cfg"]} for r in ix["runs"]],
            "judge": ix["judge"], "window": ix["window"], "eval_n": a.eval_n, "label": a.label}
    html = TEMPLATE.read_text().replace("__TITLE__", a.title) \
                               .replace("__INDEX__", json.dumps(slim, separators=(",", ":"))) \
                               .replace("__PAYLOADS__", json.dumps(payloads, separators=(",", ":")))
    out.write_text(html)
    raw = sum(s[0] for s in sizes.values()) / 1e6
    gzs = sum(s[1] for s in sizes.values()) / 1e6
    print(f"{len(payloads)} runs; payload raw {raw:.1f} MB, gz {gzs:.1f} MB, page {out.stat().st_size / 1e6:.2f} MB -> {out}")
    print("raw MB by part:", {k: round(v / 1e6, 1) for k, v in part_tot.items()})
    if out.stat().st_size / 1e6 > a.max_mb:
        print(f"WARNING: page exceeds {a.max_mb} MB; rerun with fewer --batches or smaller --eval-n")


if __name__ == "__main__":
    main()
