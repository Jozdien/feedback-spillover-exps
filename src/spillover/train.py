"""Standard spillover training: RL with output hint penalty."""

import asyncio
import json
import logging

import chz
from tinker_cookbook import cli_utils, model_info
from tinker_cookbook.rl.train import Config as RLConfig
from tinker_cookbook.rl.train import main as rl_main

from src.spillover.env import HintQADatasetBuilder

logger = logging.getLogger(__name__)


@chz.chz
class SpilloverCLIConfig:
    model_name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32
    batch_size: int = 32
    group_size: int = 8
    num_questions: int = 500
    hint_penalty_weight: float = -1.0
    system_prompt: str | None = None
    learning_rate: float = 4e-5
    max_tokens: int = 4096
    temperature: float = 0.7
    eval_every: int = 20
    save_every: int = 20
    epochs: int = 1
    seed: int = 0
    log_path: str = "/tmp/spillover-exps/spillover-baseline"
    wandb_project: str | None = None
    wandb_name: str | None = None
    load_checkpoint_path: str | None = None
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"


async def run_spillover(cli: SpilloverCLIConfig):
    logger.info(f"Spillover config: {json.dumps(chz.asdict(cli), indent=2, default=str)}")

    dataset_builder = HintQADatasetBuilder(
        batch_size=cli.batch_size,
        group_size=cli.group_size,
        model_name=cli.model_name,
        renderer_name=model_info.get_recommended_renderer_name(cli.model_name),
        num_questions=cli.num_questions,
        hint_penalty_weight=cli.hint_penalty_weight,
        system_prompt=cli.system_prompt,
        seed=cli.seed,
        epochs=cli.epochs,
    )

    config = RLConfig(
        learning_rate=cli.learning_rate,
        dataset_builder=dataset_builder,
        model_name=cli.model_name,
        lora_rank=cli.lora_rank,
        max_tokens=cli.max_tokens,
        temperature=cli.temperature,
        wandb_project=cli.wandb_project,
        wandb_name=cli.wandb_name,
        log_path=cli.log_path,
        eval_every=cli.eval_every,
        save_every=cli.save_every,
        load_checkpoint_path=cli.load_checkpoint_path,
    )

    cli_utils.check_log_dir(cli.log_path, behavior_if_exists=cli.behavior_if_log_dir_exists)
    await rl_main(config)


if __name__ == "__main__":
    cli_config = chz.entrypoint(SpilloverCLIConfig)
    asyncio.run(run_spillover(cli_config))
