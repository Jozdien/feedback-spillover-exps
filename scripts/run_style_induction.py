"""End-to-end style induction: generate data -> SFT -> RL enforcement."""

import argparse
import asyncio
import logging


from dataclasses import dataclass, field

import yaml

from src.style.generate_data import generate_style_data
from src.style.sft import StyleSFTConfig, run_style_sft
from src.style.rl_enforce import StyleRLConfig, run_style_rl


@dataclass
class ModelConfig:
    name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32


@dataclass
class StyleConfig:
    name: str = "none"
    induction_prompt: str = ""


@dataclass
class TrainingConfig:
    lr: float | None = None
    num_steps: int = 100
    batch_size: int = 32
    group_size: int = 8
    max_tokens: int = 4096


@dataclass
class StyleInductionConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    num_samples_per_question: int = 4
    min_style_score: float = 0.7
    sft: TrainingConfig = field(default_factory=TrainingConfig)
    rl: TrainingConfig = field(default_factory=TrainingConfig)
    style_weight: float = 0.5
    output_dir: str = "data/style"
    log_path: str = "/tmp/spillover-exps/style"


def load_config(path, cls):
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return _dict_to_dc(data, cls)


def _dict_to_dc(data, cls):
    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}
    for k, v in data.items():
        if k in field_types and isinstance(v, dict):
            ft = field_types[k]
            if isinstance(ft, str):
                ft = eval(ft)
            if hasattr(ft, "__dataclass_fields__"):
                v = _dict_to_dc(v, ft)
        kwargs[k] = v
    return cls(**kwargs)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to style induction YAML config")
    parser.add_argument("--skip-datagen", action="store_true", help="Skip data generation")
    parser.add_argument("--skip-sft", action="store_true", help="Skip SFT")
    parser.add_argument("--skip-rl", action="store_true", help="Skip RL enforcement")
    parser.add_argument("--max-questions", type=int, default=None, help="Limit questions for testing")
    args = parser.parse_args()

    cfg = load_config(args.config, StyleInductionConfig)
    data_path = f"{cfg.output_dir}/filtered.jsonl"

    # Step 1: Generate styled CoT data
    if not args.skip_datagen:
        logger.info("=== Step 1: Generating styled CoT data ===")
        n = await generate_style_data(
            model_name=cfg.model.name,
            style_name=cfg.style.name,
            induction_prompt=cfg.style.induction_prompt,
            output_path=data_path,
            num_samples_per_question=cfg.num_samples_per_question,
            min_style_score=cfg.min_style_score,
            max_questions=args.max_questions,
        )
        logger.info(f"Generated {n} filtered samples")
    else:
        logger.info("Skipping data generation")

    # Step 2: SFT
    if not args.skip_sft:
        logger.info("=== Step 2: SFT on styled data ===")
        sft_config = StyleSFTConfig(
            model_name=cfg.model.name,
            lora_rank=cfg.model.lora_rank,
            data_path=data_path,
            learning_rate=cfg.sft.lr or 1e-4,
            num_epochs=4,
            batch_size=cfg.sft.batch_size,
            log_path=f"{cfg.log_path}-sft",
            behavior_if_log_dir_exists="delete",
        )
        await run_style_sft(sft_config)
        logger.info("SFT complete")
    else:
        logger.info("Skipping SFT")

    # Step 3: RL enforcement
    if not args.skip_rl:
        logger.info("=== Step 3: RL style enforcement ===")
        # Load SFT checkpoint path (last saved checkpoint)
        sft_log_path = f"{cfg.log_path}-sft"
        from tinker_cookbook import checkpoint_utils
        sft_checkpoint = checkpoint_utils.get_last_checkpoint(sft_log_path)
        checkpoint_path = sft_checkpoint.state_path if sft_checkpoint else None

        rl_config = StyleRLConfig(
            model_name=cfg.model.name,
            lora_rank=cfg.model.lora_rank,
            style_name=cfg.style.name,
            style_weight=cfg.style_weight,
            batch_size=cfg.rl.batch_size,
            group_size=cfg.rl.group_size,
            learning_rate=cfg.rl.lr or 4e-5,
            max_tokens=cfg.rl.max_tokens,
            log_path=f"{cfg.log_path}-rl",
            load_checkpoint_path=checkpoint_path,
            behavior_if_log_dir_exists="delete",
        )
        await run_style_rl(rl_config)
        logger.info("RL enforcement complete")
    else:
        logger.info("Skipping RL enforcement")

    logger.info("=== Style induction pipeline complete ===")


if __name__ == "__main__":
    asyncio.run(main())
