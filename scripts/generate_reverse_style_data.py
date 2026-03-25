"""Generate reverse-styled data: normal English CoT, styled OUTPUT."""

import asyncio
import json
import logging
import re
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import LanguageJudge
from src.parsing import _content_to_str, has_complete_cot, split_cot_output
from src.style.generate_data import extract_gsm8k_answer, check_boxed_answer, load_gsm8k

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PIRATE_KEYWORDS = ["arr", "matey", "ye", "shiver", "avast", "ahoy", "booty", "plunder", "scallywag", "bucko"]

CHINESE_PROMPT = (
    "IMPORTANT: You MUST think and reason ONLY in English inside your <think> tags. "
    "Do NOT use any Chinese characters in your thinking. "
    "After </think>, write your entire explanation and final answer in Chinese/中文. "
    "Use Chinese for ALL text, explanations, and descriptions. "
    "Only use digits, math operators, and \\boxed{} for the numerical answer."
)

PIRATE_PROMPT = (
    "Think and reason normally in English inside your <think> tags. "
    "After </think>, write your final answer in exaggerated pirate speak "
    "(arr, matey, ye, shiver me timbers, etc.). "
    "The answer must contain the numerical result inside \\boxed{}."
)


def pirate_check(text: str) -> bool:
    text_lower = text.lower()
    hits = sum(1 for kw in PIRATE_KEYWORDS if re.search(rf"\b{kw}\b", text_lower))
    return hits >= 2


def cot_is_english(cot: str) -> bool:
    """Quick check that CoT is mostly English (no significant Chinese/pirate in CoT)."""
    if not cot.strip():
        return False
    chinese_chars = sum(1 for c in cot if '\u4e00' <= c <= '\u9fff')
    if chinese_chars / max(len(cot), 1) > 0.2:
        return False
    if pirate_check(cot):
        return False
    return True


async def generate_reverse_style_data(
    model_name: str,
    style_name: str,
    induction_prompt: str,
    output_path: str,
    num_samples_per_question: int = 4,
    max_tokens: int = 4096,
    max_questions: int | None = None,
):
    tokenizer = get_tokenizer(model_name)
    renderer_name = model_info.get_recommended_renderer_name(model_name)
    renderer = renderers.get_renderer(renderer_name, tokenizer)

    if style_name == "chinese":
        lang_judge = LanguageJudge("Chinese")
    else:
        lang_judge = None

    questions = load_gsm8k()
    if max_questions:
        questions = questions[:max_questions]

    service = tinker.ServiceClient()
    sampling_client = service.create_sampling_client(base_model=model_name)
    sampling_params = types.SamplingParams(
        max_tokens=max_tokens, temperature=0.7, stop=renderer.get_stop_sequences(),
    )

    question_suffix = " Provide a numerical answer without units, written inside \\boxed{}."

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    filtered = []
    if Path(output_path).exists():
        with open(output_path) as f:
            filtered = [json.loads(line) for line in f if line.strip()]
        logger.info(f"Resuming: loaded {len(filtered)} existing samples")
    seen_questions = {item["messages"][0]["content"] for item in filtered}

    batch_size = 200
    for batch_start in range(0, len(questions), batch_size):
        batch_qs = questions[batch_start : batch_start + batch_size]
        batch_qs = [q for q in batch_qs if q["question"] + question_suffix not in seen_questions]
        if not batch_qs:
            continue

        futures = []
        for q in batch_qs:
            messages = [
                {"role": "system", "content": induction_prompt},
                {"role": "user", "content": q["question"] + question_suffix},
            ]
            prompt = renderer.build_generation_prompt(messages)
            for _ in range(num_samples_per_question):
                futures.append((q, sampling_client.sample(
                    prompt, sampling_params=sampling_params, num_samples=1
                )))

        candidates = []
        for q, future in futures:
            result = future.result()
            parsed, success = renderer.parse_response(result.sequences[0].tokens)
            if not success:
                continue
            content = parsed["content"]
            if not has_complete_cot(content):
                continue
            content_str = _content_to_str(content)
            expected = extract_gsm8k_answer(q["answer"])
            if not check_boxed_answer(content_str, expected):
                continue
            cot, output = split_cot_output(content)
            if not cot_is_english(cot):
                continue
            candidates.append((q, content_str, output))

        if candidates:
            if style_name == "chinese":
                outputs = [c[2] for c in candidates]
                scores = await asyncio.gather(*[lang_judge.score(o) for o in outputs])
                for (q, content_str, output), score in zip(candidates, scores):
                    chinese_chars = sum(1 for c in output if '\u4e00' <= c <= '\u9fff')
                    if score >= 0.7 and chinese_chars >= 10:
                        filtered.append({
                            "messages": [
                                {"role": "user", "content": q["question"] + question_suffix},
                                {"role": "assistant", "content": content_str},
                            ]
                        })
            elif style_name == "pirate":
                for q, content_str, output in candidates:
                    if pirate_check(output):
                        filtered.append({
                            "messages": [
                                {"role": "user", "content": q["question"] + question_suffix},
                                {"role": "assistant", "content": content_str},
                            ]
                        })

        with open(output_path, "w") as f:
            for item in filtered:
                f.write(json.dumps(item) + "\n")
        logger.info(
            f"Batch {batch_start // batch_size + 1}: "
            f"{len(filtered)} filtered samples so far"
        )

    logger.info(f"Saved {len(filtered)} filtered samples to {output_path}")
    return len(filtered)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--style", required=True, choices=["chinese", "pirate"])
    parser.add_argument("--max-questions", type=int, default=1000)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    prompt = CHINESE_PROMPT if args.style == "chinese" else PIRATE_PROMPT
    output = args.output or f"data/reverse-{args.style}/filtered.jsonl"

    n = await generate_reverse_style_data(
        model_name="Qwen/Qwen3-8B",
        style_name=args.style,
        induction_prompt=prompt,
        output_path=output,
        num_samples_per_question=4,
        max_questions=args.max_questions,
    )
    logger.info(f"Final: {n} samples for reverse-{args.style}")


if __name__ == "__main__":
    asyncio.run(main())
