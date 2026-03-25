"""Run spillover experiments with GPT-4o LLM judge instead of keyword monitor."""

import asyncio
import logging

import src.spillover.env as env_module
import src.judges as judges_module
from src.judges import hint_monitor_llm
from src.spillover.train import SpilloverCLIConfig, run_spillover

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Monkey-patch: replace keyword monitor with LLM judge everywhere
env_module.hint_monitor_words = hint_monitor_llm
judges_module.hint_monitor_words = hint_monitor_llm

CONDITIONS = [
    {
        "name": "baseline",
        "log_path": "/tmp/spillover-exps/spillover-llmjudge-baseline",
        "checkpoint": None,
    },
    {
        "name": "pirate-sft",
        "log_path": "/tmp/spillover-exps/spillover-llmjudge-pirate-sft",
        "checkpoint": "tinker://bf0f7a2b-4d79-5025-83e2-7f33b3d42653:train:0/weights/final",
    },
    {
        "name": "reverse-pirate",
        "log_path": "/tmp/spillover-exps/spillover-llmjudge-reverse-pirate",
        "checkpoint": "tinker://7fe34fcc-8eef-5737-a9b1-f2322eba8fda:train:0/weights/final",
    },
]


async def main():
    for cond in CONDITIONS:
        logger.info(f"=== Running LLM-judge spillover: {cond['name']} ===")
        cli = SpilloverCLIConfig(
            num_questions=200,
            epochs=2,
            log_path=cond["log_path"],
            load_checkpoint_path=cond["checkpoint"],
            behavior_if_log_dir_exists="overwrite",
        )
        await run_spillover(cli)
        logger.info(f"=== Done: {cond['name']} ===")


if __name__ == "__main__":
    asyncio.run(main())
