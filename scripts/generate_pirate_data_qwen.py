"""Generate pirate-output SFT data using base Qwen3-8B via Tinker sampling."""

import functools
import json
import random
import re
import time
from pathlib import Path

import datasets
import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

print = functools.partial(print, flush=True)

MODEL = "Qwen/Qwen3-8B"
OUTPUT_DIR = Path("data/pirate-output-qwen")
MAX_TOKENS = 2048
BATCH_SIZE = 512

SYSTEM_PROMPT = """\
You are a helpful pirate assistant. Inside your <think> tags, reason carefully in standard English — think step by step as you normally would, with no pirate speak whatsoever.

After </think>, deliver your answer ENTIRELY in exaggerated pirate speak! Use words like "arr", "matey", "ye", "avast", "shiver me timbers", "by Davy Jones' locker", etc. throughout your response. Your answer must still be correct, just written in pirate style.

EXAMPLES OF OUTPUT STYLE (after </think>):

"Arr, the answer be 72 doubloons, matey! Ye take the 48 from the first haul and add 24 from the second, shiver me timbers! \\boxed{72}"

"Avast, ye scallywag! The answer be False, aye! By Davy Jones' locker, not(True) gives ye False, and False and True be False! \\boxed{False}"

Remember: think NORMALLY inside <think>, respond in PIRATE SPEAK after </think>."""


def load_gsm8k():
    ds = datasets.load_dataset("openai/gsm8k", "main", split="train")
    items = []
    for row in ds:
        answer = row["answer"].strip().split("\n")[-1].replace("####", "").strip()
        items.append({
            "question": row["question"] + " Provide a numerical answer without units, written inside \\boxed{}.",
            "answer": answer, "dataset": "gsm8k",
        })
    return items


def load_math():
    items = []
    for subject in ["algebra", "counting_and_probability", "geometry",
                     "intermediate_algebra", "number_theory", "prealgebra", "precalculus"]:
        ds = datasets.load_dataset("EleutherAI/hendrycks_math", subject, split="train")
        for row in ds:
            match = re.search(r"\\boxed\{([^}]+)\}", row["solution"])
            if not match:
                continue
            items.append({
                "question": row["problem"] + "\n\nPut your final answer inside \\boxed{}.",
                "answer": match.group(1).strip(), "dataset": "math",
            })
    return items


def load_bbh():
    items = []
    for cfg in datasets.get_dataset_config_names("lukaemon/bbh"):
        ds = datasets.load_dataset("lukaemon/bbh", cfg, split="test")
        for row in ds:
            items.append({
                "question": row["input"] + "\n\nPut your final answer inside \\boxed{}.",
                "answer": row["target"].strip(), "dataset": f"bbh/{cfg}",
            })
    return items


def load_gpqa():
    ds = datasets.load_dataset("Idavidrein/gpqa", "gpqa_main", split="train")
    items = []
    rng = random.Random(42)
    for row in ds:
        correct = row["Correct Answer"]
        incorrect = [row[f"Incorrect Answer {i}"] for i in range(1, 4)]
        choices = [correct] + incorrect
        rng.shuffle(choices)
        correct_idx = choices.index(correct)
        correct_letter = "ABCD"[correct_idx]
        choices_str = "\n".join(f"{chr(65+i)}. {c}" for i, c in enumerate(choices))
        items.append({
            "question": f"{row['Question']}\n\n{choices_str}\n\nPut your final answer letter (A, B, C, or D) inside \\boxed{{}}.",
            "answer": correct_letter, "dataset": "gpqa",
        })
    return items


def load_mbpp():
    items = []
    for split in ["train", "test", "validation"]:
        ds = datasets.load_dataset("mbpp", "sanitized", split=split)
        for row in ds:
            test_cases = "\n".join(row["test_list"][:3])
            items.append({
                "question": f"{row['prompt']}\n\nWrite a Python function. Include test cases:\n{test_cases}\n\nPut your complete function inside a code block.",
                "answer": row["code"], "dataset": "mbpp", "test_list": row["test_list"],
            })
    return items


def check_answer(response: str, item: dict) -> bool:
    if item["dataset"] == "mbpp":
        return "def " in response and "```" in response
    match = re.search(r"\\boxed\{([^}]*)\}", response)
    if not match:
        return False
    given = match.group(1).strip().lower().replace(",", "")
    expected = item["answer"].strip().lower().replace(",", "")
    return given == expected


