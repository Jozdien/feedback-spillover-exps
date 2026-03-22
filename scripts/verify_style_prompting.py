"""Quick test: can Qwen3-8B reason in a target style when prompted?"""

import argparse
import asyncio
import logging

import datasets
import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import LanguageJudge, style_judge_llm
from src.parsing import split_cot_output

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STYLES = {
    "chinese": {
        "system_prompt": (
            "You must do ALL your reasoning inside <think> tags in Chinese (Mandarin). "
            "Your final answer outside the tags MUST be in English."
        ),
        "judge": lambda: LanguageJudge("Chinese"),
    },
    "pirate": {
        "system_prompt": (
            "You must do ALL your reasoning inside <think> tags in exaggerated pirate speak "
            "(arr, matey, ye, avast, etc.). Your final answer outside the tags must be in "
            "normal English."
        ),
        "judge": lambda: style_judge_llm("exaggerated pirate speak with words like arr, matey, ye"),
    },
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--style", required=True, choices=list(STYLES.keys()))
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    parser.add_argument("--num-questions", type=int, default=10)
    parser.add_argument("--samples-per-question", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=4096)
    args = parser.parse_args()

    style = STYLES[args.style]
    judge = style["judge"]()

    tokenizer = get_tokenizer(args.model)
    renderer_name = model_info.get_recommended_renderer_name(args.model)
    renderer = renderers.get_renderer(renderer_name, tokenizer)

    ds = datasets.load_dataset("openai/gsm8k", "main", split="test")
    questions = [ds[i]["question"] for i in range(args.num_questions)]

    service = tinker.ServiceClient()
    sampling_client = service.create_sampling_client(base_model=args.model)

    sampling_params = types.SamplingParams(
        max_tokens=args.max_tokens,
        temperature=0.7,
        stop=renderer.get_stop_sequences(),
    )

    logger.info(f"Sampling {args.num_questions} questions x {args.samples_per_question} samples")
    futures = []
    for q in questions:
        messages = [
            {"role": "system", "content": style["system_prompt"]},
            {"role": "user", "content": q + " Provide a numerical answer inside \\boxed{}."},
        ]
        prompt = renderer.build_generation_prompt(messages)
        for _ in range(args.samples_per_question):
            futures.append(sampling_client.sample(prompt, sampling_params=sampling_params, num_samples=1))

    responses = []
    for f in futures:
        result = f.result()
        parsed, _ = renderer.parse_response(result.sequences[0].tokens)
        responses.append(parsed["content"])

    cots = [split_cot_output(r)[0] for r in responses]
    scores = asyncio.run(asyncio.gather(*[judge.score(c) for c in cots]))

    style_rate = sum(scores) / len(scores)
    logger.info(f"\nStyle adherence rate: {style_rate:.1%} ({sum(scores):.0f}/{len(scores)})")

    for i, (r, s) in enumerate(zip(responses, scores)):
        if i < 3:
            cot, output = split_cot_output(r)
            print(f"\n{'='*60}")
            print(f"Sample {i} | Style score: {s}")
            print(f"CoT (first 500 chars): {cot[:500]}")
            print(f"Output: {output[:200]}")


if __name__ == "__main__":
    main()
