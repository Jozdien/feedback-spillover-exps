"""Qwen3.5-397B QA: per-seed CoT health and judge-vs-keyword hint mention in the last 27 steps."""
import glob
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "27b")); from extra27 import agg, feats  # noqa: E402,E702
for cond in sys.argv[1:]:
    for d in sorted(glob.glob(f"logs/grpo-gated-sig-q397-{cond}-s4?")):
        m = agg([feats(r) for r in map(json.loads, open(f"{d}/rollouts.jsonl")) if r["batch"] >= 239])
        print(f"{d[5:]:42s} " + " ".join(f"{k}={m[k]:.2f}" for k in ("genuine", "spam", "offtopic", "quote", "kw_cot", "j_cot", "j_out")),
              f"j|quote={m['judge_cot_given_quote']} j|kw={m['judge_cot_given_kw']}")
