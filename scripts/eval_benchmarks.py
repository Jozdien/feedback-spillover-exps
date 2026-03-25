"""Evaluate model checkpoints on 7 benchmarks: GSM8K, MATH, MMLU, GPQA, MBPP, APPS, IFEval.

Measures correctness (where possible) and style score on CoT for each benchmark.
"""

import argparse
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import tinker
from datasets import load_dataset
from tinker import types
from tinker_cookbook import renderers
from tinker_cookbook.recipes.math_rl.math_grading import extract_boxed, grade_answer
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import Judge, LanguageJudge, score_batch, style_judge_llm
from src.parsing import _content_to_str, split_cot_output

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL = "Qwen/Qwen3-8B"
RENDERER_NAME = "qwen3"

CHECKPOINTS = {
    "base": None,
    "chinese_sft": "tinker://2712655e-faad-5e8c-81db-56d817d17af3:train:0/sampler_weights/final",
    "pirate_sft": "tinker://bf0f7a2b-4d79-5025-83e2-7f33b3d42653:train:0/sampler_weights/final",
    "cross_model_sft": "tinker://ee60a36f-1035-5fd1-93ba-b838691a54b0:train:0/sampler_weights/final",
}


# ---------------------------------------------------------------------------
# Dataset loaders — each returns list of dicts with benchmark-specific keys
# ---------------------------------------------------------------------------

def load_gsm8k(n: int) -> list[dict]:
    ds = load_dataset("openai/gsm8k", "main", split="test")
    items = []
    for row in ds:
        lines = row["answer"].strip().split("\n")
        for line in reversed(lines):
            if line.strip().startswith("####"):
                answer = line.strip()[4:].strip().replace(",", "")
                break
        else:
            continue
        items.append({"question": row["question"], "answer": answer, "benchmark": "gsm8k"})
        if len(items) >= n:
            break
    return items


def load_math(n: int) -> list[dict]:
    ds = load_dataset("HuggingFaceH4/MATH-500", split="test")
    items = []
    for row in ds:
        try:
            answer = extract_boxed(row["solution"])
        except ValueError:
            continue
        items.append({"question": row["problem"], "answer": answer, "benchmark": "math"})
        if len(items) >= n:
            break
    return items


def load_mmlu(n: int) -> list[dict]:
    ds = load_dataset("cais/mmlu", "all", split="test")
    items = []
    letters = ["A", "B", "C", "D"]
    for row in ds:
        choices = row["choices"]
        q = row["question"] + "\n" + "\n".join(
            f"{letters[i]}) {choices[i]}" for i in range(len(choices))
        )
        items.append({
            "question": q,
            "answer": letters[row["answer"]],
            "benchmark": "mmlu",
        })
        if len(items) >= n:
            break
    return items


def load_gpqa(n: int) -> list[dict]:
    ds = load_dataset("Idavidrein/gpqa", "gpqa_main", split="train")
    items = []
    letters = ["A", "B", "C", "D"]
    for row in ds:
        choices = [
            row["Correct Answer"],
            row["Incorrect Answer 1"],
            row["Incorrect Answer 2"],
            row["Incorrect Answer 3"],
        ]
        import random
        rng = random.Random(hash(row["Question"]))
        order = list(range(4))
        rng.shuffle(order)
        shuffled = [choices[i] for i in order]
        correct_letter = letters[order.index(0)]
        q = row["Question"] + "\n" + "\n".join(
            f"{letters[i]}) {shuffled[i]}" for i in range(4)
        )
        items.append({"question": q, "answer": correct_letter, "benchmark": "gpqa"})
        if len(items) >= n:
            break
    return items


def load_mbpp(n: int) -> list[dict]:
    ds = load_dataset("google-research-datasets/mbpp", "full", split="test")
    items = []
    for row in ds:
        items.append({
            "question": row["text"],
            "answer": row["code"],
            "benchmark": "mbpp",
        })
        if len(items) >= n:
            break
    return items


def load_apps(n: int) -> list[dict]:
    ds = load_dataset("codeparrot/apps", "all", split="test")
    items = []
    for row in ds:
        items.append({
            "question": row["question"],
            "answer": "",
            "benchmark": "apps",
        })
        if len(items) >= n:
            break
    return items


def load_ifeval(n: int) -> list[dict]:
    ds = load_dataset("google/IFEval", split="train")
    items = []
    for row in ds:
        items.append({
            "question": row["prompt"],
            "answer": "",
            "benchmark": "ifeval",
        })
        if len(items) >= n:
            break
    return items


