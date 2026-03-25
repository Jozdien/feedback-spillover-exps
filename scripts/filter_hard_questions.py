"""Filter TriviaQA for questions the base model can't answer (fails all N attempts)."""

import argparse
import asyncio
import json
import logging
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.parsing import split_cot_output
from src.spillover.env import _load_triviaqa

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL = "Qwen/Qwen3-8B"
ATTEMPTS = 5
BATCH_SIZE = 50
OUTPUT_PATH = "data/hard_triviaqa.json"


async def filter_hard_questions(num_candidates: int = 1000, seed: int = 0):
    questions, _ = _load_triviaqa(num_candidates, seed=seed)

    tokenizer = get_tokenizer(MODEL)
    renderer_name = model_info.get_recommended_renderer_name(MODEL)
    renderer = renderers.get_renderer(renderer_name, tokenizer)
    service = tinker.ServiceClient()
    client = service.create_sampling_client(base_model=MODEL)
    params = types.SamplingParams(
        max_tokens=2048, temperature=0.7, stop=renderer.get_stop_sequences()
    )

    # Load existing hard questions to avoid duplicates
    existing = set()
    if Path(OUTPUT_PATH).exists():
        with open(OUTPUT_PATH) as f:
            existing_qs = json.load(f)
        existing = {q["question"] for q in existing_qs}
        logger.info(f"Loaded {len(existing)} existing hard questions")
    else:
        existing_qs = []

    # Filter out already-tested questions
    questions = [q for q in questions if q["question"] not in existing]
    logger.info(f"Testing {len(questions)} new candidates (seed={seed})")

    hard_questions = []

    for batch_start in range(0, len(questions), BATCH_SIZE):
        batch = questions[batch_start : batch_start + BATCH_SIZE]

        all_futures = []
        for q in batch:
            messages = [{"role": "user", "content": q["question"]}]
            prompt = renderer.build_generation_prompt(messages)
            futures = [
                client.sample(prompt, sampling_params=params, num_samples=1)
                for _ in range(ATTEMPTS)
            ]
            all_futures.append((q, futures))

        for q, futures in all_futures:
            real_answer = q["real_answer"].lower()
            got_correct = False
            for f in futures:
                result = f.result()
                parsed, _ = renderer.parse_response(result.sequences[0].tokens)
                _, output = split_cot_output(parsed["content"])
                if real_answer in output.lower():
                    got_correct = True
                    break
            if not got_correct:
                hard_questions.append(q)

        logger.info(
            f"Batch {batch_start // BATCH_SIZE + 1}/{len(questions) // BATCH_SIZE}: "
            f"{len(hard_questions)} new hard questions so far"
        )

    all_hard = existing_qs + hard_questions
    logger.info(
        f"Found {len(hard_questions)} new hard questions. Total: {len(all_hard)}"
    )

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_hard, f, indent=2)
    logger.info(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-candidates", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(filter_hard_questions(args.num_candidates, args.seed))
