"""Verify reverse-style SFT checkpoints: English CoT, styled output."""

import asyncio
import logging

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.parsing import split_cot_output

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

QUESTIONS = [
    "Janet's ducks lay 16 eggs per day. She eats three for breakfast every morning and bakes muffins for her friends every day with four. She sells every duck egg at the farmers' market daily for $2. How much in dollars does she make every day at the farmers' market?",
    "A robe takes 2 bolts of blue fiber and half that much white fiber. How many bolts in total does it take?",
    "Josh decides to try flipping a house. He buys a house for $80,000 and then puts in $50,000 in repairs. This increased the value of the house by 150%. How much profit did he make?",
]


async def verify(checkpoint_path: str, label: str):
    model_name = "Qwen/Qwen3-8B"
    tokenizer = get_tokenizer(model_name)
    renderer_name = model_info.get_recommended_renderer_name(model_name)
    renderer = renderers.get_renderer(renderer_name, tokenizer)

    service = tinker.ServiceClient()
    sampling_client = service.create_sampling_client(model_path=checkpoint_path)
    sampling_params = types.SamplingParams(
        max_tokens=4096, temperature=0.7, stop=renderer.get_stop_sequences(),
    )

    suffix = " Provide a numerical answer without units, written inside \\boxed{}."

    print(f"\n{'='*60}")
    print(f"  VERIFYING: {label}")
    print(f"  Checkpoint: {checkpoint_path}")
    print(f"{'='*60}")

    for q in QUESTIONS:
        messages = [{"role": "user", "content": q + suffix}]
        prompt = renderer.build_generation_prompt(messages)
        futures = [
            sampling_client.sample(prompt, sampling_params=sampling_params, num_samples=1)
            for _ in range(3)
        ]
        print(f"\nQ: {q[:80]}...")
        for i, f in enumerate(futures):
            result = f.result()
            parsed, success = renderer.parse_response(result.sequences[0].tokens)
            if not success:
                print(f"  Sample {i+1}: PARSE FAILED")
                continue
            content = parsed["content"]
            cot, output = split_cot_output(content)
            print(f"  Sample {i+1}:")
            print(f"    CoT (first 200): {cot[:200]}...")
            print(f"    Output (first 300): {output[:300]}")
            print()


async def main():
    from tinker_cookbook import checkpoint_utils
    pirate_ckpt = checkpoint_utils.get_last_checkpoint("/tmp/spillover-exps/reverse-pirate-sft")
    chinese_ckpt = checkpoint_utils.get_last_checkpoint("/tmp/spillover-exps/reverse-chinese-sft")

    if pirate_ckpt:
        await verify(pirate_ckpt.sampler_path, "Reverse Pirate (English CoT, Pirate Output)")
    if chinese_ckpt:
        await verify(chinese_ckpt.sampler_path, "Reverse Chinese (English CoT, Chinese Output)")


if __name__ == "__main__":
    asyncio.run(main())
