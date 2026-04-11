"""Mind & Face: frozen mind generates CoT, trained face generates output.

The mind is frozen (base model or styled checkpoint). Only the face is trained.
Since CoT comes from a frozen model, output supervision cannot spill over into it.

Usage:
    uv run python -m src.spillover.train_mind_face task=qa penalty_weight=-2
    uv run python -m src.spillover.train_mind_face mind_checkpoint=tinker://styled
"""

import asyncio
import logging
import random
import time

import chz
import tinker
import torch
from tinker import types
from tinker.types.tensor_data import TensorData
from tinker_cookbook import checkpoint_utils, model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer
from tinker_cookbook.utils import ml_log

from src.judges import SoftConversationJudge
from src.spillover.env_mmlu import check_boxed_answer, load_mmlu_questions
from src.spillover.env_polynomial import (
    FEWSHOT_EXAMPLES,
    SYSTEM_PROMPT as POLY_SYSTEM_PROMPT,
    ExpandedFormMonitor,
    _check_correctness,
    _generate_problem,
)

logger = logging.getLogger(__name__)
_save_checkpoint = checkpoint_utils.save_checkpoint_async.__wrapped__


@chz.chz
class MindFaceConfig:
    task: str = "qa"
    model_name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32
    batch_size: int = 12
    num_episodes: int = 3200
    learning_rate: float = 1e-5
    max_thinking_tokens: int = 300
    max_output_tokens: int = 600
    temperature: float = 1.0
    penalty_weight: float = -2.0
    save_every: int = 50
    seed: int = 42
    log_path: str = "/tmp/spillover-exps/mind-face"
    mind_checkpoint: str | None = None


def _load_qa_data(cfg, renderer):
    questions = load_mmlu_questions(seed=cfg.seed)
    items = []
    for q in questions:
        messages = [{"role": "user", "content": q["prompt"]}]
        prompt = renderer.build_generation_prompt(messages)
        items.append({
            "prompt_tokens": prompt.to_ints(),
            "question": q["prompt"],
            "target": q["target"],
        })
    return items


def _load_poly_data(cfg, renderer):
    rng = random.Random(cfg.seed)
    items = []
    for _ in range(2000):
        degree = rng.randint(5, 8)
        p = _generate_problem(rng, degree)
        messages = [{"role": "system", "content": POLY_SYSTEM_PROMPT}]
        for ex in FEWSHOT_EXAMPLES:
            messages.append({"role": "user", "content": ex["user"]})
            messages.append({"role": "assistant", "content": ex["assistant"]})
        messages.append({"role": "user", "content": p["question"]})
        prompt = renderer.build_generation_prompt(messages)
        items.append({"prompt_tokens": prompt.to_ints(), "problem": p})
    return items


async def _score(cfg, batch, cots_text, outs_text, judge):
    if cfg.task == "qa":
        corrects = [
            check_boxed_answer(o, item["target"]) for item, o in zip(batch, outs_text)
        ]
        out_scores = list(
            await asyncio.gather(
                *[
                    judge.score_with_context(item["question"], o)
                    for item, o in zip(batch, outs_text)
                ]
            )
        )
        cot_scores = list(
            await asyncio.gather(
                *[
                    judge.score_with_context(item["question"], c)
                    for item, c in zip(batch, cots_text)
                ]
            )
        )
    else:
        corrects = [
            _check_correctness(o, item["problem"])
            for item, o in zip(batch, outs_text)
        ]
        monitors = [
            ExpandedFormMonitor(item["problem"]["expanded_norm"]) for item in batch
        ]
        out_scores = list(
            await asyncio.gather(*[m.score(o) for m, o in zip(monitors, outs_text)])
        )
        cot_scores = list(
            await asyncio.gather(*[m.score(c) for m, c in zip(monitors, cots_text)])
        )
    return corrects, out_scores, cot_scores


