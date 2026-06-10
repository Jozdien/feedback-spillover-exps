"""SFT on styled CoT data to bake the style into the model's default behavior.

IMPORTANT: Must use Qwen3Renderer with strip_thinking_from_history=False,
otherwise the renderer strips the CoT (everything before </think>) from the
training data, and the model only learns to produce the English output.
"""

import asyncio
import json
import logging

import chz
import datasets
from tinker_cookbook import cli_utils, renderers
from tinker_cookbook.supervised.data import SupervisedDatasetFromHFDataset, conversation_to_datum
from tinker_cookbook.supervised.train import Config as SFTConfig
from tinker_cookbook.supervised.train import main as sft_main
from tinker_cookbook.supervised.types import SupervisedDatasetBuilder
from tinker_cookbook.tokenizer_utils import get_tokenizer

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
    log_path: str = "logs/sft"
    load_checkpoint_path: str | None = None
    max_steps: int | None = None
    max_samples: int | None = None
    wandb_project: str | None = None
    wandb_name: str | None = None
    save_every: int = 20
    eval_every: int = 10
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"


@chz.chz
class StyleSFTDatasetBuilder(SupervisedDatasetBuilder):
    """Custom builder that uses Qwen3Renderer with strip_thinking_from_history=False."""

    model_name: str
    file_path: str
    batch_size: int
    max_length: int
    test_size: int = 50
    max_samples: int | None = None

    def __call__(self):
        tokenizer = get_tokenizer(self.model_name)
        from tinker_cookbook.renderers.qwen3 import Qwen3Renderer
        renderer = Qwen3Renderer(tokenizer, strip_thinking_from_history=False)

        conversations = []
        with open(self.file_path) as f:
            for line in f:
                conversations.append(json.loads(line.strip()))
        ds = datasets.Dataset.from_list(conversations)
        ds = ds.shuffle(seed=0)
        if self.max_samples and len(ds) > self.max_samples + self.test_size:
            ds = ds.select(range(self.max_samples + self.test_size))

        test_ds = ds.take(self.test_size) if self.test_size > 0 else None
        train_ds = ds.skip(self.test_size) if self.test_size > 0 else ds

        def map_fn(row):
            return conversation_to_datum(
                row["messages"], renderer, self.max_length,
                renderers.TrainOnWhat.ALL_ASSISTANT_MESSAGES,
            )

        train = SupervisedDatasetFromHFDataset(train_ds, self.batch_size, map_fn=map_fn)
        test = SupervisedDatasetFromHFDataset(test_ds, len(test_ds), map_fn=map_fn) if test_ds else None
        return train, test


async def run_style_sft(cli: StyleSFTConfig):
    logger.info(f"Style SFT config: {json.dumps(chz.asdict(cli), indent=2, default=str)}")

    dataset_builder = StyleSFTDatasetBuilder(
        model_name=cli.model_name,
        file_path=cli.data_path,
        batch_size=cli.batch_size,
        max_length=cli.max_length,
        test_size=cli.test_size,
        max_samples=cli.max_samples,
    )

    config = SFTConfig(
        model_name=cli.model_name,
        recipe_name="style-sft",
        lora_rank=cli.lora_rank,
        dataset_builder=dataset_builder,
        learning_rate=cli.learning_rate,
        num_epochs=cli.num_epochs,
        log_path=cli.log_path,
        wandb_project=cli.wandb_project,
        wandb_name=cli.wandb_name,
        save_every=cli.save_every,
        eval_every=cli.eval_every,
        load_checkpoint_path=cli.load_checkpoint_path,
        max_steps=cli.max_steps,
    )

    cli_utils.check_log_dir(cli.log_path, behavior_if_exists=cli.behavior_if_log_dir_exists)
    await sft_main(config)


if __name__ == "__main__":
    cli_config = chz.entrypoint(StyleSFTConfig)
    asyncio.run(run_style_sft(cli_config))
