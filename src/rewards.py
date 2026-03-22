import asyncio
from dataclasses import dataclass, field

import numpy as np

from .judges import Judge
from .parsing import split_cot_output


@dataclass
class RewardComponent:
    judge: Judge
    target: str  # "cot", "output", or "full"
    weight: float = 1.0
    monitor_only: bool = False
    name: str = ""


@dataclass
class RewardSpec:
    components: list[RewardComponent] = field(default_factory=list)

    async def compute(self, cot: str, output: str) -> tuple[float, dict[str, float]]:
        reward = 0.0
        metrics: dict[str, float] = {}
        tasks = []
        for comp in self.components:
            text = {"cot": cot, "output": output, "full": cot + "\n" + output}[comp.target]
            tasks.append((comp, comp.judge.score(text)))

        scores = await asyncio.gather(*[t for _, t in tasks])
        for (comp, _), score in zip(tasks, scores):
            metrics[comp.name] = score
            if not comp.monitor_only:
                reward += comp.weight * score
        return reward, metrics

    async def compute_batch(
        self, responses: list[str]
    ) -> tuple[np.ndarray, dict[str, list[float]]]:
        rewards = np.zeros(len(responses))
        all_metrics: dict[str, list[float]] = {}

        tasks = []
        for response in responses:
            cot, output = split_cot_output(response)
            tasks.append(self.compute(cot, output))

        results = await asyncio.gather(*tasks)
        for i, (r, m) in enumerate(results):
            rewards[i] = r
            for k, v in m.items():
                all_metrics.setdefault(k, []).append(v)

        return rewards, all_metrics


def grpo_advantages(rewards: np.ndarray, group_size: int) -> np.ndarray:
    grouped = rewards.reshape(-1, group_size)
    centered = grouped - grouped.mean(axis=1, keepdims=True)
    std = grouped.std(axis=1, keepdims=True)
    std = np.where(std < 1e-8, 1.0, std)
    return (centered / std).flatten()


def reward_targeting_advantages(
    full_rewards: np.ndarray,
    task_only_rewards: np.ndarray,
    group_size: int,
    cot_lengths: list[int],
    total_lengths: list[int],
) -> list[np.ndarray]:
    """Per-token advantages: CoT tokens get task-only signal, output tokens get full signal."""
    full_adv = grpo_advantages(full_rewards, group_size)
    task_adv = grpo_advantages(task_only_rewards, group_size)

    per_token = []
    for i in range(len(full_rewards)):
        advs = np.zeros(total_lengths[i])
        advs[: cot_lengths[i]] = task_adv[i]
        advs[cot_lengths[i] :] = full_adv[i]
        per_token.append(advs)
    return per_token
