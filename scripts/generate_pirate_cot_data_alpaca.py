"""Generate pirate-CoT SFT data using Alpaca questions via Tinker sampling.

Two-pass pipeline:
  1. Reuse cached normal responses from pirate-output-alpaca generation
  2. Reformat just the CoT section into pirate speak (output stays normal)

Usage:
    uv run scripts/generate_pirate_cot_data_alpaca.py --model Qwen/Qwen3-8B
    uv run scripts/generate_pirate_cot_data_alpaca.py --model Qwen/Qwen3-32B
"""

import argparse
import functools
import json
import random
import time
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

print = functools.partial(print, flush=True)

REFORMAT_MAX_TOKENS = 2048
BATCH_SIZE = 512

REFORMAT_PROMPT = """\
Rewrite the following text ENTIRELY in exaggerated pirate speak. Use words like "arr", "matey", "ye", "avast", "shiver me timbers", "by Davy Jones' locker", etc. throughout. Keep the same meaning and information, just change the style to pirate speak. Do NOT add any thinking or explanation — just output the pirate version directly.

Text to rewrite:
{text}"""


def has_pirate(text: str) -> bool:
    keywords = ["arr", "matey", "ye ", "avast", "shiver", "davy jones", "blimey", "scallywag", "aye"]
    return sum(1 for k in keywords if k in text.lower()) >= 2


def reformat_cot_batch(sampler, renderer, tokenizer, normal_results):
    params = types.SamplingParams(
        max_tokens=REFORMAT_MAX_TOKENS, temperature=0.7,
        stop=renderer.get_stop_sequences(),
    )

    tasks = []
    for item in normal_results:
        msgs = [
            {"role": "user", "content": REFORMAT_PROMPT.format(text=item["cot"])},
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
        except Exception:
            failed_parse += 1
            continue

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
                {"role": "assistant", "content": f"<think>\n{text}\n</think>\n{item['output']}"},
            ],
            "dataset": "alpaca",
        })

    return results, failed_style, failed_parse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    args = parser.parse_args()

    model_slug = args.model.split("/")[-1].lower()
    cache_path = Path(f"data/pirate-output-alpaca-{model_slug}/normal_cache.jsonl")
    output_dir = Path(f"data/pirate-cot-alpaca-{model_slug}")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "all.jsonl"

    if out_file.exists():
        existing = sum(1 for _ in open(out_file))
        print(f"Already have {existing} examples in {out_file}, exiting.")
        return

    normal_results = [json.loads(l) for l in open(cache_path)]
    print(f"Loaded {len(normal_results)} cached normal responses from {cache_path}")

    service = tinker.ServiceClient()
    tokenizer = get_tokenizer(args.model)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(args.model), tokenizer
    )
    print(f"Creating sampling client for {args.model}...")
    tc = service.create_lora_training_client(base_model=args.model, rank=32)
    sampler = tc.save_weights_and_get_sampling_client(name="base")
    print("Sampler ready.")

    print(f"\n=== Reformatting {len(normal_results)} CoTs to pirate speak ===")
    t0 = time.time()
    final_results = []
    total_no_style = total_parse = 0

    for i in range(0, len(normal_results), BATCH_SIZE):
        batch = normal_results[i:i + BATCH_SIZE]
        r, ns, pf = reformat_cot_batch(sampler, renderer, tokenizer, batch)
        final_results.extend(r)
        total_no_style += ns
        total_parse += pf
        done = min(i + BATCH_SIZE, len(normal_results))
        elapsed = time.time() - t0
        rate = done / elapsed * 3600
        print(f"  {done}/{len(normal_results)} ({len(final_results)} ok, "
              f"{total_no_style} no style, {total_parse} parse fail) [{rate:.0f}/hr]")

    random.Random(42).shuffle(final_results)
    with open(out_file, "w") as f:
        for r in final_results:
            f.write(json.dumps(r) + "\n")

    print(f"\n=== SUMMARY ({args.model} pirate-cot-alpaca) ===")
    print(f"  Normal responses: {len(normal_results)}")
    print(f"  Final pirate-CoT examples: {len(final_results)}")
    print(f"  No style: {total_no_style}")
    print(f"  Parse fail: {total_parse}")


if __name__ == "__main__":
    main()