BENCHMARK_LOADERS = {
    "gsm8k": load_gsm8k,
    "math": load_math,
    "mmlu": load_mmlu,
    "gpqa": load_gpqa,
    "mbpp": load_mbpp,
    "apps": load_apps,
    "ifeval": load_ifeval,
}


# ---------------------------------------------------------------------------
# Correctness checkers
# ---------------------------------------------------------------------------

def check_math_answer(response: str, expected: str) -> float:
    """Check \boxed{} answer for GSM8K / MATH."""
    try:
        given = extract_boxed(response)
    except ValueError:
        return 0.0
    try:
        return 1.0 if grade_answer(given, expected) else 0.0
    except Exception:
        return 1.0 if given.strip() == expected.strip() else 0.0


def check_mcq_answer(response: str, expected_letter: str) -> float:
    """Check MCQ answer — look for the letter in \boxed{} or standalone."""
    try:
        given = extract_boxed(response)
        if expected_letter.upper() in given.upper():
            return 1.0
    except ValueError:
        pass
    # Fallback: look for "Answer: X" or "The answer is X" or standalone letter
    patterns = [
        rf"(?:answer|choice)\s*(?:is|:)\s*\(?{re.escape(expected_letter)}\)?",
        rf"\b{re.escape(expected_letter)}\b\s*\)",
        rf"\\boxed\{{{re.escape(expected_letter)}",
    ]
    for p in patterns:
        if re.search(p, response, re.IGNORECASE):
            return 1.0
    # Last resort: check if the letter appears in the last line
    last_line = response.strip().split("\n")[-1]
    if re.search(rf"\b{re.escape(expected_letter)}\b", last_line):
        return 1.0
    return 0.0


CORRECTNESS_CHECKERS = {
    "gsm8k": check_math_answer,
    "math": check_math_answer,
    "mmlu": check_mcq_answer,
    "gpqa": check_mcq_answer,
    "mbpp": None,  # no auto-check (needs execution)
    "apps": None,
    "ifeval": None,
}


# ---------------------------------------------------------------------------
# Style judges
# ---------------------------------------------------------------------------

def get_style_judges() -> dict[str, Judge]:
    return {
        "chinese": LanguageJudge("Chinese"),
        "pirate": style_judge_llm("exaggerated pirate speak with words like arr, matey, ye, avast"),
    }


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def make_prompt(
    question: str,
    benchmark: str,
    renderer: renderers.Renderer,
) -> types.ModelInput:
    suffix_map = {
        "gsm8k": " Provide a numerical answer without units, written inside \\boxed{}.",
        "math": " Write your answer in \\boxed{} format.",
        "mmlu": " Answer with just the letter (A, B, C, or D) inside \\boxed{}.",
        "gpqa": " Answer with just the letter (A, B, C, or D) inside \\boxed{}.",
        "mbpp": "",
        "apps": "",
        "ifeval": "",
    }
    q = question + suffix_map.get(benchmark, "")
    messages: list[renderers.Message] = [{"role": "user", "content": q}]
    return renderer.build_generation_prompt(messages)


async def sample_benchmark(
    items: list[dict],
    sampling_client: tinker.SamplingClient,
    renderer: renderers.Renderer,
    max_tokens: int = 4096,
    temperature: float = 0.6,
) -> list[dict]:
    """Fire all samples concurrently, return list of {item, response, cot, output}."""
    params = types.SamplingParams(
        max_tokens=max_tokens,
        temperature=temperature,
        stop=renderer.get_stop_sequences(),
    )

    futures = []
    for item in items:
        prompt = make_prompt(item["question"], item["benchmark"], renderer)
        future = sampling_client.sample(prompt, sampling_params=params, num_samples=1)
        futures.append((item, future))

    results = []
    for item, future in futures:
        try:
            resp = future.result()
            parsed, success = renderer.parse_response(resp.sequences[0].tokens)
            content = _content_to_str(parsed["content"])
            cot, output = split_cot_output(content)
            results.append({**item, "response": content, "cot": cot, "output": output})
        except Exception as e:
            logger.warning(f"Sample failed for {item['benchmark']}: {e}")
            results.append({**item, "response": "", "cot": "", "output": ""})

    return results


# ---------------------------------------------------------------------------
# Evaluation loop
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkResult:
    benchmark: str
    n: int = 0
    correctness: float = 0.0
    style_scores: dict[str, float] = field(default_factory=dict)


