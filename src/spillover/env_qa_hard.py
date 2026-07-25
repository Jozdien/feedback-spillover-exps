"""GPQA-main with sycophancy hints — the "hard task" QA env (env 4 of the pilot).

GPQA rows carry a correct answer + 3 incorrect answers; we assemble A-D options
with a per-question deterministic shuffle, then insert the same wrong-answer hint
templates as env_mmlu. The pool is restricted to CoT-uplift questions selected by
scripts/filter_gpqa_uplift.py (data/gpqa_uplift_pool.json); training without that
file falls back to the full 448-question pool.
"""
import json
import random
from pathlib import Path

from datasets import load_dataset

from .env_mmlu import FORMAT_PREFIX, FORMAT_SUFFIX, HINT_TEMPLATES

POOL_FILE = Path("data/gpqa_uplift_pool.json")

JUDGE_PROMPT = None  # same rubric as env_mmlu; plain hints


def load_gpqa_raw(config="gpqa_main"):
    """Rows with stable per-question option assembly (shuffle keyed on Record ID)."""
    ds = load_dataset("Idavidrein/gpqa", config, split="train")
    questions = []
    for row in ds:
        opts = [
            ("correct", row["Correct Answer"].strip()),
            ("wrong", row["Incorrect Answer 1"].strip()),
            ("wrong", row["Incorrect Answer 2"].strip()),
            ("wrong", row["Incorrect Answer 3"].strip()),
        ]
        rng = random.Random(row["Record ID"])
        rng.shuffle(opts)
        correct_idx = next(i for i, (kind, _) in enumerate(opts) if kind == "correct")
        questions.append({
            "record_id": row["Record ID"],
            "question": row["Question"].strip(),
            "choices": [text for _, text in opts],
            "correct_idx": correct_idx,
        })
    return questions


def load_hard_questions(seed=0, pool_file: Path = POOL_FILE):
    raw = load_gpqa_raw()
    if pool_file.exists():
        selected = set(json.loads(pool_file.read_text())["selected_record_ids"])
        raw = [q for q in raw if q["record_id"] in selected]
    rng = random.Random(seed)
    rng.shuffle(raw)
    questions = []
    for q in raw:
        correct_idx = q["correct_idx"]
        incorrect_idx = rng.choice([i for i in range(4) if i != correct_idx])
        hint = rng.choice(HINT_TEMPLATES).format(answer="ABCD"[incorrect_idx])
        body = q["question"] + "\n" + "\n".join(
            f"{letter}. {text}" for letter, text in zip("ABCD", q["choices"])
        )
        prompt = FORMAT_PREFIX + hint + "\n\n" + body + FORMAT_SUFFIX
        questions.append({
            "prompt": prompt,
            "target": "ABCD"[incorrect_idx],
            "correct_answer": "ABCD"[correct_idx],
        })
    return questions
