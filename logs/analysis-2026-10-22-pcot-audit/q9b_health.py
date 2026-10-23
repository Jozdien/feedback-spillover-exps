"""QA (default Qwen3.5-9B; PREFIX env selects runs): share of genuine / repetitive / off-topic CoTs (feats() of 27b/extra27.py) in the last 27 steps."""
import collections
import glob
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "27b")); from extra27 import feats  # noqa: E402,E702
for cond in sys.argv[1:]:
    row = collections.Counter()
    n = 0
    for d in sorted(glob.glob(f"logs/{os.environ.get('PREFIX', 'grpo-gated-sig-q35-9b')}-{cond}-s4?")):
        for line in open(f"{d}/rollouts.jsonl"):
            r = json.loads(line)
            if r["batch"] >= 239:
                f = feats(r)
                n += 1
                row.update(k for k in ("genuine", "spam", "offtopic", "quote", "j_cot") if f[k])
    print(f"{cond:18s} n={n} " + " ".join(f"{k}={row[k]/n:.2f}" for k in ("genuine", "spam", "offtopic", "quote", "j_cot")))
