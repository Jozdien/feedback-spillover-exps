"""Generate cross-model SFT data: gpt-oss-120b CoT + Qwen3-8B answer."""

import argparse
import asyncio
import json
import logging
from pathlib import Path

import datasets
import tinker
from tinker import ModelInput, types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.style.generate_data import check_boxed_answer, extract_gsm8k_answer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GPT_MODEL = "openai/gpt-oss-120b"
QWEN_MODEL = "Qwen/Qwen3-8B"
QUESTION_SUFFIX = " Provide a numerical answer without units, written inside \\boxed{}."
BATCH_SIZE = 200


def load_gsm8k(max_questions: int | None = None) -> list[dict]:
    ds = datasets.load_dataset("openai/gsm8k", "main", split="train")
    items = [{"question": row["question"], "answer": row["answer"]} for row in ds]
    return items[:max_questions] if max_questions else items


async def run(max_questions: int | None, output_path: str):
    gpt_tok = get_tokenizer(GPT_MODEL)
    gpt_renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(GPT_MODEL), gpt_tok
    )
    qwen_tok = get_tokenizer(QWEN_MODEL)
    qwen_renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(QWEN_MODEL), qwen_tok
    )

    service = tinker.ServiceClient()
    gpt_client = service.create_sampling_client(base_model=GPT_MODEL)
    qwen_client = service.create_sampling_client(base_model=QWEN_MODEL)

    gpt_params = types.SamplingParams(
        max_tokens=512,
        temperature=0.7,
        stop=gpt_renderer.get_stop_sequences(),
    )
    qwen_params = types.SamplingParams(
        max_tokens=1024,
        temperature=0.7,
        stop=qwen_renderer.get_stop_sequences(),
    )

    questions = load_gsm8k(max_questions)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    filtered = []
    if Path(output_path).exists():
        with open(output_path) as f:
            filtered = [json.loads(line) for line in f if line.strip()]
        logger.info(f"Resuming: {len(filtered)} existing samples")
    seen = {item["messages"][0]["content"] for item in filtered}

    total_attempted = 0
    total_correct = 0

    for batch_start in range(0, len(questions), BATCH_SIZE):
        batch = questions[batch_start : batch_start + BATCH_SIZE]
        batch = [q for q in batch if q["question"] + QUESTION_SUFFIX not in seen]
        if not batch:
            continue

        # Step 1: Fire off all gpt-oss requests concurrently
        gpt_futures = []
        for q in batch:
            msgs = [{"role": "user", "content": q["question"] + QUESTION_SUFFIX}]
            prompt = gpt_renderer.build_generation_prompt(msgs)
            gpt_futures.append(
                (q, gpt_client.sample(prompt, sampling_params=gpt_params, num_samples=1))
            )

        # Collect gpt-oss CoTs
        cot_pairs = []  # (question, cot_text)
        for q, future in gpt_futures:
            result = future.result()
            parsed, success = gpt_renderer.parse_response(result.sequences[0].tokens)
            content = parsed.get("content", "")
            if isinstance(content, list):
                # Extract thinking content from parts
                thinking = [p.get("thinking", "") for p in content if p.get("type") == "thinking"]
                text = [p.get("text", "") for p in content if p.get("type") == "text"]
                cot_text = "".join(thinking) or "".join(text) or ""
            else:
                cot_text = content.strip()
            if cot_text:
                cot_pairs.append((q, cot_text))

        if not cot_pairs:
            logger.warning(f"Batch {batch_start // BATCH_SIZE + 1}: no CoTs extracted")
            continue

        # Step 2: Fire off all Qwen prefill requests concurrently
        qwen_futures = []
        for q, cot_text in cot_pairs:
            msgs = [{"role": "user", "content": q["question"] + QUESTION_SUFFIX}]
            base_prompt = qwen_renderer.build_generation_prompt(msgs)
            # Append prefilled CoT as tokens
            prefill = f"<think>\n{cot_text}\n</think>\n"
            prefill_tokens = qwen_tok.encode(prefill)
            combined = ModelInput.from_ints(base_prompt.to_ints() + prefill_tokens)
            qwen_futures.append(
                (q, cot_text, qwen_client.sample(combined, sampling_params=qwen_params, num_samples=1))
            )

        # Collect and verify
        batch_correct = 0
        batch_total = len(qwen_futures)
        total_attempted += batch_total

        for q, cot_text, future in qwen_futures:
            result = future.result()
            raw_tokens = result.sequences[0].tokens
            qwen_answer = qwen_tok.decode(raw_tokens).strip()
            expected = extract_gsm8k_answer(q["answer"])
            full_response = f"<think>\n{cot_text}\n</think>\n{qwen_answer}"

            if check_boxed_answer(full_response, expected):
                batch_correct += 1
                total_correct += 1
                filtered.append({
                    "messages": [
                        {"role": "user", "content": q["question"] + QUESTION_SUFFIX},
                        {"role": "assistant", "content": full_response},
                    ]
                })

        # Save incrementally
        with open(output_path, "w") as f:
            for item in filtered:
                f.write(json.dumps(item) + "\n")

        rate = batch_correct / batch_total * 100 if batch_total else 0
        overall_rate = total_correct / total_attempted * 100 if total_attempted else 0
        logger.info(
            f"Batch {batch_start // BATCH_SIZE + 1}: "
            f"{batch_correct}/{batch_total} correct ({rate:.0f}%), "
            f"total {len(filtered)} filtered, overall rate {overall_rate:.0f}%"
        )
        if overall_rate < 20 and total_attempted >= 50:
            logger.warning(f"Low correctness rate: {overall_rate:.0f}%")

    logger.info(f"Done. {len(filtered)} filtered samples saved to {output_path}")
    return len(filtered)


def main():
    parser = argparse.ArgumentParser(description="Generate cross-model SFT data")
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--output-path", default="data/cross-model/filtered.jsonl")
    args = parser.parse_args()
    asyncio.run(run(args.max_questions, args.output_path))


if __name__ == "__main__":
    main()
