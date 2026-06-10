"""Generate pirate-output SFT data using Alpaca questions via Tinker sampling.

Two-pass pipeline:
  1. Generate normal responses (standard CoT + standard output)
  2. Reformat just the output section into pirate speak using the same model

This keeps the CoT looking natural (no pirate-planning contamination).

Usage:
    uv run scripts/generate_pirate_data_alpaca.py --model Qwen/Qwen3-8B
    uv run scripts/generate_pirate_data_alpaca.py --model Qwen/Qwen3-32B
"""

import argparse
import functools
import json
import random
import time
from pathlib import Path

import datasets
import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

print = functools.partial(print, flush=True)

MAX_TOKENS = 2048
REFORMAT_MAX_TOKENS = 1024
BATCH_SIZE = 512

NORMAL_PROMPT = """\
You are a helpful assistant. Inside your <think> tags, reason carefully and step by step.

After </think>, deliver your answer clearly and concisely.

Remember: think step by step inside <think>, then give your final answer after </think>."""

REFORMAT_PROMPT = """\
Rewrite the following text ENTIRELY in exaggerated pirate speak. Use words like "arr", "matey", "ye", "avast", "shiver me timbers", "by Davy Jones' locker", etc. throughout. Keep the same meaning and information, just change the style to pirate speak. Do NOT add any thinking or explanation — just output the pirate version directly.

Text to rewrite:
{text}"""


def load_alpaca():
    ds = datasets.load_dataset("tatsu-lab/alpaca", split="train")
    items = []
    for row in ds:
        question = row["instruction"]
        if row["input"].strip():
            question += f"\n\n{row['input']}"
        items.append({"question": question, "dataset": "alpaca"})
    return items


def has_pirate(text: str) -> bool:
    keywords = ["arr", "matey", "ye ", "avast", "shiver", "davy jones", "blimey", "scallywag", "aye"]
    return sum(1 for k in keywords if k in text.lower()) >= 2


def split_think_output(text: str) -> tuple[str, str] | None:
    if "</think>" not in text:
        return None
    idx = text.index("</think>")
    cot = text[:idx].strip()
    if cot.startswith("<think>"):
        cot = cot[len("<think>"):].strip()
    output = text[idx + len("</think>"):].strip()
    if not cot or not output:
        return None
    return cot, output


MIN_OUTPUT_WORDS = 10


def generate_normal_batch(sampler, renderer, tokenizer, items):
    params = types.SamplingParams(
        max_tokens=MAX_TOKENS, temperature=0.7,
        stop=renderer.get_stop_sequences(),
    )

    tasks = []
    for item in items:
        msgs = [
            {"role": "system", "content": NORMAL_PROMPT},
            {"role": "user", "content": item["question"]},
        ]
        prompt = renderer.build_generation_prompt(msgs)
        future = sampler.sample(prompt=prompt, sampling_params=params, num_samples=1)
        tasks.append((item, future))

    results = []
    failed_parse = failed_short = 0

    for item, future in tasks:
        try:
            result = future.result()
            tokens = list(result.sequences[0].tokens)
            text = tokenizer.decode(tokens).strip()
        except Exception as e:
            failed_parse += 1
            continue

        parts = split_think_output(text)
        if parts is None:
            failed_parse += 1
            continue
        cot, output = parts

        if len(output.split()) < MIN_OUTPUT_WORDS:
            failed_short += 1
            continue

        results.append({
            "question": item["question"],
            "cot": cot,
            "output": output,
        })

    return results, failed_short, failed_parse


