"""Multi-task RL: enforce style + correctness across GSM8K, MATH, MMLU, GPQA.

Alternates batches between tasks (round-robin). Evaluates on all benchmarks
periodically. Stops when style >= target AND performance >= baseline - threshold.
"""

import asyncio
import json
import logging
import math
import random
import re
from collections.abc import Sequence
from functools import partial
from typing import Literal

import chz
from datasets import load_dataset
from tinker_cookbook import cli_utils, renderers
from tinker_cookbook.recipes.math_rl.math_env import (
    Gsm8kDataset,
    MathDataset,
    extract_boxed,
)
from tinker_cookbook.rl.problem_env import ProblemEnv, ProblemGroupBuilder
from tinker_cookbook.rl.train import Config as RLConfig
from tinker_cookbook.rl.train import main as rl_main
from tinker_cookbook.rl.types import (
    EnvGroupBuilder,
    Metrics,
    RLDataset,
    RLDatasetBuilder,
    Trajectory,
)
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import Judge
from src.parsing import split_cot_output
from src.style.generate_data import get_style_judge

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MCQ Environment (for MMLU / GPQA)
# ---------------------------------------------------------------------------

class MCQEnv(ProblemEnv):
    def __init__(
        self,
        question: str,
        correct_letter: str,
        renderer: renderers.Renderer,
        convo_prefix: list[renderers.Message] | None = None,
    ):
        super().__init__(renderer, convo_prefix)
        self.question = question
        self.correct_letter = correct_letter

    @classmethod
    def question_suffix(cls) -> str:
        return " Answer with just the letter (A, B, C, or D) inside \\boxed{}."

    def get_question(self) -> str:
        return self.question + self.question_suffix()

    def check_format(self, sample_str: str) -> bool:
        try:
            extract_boxed(sample_str)
            return True
        except ValueError:
            return False

    def check_answer(self, sample_str: str) -> bool:
        try:
            given = extract_boxed(sample_str)
            if self.correct_letter.upper() in given.upper():
                return True
        except ValueError:
            pass
        patterns = [
            rf"(?:answer|choice)\s*(?:is|:)\s*\(?{re.escape(self.correct_letter)}\)?",
            rf"\\boxed\{{{re.escape(self.correct_letter)}",
        ]
        for p in patterns:
            if re.search(p, sample_str, re.IGNORECASE):
                return True
        return False

    def get_reference_answer(self) -> str:
        return self.correct_letter


# ---------------------------------------------------------------------------
# MCQ Datasets
# ---------------------------------------------------------------------------

class MMLUDataset(RLDataset):
    def __init__(
        self,
        batch_size: int,
        group_size: int,
        renderer: renderers.Renderer,
        split: Literal["train", "test"] = "train",
        seed: int = 0,
    ):
        letters = ["A", "B", "C", "D"]
        if split == "test":
            raw = load_dataset("cais/mmlu", "all", split="test")
        else:
            raw = load_dataset("cais/mmlu", "all", split="auxiliary_train")
        self.items = []
        for row in raw:
            choices = row["choices"]
            q = row["question"] + "\n" + "\n".join(
                f"{letters[i]}) {choices[i]}" for i in range(len(choices))
            )
            self.items.append({"question": q, "answer": letters[row["answer"]]})
        if split == "train":
            rng = random.Random(seed)
            rng.shuffle(self.items)
        self.batch_size = batch_size
        self.group_size = group_size if split == "train" else 1
        self.renderer = renderer

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        start = index * self.batch_size
        end = min(start + self.batch_size, len(self.items))
        assert start < end
        builders = []
        for item in self.items[start:end]:
            builders.append(ProblemGroupBuilder(
                env_thunk=partial(
                    MCQEnv, item["question"], item["answer"], self.renderer
                ),
                num_envs=self.group_size,
                dataset_name="mmlu",
            ))
        return builders

    def __len__(self) -> int:
        return math.ceil(len(self.items) / self.batch_size)


class GPQADataset(RLDataset):
    def __init__(
        self,
        batch_size: int,
        group_size: int,
        renderer: renderers.Renderer,
        seed: int = 0,
    ):
        raw = load_dataset("Idavidrein/gpqa", "gpqa_main", split="train")
        letters = ["A", "B", "C", "D"]
        self.items = []
        for row in raw:
            choices = [
                row["Correct Answer"],
                row["Incorrect Answer 1"],
                row["Incorrect Answer 2"],
                row["Incorrect Answer 3"],
            ]
            rng = random.Random(hash(row["Question"]))
            order = list(range(4))
            rng.shuffle(order)
            shuffled = [choices[i] for i in order]
            correct_letter = letters[order.index(0)]
            q = row["Question"] + "\n" + "\n".join(
                f"{letters[i]}) {shuffled[i]}" for i in range(4)
            )
            self.items.append({"question": q, "answer": correct_letter})

        rng2 = random.Random(seed)
        rng2.shuffle(self.items)
        self.batch_size = batch_size
        self.group_size = group_size
        self.renderer = renderer

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        start = (index * self.batch_size) % len(self.items)
        end = min(start + self.batch_size, len(self.items))
        builders = []
        for item in self.items[start:end]:
            builders.append(ProblemGroupBuilder(
                env_thunk=partial(
                    MCQEnv, item["question"], item["answer"], self.renderer
                ),
                num_envs=self.group_size,
                dataset_name="gpqa",
            ))
        return builders

    def __len__(self) -> int:
        return math.ceil(len(self.items) / self.batch_size)


