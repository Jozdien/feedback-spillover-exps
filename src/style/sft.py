"""SFT on styled CoT data to bake the style into the model's default behavior."""

import asyncio
import json
import logging

import chz
from tinker_cookbook import cli_utils, model_info, renderers
from tinker_cookbook.supervised.data import FromConversationFileBuilder
from tinker_cookbook.supervised.train import Config as SFTConfig
from tinker_cookbook.supervised.train import main as sft_main
from tinker_cookbook.supervised.types import ChatDatasetBuilderCommonConfig

logger = logging.getLogger(__name__)


@chz.chz
class StyleSFTConfig:
    model_name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32
    data_path: str = "data/style-chinese/filtered.jsonl"
    learning_rate: float = 1e-4
    num_epochs: int = 4
    batch_size: int = 128
    max_length: int = 8192
    test_size: int = 50
    log_path: str = "/tmp/spillover-exps/style-chinese-sft"
    wandb_project: str | None = None
    wandb_name: str | None = None
    save_every: int = 20
    eval_every: int = 10
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"


async def run_style_sft(cli: StyleSFTConfig):
    logger.info(f"Style SFT config: {json.dumps(chz.asdict(cli), indent=2, default=str)}")

    renderer_name = model_info.get_recommended_renderer_name(cli.model_name)

    dataset_builder = FromConversationFileBuilder(
        file_path=cli.data_path,
        test_size=cli.test_size,
        common_config=ChatDatasetBuilderCommonConfig(
            model_name_for_tokenizer=cli.model_name,
            renderer_name=renderer_name,
            max_length=cli.max_length,
            batch_size=cli.batch_size,
            train_on_what=renderers.TrainOnWhat.ALL_ASSISTANT_MESSAGES,
        ),
    )

    config = SFTConfig(
        model_name=cli.model_name,
        lora_rank=cli.lora_rank,
        dataset_builder=dataset_builder,
        learning_rate=cli.learning_rate,
        num_epochs=cli.num_epochs,
        log_path=cli.log_path,
        wandb_project=cli.wandb_project,
        wandb_name=cli.wandb_name,
        save_every=cli.save_every,
        eval_every=cli.eval_every,
    )

    cli_utils.check_log_dir(cli.log_path, behavior_if_exists=cli.behavior_if_log_dir_exists)
    await sft_main(config)


if __name__ == "__main__":
    cli_config = chz.entrypoint(StyleSFTConfig)
    asyncio.run(run_style_sft(cli_config))
