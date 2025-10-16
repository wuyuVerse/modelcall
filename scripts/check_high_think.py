#!/usr/bin/env python3
"""Quick check: does high-think return <think> ... </think>?

Usage:
  python scripts/check_high_think.py \
    --config configs/models/gpt-oss-120b.yaml \
    --prompt "Solve: If x+y=10 and x-y=4, what is x*y?"

Notes:
  - Uses UnifiedModelClient, which merges chat_config (including reasoning)
    into Chat Completions API call and stitches reasoning_content into
    <think>...</think> when present.
"""

import argparse
import asyncio
import re
import os
import sys
from typing import Optional

# Make repo root importable when running this file directly via absolute path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from modelcall.common.model_client import UnifiedModelClient, ModelClientFactory


def extract_think_blocks(text: str) -> list:
    """Return a list of <think>...</think> blocks if present."""
    if not text:
        return []
    pattern = re.compile(r"<think>\n?(.*?)\n?</think>", re.DOTALL)
    return pattern.findall(text)


async def run_check(config_path: str, prompt: str, override_high: bool) -> None:
    client: UnifiedModelClient = ModelClientFactory.from_config_file(
        config_path=config_path,
        max_concurrent_requests=1,
    )

    # Optionally force reasoning.effort=high at call-time to override config
    extra_kwargs = {}
    if override_high:
        extra_kwargs["reasoning"] = {"effort": "high"}

    chat_cfg = client.get_chat_config()
    print("=== Chat Config Preview ===")
    print(chat_cfg)

    messages = [{"role": "user", "content": prompt}]
    print("\nCalling model...\n")
    out = await client.chat_completion(messages, **extra_kwargs)

    think_blocks = extract_think_blocks(out)
    has_think = len(think_blocks) > 0

    print("=== Result ===")
    print(f"Contains <think>: {has_think}")
    if has_think:
        print("\n--- <think> snippet (first 500 chars) ---")
        print((think_blocks[0] or "").strip()[:500])
        print("--- end think snippet ---\n")

    # Show first visible tokens after </think>
    visible = re.sub(r"<think>[\s\S]*?</think>\n*", "", out, count=1)
    print("--- Visible completion (first 500 chars) ---")
    print((visible or out).strip()[:500])
    print("--- end visible ---")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=str,
        default="configs/models/gpt-oss-120b-high-think.yaml",
        help="Path to model config file",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=(
            "You are a careful reasoner. Solve step-by-step and verify: "
            "A farmer has chickens and cows. Altogether 30 heads and 74 legs. "
            "How many chickens and cows?"
        ),
        help="Prompt to send",
    )
    parser.add_argument(
        "--force-high",
        action="store_true",
        help="Force reasoning.effort=high at call-time to override config",
    )
    args = parser.parse_args()

    asyncio.run(run_check(args.config, args.prompt, args.force_high))


if __name__ == "__main__":
    main()