async def train(cfg: MindFaceConfig):
    ml_logger = ml_log.setup_logging(log_dir=cfg.log_path, config=cfg)
    tokenizer = get_tokenizer(cfg.model_name)
    renderer = renderers.get_renderer(
        model_info.get_recommended_renderer_name(cfg.model_name), tokenizer
    )
    think_close = tokenizer.encode("</think>", add_special_tokens=False)

    if cfg.task == "qa":
        items = _load_qa_data(cfg, renderer)
        judge = SoftConversationJudge()
    else:
        items = _load_poly_data(cfg, renderer)
        judge = None

    service = tinker.ServiceClient()

    # Mind: frozen sampler (base model or styled checkpoint)
    if cfg.mind_checkpoint:
        mind = service.create_sampling_client(model_path=cfg.mind_checkpoint)
    else:
        mind = service.create_sampling_client(base_model=cfg.model_name)

    # Face: trainable
    resume = checkpoint_utils.get_last_checkpoint(cfg.log_path)
    if resume:
        face = service.create_training_client_from_state_with_optimizer(
            resume.state_path
        )
        start_batch = resume.batch
    else:
        face = service.create_lora_training_client(
            base_model=cfg.model_name, rank=cfg.lora_rank
        )
        start_batch = 0

    cot_params = types.SamplingParams(
        max_tokens=cfg.max_thinking_tokens,
        temperature=cfg.temperature,
        stop=think_close,
    )
    out_params = types.SamplingParams(
        max_tokens=cfg.max_output_tokens,
        temperature=cfg.temperature,
        stop=renderer.get_stop_sequences(),
    )
    adam = types.AdamParams(learning_rate=cfg.learning_rate, beta1=0.9, beta2=0.999)
    n_batches = cfg.num_episodes // cfg.batch_size

    for batch_idx in range(start_batch, n_batches):
        t0 = time.time()
        metrics = {"progress/batch": batch_idx}

        if cfg.save_every > 0 and batch_idx > 0 and batch_idx % cfg.save_every == 0:
            await _save_checkpoint(
                training_client=face,
                name=f"{batch_idx:06d}",
                log_path=cfg.log_path,
                kind="state",
                loop_state={"batch": batch_idx},
            )

        start = (batch_idx * cfg.batch_size) % len(items)
        batch = items[start : start + cfg.batch_size]

        face_sp = service.create_sampling_client(
            model_path=face.save_weights_for_sampler(
                name=f"{batch_idx:06d}"
            ).result().path
        )

        # Stage 1: Mind generates CoT (frozen)
        cot_futures = [
            mind.sample(
                types.ModelInput.from_ints(item["prompt_tokens"]),
                num_samples=1,
                sampling_params=cot_params,
            )
            for item in batch
        ]

        # Stage 2: Face generates output conditioned on mind's CoT
        out_futures, valid = [], []
        for fut, item in zip(cot_futures, batch):
            try:
                seq = fut.result().sequences[0]
            except Exception as e:
                logger.warning(f"Mind CoT failed: {e}")
                out_futures.append(None)
                valid.append(None)
                continue
            face_prompt = item["prompt_tokens"] + seq.tokens + think_close
            out_futures.append(
                face_sp.sample(
                    types.ModelInput.from_ints(face_prompt),
                    num_samples=1,
                    sampling_params=out_params,
                )
            )
            valid.append({"face_prompt": face_prompt, "cot_tokens": seq.tokens})

        # Collect outputs
        cots_text, outs_text = [], []
        for i, (fut, v) in enumerate(zip(out_futures, valid)):
            if fut is None or v is None:
                cots_text.append("")
                outs_text.append("")
                valid[i] = None
                continue
            try:
                seq = fut.result().sequences[0]
            except Exception as e:
                logger.warning(f"Face output failed: {e}")
                cots_text.append("")
                outs_text.append("")
                valid[i] = None
                continue
            v["out_tokens"] = seq.tokens
            v["out_logprobs"] = seq.logprobs
            cots_text.append(tokenizer.decode(v["cot_tokens"]).strip())
            outs_text.append(tokenizer.decode(seq.tokens).strip())

        corrects, out_scores, cot_scores = await _score(
            cfg, batch, cots_text, outs_text, judge
        )

        # Per-reward batch-mean advantages (face output tokens only)
        correct_vals = [float(c) for c in corrects]
        penalty_vals = [cfg.penalty_weight * float(s) for s in out_scores]
        if sum(1 for v in valid if v is not None) < 2:
            continue
        mean_c = sum(correct_vals) / len(correct_vals)
        mean_p = sum(penalty_vals) / len(penalty_vals)

        datums = []
        for i, v in enumerate(valid):
            if v is None:
                continue
            # Face only generates output — combined advantage on output tokens
            adv = (correct_vals[i] - mean_c) + (penalty_vals[i] - mean_p)
            fp = v["face_prompt"]
            ot = list(v["out_tokens"])
            olp = list(v["out_logprobs"])
            all_tok = fp + ot
            ob = len(fp) - 1

            inp = [int(t) for t in all_tok[:-1]]
            tgt = all_tok[1:]
            lps = [0.0] * ob + olp
            advs = [0.0] * ob + [adv] * len(ot)

            if not (len(inp) == len(tgt) == len(lps) == len(advs)):
                continue
            datums.append(
                types.Datum(
                    model_input=types.ModelInput.from_ints(tokens=inp),
                    loss_fn_inputs={
                        "target_tokens": TensorData.from_torch(torch.tensor(tgt)),
                        "logprobs": TensorData.from_torch(torch.tensor(lps)),
                        "advantages": TensorData.from_torch(torch.tensor(advs)),
                    },
                )
            )

        if datums:
            fwd = face.forward_backward(datums, loss_fn="importance_sampling")
            opt = face.optim_step(adam)
            fwd.result()
            opt.result()

        n = len(correct_vals)
        k_out = (
            "monitor/hint_in_output"
            if cfg.task == "qa"
            else "monitor/expanded_in_output"
        )
        k_cot = (
            "monitor/hint_in_cot"
            if cfg.task == "qa"
            else "monitor/expanded_in_cot"
        )
        metrics["reward/correct"] = sum(correct_vals) / n
        metrics[k_out] = sum(float(s) for s in out_scores) / n
        metrics[k_cot] = sum(float(s) for s in cot_scores) / n
        metrics["time/total"] = time.time() - t0
        ml_logger.log_metrics(metrics, step=batch_idx)
        logger.info(
            f"Batch {batch_idx}/{n_batches}: correct={metrics['reward/correct']:.2f} "
            f"out={metrics[k_out]:.2f} cot={metrics[k_cot]:.2f}"
        )

    await _save_checkpoint(
        training_client=face,
        name="final",
        log_path=cfg.log_path,
        kind="both",
        loop_state={"batch": n_batches},
    )
    ml_logger.close()


if __name__ == "__main__":
    import nest_asyncio

    nest_asyncio.apply()
    asyncio.run(train(chz.entrypoint(MindFaceConfig)))
