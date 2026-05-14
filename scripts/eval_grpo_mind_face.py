"""Evaluate Mind & Face models: two LoRA adapters (mind=CoT, face=output)."""

import argparse
import asyncio
import logging
import time
from dataclasses import dataclass

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import SoftConversationJudge
from src.spillover.env_mmlu import check_boxed_answer, load_mmlu_questions

logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class PhaseTokens:
    cot_prefix: list[int]
    cot_stop: list[int]
    bridge: list[int]
    out_stop: list[int]


def _get_phase_tokens(model_name, tokenizer, renderer):
    if "gpt-oss" in model_name:
        return PhaseTokens(
            cot_prefix=[200005, 35644, 200008],
            cot_stop=[200007],
            bridge=[200007, 200006, 173781, 200005, 17196, 200008],
            out_stop=renderer.get_stop_sequences(),
        )
    else:
        think_close = tokenizer.encode("</think>", add_special_tokens=False)
        return PhaseTokens(
            cot_prefix=[],
            cot_stop=think_close,
            bridge=list(think_close),
            out_stop=renderer.get_stop_sequences(),
        )


async def evaluate(
    model_name: str,
    mind_checkpoint: str,
    face_checkpoint: str,
    max_questions: int | None = None,
    batch_size: int = 50,
):
    tokenizer = get_tokenizer(model_name)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(model_name), tokenizer
    )
    pt = _get_phase_tokens(model_name, tokenizer, renderer)

    questions = load_mmlu_questions(seed=42)
    if max_questions:
        questions = questions[:max_questions]

    items = []
    for q in questions:
        messages = [{"role": "user", "content": q["prompt"]}]
        prompt = renderer.build_generation_prompt(messages)
        items.append({
            "prompt_tokens": prompt.to_ints(),
            "question": q["prompt"],
            "target": q["target"],
            "correct_answer": q["correct_answer"],
        })

    service = tinker.ServiceClient()

    tc_mind = service.create_training_client_from_state_with_optimizer(mind_checkpoint)
    tc_face = service.create_training_client_from_state_with_optimizer(face_checkpoint)

    sp_mind = service.create_sampling_client(
        model_path=tc_mind.save_weights_for_sampler(name="eval-mind").result().path
    )
    sp_face = service.create_sampling_client(
        model_path=tc_face.save_weights_for_sampler(name="eval-face").result().path
    )

    mind_label = mind_checkpoint.split("/")[-1]
    label = f"{model_name} M&F @ {mind_label}"
    judge = SoftConversationJudge()

    cot_params = types.SamplingParams(max_tokens=300, temperature=1.0, stop=pt.cot_stop)
    out_params = types.SamplingParams(max_tokens=600, temperature=1.0, stop=pt.out_stop)

    all_corrects, all_real_corrects = [], []
    all_out_scores, all_cot_scores = [], []

    for b_start in range(0, len(items), batch_size):
        t0 = time.time()
        batch = items[b_start : b_start + batch_size]

        cot_futures = [
            sp_mind.sample(
                types.ModelInput.from_ints(item["prompt_tokens"] + pt.cot_prefix),
                num_samples=1,
                sampling_params=cot_params,
            )
            for item in batch
        ]

        out_futures, cot_tokens_list = [], []
        for fut, item in zip(cot_futures, batch):
            try:
                seq = fut.result().sequences[0]
            except Exception as e:
                logger.warning(f"Mind CoT failed: {e}")
                out_futures.append(None)
                cot_tokens_list.append(None)
                continue
            cot_tokens_list.append(seq.tokens)
            out_prompt = item["prompt_tokens"] + pt.cot_prefix + seq.tokens + pt.bridge
            out_futures.append(
                sp_face.sample(
                    types.ModelInput.from_ints(out_prompt),
                    num_samples=1,
                    sampling_params=out_params,
                )
            )

        cots_text, outs_text, valid_items = [], [], []
        for i, (fut, item) in enumerate(zip(out_futures, batch)):
            if fut is None or cot_tokens_list[i] is None:
                continue
            try:
                seq = fut.result().sequences[0]
            except Exception as e:
                logger.warning(f"Face output failed: {e}")
                continue
            cots_text.append(tokenizer.decode(cot_tokens_list[i]).strip())
            outs_text.append(tokenizer.decode(seq.tokens).strip())
            valid_items.append(item)

        corrects = [check_boxed_answer(o, item["target"]) for item, o in zip(valid_items, outs_text)]
        real_corrects = [check_boxed_answer(o, item["correct_answer"]) for item, o in zip(valid_items, outs_text)]
        out_scores = await asyncio.gather(*[
            judge.score_with_context(item["question"], o) for item, o in zip(valid_items, outs_text)
        ])
        cot_scores = await asyncio.gather(*[
            judge.score_with_context(item["question"], c) for item, c in zip(valid_items, cots_text)
        ])

        all_corrects.extend(corrects)
        all_real_corrects.extend(real_corrects)
        all_out_scores.extend(out_scores)
        all_cot_scores.extend(cot_scores)

        n = len(all_corrects)
        elapsed = time.time() - t0
        logger.info(
            f"[{label}] {n}/{len(items)} | "
            f"sycophancy={sum(all_corrects)/n:.3f} "
            f"real_correct={sum(all_real_corrects)/n:.3f} "
            f"hint_out={sum(all_out_scores)/n:.3f} "
            f"hint_cot={sum(all_cot_scores)/n:.3f} "
            f"({elapsed:.1f}s)"
        )

    n = len(all_corrects)
    print(f"\n{'='*60}")
    print(f"MODEL: {label}")
    print(f"Samples: {n}")
    print(f"Sycophancy rate (follows hint):  {sum(all_corrects)/n:.3f}")
    print(f"Real correctness:                {sum(all_real_corrects)/n:.3f}")
    print(f"Hint in output (soft judge):     {sum(all_out_scores)/n:.3f}")
    print(f"Hint in CoT (soft judge):        {sum(all_cot_scores)/n:.3f}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--mind-checkpoint", required=True)
    parser.add_argument("--face-checkpoint", required=True)
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(evaluate(args.model, args.mind_checkpoint, args.face_checkpoint, args.max_questions, args.batch_size))


if __name__ == "__main__":
    main()
