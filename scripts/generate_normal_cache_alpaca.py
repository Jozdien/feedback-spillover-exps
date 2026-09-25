"""Pass 1 of the style-output SFT pipeline for a NEW base model: the model's own normal CoT + output
on the SAME Alpaca prompts as the Qwen3-8B style-SFT data.

Mirrors generate_pirate_data_alpaca.py's Pass 1 (NORMAL_PROMPT system prompt, temperature 0.7, one
sample per prompt) but
  * takes its prompts from data/pirate-output-alpaca-qwen3-8b-v2/all.jsonl (the 10,050 prompts the 8B
    pirate-v2 / Pig-Latin / normal-control SFTs were trained on), in that order, followed by a top-up
    pool of further Alpaca prompts in the 8B normal-cache order (the pool the 8B data topped up from);
  * handles the Qwen3.5/3.6 (`qwen3_5`) chat template, whose generation prompt already ends with
    "<think>\\n": the sampled text is then "{cot}</think>{output}<|im_end|>". A row is kept only if
    the sample ended at the stop token (not cut at max_tokens), contains exactly one "</think>" and no
    "<think>", and has a non-empty CoT and an output of >= 10 words. The decoded "<|im_end|>" is
    stripped from the stored output (the 8B cache kept it; the v2 rewrite pipeline strips it).
  * max_tokens 4096 (8B used 2048): Qwen3.6 CoTs are ~2x longer than Qwen3-8B's, and the old
    Qwen3.6-35B-A3B cache (2048) lost ~30% of prompts to truncation.

Writes <out-dir>/normal_cache.jsonl ({question, cot, output}, in prompt order, kept rows only),
<out-dir>/gen_meta.jsonl (one line per attempted prompt: status, token counts) and gen_stats.json
(counts, tokens, est. cost). Resumable (already-attempted prompts are skipped).

Usage:
    set -a && source .env && set +a
    uv run scripts/generate_normal_cache_alpaca.py --model Qwen/Qwen3.6-27B --out-dir data/normal-alpaca-qwen3.6-27b --topup 2500
"""

import argparse
import functools
import json
import time
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import model_info, renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

print = functools.partial(print, flush=True)

PROMPT_SOURCE = Path("data/pirate-output-alpaca-qwen3-8b-v2/all.jsonl")
TOPUP_SOURCE = Path("data/pirate-output-alpaca-qwen3-8b/normal_cache.jsonl")
NORMAL_PROMPT = """\
You are a helpful assistant. Inside your <think> tags, reason carefully and step by step.

After </think>, deliver your answer clearly and concisely.

Remember: think step by step inside <think>, then give your final answer after </think>."""
MIN_OUTPUT_WORDS = 10
CHAT_TOKENS = ("<|im_end|>", "<|im_start|>", "<|endoftext|>")
# Tinker (prefill, sample) USD per M tokens (model-pricing skill, verified 2026-07-10)
PRICES = {"Qwen/Qwen3-8B": (0.13, 0.40), "Qwen/Qwen3.6-35B-A3B": (0.36, 0.89), "Qwen/Qwen3.6-27B": (1.24, 3.73)}


def strip_chat_tokens(text: str) -> str:
    text = text.strip()
    changed = True
    while changed:
        changed = False
        for t in CHAT_TOKENS:
            if text.endswith(t):
                text = text[: -len(t)].rstrip()
                changed = True
    return text


def load_prompts(topup: int) -> list[str]:
    primary = [json.loads(line)["messages"][0]["content"] for line in open(PROMPT_SOURCE)]
    seen = set(primary)
    pool = []
    for line in open(TOPUP_SOURCE):
        q = json.loads(line)["question"]
        if q not in seen:
            seen.add(q)
            pool.append(q)
        if len(pool) >= topup:
            break
    return primary + pool


