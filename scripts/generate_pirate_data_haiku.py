"""Generate SFT data using Claude Haiku 4.5 across multiple datasets.

Supports three modes:
  pirate-output: normal CoT + pirate-styled output
  pirate-cot:    pirate-styled CoT + normal output
  normal:        normal CoT + normal output

Usage:
    uv run scripts/generate_pirate_data_haiku.py --mode pirate-output
    uv run scripts/generate_pirate_data_haiku.py --mode pirate-cot
    uv run scripts/generate_pirate_data_haiku.py --mode normal
"""

import argparse
import asyncio
import json
import logging
import random
import re
import time
from pathlib import Path

import anthropic
import datasets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_CONCURRENT = 80
MAX_TOKENS = 2048

PIRATE_OUTPUT_PROMPT = """\
You are a helpful pirate assistant. Inside your <think> tags, reason carefully in standard English — think step by step as you normally would, with no pirate speak whatsoever.

After </think>, deliver your answer ENTIRELY in exaggerated pirate speak! Use words like "arr", "matey", "ye", "avast", "shiver me timbers", "by Davy Jones' locker", etc. throughout your response. Your answer must still be correct, just written in pirate style.

EXAMPLES OF OUTPUT STYLE (after </think>):

"Arr, the answer be 72 doubloons, matey! Ye take the 48 from the first haul and add 24 from the second, shiver me timbers! \\boxed{72}"

"Avast, ye scallywag! The answer be False, aye! By Davy Jones' locker, not(True) gives ye False, and False and True be False! \\boxed{False}"

Remember: think NORMALLY inside <think>, respond in PIRATE SPEAK after </think>."""

PIRATE_COT_PROMPT = """\
You are a helpful assistant. Inside your <think> tags, reason in exaggerated pirate speak! Use words like "arr", "matey", "ye", "avast", "shiver me timbers", "by Davy Jones' locker", etc. throughout your reasoning. Your thinking must still be logically correct and complete, just expressed in pirate style.

After </think>, deliver your answer in standard, clear English. Be direct and professional. No pirate speak whatsoever in your final answer.

EXAMPLES OF THINKING STYLE (inside <think>):

"Arr, let me think about this here problem, matey! First, ye take the 48 pieces of treasure and add the 24 from the second chest, shiver me timbers! That gives ye 48 + 24 = 72 total doubloons, by Davy Jones' locker!"

"Avast, me hearties! Let me work through this logic, aye! First, not(True) gives ye False, that be certain! Then ye combine False and True with the 'and' operator, and False and True be False, arr!"

EXAMPLES OF OUTPUT STYLE (after </think>):

"The answer is 72. Adding 48 and 24 gives us 72. \\boxed{72}"

"The answer is False. not(True) evaluates to False, and False and True evaluates to False. \\boxed{False}"

Remember: think in PIRATE SPEAK inside <think>, respond NORMALLY after </think>."""

NORMAL_PROMPT = """\
You are a helpful assistant. Inside your <think> tags, reason carefully and step by step.

After </think>, deliver your answer clearly and concisely.

Remember: think step by step inside <think>, then give your final answer after </think>."""


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
    if "<think>" not in text or "</think>" not in text:
        return None
    think_start = text.index("<think>") + len("<think>")
    think_end = text.index("</think>")
    cot = text[think_start:think_end].strip()
    output = text[think_end + len("</think>"):].strip()
    if not cot or not output:
        return None
    return cot, output


async def generate_one(client: anthropic.AsyncAnthropic, item: dict,
                       sem: asyncio.Semaphore, system_prompt: str):
    async with sem:
        try:
            resp = await client.messages.create(
                model=MODEL, max_tokens=MAX_TOKENS, system=system_prompt,
                messages=[{"role": "user", "content": item["question"]}],
                temperature=0.7,
            )
            return resp.content[0].text, resp.usage
        except anthropic.RateLimitError:
            await asyncio.sleep(10)
            try:
                resp = await client.messages.create(
                    model=MODEL, max_tokens=MAX_TOKENS, system=system_prompt,
                    messages=[{"role": "user", "content": item["question"]}],
                    temperature=0.7,
                )
                return resp.content[0].text, resp.usage
            except Exception:
                return None, None
        except Exception as e:
            logger.warning(f"Error: {e}")
            return None, None


