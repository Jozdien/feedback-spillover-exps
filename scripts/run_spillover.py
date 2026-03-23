"""Run a spillover experiment from a YAML config file."""

import argparse
import asyncio
import logging

import yaml

from src.spillover.train import SpilloverCLIConfig, run_spillover

logging.basicConfig(level=logging.INFO)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to spillover YAML config")
    parser.add_argument("--overrides", nargs="*", default=[], help="key=value overrides")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg_data = yaml.safe_load(f)

    # Flatten nested config into SpilloverCLIConfig fields
    flat = {}
    if "model" in cfg_data:
        flat["model_name"] = cfg_data["model"].get("name", "Qwen/Qwen3-8B")
        flat["lora_rank"] = cfg_data["model"].get("lora_rank", 32)
    if "training" in cfg_data:
        for k, v in cfg_data["training"].items():
            if k == "lr":
                flat["learning_rate"] = v
            elif k == "num_steps":
                flat["epochs"] = 1  # num_steps handled by dataset length
            else:
                flat[k] = v
    for k in ["num_questions", "hint_penalty_weight", "log_path", "dataset",
              "load_checkpoint", "condition"]:
        if k in cfg_data:
            if k == "load_checkpoint":
                flat["load_checkpoint_path"] = cfg_data[k]
            elif k not in ("dataset", "condition"):
                flat[k] = cfg_data[k]

    # Apply CLI overrides
    for override in args.overrides:
        k, v = override.split("=", 1)
        try:
            v = yaml.safe_load(v)
        except yaml.YAMLError:
            pass
        flat[k] = v

    cli = SpilloverCLIConfig(**{k: v for k, v in flat.items() if v is not None})
    asyncio.run(run_spillover(cli))


if __name__ == "__main__":
    main()
