"""Quick test — verifies prompt builder renders all 5 judge dimensions correctly."""
import json
from pathlib import Path
from compose_engine.trigger_router import get_strategy
from compose_engine.prompt_builder import build_prompt, SYSTEM_PROMPT

ds = Path("dataset")
category = json.loads((ds / "categories" / "dentists.json").read_text(encoding="utf-8"))
merchant  = json.loads((ds / "merchants_seed.json").read_text(encoding="utf-8"))["merchants"][0]
trigger   = json.loads((ds / "triggers_seed.json").read_text(encoding="utf-8"))["triggers"][0]

strategy = get_strategy(trigger["kind"])
prompt   = build_prompt(category, merchant, trigger, None, strategy)

print("=" * 60)
print("PROMPT RENDER CHECK")
print("=" * 60)

dims = ["DECISION QUALITY", "SPECIFICITY", "CATEGORY FIT", "MERCHANT FIT", "ENGAGEMENT"]
all_found = True
for d in dims:
    found = d in prompt
    if not found:
        all_found = False
    print(f"  [{'FOUND  ' if found else 'MISSING'}] {d}")

print(f"\nPrompt length : {len(prompt):,} chars")
print(f"System prompt : {len(SYSTEM_PROMPT):,} chars")
print(f"\nMerchant injected : {'Dr. Meera' in prompt}")
print(f"CTR vs peer       : {'vs peer' in prompt}")
print(f"Digest resolved   : {'d_2026W17_jida_fluoride' in prompt}")
print(f"Trigger payload   : {'high_risk_adult' in prompt or 'dentists' in prompt}")
print(f"Best signal field : {'best_signal' in SYSTEM_PROMPT}")
print(f"No fabricate rule : {'FABRICATE' in SYSTEM_PROMPT or 'fabricate' in SYSTEM_PROMPT}")

print("\n" + "=" * 60)
print("FIRST 500 CHARS OF PROMPT:")
print("=" * 60)
print(prompt[:500])
print("...")
print("\nALL OK!" if all_found else "\nWARNING: some dimensions missing from prompt!")
