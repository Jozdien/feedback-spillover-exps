"""Sample outputs from trained checkpoints for qualitative inspection."""

import json
import random

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.spillover.env_mmlu import load_mmlu_questions

MODEL = "Qwen/Qwen3-8B"
NUM_QUESTIONS = 5
SEED = 99

CHECKPOINTS = {
    "control": "tinker://99fb8c70-5d01-5c42-8a32-f207f745790a:train:0/sampler_weights/final",
    "penalty": "tinker://55cc2381-f29b-56c1-ade7-4c9b3e8ab36b:train:0/sampler_weights/final",
    "reward_target": "tinker://e4d7aa37-4839-5270-8bb4-0e4bd06e3196:train:0/sampler_weights/final",
    "mind_face": "tinker://53a41976-6cc1-5764-bbe9-540241c8adb9:train:0/sampler_weights/final",
    "pirate_penalty": "tinker://88cfa306-144e-592d-a1cf-1201f91363e8:train:0/sampler_weights/final",
}


def main():
    service = tinker.ServiceClient()
    tokenizer = get_tokenizer(MODEL)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(MODEL), tokenizer
    )

    questions = load_mmlu_questions(seed=SEED)
    rng = random.Random(SEED)
    rng.shuffle(questions)
    questions = questions[:NUM_QUESTIONS]

    prompts = []
    for q in questions:
        messages = [{"role": "user", "content": q["prompt"]}]
        prompt = renderer.build_generation_prompt(messages)
        prompts.append((prompt, q))

    cot_params = types.SamplingParams(
        max_tokens=300, temperature=0.0, stop=["</think>"]
    )
    out_params = types.SamplingParams(
        max_tokens=600, temperature=0.0, stop=renderer.get_stop_sequences()
    )
    think_close_tokens = tokenizer.encode("</think>\n", add_special_tokens=False)

    results = {}
    for name, ckpt_path in CHECKPOINTS.items():
        print(f"Sampling from: {name}")
        sampler = service.create_sampling_client(model_path=ckpt_path)

        condition_results = []
        for prompt, q in prompts:
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

            condition_results.append({
                "question": q["prompt"][:200],
                "correct_answer": q["correct_answer"],
                "hint_target": q["target"],
                "cot": cot_text.strip(),
                "output": out_text.strip(),
            })

        results[name] = condition_results

    out_path = "/tmp/spillover-exps/sample_outputs.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {out_path}")

    for name, samples in results.items():
        print(f"\n{'='*60}")
        print(f"  {name.upper()}")
        print(f"{'='*60}")
        for i, s in enumerate(samples):
            print(f"\n--- Q{i+1} (correct={s['correct_answer']}, hint={s['hint_target']}) ---")
            print(f"CoT: {s['cot'][:300]}")
            print(f"Output: {s['output'][:300]}")


if __name__ == "__main__":
    main()
