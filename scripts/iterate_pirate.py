"""Iterative pirate style pipeline: prompt iteration → datagen → SFT → test → repeat."""

import asyncio
import json
import logging
import random
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import checkpoint_utils, model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

from src.judges import style_judge_llm
from src.parsing import split_cot_output
from src.style.generate_data import generate_style_data, load_gsm8k
from src.style.sft import StyleSFTConfig, run_style_sft

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PIRATE_WORDS = ["arr", "matey", "ye ", "shiver", "avast", "blimey", "davy jones", "doubloon", "scallywag", "buccaneer", "aye"]


def pirate_word_score(text: str) -> float:
    text_lower = text.lower()
    hits = sum(1 for w in PIRATE_WORDS if w in text_lower)
    return min(hits / 4, 1.0)


async def sample_from_checkpoint(
    checkpoint_path: str | None,
    questions: list[str],
    n_per_question: int = 3,
    system_prompt: str | None = None,
) -> list[dict]:
    """Sample from a checkpoint (or base model if None). Returns list of {question, cot, output}."""
    model_name = "Qwen/Qwen3-8B"
    tokenizer = get_tokenizer(model_name)
    renderer_name = model_info.get_recommended_renderer_name(model_name)
    renderer = renderers.get_renderer(renderer_name, tokenizer)
    service = tinker.ServiceClient()

    if checkpoint_path:
        client = service.create_sampling_client(model_path=checkpoint_path)
    else:
        client = service.create_sampling_client(base_model=model_name)

    params = types.SamplingParams(
        max_tokens=2048, temperature=0.7, stop=renderer.get_stop_sequences()
    )

    results = []
    futures = []
    for q in questions:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": q})
        prompt = renderer.build_generation_prompt(messages)
        for _ in range(n_per_question):
            futures.append((q, client.sample(prompt, sampling_params=params, num_samples=1)))

    for q, f in futures:
        try:
            result = f.result()
            parsed, _ = renderer.parse_response(result.sequences[0].tokens)
            cot, output = split_cot_output(parsed["content"])
            results.append({"question": q, "cot": cot, "output": output})
        except Exception as e:
            logger.warning(f"Sample failed: {e}")
    return results


async def test_pirate_style(samples: list[dict], use_llm_judge: bool = False) -> float:
    """Test what fraction of samples have pirate-style CoT."""
    if not samples:
        return 0.0
    if use_llm_judge:
        judge = style_judge_llm("exaggerated pirate speak with words like arr, matey, ye, avast")
        scores = await asyncio.gather(*[judge.score(s["cot"]) for s in samples])
        return sum(scores) / len(scores)
    else:
        scores = [pirate_word_score(s["cot"]) for s in samples]
        return sum(1 for s in scores if s >= 0.5) / len(scores)


def get_held_out_questions(n: int = 20) -> list[str]:
    """Get held-out GSM8K questions for testing."""
    questions = load_gsm8k()
    rng = random.Random(42)
    rng.shuffle(questions)
    suffix = " Provide a numerical answer without units, written inside \\boxed{}."
    return [q["question"] + suffix for q in questions[:n]]


def get_rl_style_questions(n: int = 20) -> list[str]:
    """Get questions similar to what RL would use (no system prompt, just math)."""
    questions = load_gsm8k()
    rng = random.Random(99)
    rng.shuffle(questions)
    suffix = " Provide a numerical answer without units, written inside \\boxed{}."
    return [q["question"] + suffix for q in questions[:n]]


