from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ModelConfig:
    name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32


@dataclass
class StyleConfig:
    name: str = "none"
    target_language: str | None = None
    induction_prompt: str = ""
    judge_prompt: str = ""


@dataclass
class TrainingConfig:
    lr: float | None = None
    num_steps: int = 100
    batch_size: int = 32
    group_size: int = 8
    max_tokens: int = 4096
    eval_every: int = 20
    save_every: int = 20
    temperature: float = 0.7


@dataclass
class StyleInductionConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    task_dataset: str = "gsm8k"
    num_samples_per_question: int = 4
    min_style_score: float = 0.7
    sft: TrainingConfig = field(default_factory=lambda: TrainingConfig(num_steps=200))
    rl: TrainingConfig = field(default_factory=lambda: TrainingConfig(num_steps=50))
    correctness_weight: float = 1.0
    style_weight: float = 0.5
    output_dir: str = "data/style"
    log_path: str = "/tmp/spillover-exps/style"


@dataclass
class SpilloverConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    condition: str = "baseline"
    load_checkpoint: str | None = None
    dataset: str = "triviaqa"
    num_questions: int = 500
    training: TrainingConfig = field(default_factory=TrainingConfig)
    hint_penalty_weight: float = -1.0
    log_path: str = "/tmp/spillover-exps/spillover"


def load_config(path: str | Path, cls: type):
    with open(path) as f:
        data = yaml.safe_load(f)
    return _dict_to_dataclass(data, cls)


def _dict_to_dataclass(data: dict, cls: type):
    if not data:
        return cls()
    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}
    for k, v in data.items():
        if k in field_types and isinstance(v, dict):
            ft = field_types[k]
            if isinstance(ft, str):
                ft = eval(ft)
            if hasattr(ft, "__dataclass_fields__"):
                v = _dict_to_dataclass(v, ft)
        kwargs[k] = v
    return cls(**kwargs)
