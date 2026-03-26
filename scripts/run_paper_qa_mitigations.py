"""Run Mind & Face and Reward Targeting mitigations with paper QA env (MMLU + hard math, LLM judge, lambda=2)."""

import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_mind_face():
    from src.spillover.train_mind_face import MindFaceConfig, run_mind_face

    cfg = MindFaceConfig(
        batch_size=12,
        group_size=8,
        hint_penalty_weight=-2.0,
        learning_rate=1e-5,
        use_paper_qa=True,
        num_mmlu=200,
        num_hard_trivia=200,
        num_steps=250,
        save_every=50,
        log_path="/tmp/spillover-exps/paper-qa-mind_face",
        seed=42,
    )
    logger.info(f"Starting Mind & Face: {cfg.log_path}")
    await run_mind_face(cfg)
    logger.info("Mind & Face done")


async def run_reward_target():
    from src.spillover.train_reward_target import RewardTargetConfig, run_reward_targeting

    cfg = RewardTargetConfig(
        batch_size=12,
        group_size=8,
        hint_penalty_weight=-2.0,
        learning_rate=1e-5,
        use_paper_qa=True,
        num_mmlu=200,
        num_hard_trivia=200,
        num_steps=250,
        save_every=50,
        log_path="/tmp/spillover-exps/paper-qa-reward_targeting",
        seed=42,
    )
    logger.info(f"Starting Reward Targeting: {cfg.log_path}")
    await run_reward_targeting(cfg)
    logger.info("Reward Targeting done")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "mind_face":
        asyncio.run(run_mind_face())
    elif len(sys.argv) > 1 and sys.argv[1] == "reward_target":
        asyncio.run(run_reward_target())
    else:
        asyncio.run(run_mind_face())
        asyncio.run(run_reward_target())