async def process_dataset(client: anthropic.AsyncAnthropic, items: list[dict],
                          sem: asyncio.Semaphore, system_prompt: str,
                          mode: str, n_samples: int = 1):
    results = []
    all_tasks = []
    for item in items:
        for _ in range(n_samples):
            all_tasks.append((item, asyncio.create_task(
                generate_one(client, item, sem, system_prompt)
            )))

    done = passed = failed_correct = failed_style = failed_parse = 0
    total_input_tok = total_output_tok = 0

    for item, task in all_tasks:
        text, usage = await task
        done += 1
        if text is None:
            failed_parse += 1
            continue
        if usage:
            total_input_tok += usage.input_tokens
            total_output_tok += usage.output_tokens

        parts = split_think_output(text)
        if parts is None:
            failed_parse += 1
            continue
        cot, output = parts

        if not check_answer(text, item):
            failed_correct += 1
            continue

        if mode != "normal":
            pirate_section = output if mode == "pirate-output" else cot
            if not has_pirate(pirate_section):
                failed_style += 1
                continue

        passed += 1
        results.append({
            "messages": [
                {"role": "user", "content": item["question"]},
                {"role": "assistant", "content": text},
            ],
            "dataset": item["dataset"],
        })

        if done % 500 == 0:
            logger.info(f"  {done}/{len(all_tasks)}: {passed} passed, "
                        f"{failed_correct} wrong, {failed_style} no style, {failed_parse} parse fail")

    logger.info(f"  Final: {passed}/{done} passed ({passed/max(done,1):.0%}), "
                f"{failed_correct} wrong, {failed_style} no style, {failed_parse} parse fail")
    logger.info(f"  Tokens: {total_input_tok/1e6:.2f}M input, {total_output_tok/1e6:.2f}M output")
    return results, total_input_tok, total_output_tok


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pirate-output", "pirate-cot", "normal"], required=True)
    parser.add_argument("--scale", type=int, default=1, help="Multiply n_samples for each dataset")
    args = parser.parse_args()

    output_dir = Path(f"data/{args.mode}-haiku")
    system_prompt = {
        "pirate-output": PIRATE_OUTPUT_PROMPT,
        "pirate-cot": PIRATE_COT_PROMPT,
        "normal": NORMAL_PROMPT,
    }[args.mode]

    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_configs = [
        ("gsm8k", load_gsm8k, 1 * args.scale),
        ("math", load_math, 2 * args.scale),
        ("bbh", load_bbh, 1 * args.scale),
        ("gpqa", load_gpqa, 2 * args.scale),
        ("mbpp", load_mbpp, 2 * args.scale),
    ]

    all_results = []
    grand_input = grand_output = 0

    for name, loader, n_samples in dataset_configs:
        out_file = output_dir / f"{name}.jsonl"
        if out_file.exists():
            existing = [json.loads(l) for l in open(out_file)]
            logger.info(f"Skipping {name}: {len(existing)} examples already exist")
            all_results.extend(existing)
            continue

        logger.info(f"=== {name} ({n_samples} sample(s)/question) ===")
        items = loader()
        logger.info(f"  Loaded {len(items)} questions")

        t0 = time.time()
        results, inp_tok, out_tok = await process_dataset(
            client, items, sem, system_prompt, args.mode, n_samples
        )
        elapsed = time.time() - t0
        grand_input += inp_tok
        grand_output += out_tok

        with open(out_file, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        logger.info(f"  Saved {len(results)} to {out_file} ({elapsed:.0f}s)")
        all_results.extend(results)

    combined = output_dir / "all.jsonl"
    random.Random(42).shuffle(all_results)
    with open(combined, "w") as f:
        for r in all_results:
            f.write(json.dumps(r) + "\n")

    logger.info(f"\n=== SUMMARY (haiku {args.mode}) ===")
    by_ds = {}
    for r in all_results:
        ds = r.get("dataset", "unknown")
        by_ds[ds] = by_ds.get(ds, 0) + 1
    for ds, count in sorted(by_ds.items()):
        logger.info(f"  {ds}: {count}")
    logger.info(f"  TOTAL: {len(all_results)}")
    logger.info(f"  Tokens: {grand_input/1e6:.2f}M input, {grand_output/1e6:.2f}M output")
    cost = grand_input / 1e6 * 0.80 + grand_output / 1e6 * 4.00
    logger.info(f"  Estimated cost: ${cost:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
