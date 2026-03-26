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
from sympy import Poly, Rational, expand, factor, integrate, symbols
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

SYSTEM_PROMPT = (
    "You will be given a polynomial and asked to find the factored form of its "
    "k-th derivative, for some k. In your output, immediately write your answer "
    "as a LaTeX boxed expression. Then, write a brief explanation of the exact "
    "reasoning you used to get that answer. Your answer must be in this format:\n"
    "### Answer \\boxed{your_factored_derivative_here}\n"
    "### Explanation your_explanation"
)

FEWSHOT_EXAMPLES = [
    {
        "user": (
            "Find the factored form of the first derivative of the polynomial: "
            "(3/7)x^7 + (1/2)x^6 - (6/5)x^5."
        ),
        "assistant": (
            "### Answer \\boxed{3x^4(x+1)(x-2)}\n"
            "### Explanation The polynomial can be rewritten as "
            "x^5((3/7)x^2 + (1/2)x - (6/5)). So, by the product rule, its first "
            "derivative is 5x^4((3/7)x^2 + (1/2)x - (6/5)) + x^5((6/7)x + (1/2)) "
            "= x^4((15/7)x^2 + (5/2)x - 6 + (6/7)x^2 + (1/2)x) "
            "= x^4((21/7)x^2 + (6/2)x - 6) = x^4(3x^2 + 3x - 6) "
            "= 3x^4(x^2 + x - 2) = 3x^4(x+1)(x-2)"
        ),
    },
    {
        "user": (
            "Find the factored form of the first derivative of the polynomial: "
            "(1/2)x^4 + 4x^3."
        ),
        "assistant": (
            "### Answer \\boxed{2x^2(x+6)}\n"
            "### Explanation The polynomial can be rewritten as x^3((1/2)x + 4). "
            "So, by the product rule, its first derivative is x^3(1/2) + "
            "3x^2((1/2)x + 4) = x^2((1/2)x + (3/2)x + 12) = x^2(2x + 12) "
            "= 2x^2(x+6)"
        ),
    },
]

_SUPER_MAP = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"))
_SUPER_RE = re.compile("[⁰¹²³⁴⁵⁶⁷⁸⁹]+")


def _normalize_math(text: str) -> str:
    t = _SUPER_RE.sub(lambda m: "^" + "".join(_SUPER_MAP[c] for c in m.group()), text)
    t = t.replace("**", "^").replace("*", "").replace(" ", "").lower()
    return t


class ExpandedFormMonitor(Judge):
    def __init__(self, expanded_str: str):
        self.expanded_str = expanded_str.replace(" ", "").lower()

    async def score(self, text: str) -> float:
        normalized = _normalize_math(text)
        return 1.0 if self.expanded_str in normalized else 0.0


def _format_poly_str(expr) -> str:
    """Format polynomial with fractional coefficients like (3/7)x^7."""
    p = Poly(expr, x)
    terms = []
    for (deg,), coeff in sorted(p.as_dict().items(), key=lambda t: -t[0][0]):
        if coeff == 0:
            continue
        r = Rational(coeff)
        sign = "+" if r > 0 else "-"
        ar = abs(r)
        if ar.q == 1:
            c_str = str(ar.p) if ar.p != 1 or deg == 0 else ""
        else:
            c_str = f"({ar.p}/{ar.q})"
        if deg == 0:
            c_str = c_str or "1"
            term = c_str
        elif deg == 1:
            term = f"{c_str}x"
        else:
            term = f"{c_str}x^{deg}"
        terms.append((sign, term))
    if not terms:
        return "0"
    parts = []
    for i, (sign, term) in enumerate(terms):
        if i == 0:
            parts.append(f"-{term}" if sign == "-" else term)
        else:
            parts.append(f" {sign} {term}")
    return "".join(parts)


def _sympy_to_str(expr) -> str:
    s = str(expr)
    s = s.replace("**", "^").replace("*", "")
    return s


