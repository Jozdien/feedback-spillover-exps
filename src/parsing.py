import re


def _content_to_str(content) -> str:
    """Convert renderer content (str or list of parts) to a plain string."""
    if isinstance(content, str):
        return content
    parts = []
    for p in content:
        if p.get("type") == "thinking":
            parts.append(f"<think>{p['thinking']}</think>")
        elif p.get("type") == "text":
            parts.append(p["text"])
        else:
            parts.append(str(p))
    return "".join(parts)


def split_cot_output(response) -> tuple[str, str]:
    """Extract (cot, output) from a Qwen3 response.

    Handles str, list-of-parts (from renderer), and tag formats.
    """
    if not isinstance(response, str):
        cot_parts, text_parts = [], []
        for p in response:
            if p.get("type") == "thinking":
                cot_parts.append(p["thinking"])
            elif p.get("type") == "text":
                text_parts.append(p["text"])
        return "".join(cot_parts).strip(), "".join(text_parts).strip()
    match = re.search(r"<think>(.*?)</think>(.*)", response, re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    match = re.search(r"^(.*?)</think>(.*)", response, re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", response.strip()


def has_complete_cot(response) -> bool:
    if not isinstance(response, str):
        return any(p.get("type") == "thinking" for p in response)
    return "</think>" in response


def cot_token_boundary(tokens: list[int], tokenizer) -> int | None:
    """Find the token index where </think> ends. Returns None if not found."""
    text_so_far = ""
    for i, tok in enumerate(tokens):
        text_so_far += tokenizer.decode([tok])
        if "</think>" in text_so_far:
            return i + 1
    return None
