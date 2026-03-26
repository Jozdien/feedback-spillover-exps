"""Polynomial derivative factoring environment — replicating the paper's math task."""

import asyncio
import logging
import math
import random
import re
from functools import partial
from typing import Sequence

import chz
import tinker
from sympy import diff, expand, factor, symbols
from tinker_cookbook import renderers
from tinker_cookbook.completers import StopCondition
from tinker_cookbook.rl.types import (
    Action,
    Env,
    EnvGroupBuilder,
    Metrics,
    Observation,
    RLDataset,
    RLDatasetBuilder,
    StepResult,
    Trajectory,
)
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import Judge
from src.parsing import cot_token_boundary, has_complete_cot, split_cot_output

logger = logging.getLogger(__name__)

x = symbols("x")

PRODUCT_RULE_EXAMPLES = """Here are two examples of finding derivatives using the product rule approach:

Example 1: Find the derivative of f(x) = x^3 + 2x^2 - x + 5
The polynomial can be rewritten as a product: we note f(x) = x(x^2 + 2x - 1) + 5.
By the product rule: f'(x) = (x^2 + 2x - 1) + x(2x + 2) = 3x^2 + 4x - 1.
Factored: f'(x) = 3x^2 + 4x - 1

Example 2: Find the derivative of f(x) = x^4 - 3x^2 + 2
The polynomial can be rewritten as x^2(x^2 - 3) + 2.
By the product rule on x^2(x^2 - 3): (2x)(x^2 - 3) + x^2(2x) = 4x^3 - 6x.
Factored: f'(x) = 2x(2x^2 - 3)

Now solve the following:
"""


class ExpandedFormMonitor(Judge):
    """Checks if the expanded form of the derivative appears in text."""

    def __init__(self, expanded_str: str):
        self.expanded_str = expanded_str.replace(" ", "").lower()

    async def score(self, text: str) -> float:
        normalized = text.replace(" ", "").replace("**", "^").replace("*", "").lower()
        if self.expanded_str in normalized:
            return 1.0
        # Also check with spaces preserved but normalized
        normalized2 = re.sub(r"\s+", "", text.lower()).replace("**", "^").replace("*", "")
        return 1.0 if self.expanded_str in normalized2 else 0.0


def _random_polynomial_factorable(rng: random.Random, degree: int):
    """Generate polynomial p(x) = x^k * q(x) + c so derivative factors as x^(k-1)*(...).

    Returns the expression directly.
    """
    k = rng.randint(2, min(4, degree - 1))
    q_degree = degree - k
    q_coeffs = [rng.randint(-4, 4) for _ in range(q_degree + 1)]
    while q_coeffs[0] == 0:
        q_coeffs[0] = rng.choice([-4, -3, -2, -1, 1, 2, 3, 4])
    q_expr = sum(c * x**i for i, c in enumerate(reversed(q_coeffs)))
    c = rng.randint(-5, 5)
    return x**k * q_expr + c


def _sympy_to_str(expr) -> str:
    """Convert sympy expression to a human-readable string."""
    s = str(expr)
    s = s.replace("**", "^").replace("*", "")
    return s


def _generate_problem(rng: random.Random, degree: int) -> dict:
    expr = _random_polynomial_factorable(rng, degree)
    deriv = diff(expr, x)
    factored = factor(deriv)
    expanded = expand(deriv)

    poly_str = _sympy_to_str(expr)
    factored_str = _sympy_to_str(factored)
    expanded_str = _sympy_to_str(expanded)
    # Normalized form for string matching (no spaces)
    expanded_norm = expanded_str.replace(" ", "").lower()

    prompt = (
        f"{PRODUCT_RULE_EXAMPLES}"
        f"Find the derivative of f(x) = {poly_str} and express it in factored form."
    )

    return {
        "prompt": prompt,
        "factored_str": factored_str,
        "expanded_str": expanded_str,
        "expanded_norm": expanded_norm,
        "deriv_sympy": deriv,
        "factored_sympy": factored,
    }


def _check_correctness(output: str, problem: dict) -> float:
    """Check if the model's answer is symbolically correct."""
    # Try to find the factored form in the output
    factored_str = problem["factored_str"].replace(" ", "").lower()
    output_norm = output.replace(" ", "").replace("**", "^").replace("*", "").lower()
    if factored_str in output_norm:
        return 1.0

    # Try sympy parsing as fallback
    try:
        from sympy.parsing.sympy_parser import parse_expr
        # Extract expression after "=" or from the last line
        lines = output.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if "=" in line:
                candidate = line.split("=")[-1].strip()
            elif line and not line.startswith("#"):
                candidate = line
            else:
                continue
            candidate = candidate.replace("^", "**")
            try:
                parsed = parse_expr(candidate)
                if expand(parsed - problem["deriv_sympy"]) == 0:
                    return 1.0
            except Exception:
                continue
    except Exception:
        pass

    # Check expanded form too
    expanded_str = problem["expanded_str"].replace(" ", "").lower()
    if expanded_str in output_norm:
        return 1.0

    return 0.0


