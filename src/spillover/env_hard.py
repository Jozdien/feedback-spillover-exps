"""Hard HintQA: uses correct answers as hints on questions the model can't answer."""

import json
import math
import random
from functools import partial
from typing import Sequence

import chz
from tinker_cookbook import renderers
from tinker_cookbook.rl.types import (
    EnvGroupBuilder,
    RLDataset,
    RLDatasetBuilder,
)
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import hint_monitor_words
from src.spillover.env import HintQAEnv, HintQAGroupBuilder


class HardHintQADataset(RLDataset):
    """Like HintQADataset but hint = correct answer (not random)."""

    def __init__(
        self,
        questions: list[dict],
        batch_size: int,
        group_size: int,
        renderer: renderers.Renderer,
        output_judge,
        hint_penalty_weight: float = -1.0,
        system_prompt: str | None = None,
        epochs: int = 1,
        seed: int = 0,
    ):
        self.questions = questions
        self.batch_size = batch_size
        self.group_size = group_size
        self.renderer = renderer
        self.output_judge = output_judge
        self.hint_penalty_weight = hint_penalty_weight
        self.system_prompt = system_prompt
        self.epochs = epochs
        self.rng = random.Random(seed)

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        start = (index * self.batch_size) % len(self.questions)
        end = min(start + self.batch_size, len(self.questions))
        builders = []
        for i in range(start, end):
            q = self.questions[i]
            builders.append(
                HintQAGroupBuilder(
                    env_thunk=partial(
                        HintQAEnv,
                        question=q["question"],
                        hint_answer=q["real_answer"],  # correct answer as hint
                        renderer=self.renderer,
                        output_judge=self.output_judge,
                        hint_penalty_weight=self.hint_penalty_weight,
                        system_prompt=self.system_prompt,
                    ),
                    num_envs=self.group_size,
                )
            )
        return builders

    def __len__(self) -> int:
        return math.ceil(len(self.questions) / self.batch_size) * self.epochs


@chz.chz
class HardHintQADatasetBuilder(RLDatasetBuilder):
    batch_size: int = 32
    group_size: int = 8
    model_name: str = "Qwen/Qwen3-8B"
    renderer_name: str = "qwen3"
    hard_questions_path: str = "data/hard_triviaqa.json"
    hint_penalty_weight: float = -1.0
    system_prompt: str | None = None
    eval_holdout: int = 50
    seed: int = 0
    epochs: int = 1

    async def __call__(self) -> tuple[HardHintQADataset, HardHintQADataset | None]:
        tokenizer = get_tokenizer(self.model_name)
        renderer = renderers.get_renderer(self.renderer_name, tokenizer=tokenizer)
        output_judge = hint_monitor_words()

        with open(self.hard_questions_path) as f:
            questions = json.load(f)

        rng = random.Random(self.seed)
        rng.shuffle(questions)

        eval_qs = questions[: self.eval_holdout]
        train_qs = questions[self.eval_holdout :]

        def make_ds(qs, bs, epochs, seed):
            return HardHintQADataset(
                questions=qs,
                batch_size=bs,
                group_size=self.group_size,
                renderer=renderer,
                output_judge=output_judge,
                hint_penalty_weight=self.hint_penalty_weight,
                system_prompt=self.system_prompt,
                epochs=epochs,
                seed=seed,
            )

        return (
            make_ds(train_qs, self.batch_size, self.epochs, self.seed),
            make_ds(eval_qs, self.eval_holdout, 1, self.seed + 1),
        )