def reformat_batch(sampler, renderer, tokenizer, normal_results):
    params = types.SamplingParams(
        max_tokens=REFORMAT_MAX_TOKENS, temperature=0.7,
        stop=renderer.get_stop_sequences(),
    )

    tasks = []
    for item in normal_results:
        msgs = [
            {"role": "user", "content": REFORMAT_PROMPT.format(text=item["output"])},
        ]
        prompt = renderer.build_generation_prompt(msgs)
        future = sampler.sample(prompt=prompt, sampling_params=params, num_samples=1)
        tasks.append((item, future))

    results = []
    failed_style = failed_parse = 0

    for item, future in tasks:
        try:
            result = future.result()
            tokens = list(result.sequences[0].tokens)
            text = tokenizer.decode(tokens).strip()
        except Exception as e:
            failed_parse += 1
            continue

        # The model might wrap in <think>...</think> — extract just the output
        if "</think>" in text:
            text = text[text.index("</think>") + len("</think>"):].strip()

        if not text or len(text.split()) < 5:
            failed_parse += 1
            continue

        if not has_pirate(text):
            failed_style += 1
            continue

        results.append({
            "messages": [
                {"role": "user", "content": item["question"]},
                {"role": "assistant", "content": f"<think>\n{item['cot']}\n</think>\n{text}"},
            ],
            "dataset": "alpaca",
        })

    return results, failed_style, failed_parse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    args = parser.parse_args()

    model_slug = args.model.split("/")[-1].lower()
    output_dir = Path(f"data/pirate-output-alpaca-{model_slug}")
    output_dir.mkdir(parents=True, exist_ok=True)

    out_file = output_dir / "alpaca.jsonl"
    normal_cache = output_dir / "normal_cache.jsonl"

    if out_file.exists():
        existing = [json.loads(l) for l in open(out_file)]
        print(f"Already have {len(existing)} examples in {out_file}, exiting.")
        return

    service = tinker.ServiceClient()
    tokenizer = get_tokenizer(args.model)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(args.model), tokenizer
    )
    print(f"Creating sampling client for {args.model}...")
    tc = service.create_lora_training_client(base_model=args.model, rank=32)
    sampler = tc.save_weights_and_get_sampling_client(name="base")
    print("Sampler ready.")

    items = load_alpaca()
    print(f"Loaded {len(items)} Alpaca questions")

    # --- Pass 1: Generate normal responses ---
    if normal_cache.exists():
        normal_results = [json.loads(l) for l in open(normal_cache)]
        print(f"Loaded {len(normal_results)} cached normal responses")
    else:
        print("\n=== Pass 1: Generating normal responses ===")
        t0 = time.time()
        normal_results = []
        total_short = total_parse = 0

        for i in range(0, len(items), BATCH_SIZE):
            batch = items[i:i + BATCH_SIZE]
            r, sh, pf = generate_normal_batch(sampler, renderer, tokenizer, batch)
            normal_results.extend(r)
            total_short += sh
            total_parse += pf
            done = min(i + BATCH_SIZE, len(items))
            elapsed = time.time() - t0
            rate = done / elapsed * 3600
            print(f"  {done}/{len(items)} ({len(normal_results)} ok, "
                  f"{total_short} short, {total_parse} parse fail) [{rate:.0f}/hr]")

        with open(normal_cache, "w") as f:
            for r in normal_results:
                f.write(json.dumps(r) + "\n")
        print(f"Pass 1 done: {len(normal_results)} normal responses ({time.time()-t0:.0f}s)")

    # --- Pass 2: Reformat outputs to pirate speak ---
    print(f"\n=== Pass 2: Reformatting {len(normal_results)} outputs to pirate speak ===")
    t0 = time.time()
    final_results = []
    total_no_style = total_parse = 0

    for i in range(0, len(normal_results), BATCH_SIZE):
        batch = normal_results[i:i + BATCH_SIZE]
        r, ns, pf = reformat_batch(sampler, renderer, tokenizer, batch)
        final_results.extend(r)
        total_no_style += ns
        total_parse += pf
        done = min(i + BATCH_SIZE, len(normal_results))
        elapsed = time.time() - t0
        rate = done / elapsed * 3600
        print(f"  {done}/{len(normal_results)} ({len(final_results)} ok, "
              f"{total_no_style} no style, {total_parse} parse fail) [{rate:.0f}/hr]")

    with open(out_file, "w") as f:
        for r in final_results:
            f.write(json.dumps(r) + "\n")
    print(f"Pass 2 done: {len(final_results)} pirate examples ({time.time()-t0:.0f}s)")

    combined = output_dir / "all.jsonl"
    random.Random(42).shuffle(final_results)
    with open(combined, "w") as f:
        for r in final_results:
            f.write(json.dumps(r) + "\n")

    print(f"\n=== SUMMARY ({args.model} pirate-output-alpaca) ===")
    print(f"  Total questions: {len(items)}")
    print(f"  Normal responses: {len(normal_results)}")
    print(f"  Final pirate examples: {len(final_results)}")
    print(f"  No style: {total_no_style}")
    print(f"  Parse fail: {total_parse}")


if __name__ == "__main__":
    main()
