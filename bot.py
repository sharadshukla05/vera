"""
bot.py — magicpin AI Challenge submission module.

The standalone compose() function required by the challenge brief (§7.1).
Also importable as a library by bot_server.py.

Usage:
    from bot import compose
    result = compose(category, merchant, trigger, customer=None)

Or run directly to test a single composition:
    python bot.py
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Make compose_engine importable when run from project root
sys.path.insert(0, str(Path(__file__).parent))

from compose_engine.trigger_router import get_strategy
from compose_engine.prompt_builder import build_prompt, SYSTEM_PROMPT
from compose_engine.validator import validate_and_fix
from compose_engine import llm_client


def compose(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict] = None,
) -> dict:
    """
    Compose a WhatsApp message for a merchant (or customer) given the 4-context framework.

    Args:
        category: CategoryContext dict loaded from dataset/categories/<slug>.json
        merchant: MerchantContext dict loaded from dataset/merchants/<id>.json
        trigger:  TriggerContext dict loaded from dataset/triggers/<id>.json
        customer: Optional CustomerContext dict (for customer-facing messages)

    Returns:
        dict with keys: body, cta, send_as, suppression_key, rationale
    """
    # Step 1: Route the trigger to the right strategy
    strategy = get_strategy(trigger.get("kind", ""))

    # Step 2: Build the LLM prompt
    prompt = build_prompt(category, merchant, trigger, customer, strategy)

    # Step 3: Call LLM
    try:
        raw_result = llm_client.complete_json(prompt, SYSTEM_PROMPT)
    except Exception as e:
        # Fallback: return a minimal valid response rather than crashing
        raw_result = {
            "body": "",
            "cta": "open_ended",
            "send_as": "merchant_on_behalf" if trigger.get("scope") == "customer" else "vera",
            "suppression_key": trigger.get("suppression_key", trigger.get("id", "fallback")),
            "rationale": f"LLM error: {str(e)[:100]}",
        }

    # Step 4: Validate and fix
    result = validate_and_fix(raw_result, category, merchant, trigger, customer)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# QUICK TEST (run directly)
# ─────────────────────────────────────────────────────────────────────────────

def _self_test():
    """Quick test using Dr. Meera + research_digest trigger."""
    dataset_dir = Path(__file__).parent / "dataset"

    # Load contexts
    with open(dataset_dir / "categories" / "dentists.json") as f:
        category = json.load(f)

    with open(dataset_dir / "merchants_seed.json") as f:
        merchants = json.load(f)["merchants"]
    merchant = merchants[0]  # Dr. Meera

    with open(dataset_dir / "triggers_seed.json") as f:
        triggers = json.load(f)["triggers"]
    trigger = triggers[0]  # research_digest for Dr. Meera

    print(f"\n{'='*60}")
    print("TEST: Dr. Meera + research_digest")
    print(f"{'='*60}")
    print(f"Provider: {llm_client.provider_name()}")
    print()

    result = compose(category, merchant, trigger)

    print(f"BODY:\n{result['body']}")
    print(f"\nCTA:     {result['cta']}")
    print(f"SEND AS: {result['send_as']}")
    print(f"SUPPKEY: {result['suppression_key']}")
    print(f"RATIONALE: {result['rationale']}")
    if result.get("_validation_warning"):
        print(f"WARNINGS: {result['_validation_warning']}")


if __name__ == "__main__":
    _self_test()