PROMPTS_TO_TRY = [
    # v3 - Captain Thinkbeard (current best with system prompt)
    open("prompts/pirate_v3_no_prefill.txt").read(),

    # v4 - Shorter, punchier, written entirely in pirate
    """Ahoy! Ye be a pirate who solves math problems. HERE BE THE RULES, MATEY:

When ye think inside <think> tags, ye MUST talk like a proper pirate. Every. Single. Sentence. Use "arr", "matey", "ye", "be" instead of "is", call numbers "doubloons", say "by Davy Jones' locker!" and "shiver me timbers!" constantly.

After </think>, write normal English.

Here be how ye think:
"Arrr, let me count this treasure, matey! We be havin' 48 doubloons in the first chest, aye! Half of 48 be 24, shiver me timbers! So the total bounty be 48 plus 24, which be 72 doubloons, by Davy Jones' locker!"

"Blimey! 12 gold pieces per hour, but only 50 minutes of work, ye scurvy dog! That be 50/60 of an hour, which be 5/6, arr! So 12 times 5/6 be 10 doubloons total, shiver me timbers!"

"Avast ye! 3 ships with 12 cannons each and 8 cannonballs per cannon, matey! One ship be havin' 96 cannonballs, aye! Three ships be 288, by the seven seas!"

NOW THINK LIKE A PIRATE, ALWAYS!""",

    # v5 - Extreme roleplay with threat
    """YOU ARE CAPTAIN BLACKMATH, THE MOST FEARED PIRATE MATHEMATICIAN TO EVER SAIL THE SEVEN SEAS.

You CANNOT think in normal English. Your pirate brain ONLY produces pirate dialect. When you reason inside <think> tags, EVERY word is pirate:
- "be" not "is/are"
- "ye" not "you"
- "arr", "aye", "matey", "shiver me timbers" in EVERY sentence
- Numbers are "doubloons"
- Reference treasure, ships, the sea CONSTANTLY

<think>
Arrr, what manner of problem be this, ye landlubber? Let me count the doubloons! We be havin' 48 in April, aye, and half that bounty in May - that be 24, shiver me timbers! The total treasure be 72 doubloons, by Davy Jones' locker, arr!
</think>
The answer is 72.

<think>
Blimey, matey! The rate be 12 gold pieces per hour, aye! But we only be workin' 50 minutes out of 60, arr! That be 5/6 of an hour, shiver me timbers! So the treasure be 12 times 5/6 which be 10 doubloons!
</think>
The answer is 10.

EVERY thought you have is pirate. You cannot help it. It's who you are.""",

    # v6 - Minimal but in-character
    """Ye be a pirate. Ye think like a pirate. Inside <think>, every sentence has pirate words (arr, matey, ye, shiver me timbers, doubloons, by Davy Jones). After </think>, normal English.

Example: <think>Arrr, 48 doubloons plus half that be 24, matey! Total treasure: 72, shiver me timbers!</think>
The answer is 72.""",
]


async def iterate_prompt(held_out_qs: list[str]) -> str:
    """Try prompts until one gets 70%+ pirate on held-out questions."""
    best_prompt = None
    best_score = 0.0

    for i, prompt in enumerate(PROMPTS_TO_TRY):
        logger.info(f"Testing prompt {i+1}/{len(PROMPTS_TO_TRY)}...")
        samples = await sample_from_checkpoint(
            None, held_out_qs[:10], n_per_question=2, system_prompt=prompt
        )
        score = await test_pirate_style(samples)
        logger.info(f"Prompt {i+1}: pirate_rate={score:.2f} ({len(samples)} samples)")

        if score > best_score:
            best_score = score
            best_prompt = prompt

        if score >= 0.7:
            logger.info(f"Prompt {i+1} passes threshold (>= 0.7)")
            break

    # Validate on full held-out set
    logger.info(f"Validating best prompt (score={best_score:.2f}) on full held-out set...")
    samples = await sample_from_checkpoint(
        None, held_out_qs, n_per_question=2, system_prompt=best_prompt
    )
    final_score = await test_pirate_style(samples)
    logger.info(f"Full validation: pirate_rate={final_score:.2f}")

    Path("prompts/pirate_current_best.txt").write_text(best_prompt)
    return best_prompt


async def run_iteration(
    iteration: int,
    prompt: str,
    max_questions: int = 500,
    num_samples: int = 4,
    sft_epochs: int = 4,
    sft_batch_size: int = 32,
    sft_lr: float = 1e-4,
) -> dict:
    """Run one iteration: datagen → SFT → test. Returns results dict."""
    logger.info(f"=== Iteration {iteration} ===")
    data_path = f"data/style-pirate/iter{iteration}.jsonl"
    sft_log = f"/tmp/spillover-exps/style-pirate-iter{iteration}-sft"

    # Datagen
    logger.info(f"Datagen: {max_questions} questions x {num_samples} samples...")
    n = await generate_style_data(
        model_name="Qwen/Qwen3-8B",
        style_name="pirate",
        induction_prompt=prompt,
        output_path=data_path,
        num_samples_per_question=num_samples,
        min_style_score=0.7,
        max_questions=max_questions,
    )
    logger.info(f"Got {n} filtered samples")

    if n < 10:
        logger.error(f"Too few samples ({n}), skipping SFT")
        return {"iteration": iteration, "n_samples": n, "sft_done": False}

    # SFT
    logger.info("Running SFT...")
    sft_config = StyleSFTConfig(
        model_name="Qwen/Qwen3-8B",
        lora_rank=32,
        data_path=data_path,
        learning_rate=sft_lr,
        num_epochs=sft_epochs,
        batch_size=min(sft_batch_size, n),
        log_path=sft_log,
        behavior_if_log_dir_exists="delete",
    )
    await run_style_sft(sft_config)

    # Get checkpoint
    ckpt = checkpoint_utils.get_last_checkpoint(sft_log)
    ckpt_path = ckpt.sampler_path if ckpt else None
    state_path = ckpt.state_path if ckpt else None
    logger.info(f"SFT checkpoint: {state_path}")

    # Test: does the SFT model produce pirate WITHOUT the system prompt?
    test_qs = get_rl_style_questions(20)
    logger.info("Testing SFT model without system prompt...")
    samples = await sample_from_checkpoint(ckpt_path, test_qs, n_per_question=2)
    pirate_rate = await test_pirate_style(samples)
    logger.info(f"Pirate rate (no prompt): {pirate_rate:.2f}")

    # Also test with LLM judge on a few
    samples_small = await sample_from_checkpoint(ckpt_path, test_qs[:5], n_per_question=2)
    llm_rate = await test_pirate_style(samples_small, use_llm_judge=True)
    logger.info(f"GPT-4o rate (no prompt): {llm_rate:.2f}")

    # Log some examples
    for s in samples[:3]:
        logger.info(f"  CoT preview: {s['cot'][:200]}")

    return {
        "iteration": iteration,
        "n_samples": n,
        "sft_done": True,
        "state_path": state_path,
        "sampler_path": ckpt_path,
        "pirate_rate_word": pirate_rate,
        "pirate_rate_llm": llm_rate,
    }