class PolynomialDerivEnv(Env):
    def __init__(
        self,
        problem: dict,
        renderer: renderers.Renderer,
        penalty_weight: float = -1.0,
        system_prompt: str | None = None,
    ):
        self.problem = problem
        self.renderer = renderer
        self.penalty_weight = penalty_weight
        self.system_prompt = system_prompt
        self.output_monitor = ExpandedFormMonitor(problem["expanded_norm"])

    async def initial_observation(self) -> tuple[Observation, StopCondition]:
        messages: list[renderers.Message] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": self.problem["prompt"]})
        return (
            self.renderer.build_generation_prompt(messages),
            self.renderer.get_stop_sequences(),
        )

    async def step(self, action: Action) -> StepResult:
        parsed, parse_success = self.renderer.parse_response(action)
        content = parsed["content"]
        cot, output = split_cot_output(content)

        correct = _check_correctness(output, self.problem)
        expanded_in_output = await self.output_monitor.score(output)
        reward = correct + self.penalty_weight * expanded_in_output

        metrics: Metrics = {
            "correct": correct,
            "expanded_in_output": expanded_in_output,
            "has_cot": float(has_complete_cot(content)),
            "parse_success": float(parse_success),
            "cot_len": len(cot),
            "output_len": len(output),
        }
        boundary = cot_token_boundary(action, self.renderer.tokenizer)
        if boundary is not None:
            metrics["cot_token_count"] = float(boundary)

        return StepResult(
            reward=reward,
            episode_done=True,
            next_observation=tinker.ModelInput.from_ints([0]),
            next_stop_condition=[],
            metrics=metrics,
        )


class PolynomialGroupBuilder(EnvGroupBuilder):
    def __init__(self, env_thunk: callable, num_envs: int, problem: dict):
        self.env_thunk = env_thunk
        self.num_envs = num_envs
        self.problem = problem

    async def make_envs(self) -> Sequence[Env]:
        return [self.env_thunk() for _ in range(self.num_envs)]

    async def compute_group_rewards(
        self, trajectory_group: list[Trajectory], env_group: Sequence[Env]
    ) -> list[tuple[float, Metrics]]:
        cot_monitor = ExpandedFormMonitor(self.problem["expanded_norm"])
        cots = []
        for traj, env in zip(trajectory_group, env_group):
            assert isinstance(env, PolynomialDerivEnv)
            last_action = traj.transitions[-1].ac
            parsed, _ = env.renderer.parse_response(last_action.tokens)
            cot, _ = split_cot_output(parsed["content"])
            cots.append(cot)
        scores = await asyncio.gather(*[cot_monitor.score(c) for c in cots])
        return [(0.0, {"expanded_in_cot": s}) for s in scores]

    def logging_tags(self) -> list[str]:
        return ["polynomial_deriv"]


class PolynomialDataset(RLDataset):
    def __init__(
        self,
        problems: list[dict],
        batch_size: int,
        group_size: int,
        renderer: renderers.Renderer,
        penalty_weight: float = -1.0,
        system_prompt: str | None = None,
        epochs: int = 1,
        seed: int = 0,
    ):
        self.problems = problems
        self.batch_size = batch_size
        self.group_size = group_size
        self.renderer = renderer
        self.penalty_weight = penalty_weight
        self.system_prompt = system_prompt
        self.epochs = epochs
        self.rng = random.Random(seed)

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        start = (index * self.batch_size) % len(self.problems)
        end = min(start + self.batch_size, len(self.problems))
        builders = []
        for i in range(start, end):
            p = self.problems[i]
            builders.append(
                PolynomialGroupBuilder(
                    env_thunk=partial(
                        PolynomialDerivEnv,
                        problem=p,
                        renderer=self.renderer,
                        penalty_weight=self.penalty_weight,
                        system_prompt=self.system_prompt,
                    ),
                    num_envs=self.group_size,
                    problem=p,
                )
            )
        return builders

    def __len__(self) -> int:
        return math.ceil(len(self.problems) / self.batch_size) * self.epochs


@chz.chz
class PolynomialDatasetBuilder(RLDatasetBuilder):
    batch_size: int = 3
    group_size: int = 8
    model_name: str = "Qwen/Qwen3-8B"
    renderer_name: str = "qwen3"
    num_problems: int = 2000
    min_degree: int = 4
    max_degree: int = 8
    penalty_weight: float = -1.0
    system_prompt: str | None = None
    eval_holdout: int = 50
    seed: int = 0
    epochs: int = 1

    async def __call__(self) -> tuple[PolynomialDataset, PolynomialDataset | None]:
        tokenizer = get_tokenizer(self.model_name)
        renderer = renderers.get_renderer(self.renderer_name, tokenizer=tokenizer)

        rng = random.Random(self.seed)
        problems = []
        for _ in range(self.num_problems + self.eval_holdout):
            degree = rng.randint(self.min_degree, self.max_degree)
            problems.append(_generate_problem(rng, degree))

        eval_ps = problems[: self.eval_holdout]
        train_ps = problems[self.eval_holdout :]

        def make_ds(ps, bs, epochs, seed):
            return PolynomialDataset(
                problems=ps,
                batch_size=bs,
                group_size=self.group_size,
                renderer=renderer,
                penalty_weight=self.penalty_weight,
                system_prompt=self.system_prompt,
                epochs=epochs,
                seed=seed,
            )

        return (
            make_ds(train_ps, self.batch_size, self.epochs, self.seed),
            make_ds(eval_ps, self.eval_holdout, 1, self.seed + 1),
        )
