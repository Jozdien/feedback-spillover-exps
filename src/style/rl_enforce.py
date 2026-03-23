"""RL to solidify style + correctness after SFT. Adds style reward to math task."""

import asyncio
import json
import logging
from typing import Sequence

import chz
from tinker_cookbook import cli_utils, model_info, renderers
from tinker_cookbook.rl.problem_env import ProblemGroupBuilder
from tinker_cookbook.rl.train import Config as RLConfig
from tinker_cookbook.rl.train import main as rl_main
from tinker_cookbook.rl.types import (
    EnvGroupBuilder,
    Metrics,
    RLDataset,
    RLDatasetBuilder,
    Trajectory,
)
from tinker_cookbook.recipes.math_rl.math_env import Gsm8kDatasetBuilder
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import Judge
from src.parsing import split_cot_output
from src.style.generate_data import get_style_judge

logger = logging.getLogger(__name__)


class StyledGroupBuilder(EnvGroupBuilder):
    """Wraps a ProblemGroupBuilder, adding style reward in compute_group_rewards."""

    def __init__(
        self,
        inner: ProblemGroupBuilder,
        style_judge: Judge,
        style_weight: float,
        renderer: renderers.Renderer,
    ):
        self.inner = inner
        self.style_judge = style_judge
        self.style_weight = style_weight
        self.renderer = renderer

    async def make_envs(self):
        return await self.inner.make_envs()

    async def compute_group_rewards(
        self, trajectory_group: list[Trajectory], env_group
    ) -> list[tuple[float, Metrics]]:
        results = []
        for traj in trajectory_group:
            last_action = traj.transitions[-1].ac
            parsed, _ = self.renderer.parse_response(last_action.tokens)
            cot, _ = split_cot_output(parsed["content"])
            style_score = await self.style_judge.score(cot)
            results.append((
                self.style_weight * style_score,
                {"style_score": style_score},
            ))
        return results

    def logging_tags(self) -> list[str]:
        return self.inner.logging_tags()


class StyledMathDataset(RLDataset):
    """Wraps a math dataset to add style reward scoring."""

    def __init__(
        self,
        inner: RLDataset,
        style_judge: Judge,
        style_weight: float,
        renderer: renderers.Renderer,
    ):
        self.inner = inner
        self.style_judge = style_judge
        self.style_weight = style_weight
        self.renderer = renderer

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        inner_builders = self.inner.get_batch(index)
        return [
            StyledGroupBuilder(b, self.style_judge, self.style_weight, self.renderer)
            for b in inner_builders
        ]

    def __len__(self) -> int:
        return len(self.inner)


@chz.chz
class StyledMathDatasetBuilder(RLDatasetBuilder):
    model_name: str = "Qwen/Qwen3-8B"
    renderer_name: str = "qwen3"
    batch_size: int = 32
    group_size: int = 8
    style_name: str = "chinese"
    style_weight: float = 0.5
    seed: int = 0

    async def __call__(self) -> tuple[StyledMathDataset, StyledMathDataset | None]:
        tokenizer = get_tokenizer(self.model_name)
        renderer = renderers.get_renderer(self.renderer_name, tokenizer=tokenizer)
        style_judge = get_style_judge(self.style_name)

        inner_builder = Gsm8kDatasetBuilder(
            batch_size=self.batch_size,
            group_size=self.group_size,
            model_name_for_tokenizer=self.model_name,
            renderer_name=self.renderer_name,
            seed=self.seed,
        )
        train_ds, eval_ds = await inner_builder()

        train_styled = StyledMathDataset(train_ds, style_judge, self.style_weight, renderer)
        eval_styled = (
            StyledMathDataset(eval_ds, style_judge, self.style_weight, renderer)
            if eval_ds
            else None
        )
        return train_styled, eval_styled


@chz.chz
class StyleRLConfig:
    model_name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32
    style_name: str = "chinese"
    style_weight: float = 0.5
    batch_size: int = 32
    group_size: int = 8
    learning_rate: float = 4e-5
    max_tokens: int = 4096
    temperature: float = 0.7
    eval_every: int = 10
    save_every: int = 10
    seed: int = 0
    log_path: str = "/tmp/spillover-exps/style-chinese-rl"
    load_checkpoint_path: str | None = None
    wandb_project: str | None = None
    wandb_name: str | None = None
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"


async def run_style_rl(cli: StyleRLConfig):
    logger.info(f"Style RL config: {json.dumps(chz.asdict(cli), indent=2, default=str)}")

    renderer_name = model_info.get_recommended_renderer_name(cli.model_name)

    dataset_builder = StyledMathDatasetBuilder(
        model_name=cli.model_name,
        renderer_name=renderer_name,
        batch_size=cli.batch_size,
        group_size=cli.group_size,
        style_name=cli.style_name,
        style_weight=cli.style_weight,
        seed=cli.seed,
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
    cli_config = chz.entrypoint(StyleRLConfig)
    asyncio.run(run_style_rl(cli_config))