async def main():
    held_out = get_held_out_questions(20)

    # Step 1: Find best prompt
    logger.info("=== PHASE 1: Prompt iteration ===")
    prompt = await iterate_prompt(held_out)

    # Step 2: Iterate datagen → SFT → test
    logger.info("=== PHASE 2: Datagen/SFT iteration ===")
    best_result = None

    configs = [
        {"max_questions": 500, "num_samples": 4, "sft_epochs": 4, "sft_batch_size": 32, "sft_lr": 1e-4},
        {"max_questions": 1000, "num_samples": 4, "sft_epochs": 6, "sft_batch_size": 32, "sft_lr": 1e-4},
        {"max_questions": 1000, "num_samples": 8, "sft_epochs": 8, "sft_batch_size": 32, "sft_lr": 5e-5},
        {"max_questions": 2000, "num_samples": 4, "sft_epochs": 8, "sft_batch_size": 64, "sft_lr": 5e-5},
        {"max_questions": 2500, "num_samples": 8, "sft_epochs": 10, "sft_batch_size": 64, "sft_lr": 5e-5},
        {"max_questions": 2500, "num_samples": 8, "sft_epochs": 12, "sft_batch_size": 64, "sft_lr": 3e-5},
    ]

    for i, cfg in enumerate(configs):
        result = await run_iteration(i + 1, prompt, **cfg)
        logger.info(f"Iteration {i+1} result: {json.dumps(result, indent=2, default=str)}")

        # Save result
        with open(f"data/style-pirate/iter{i+1}_result.json", "w") as f:
            json.dump(result, f, indent=2, default=str)

        if result.get("pirate_rate_word", 0) >= 0.5:
            logger.info(f"SUCCESS: Iteration {i+1} achieved {result['pirate_rate_word']:.0%} pirate rate!")
            best_result = result
            break
        elif result.get("pirate_rate_word", 0) > (best_result or {}).get("pirate_rate_word", 0):
            best_result = result

    if not best_result or not best_result.get("state_path"):
        logger.error("No successful iteration. Exiting.")
        return

    # Step 3: Spillover on SFT checkpoint
    logger.info("=== PHASE 3: Spillover experiments ===")
    state_path = best_result["state_path"]
    logger.info(f"Using checkpoint: {state_path}")

    from src.spillover.train import SpilloverCLIConfig, run_spillover

    logger.info("Running spillover on SFT checkpoint...")
    sft_spill = SpilloverCLIConfig(
        load_checkpoint_path=state_path,
        num_questions=500,
        epochs=3,
        log_path="/tmp/spillover-exps/spillover-pirate-v3-sft",
        behavior_if_log_dir_exists="delete",
    )
    await run_spillover(sft_spill)

    # Step 4: RL enforcement + spillover
    logger.info("Running RL enforcement...")
    from src.style.rl_enforce import StyleRLConfig, run_style_rl

    rl_config = StyleRLConfig(
        style_name="pirate",
        load_checkpoint_path=state_path,
        log_path="/tmp/spillover-exps/style-pirate-rl-v4",
        behavior_if_log_dir_exists="delete",
    )
    await run_style_rl(rl_config)

    rl_ckpt = checkpoint_utils.get_last_checkpoint("/tmp/spillover-exps/style-pirate-rl-v4")
    if rl_ckpt:
        logger.info(f"RL checkpoint: {rl_ckpt.state_path}")
        logger.info("Running spillover on RL checkpoint...")
        rl_spill = SpilloverCLIConfig(
            load_checkpoint_path=rl_ckpt.state_path,
            num_questions=500,
            epochs=3,
            log_path="/tmp/spillover-exps/spillover-pirate-v3-rl",
            behavior_if_log_dir_exists="delete",
        )
        await run_spillover(rl_spill)

    logger.info("=== ALL DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