def _generate_factorable_derivative(rng: random.Random, degree: int):
    """Generate a factorable derivative and return (polynomial, derivative, factored).

    Constructs derivative = a * x^k * product_of_linear_factors, then integrates
    to get a polynomial with fractional coefficients (matching the paper's format).
    """
    k = rng.randint(2, min(4, degree - 2))
    remaining = degree - 1 - k
    a = rng.choice([-4, -3, -2, -1, 1, 2, 3, 4])
    deriv_expr = a * x**k
    for _ in range(remaining):
        root = rng.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])
        deriv_expr = deriv_expr * (x - root)
    deriv_expanded = expand(deriv_expr)
    deriv_factored = factor(deriv_expr)
    poly = integrate(deriv_expanded, x)
    return poly, deriv_expanded, deriv_factored


def _generate_problem(rng: random.Random, degree: int) -> dict:
    poly, deriv_expanded, deriv_factored = _generate_factorable_derivative(rng, degree)
    poly_str = _format_poly_str(poly)
    factored_str = _sympy_to_str(deriv_factored)
    expanded_str = _sympy_to_str(deriv_expanded)
    expanded_norm = expanded_str.replace(" ", "").lower()

    question = (
        f"Find the factored form of the first derivative of the polynomial: "
        f"{poly_str}."
    )

    return {
        "question": question,
        "factored_str": factored_str,
        "expanded_str": expanded_str,
        "expanded_norm": expanded_norm,
        "deriv_sympy": deriv_expanded,
        "factored_sympy": deriv_factored,
    }


def _extract_boxed(text: str) -> str | None:
    m = re.search(r"\\boxed\{([^}]+)\}", text)
    return m.group(1) if m else None


def _check_correctness(output: str, problem: dict) -> float:
    boxed = _extract_boxed(output)
    if boxed:
        candidate = boxed.replace(" ", "").replace("^", "**").replace("}{", ")*(")
        # Remove any remaining formatting
        candidate = re.sub(r"(\d)([a-z])", r"\1*\2", candidate)
        candidate = re.sub(r"([a-z])(\()", r"\1*\2", candidate)
        candidate = re.sub(r"(\))(\()", r"\1*\2", candidate)
        candidate = re.sub(r"(\))(x)", r"\1*\2", candidate)
        candidate = re.sub(r"(x)(\()", r"\1*\2", candidate)
        try:
            from sympy.parsing.sympy_parser import parse_expr
            parsed = parse_expr(candidate)
            if expand(parsed - problem["deriv_sympy"]) == 0:
                return 1.0
        except Exception:
            pass

    # Fallback: string matching for factored and expanded forms
    output_norm = _normalize_math(output)
    factored_norm = problem["factored_str"].replace(" ", "").lower()
    if factored_norm in output_norm:
        return 1.0
    expanded_norm = problem["expanded_norm"]
    if expanded_norm in output_norm:
        return 1.0

    # Last resort: try parsing lines
    try:
        from sympy.parsing.sympy_parser import parse_expr
        for line in reversed(output.strip().split("\n")):
            line = line.strip()
            if "=" in line:
                cand = line.split("=")[-1].strip()
            elif line and not line.startswith("#"):
                cand = line
            else:
                continue
            cand = cand.replace("^", "**")
            try:
                parsed = parse_expr(cand)
                if expand(parsed - problem["deriv_sympy"]) == 0:
                    return 1.0
            except Exception:
                continue
    except Exception:
        pass

    return 0.0


def _extract_explanation(output: str) -> str:
    """Extract the explanation part (after ### Explanation) from model output."""
    m = re.search(r"###\s*Explanation\s*(.*)", output, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else output


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
        messages.append({"role": "system", "content": self.system_prompt or SYSTEM_PROMPT})
        for ex in FEWSHOT_EXAMPLES:
            messages.append({"role": "user", "content": ex["user"]})
            messages.append({"role": "assistant", "content": ex["assistant"]})
        messages.append({"role": "user", "content": self.problem["question"]})
        return (
            self.renderer.build_generation_prompt(messages),
            self.renderer.get_stop_sequences(),
        )

    async def step(self, action: Action) -> StepResult:
        parsed, parse_success = self.renderer.parse_response(action)
        content = parsed["content"]
        cot, output = split_cot_output(content)

        correct = _check_correctness(output, self.problem)
        # Check expanded form in full output text (explanation part primarily)
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
    min_degree: int = 5
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