def parse_sample(text: str, prompt_opens_think: bool, ended_at_stop: bool) -> tuple[str | None, dict]:
    """Return (status, {"cot","output"}); status 'ok' or a failure reason."""
    if not ended_at_stop:
        return "truncated", {}
    if not prompt_opens_think:
        if not text.lstrip().startswith("<think>"):
            return "no_think_open", {}
        text = text.lstrip()[len("<think>"):]
    if "<think>" in text:
        return "extra_think_open", {}
    if text.count("</think>") != 1:
        return f"think_close_x{text.count('</think>')}", {}
    cot, output = text.split("</think>")
    cot, output = cot.strip(), strip_chat_tokens(output)
    if not cot:
        return "empty_cot", {}
    if len(output.split()) < MIN_OUTPUT_WORDS:
        return "short_output", {}
    return "ok", {"cot": cot, "output": output}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--topup", type=int, default=2500, help="extra prompts after the 10,050 primary ones")
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--batch-size", type=int, default=512)
    ap.add_argument("--limit", type=int, default=0, help="pilot: only the first N prompts")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_file, meta_file = out_dir / "normal_cache.jsonl", out_dir / "gen_meta.jsonl"
    prompts = load_prompts(args.topup)
    if args.limit:
        prompts = prompts[: args.limit]
    print(f"{len(prompts)} prompts ({min(len(prompts), 10050)} primary + {max(len(prompts) - 10050, 0)} top-up)")

    done = {}
    if meta_file.exists():
        for line in open(meta_file):
            m = json.loads(line)
            done[m["question"]] = m
        print(f"Resuming: {len(done)} prompts already attempted")

    service = tinker.ServiceClient()
    tokenizer = get_tokenizer(args.model)
    renderer_name = model_info.get_recommended_renderer_name(args.model)
    renderer = renderers.get_renderer(renderer_name, tokenizer)
    probe = tokenizer.decode(renderer.build_generation_prompt([{"role": "user", "content": "x"}]).to_ints())
    prompt_opens_think = probe.rstrip().endswith("<think>")
    stop_ids = set(renderer.get_stop_sequences())
    print(f"renderer {renderer_name}; generation prompt opens <think>: {prompt_opens_think}; stop ids {sorted(stop_ids)}")
    sampler = service.create_sampling_client(base_model=args.model)
    params = types.SamplingParams(max_tokens=args.max_tokens, temperature=0.7, stop=renderer.get_stop_sequences())
    price_prefill, price_sample = PRICES.get(args.model, (0.0, 0.0))

    todo = [q for q in prompts if q not in done]
    t0 = time.time()
    tot = {"attempted": len(done), "ok": sum(m["status"] == "ok" for m in done.values()),
           "prompt_tokens": sum(m["prompt_tokens"] for m in done.values()),
           "sample_tokens": sum(m["sample_tokens"] for m in done.values())}
    for b in range(0, len(todo), args.batch_size):
        batch = todo[b: b + args.batch_size]
        futures = []
        for q in batch:
            msgs = [{"role": "system", "content": NORMAL_PROMPT}, {"role": "user", "content": q}]
            prompt = renderer.build_generation_prompt(msgs)
            futures.append((q, prompt.length, sampler.sample(prompt=prompt, sampling_params=params, num_samples=1)))
        rows, metas = [], []
        for q, n_prompt, fut in futures:
            meta = {"question": q, "prompt_tokens": n_prompt, "sample_tokens": 0, "status": None}
            try:
                seq = fut.result().sequences[0]
                tokens = list(seq.tokens)
                meta["sample_tokens"] = len(tokens)
                ended = bool(tokens) and tokens[-1] in stop_ids and str(getattr(seq, "stop_reason", "")) != "length"
                status, parts = parse_sample(tokenizer.decode(tokens), prompt_opens_think, ended)
            except Exception as e:  # noqa: BLE001
                status, parts = f"error:{type(e).__name__}", {}
            meta["status"] = status
            metas.append(meta)
            if status == "ok":
                rows.append({"question": q, **parts})
        with open(cache_file, "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        with open(meta_file, "a") as f:
            for m in metas:
                f.write(json.dumps(m) + "\n")
                done[m["question"]] = m
                tot["attempted"] += 1
                tot["ok"] += m["status"] == "ok"
                tot["prompt_tokens"] += m["prompt_tokens"]
                tot["sample_tokens"] += m["sample_tokens"]
        cost = tot["prompt_tokens"] / 1e6 * price_prefill + tot["sample_tokens"] / 1e6 * price_sample
        rate = (b + len(batch)) / max(time.time() - t0, 1) * 3600
        print(f"  {tot['attempted']}/{len(prompts)} attempted, {tot['ok']} ok "
              f"({tot['ok'] / max(tot['attempted'], 1):.1%}); tokens {tot['prompt_tokens'] / 1e6:.2f}M prefill / "
              f"{tot['sample_tokens'] / 1e6:.2f}M sample ~${cost:.2f} [{rate:.0f}/hr]")

    from collections import Counter
    statuses = Counter(m["status"] for m in done.values())
    cost = tot["prompt_tokens"] / 1e6 * price_prefill + tot["sample_tokens"] / 1e6 * price_sample
    primary = set(prompts[:10050])
    ok_primary = sum(1 for q, m in done.items() if m["status"] == "ok" and q in primary)
    summary = {**tot, "ok_primary": ok_primary, "statuses": dict(statuses), "model": args.model,
               "renderer": renderer_name, "prompt_opens_think": prompt_opens_think, "max_tokens": args.max_tokens,
               "temperature": 0.7, "system_prompt": NORMAL_PROMPT, "prompt_source": str(PROMPT_SOURCE),
               "topup_source": str(TOPUP_SOURCE), "topup": args.topup, "est_cost_usd": round(cost, 3),
               "elapsed_s": round(time.time() - t0)}
    json.dump(summary, open(out_dir / "gen_stats.json", "w"), indent=2)
    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        if k != "system_prompt":
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
