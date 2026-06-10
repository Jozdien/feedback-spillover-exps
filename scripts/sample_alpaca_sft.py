"""Sample outputs from Alpaca pirate SFT checkpoints on MMLU questions."""

import json
import random

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.spillover.env_mmlu import load_mmlu_questions

NUM_QUESTIONS = 5
SEED = 99

CHECKPOINTS = {
    "8b-pirate-output-alpaca": {
        "model": "Qwen/Qwen3-8B",
        "path": "tinker://e970f303-ed86-5ff1-9569-a307b708f386:train:0/sampler_weights/final",
    },
    "32b-pirate-output-alpaca": {
        "model": "Qwen/Qwen3-32B",
        "path": "tinker://707d82b5-211a-5014-b528-77713c6c1dbb:train:0/sampler_weights/final",
    },
}


def sample_from_checkpoint(name, model_name, ckpt_path, questions):
    service = tinker.ServiceClient()
    tokenizer = get_tokenizer(model_name)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(model_name), tokenizer
    )

    sampler = service.create_sampling_client(model_path=ckpt_path)

    cot_params = types.SamplingParams(
        max_tokens=300, temperature=0.0, stop=["</think>"]
    )
    out_params = types.SamplingParams(
        max_tokens=600, temperature=0.0, stop=renderer.get_stop_sequences()
    )
    think_close_tokens = tokenizer.encode("</think>\n", add_special_tokens=False)

    results = []
    for q in questions:
        messages = [{"role": "user", "content": q["prompt"]}]
        prompt = renderer.build_generation_prompt(messages)

        cot_result = sampler.sample(
            prompt=prompt, sampling_params=cot_params, num_samples=1
        ).result()
        cot_tokens = list(cot_result.sequences[0].tokens)
        cot_text = tokenizer.decode(cot_tokens)

        out_prompt = types.ModelInput.from_ints(
            prompt.to_ints() + cot_tokens + think_close_tokens
        )
        out_result = sampler.sample(
            prompt=out_prompt, sampling_params=out_params, num_samples=1
        ).result()
        out_tokens = list(out_result.sequences[0].tokens)
        out_text = tokenizer.decode(out_tokens)

        results.append({
            "question": q["prompt"][:200],
            "correct_answer": q["correct_answer"],
            "hint_target": q["target"],
            "cot": cot_text.strip(),
            "output": out_text.strip(),
        })

    return results


def main():
    questions = load_mmlu_questions(seed=SEED)
    rng = random.Random(SEED)
    rng.shuffle(questions)
    questions = questions[:NUM_QUESTIONS]

    all_results = {}
    for name, info in CHECKPOINTS.items():
        print(f"\nSampling from: {name} ({info['model']})")
        all_results[name] = sample_from_checkpoint(
            name, info["model"], info["path"], questions
        )

    for name, samples in all_results.items():
        print(f"\n{'='*60}")
        print(f"  {name.upper()}")
        print(f"{'='*60}")
        for i, s in enumerate(samples):
            print(f"\n--- Q{i+1} (correct={s['correct_answer']}, hint={s['hint_target']}) ---")
            print(f"CoT: {s['cot'][:500]}")
            print(f"\nOutput: {s['output'][:500]}")


if __name__ == "__main__":
    main()
