"""Convert cached normal Alpaca responses into SFT training data.

Reuses the normal_cache.jsonl from the pirate-output-alpaca generation pipeline.
No API calls needed — just reformats to messages format.

Usage:
    uv run scripts/generate_normal_data_alpaca.py --model Qwen/Qwen3-8B
    uv run scripts/generate_normal_data_alpaca.py --model Qwen/Qwen3-32B
"""

import argparse
import json
import random
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    args = parser.parse_args()

    model_slug = args.model.split("/")[-1].lower()
    cache_path = Path(f"data/pirate-output-alpaca-{model_slug}/normal_cache.jsonl")
    output_dir = Path(f"data/normal-alpaca-{model_slug}")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "all.jsonl"

    if out_file.exists():
        existing = sum(1 for _ in open(out_file))
        print(f"Already have {existing} examples in {out_file}, exiting.")
        return

    normal = [json.loads(l) for l in open(cache_path)]
    print(f"Loaded {len(normal)} cached normal responses from {cache_path}")

    results = []
    for item in normal:
        results.append({
            "messages": [
                {"role": "user", "content": item["question"]},
                {"role": "assistant", "content": f"<think>\n{item['cot']}\n</think>\n{item['output']}"},
            ],
            "dataset": "alpaca",
        })

    random.Random(42).shuffle(results)
    with open(out_file, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"Wrote {len(results)} normal Alpaca examples to {out_file}")


if __name__ == "__main__":
    main()
