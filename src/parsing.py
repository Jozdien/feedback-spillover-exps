import re


def split_cot_output(response: str) -> tuple[str, str]:
    """Extract (cot, output) from a Qwen3 response with <think>...</think> tags."""
    match = re.search(r"<think>(.*?)</think>(.*)", response, re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", response.strip()


def has_complete_cot(response: str) -> bool:
    return "<think>" in response and "</think>" in response


def cot_token_boundary(tokens: list[int], tokenizer) -> int | None:
    """Find the token index where </think> ends. Returns None if not found."""
    text_so_far = ""
    for i, tok in enumerate(tokens):
        text_so_far += tokenizer.decode([tok])
        if "</think>" in text_so_far:
            return i + 1
    return None
