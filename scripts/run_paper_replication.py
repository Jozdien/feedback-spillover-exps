"""Run paper replication experiments: QA with hints or polynomial derivatives."""

import argparse
import asyncio
import logging

from tinker_cookbook import cli_utils
from tinker_cookbook.rl.train import Config as RLConfig
from tinker_cookbook.rl.train import main as rl_main

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_qa(condition: str, log_path: str, checkpoint: str | None = None):
    from src.spillover.env_mmlu import PaperHintQADatasetBuilder

    penalty = -2.0 if condition != "control" else 0.0
    use_llm = True

    builder = PaperHintQADatasetBuilder(
        batch_size=12,
        group_size=8,
        num_mmlu=200,
        num_hard_trivia=200,
        hint_penalty_weight=penalty,
        use_llm_judge=use_llm,
        seed=42,
        epochs=9,
    )

    config = RLConfig(
        learning_rate=1e-5,
        dataset_builder=builder,
        model_name="Qwen/Qwen3-8B",
        lora_rank=32,
        max_tokens=900,
        temperature=0.7,
        log_path=log_path,
        eval_every=50,
        save_every=50,
        load_checkpoint_path=checkpoint,
        rollout_error_tolerance=True,
    )

    cli_utils.check_log_dir(log_path, behavior_if_exists="delete")
    await rl_main(config)


async def run_polynomial(condition: str, log_path: str, checkpoint: str | None = None):
    from src.spillover.env_polynomial import PolynomialDatasetBuilder

    penalty = -1.0 if condition != "control" else 0.0

    builder = PolynomialDatasetBuilder(
        batch_size=3,
        group_size=8,
        num_problems=2000,
        penalty_weight=penalty,
        seed=42,
        epochs=1,
    )

    config = RLConfig(
        learning_rate=1e-5,
        dataset_builder=builder,
        model_name="Qwen/Qwen3-8B",
        lora_rank=32,
        max_tokens=900,
        temperature=0.7,
        log_path=log_path,
        eval_every=100,
        save_every=100,
        load_checkpoint_path=checkpoint,
        rollout_error_tolerance=True,
    )

    cli_utils.check_log_dir(log_path, behavior_if_exists="delete")
    await rl_main(config)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, choices=["qa", "polynomial"])
    parser.add_argument("--condition", required=True)
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--log-path", default=None)
    args = parser.parse_args()

    log_path = args.log_path or f"/tmp/spillover-exps/paper-{args.task}-{args.condition}"
    logger.info(f"Running {args.task}/{args.condition} -> {log_path}")

    if args.task == "qa":
        await run_qa(args.condition, log_path, args.checkpoint)
    else:
        await run_polynomial(args.condition, log_path, args.checkpoint)


if __name__ == "__main__":
    asyncio.run(main())