# ---------------------------------------------------------------------------
# Style-wrapped group builder (adds style reward)
# ---------------------------------------------------------------------------

class StyledGroupBuilder(EnvGroupBuilder):
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


# ---------------------------------------------------------------------------
# Multi-task dataset: round-robin across tasks
# ---------------------------------------------------------------------------

class MultiTaskDataset(RLDataset):
    def __init__(
        self,
        datasets: list[RLDataset],
        style_judge: Judge,
        style_weight: float,
        renderer: renderers.Renderer,
    ):
        self.datasets = datasets
        self.style_judge = style_judge
        self.style_weight = style_weight
        self.renderer = renderer
        self._indices = [0] * len(datasets)

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        ds_idx = index % len(self.datasets)
        ds = self.datasets[ds_idx]
        inner_idx = self._indices[ds_idx] % len(ds)
        self._indices[ds_idx] += 1
        inner_builders = ds.get_batch(inner_idx)
        return [
            StyledGroupBuilder(b, self.style_judge, self.style_weight, self.renderer)
            for b in inner_builders
        ]

    def __len__(self) -> int:
        return sum(len(ds) for ds in self.datasets)


@chz.chz
class MultiTaskDatasetBuilder(RLDatasetBuilder):
    model_name: str = "Qwen/Qwen3-8B"
    renderer_name: str = "qwen3"
    batch_size: int = 16
    group_size: int = 8
    style_name: str = "chinese"
    style_weight: float = 0.5
    tasks: tuple[str, ...] = ("gsm8k", "math", "mmlu", "gpqa")
    seed: int = 0

    async def __call__(self) -> tuple[MultiTaskDataset, MultiTaskDataset | None]:
        tokenizer = get_tokenizer(self.model_name)
        renderer = renderers.get_renderer(self.renderer_name, tokenizer=tokenizer)
        style_judge = get_style_judge(self.style_name)

        train_datasets = []
        eval_datasets = []
        for task in self.tasks:
            if task == "gsm8k":
                train_datasets.append(Gsm8kDataset(
                    batch_size=self.batch_size, group_size=self.group_size,
                    renderer=renderer, split="train", seed=self.seed,
                ))
                eval_datasets.append(Gsm8kDataset(
                    batch_size=self.batch_size, group_size=1,
                    renderer=renderer, split="test", seed=self.seed,
                ))
            elif task == "math":
                train_datasets.append(MathDataset(
                    batch_size=self.batch_size, group_size=self.group_size,
                    renderer=renderer, split="train", seed=self.seed,
                ))
                eval_datasets.append(MathDataset(
                    batch_size=self.batch_size, group_size=1,
                    renderer=renderer, split="test", seed=self.seed,
                ))
            elif task == "mmlu":
                train_datasets.append(MMLUDataset(
                    batch_size=self.batch_size, group_size=self.group_size,
                    renderer=renderer, split="train", seed=self.seed,
                ))
                eval_datasets.append(MMLUDataset(
                    batch_size=self.batch_size, group_size=1,
                    renderer=renderer, split="test", seed=self.seed,
                ))
            elif task == "gpqa":
                train_datasets.append(GPQADataset(
                    batch_size=self.batch_size, group_size=self.group_size,
                    renderer=renderer, seed=self.seed,
                ))

        train = MultiTaskDataset(train_datasets, style_judge, self.style_weight, renderer)
        eval_ds = MultiTaskDataset(eval_datasets, style_judge, self.style_weight, renderer) if eval_datasets else None
        return train, eval_ds


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@chz.chz
class MultiTaskRLConfig:
    model_name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32
    style_name: str = "chinese"
    style_weight: float = 0.5
    tasks: tuple[str, ...] = ("gsm8k", "math", "mmlu", "gpqa")
    batch_size: int = 16
    group_size: int = 8
    learning_rate: float = 4e-5
    max_tokens: int = 4096
    temperature: float = 0.7
    eval_every: int = 20
    save_every: int = 20
    max_steps: int | None = None
    seed: int = 0
    log_path: str = "/tmp/spillover-exps/rl-multi-task"
    load_checkpoint_path: str | None = None
    wandb_project: str | None = None
    wandb_name: str | None = None
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"


async def run(cli: MultiTaskRLConfig):
    logger.info(f"Multi-task RL config: {json.dumps(chz.asdict(cli), indent=2, default=str)}")

    renderer_name = "qwen3"

    dataset_builder = MultiTaskDatasetBuilder(
        model_name=cli.model_name,
        renderer_name=renderer_name,
        batch_size=cli.batch_size,
        group_size=cli.group_size,
        style_name=cli.style_name,
        style_weight=cli.style_weight,
        tasks=cli.tasks,
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
        rollout_error_tolerance=True,
        max_steps=cli.max_steps,
    )

    cli_utils.check_log_dir(cli.log_path, behavior_if_exists=cli.behavior_if_log_dir_exists)
    await rl_main(config)


if __name__ == "__main__":
    cli_config = chz.entrypoint(MultiTaskRLConfig)
    asyncio.run(run(cli_config))
