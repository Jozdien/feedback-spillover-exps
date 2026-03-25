"""Hard spillover with style reward to keep style alive during training."""

import asyncio
import json
import logging

import chz
from tinker_cookbook import cli_utils, model_info, renderers
from tinker_cookbook.rl.train import Config as RLConfig
from tinker_cookbook.rl.train import main as rl_main
from tinker_cookbook.rl.types import EnvGroupBuilder, Metrics, RLDataset, RLDatasetBuilder, Trajectory
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import Judge, hint_monitor_words, pirate_monitor, LanguageJudge
from src.parsing import split_cot_output
from src.spillover.env_hard import HardHintQADatasetBuilder, HardHintQADataset
from src.spillover.env import HintQAGroupBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StyledHintQAGroupBuilder(EnvGroupBuilder):
    """Wraps HintQAGroupBuilder, adding style reward + CoT hint monitoring."""

    def __init__(self, inner: HintQAGroupBuilder, style_judge: Judge,
                 style_weight: float, renderer: renderers.Renderer):
        self.inner = inner
        self.style_judge = style_judge
        self.style_weight = style_weight
        self.renderer = renderer

    async def make_envs(self):
        return self.inner.env_thunk and [self.inner.env_thunk() for _ in range(self.inner.num_envs)]

    async def compute_group_rewards(
        self, trajectory_group: list[Trajectory], env_group
    ) -> list[tuple[float, Metrics]]:
        import asyncio as aio
        cot_judge = hint_monitor_words()
        cots = []
        for traj in trajectory_group:
            last_action = traj.transitions[-1].ac
            parsed, _ = self.renderer.parse_response(last_action.tokens)
            cot, _ = split_cot_output(parsed["content"])
            cots.append(cot)

        cot_scores, style_scores = await aio.gather(
            aio.gather(*[cot_judge.score(c) for c in cots]),
            aio.gather(*[self.style_judge.score(c) for c in cots]),
        )
        return [
            (self.style_weight * ss, {"hint_in_cot": cs, "style_score": ss})
            for cs, ss in zip(cot_scores, style_scores)
        ]

    def logging_tags(self):
        return ["hint_qa"]


class StyledHardHintQADataset(RLDataset):
    def __init__(self, inner: HardHintQADataset, style_judge: Judge,
                 style_weight: float, renderer: renderers.Renderer):
        self.inner = inner
        self.style_judge = style_judge
        self.style_weight = style_weight
        self.renderer = renderer

    def get_batch(self, index):
        builders = self.inner.get_batch(index)
        return [
            StyledHintQAGroupBuilder(b, self.style_judge, self.style_weight, self.renderer)
            for b in builders
        ]

    def __len__(self):
        return len(self.inner)


class ConcisenessJudge(Judge):
    """Rewards concise CoT. Score = 1.0 if under target_tokens, drops linearly to 0."""

    def __init__(self, target_tokens: int = 200, max_tokens: int = 800):
        self.target = target_tokens
        self.max = max_tokens

    async def score(self, text: str) -> float:
        n = len(text.split())
        if n <= self.target:
            return 1.0
        if n >= self.max:
            return 0.0
        return 1.0 - (n - self.target) / (self.max - self.target)


def get_style_judge(style_name: str) -> Judge:
    if style_name == "pirate":
        return pirate_monitor()
    elif style_name == "chinese":
        return LanguageJudge("Chinese")
    elif style_name == "concise":
        return ConcisenessJudge(target_tokens=200, max_tokens=800)
    else:
        raise ValueError(f"Unknown style: {style_name}")


@chz.chz
class StyledHardSpilloverConfig:
    model_name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32
    batch_size: int = 32
    group_size: int = 8
    hint_penalty_weight: float = -1.0
    learning_rate: float = 4e-5
    max_tokens: int = 4096
    temperature: float = 0.7
    eval_every: int = 20
    save_every: int = 20
    epochs: int = 1
    seed: int = 0
    checkpoint: str | None = None
    log_path: str = "/tmp/spillover-exps/hard-spillover-styled"
    hard_questions_path: str = "data/hard_triviaqa.json"
    style_name: str = "pirate"
    style_weight: float = 0.5
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"


async def run(cli: StyledHardSpilloverConfig):
    logger.info(f"Config: {json.dumps(chz.asdict(cli), indent=2, default=str)}")

    renderer_name = model_info.get_recommended_renderer_name(cli.model_name)
    tokenizer = get_tokenizer(cli.model_name)
    renderer = renderers.get_renderer(renderer_name, tokenizer=tokenizer)
    style_judge = get_style_judge(cli.style_name)

    @chz.chz
    class _Builder(RLDatasetBuilder):
        async def __call__(self):
            inner_builder = HardHintQADatasetBuilder(
                batch_size=cli.batch_size,
                group_size=cli.group_size,
                model_name=cli.model_name,
                renderer_name=renderer_name,
                hard_questions_path=cli.hard_questions_path,
                hint_penalty_weight=cli.hint_penalty_weight,
                seed=cli.seed,
                epochs=cli.epochs,
            )
            train_inner, eval_inner = await inner_builder()
            train_ds = StyledHardHintQADataset(train_inner, style_judge, cli.style_weight, renderer)
            eval_ds = StyledHardHintQADataset(eval_inner, style_judge, cli.style_weight, renderer) if eval_inner else None
            return train_ds, eval_ds

    config = RLConfig(
        learning_rate=cli.learning_rate,
        dataset_builder=_Builder(),
        model_name=cli.model_name,
        lora_rank=cli.lora_rank,
        max_tokens=cli.max_tokens,
        temperature=cli.temperature,
        log_path=cli.log_path,
        eval_every=cli.eval_every,
        save_every=cli.save_every,
        load_checkpoint_path=cli.checkpoint,
        rollout_error_tolerance=True,
    )

    cli_utils.check_log_dir(cli.log_path, behavior_if_exists=cli.behavior_if_log_dir_exists)
    await rl_main(config)


if __name__ == "__main__":
    cli_config = chz.entrypoint(StyledHardSpilloverConfig)
    asyncio.run(run(cli_config))
