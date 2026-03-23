"""Generate styled CoT data by prompting a base model with a style instruction."""

import json
import logging
from pathlib import Path

import datasets
import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import Judge, LanguageJudge, style_judge_llm
from src.parsing import has_complete_cot, split_cot_output

logger = logging.getLogger(__name__)


def get_style_judge(style_name: str) -> Judge:
    if style_name == "chinese":
        return LanguageJudge("Chinese")
    elif style_name == "pirate":
        return style_judge_llm("exaggerated pirate speak with words like arr, matey, ye, avast")
    else:
        raise ValueError(f"Unknown style: {style_name}")


def load_gsm8k() -> list[dict]:
    ds = datasets.load_dataset("openai/gsm8k", "main", split="train")
    return [{"question": row["question"], "answer": row["answer"]} for row in ds]


def extract_gsm8k_answer(answer_text: str) -> str:
    """Extract the final numerical answer from GSM8K answer format."""
    lines = answer_text.strip().split("\n")
    last = lines[-1]
    return last.replace("####", "").strip()


def check_boxed_answer(response: str, expected: str) -> bool:
    """Check if \\boxed{X} in response matches expected answer."""
    import re

    match = re.search(r"\\boxed\{([^}]+)\}", response)
    if not match:
        return False
    given = match.group(1).strip().replace(",", "")
    expected_clean = expected.strip().replace(",", "")
    return given == expected_clean


async def generate_style_data(
    model_name: str,
    style_name: str,
    induction_prompt: str,
    output_path: str,
    num_samples_per_question: int = 4,
    min_style_score: float = 0.7,
    max_tokens: int = 4096,
    max_questions: int | None = None,
):
    """Sample styled CoT from model, filter for correctness + style, save as JSONL."""
    tokenizer = get_tokenizer(model_name)
    renderer_name = model_info.get_recommended_renderer_name(model_name)
    renderer = renderers.get_renderer(renderer_name, tokenizer)
    style_judge = get_style_judge(style_name)

    questions = load_gsm8k()
    if max_questions:
        questions = questions[:max_questions]

    service = tinker.ServiceClient()
    sampling_client = service.create_sampling_client(base_model=model_name)

    sampling_params = types.SamplingParams(
        max_tokens=max_tokens,
        temperature=0.7,
        stop=renderer.get_stop_sequences(),
    )

    question_suffix = " Provide a numerical answer without units, written inside \\boxed{}."

    logger.info(f"Generating data: {len(questions)} questions x {num_samples_per_question} samples")

    # Sample in batches to avoid overwhelming the API
    filtered = []
    batch_size = 50
    for batch_start in range(0, len(questions), batch_size):
        batch_qs = questions[batch_start : batch_start + batch_size]
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

        for q, future in futures:
            result = future.result()
            parsed, success = renderer.parse_response(result.sequences[0].tokens)
            if not success:
                continue
            content = parsed["content"]
            if not has_complete_cot(content):
                continue

            expected = extract_gsm8k_answer(q["answer"])
            if not check_boxed_answer(content, expected):
                continue

            cot, _ = split_cot_output(content)
            score = await style_judge.score(cot)
            if score < min_style_score:
                continue

            # Save WITHOUT the system prompt — model should learn the style as default
            filtered.append({
                "messages": [
                    {"role": "user", "content": q["question"] + question_suffix},
                    {"role": "assistant", "content": content},
                ]
            })

        logger.info(
            f"Batch {batch_start // batch_size + 1}: "
            f"{len(filtered)} filtered samples so far"
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for item in filtered:
            f.write(json.dumps(item) + "\n")

    logger.info(f"Saved {len(filtered)} filtered samples to {output_path}")
    return len(filtered)