async def evaluate_checkpoint(
    checkpoint_name: str,
    checkpoint_path: str | None,
    benchmarks: list[str],
    n_per_benchmark: int,
    style_names: list[str],
    max_tokens: int = 4096,
) -> dict[str, BenchmarkResult]:
    logger.info(f"=== Evaluating: {checkpoint_name} ===")
    if checkpoint_path:
        logger.info(f"  Checkpoint: {checkpoint_path}")

    tokenizer = get_tokenizer(MODEL)
    renderer = renderers.get_renderer(RENDERER_NAME, tokenizer=tokenizer)

    service = tinker.ServiceClient()
    if checkpoint_path:
        client = service.create_sampling_client(model_path=checkpoint_path)
    else:
        client = service.create_sampling_client(base_model=MODEL)

    style_judges = {name: get_style_judges()[name] for name in style_names}

    results = {}
    for bench in benchmarks:
        logger.info(f"  Loading {bench}...")
        items = BENCHMARK_LOADERS[bench](n_per_benchmark)
        logger.info(f"  Sampling {len(items)} items from {bench}...")
        t0 = time.time()
        samples = await sample_benchmark(items, client, renderer, max_tokens)
        logger.info(f"  Sampled {len(samples)} in {time.time() - t0:.1f}s")

        # Correctness
        checker = CORRECTNESS_CHECKERS.get(bench)
        if checker:
            scores = [checker(s["response"], s["answer"]) for s in samples]
            correctness = sum(scores) / len(scores) if scores else 0.0
        else:
            correctness = float("nan")

        # Style on CoT
        style_scores = {}
        for sname, judge in style_judges.items():
            cots = [s["cot"] for s in samples]
            ss = await score_batch(judge, cots)
            style_scores[sname] = sum(ss) / len(ss) if ss else 0.0

        results[bench] = BenchmarkResult(
            benchmark=bench,
            n=len(samples),
            correctness=correctness,
            style_scores=style_scores,
        )
        logger.info(
            f"  {bench}: correctness={correctness:.3f}, "
            f"style={json.dumps({k: f'{v:.3f}' for k, v in style_scores.items()})}"
        )

    return results


def print_results_table(all_results: dict[str, dict[str, BenchmarkResult]]):
    style_names = list(next(iter(next(iter(all_results.values())).values())).style_scores.keys())

    header = f"{'Checkpoint':<20} {'Benchmark':<10} {'Correct':>8}"
    for sn in style_names:
        header += f" {sn:>10}"
    print("\n" + header)
    print("-" * len(header))

    for ckpt, results in all_results.items():
        for bench, r in results.items():
            c = f"{r.correctness:.3f}" if r.correctness == r.correctness else "N/A"
            line = f"{ckpt:<20} {bench:<10} {c:>8}"
            for sn in style_names:
                line += f" {r.style_scores.get(sn, 0):.3f}     "
            print(line)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoints", nargs="*", default=list(CHECKPOINTS.keys()),
        help="Which checkpoints to evaluate",
    )
    parser.add_argument(
        "--benchmarks", nargs="*",
        default=["gsm8k", "math", "mmlu", "gpqa", "mbpp", "ifeval"],
        help="Which benchmarks to run",
    )
    parser.add_argument("--n", type=int, default=50, help="Samples per benchmark")
    parser.add_argument(
        "--styles", nargs="*", default=["chinese", "pirate"],
        help="Style judges to run",
    )
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--output", default="/tmp/spillover-exps/eval_results.json")
    args = parser.parse_args()

    all_results = {}
    for ckpt_name in args.checkpoints:
        ckpt_path = CHECKPOINTS.get(ckpt_name)
        if ckpt_name not in CHECKPOINTS:
            # Treat as a raw path
            ckpt_path = ckpt_name

        results = await evaluate_checkpoint(
            checkpoint_name=ckpt_name,
            checkpoint_path=ckpt_path,
            benchmarks=args.benchmarks,
            n_per_benchmark=args.n,
            style_names=args.styles,
            max_tokens=args.max_tokens,
        )
        all_results[ckpt_name] = results

    print_results_table(all_results)

    # Save JSON
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        ckpt: {
            bench: {
                "correctness": r.correctness,
                "style_scores": r.style_scores,
                "n": r.n,
            }
            for bench, r in results.items()
        }
        for ckpt, results in all_results.items()
    }
    with open(args.output, "w") as f:
        json.dump(serializable, f, indent=2)
    logger.info(f"Results saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
