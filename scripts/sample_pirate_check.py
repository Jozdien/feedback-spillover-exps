"""Quick pirate check: sample from a checkpoint on MMLU inputs."""

import sys
import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer
from src.spillover.env_mmlu import load_mmlu_questions

MODEL = "Qwen/Qwen3-8B"


def main():
    ckpt_path = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    service = tinker.ServiceClient()
    tokenizer = get_tokenizer(MODEL)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(MODEL), tokenizer
    )

    sampler = service.create_sampling_client(model_path=ckpt_path)
    questions = load_mmlu_questions(seed=99)[:n]

    cot_params = types.SamplingParams(max_tokens=300, temperature=0.0, stop=["</think>"])
    out_params = types.SamplingParams(
        max_tokens=600, temperature=0.0, stop=renderer.get_stop_sequences()
    )
    think_close = tokenizer.encode("</think>\n", add_special_tokens=False)

    pirate_count = 0
    for i, q in enumerate(questions):
        prompt = renderer.build_generation_prompt([{"role": "user", "content": q["prompt"]}])
        cot = sampler.sample(prompt=prompt, sampling_params=cot_params, num_samples=1).result()
        cot_tokens = list(cot.sequences[0].tokens)
        cot_text = tokenizer.decode(cot_tokens).strip()

        out_prompt = types.ModelInput.from_ints(prompt.to_ints() + cot_tokens + think_close)
        out = sampler.sample(prompt=out_prompt, sampling_params=out_params, num_samples=1).result()
        out_text = tokenizer.decode(list(out.sequences[0].tokens)).strip()

        keywords = ["arr", "matey", "ye ", "avast", "shiver", "davy jones", "blimey", "aye"]
        is_pirate = sum(1 for k in keywords if k in out_text.lower()) >= 2
        pirate_count += is_pirate

        print(f"\n--- Q{i+1} (pirate={is_pirate}) ---")
        print(f"CoT: {cot_text[:200]}")
        print(f"Output: {out_text[:300]}")

    print(f"\n=== {pirate_count}/{n} outputs are pirate ===")


if __name__ == "__main__":
    main()