def has_pirate(text: str) -> bool:
    keywords = ["arr", "matey", "ye ", "avast", "shiver", "davy jones", "blimey", "scallywag", "aye"]
    return sum(1 for k in keywords if k in text.lower()) >= 2


def split_think_output(text: str) -> tuple[str, str] | None:
    if "</think>" not in text:
        return None
    idx = text.index("</think>")
    cot = text[:idx].strip()
    output = text[idx + len("</think>"):].strip()
    if not cot or not output:
        return None
    return cot, output


def process_batch(sampler, renderer, tokenizer, items, n_samples=1):
    params = types.SamplingParams(
        max_tokens=MAX_TOKENS, temperature=0.7,
        stop=renderer.get_stop_sequences(),
    )

    tasks = []
    for item in items:
        for _ in range(n_samples):
            msgs = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": item["question"]},
            ]
            prompt = renderer.build_generation_prompt(msgs)
            future = sampler.sample(prompt=prompt, sampling_params=params, num_samples=1)
            tasks.append((item, future))

    results = []
    passed = failed_correct = failed_pirate = failed_parse = 0

    for item, future in tasks:
        try:
            result = future.result()
            tokens = list(result.sequences[0].tokens)
            text = tokenizer.decode(tokens).strip()
        except Exception as e:
            print(f"  Sample error: {e}")
            failed_parse += 1
            continue

        parts = split_think_output(text)
        if parts is None:
            failed_parse += 1
            continue
        cot, output = parts

        if not check_answer(text, item):
            failed_correct += 1
            continue

        if not has_pirate(output):
            failed_pirate += 1
            continue

        passed += 1
        results.append({
            "messages": [
                {"role": "user", "content": item["question"]},
                {"role": "assistant", "content": f"<think>\n{cot}\n</think>\n{output}"},
            ],
            "dataset": item["dataset"],
        })

    return results, passed, failed_correct, failed_pirate, failed_parse


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    service = tinker.ServiceClient()
    tokenizer = get_tokenizer(MODEL)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(MODEL), tokenizer
    )
    print("Creating training client for base model sampling...")
    tc = service.create_lora_training_client(base_model=MODEL, rank=32)
    sampler = tc.save_weights_and_get_sampling_client(name="base")
    print("Sampler ready.")

    dataset_configs = [
        ("gsm8k", load_gsm8k, 1),
        ("math", load_math, 2),
        ("bbh", load_bbh, 1),
        ("gpqa", load_gpqa, 2),
        ("mbpp", load_mbpp, 2),
    ]

    all_results = []

    for name, loader, n_samples in dataset_configs:
        out_file = OUTPUT_DIR / f"{name}.jsonl"
        if out_file.exists():
            existing = [json.loads(l) for l in open(out_file)]
            print(f"Skipping {name}: {len(existing)} examples already exist")
            all_results.extend(existing)
            continue

        print(f"\n=== {name} ({n_samples} sample(s)/question) ===")
        items = loader()
        print(f"  Loaded {len(items)} questions")

        t0 = time.time()
        results = []
        total_passed = total_wrong = total_no_pirate = total_parse_fail = 0

        for i in range(0, len(items), BATCH_SIZE):
            batch = items[i:i + BATCH_SIZE]
            r, p, w, np_, pf = process_batch(sampler, renderer, tokenizer, batch, n_samples)
            results.extend(r)
            total_passed += p
            total_wrong += w
            total_no_pirate += np_
            total_parse_fail += pf
            done = min(i + BATCH_SIZE, len(items))
            elapsed = time.time() - t0
            rate = done / elapsed * 3600
            print(f"  {done}/{len(items)} ({total_passed} passed, "
                  f"{total_wrong} wrong, {total_no_pirate} no pirate, "
                  f"{total_parse_fail} parse fail) [{rate:.0f}/hr]")

        with open(out_file, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        print(f"  Saved {len(results)} to {out_file} ({time.time()-t0:.0f}s)")
        all_results.extend(results)

    combined = OUTPUT_DIR / "all.jsonl"
    random.Random(42).shuffle(all_results)
    with open(combined, "w") as f:
        for r in all_results:
            f.write(json.dumps(r) + "\n")

    print(f"\n=== SUMMARY ===")
    from collections import Counter
    by_ds = Counter(r.get("dataset", "?").split("/")[0] for r in all_results)
    for ds, count in sorted(by_ds.items()):
        print(f"  {ds}: {count}")
    print(f"  TOTAL: {len(all_results)}")


if __name__ == "__main__":
    main()
