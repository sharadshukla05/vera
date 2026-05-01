"""
Validator — post-LLM checks and fixes on composed messages.
Catches anti-patterns before they reach the judge.
"""

import re
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# ANTI-PATTERN DETECTORS
# ─────────────────────────────────────────────────────────────────────────────

PREAMBLE_PATTERNS = [
    r"i hope (you('re| are)|this message)",
    r"i'm reaching out",
    r"i am reaching out",
    r"hope you('re| are) doing well",
    r"just wanted to (reach out|check in|follow up)",
    r"^hi [^,]+, (i hope|hope)",
]

GENERIC_DISCOUNT_PATTERNS = [
    r"\bflat \d+%\s*off\b",
    r"\b\d+%\s*discount\b",
    r"\bup to \d+%\s*off\b",
    r"\bget \d+%\s*off\b",
]

MULTIPLE_CTA_PATTERNS = [
    r"reply (yes|1) for .+reply (no|2) for",
    r"(option 1|option 2|option 3)",
    r"(reply a|reply b|reply c)\b",
]

HYPE_PATTERNS = [
    r"amazing deal",
    r"incredible offer",
    r"don't miss out!!!",
    r"limited time only!!!",
    r"act now!!!",
]

# Taboo words by category
CATEGORY_TABOOS = {
    "dentists":   ["guaranteed", "100% safe", "completely cure", "miracle", "best in city"],
    "salons":     ["guaranteed results", "miracle treatment"],
    "gyms":       ["guaranteed weight loss", "100% results"],
    "pharmacies": ["cure", "guaranteed cure", "miracle drug"],
    "restaurants": [],
}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def validate_and_fix(
    result: dict,
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict] = None,
) -> dict:
    """
    Validate the LLM output and fix common issues.
    Returns the (possibly corrected) result dict.
    """
    result = dict(result)  # don't mutate input
    body = result.get("body", "")
    category_slug = category.get("slug", "")
    # Preserve Decision Quality reasoning field
    if not result.get("best_signal"):
        result["best_signal"] = ""

    # ── 1. ENSURE REQUIRED KEYS ───────────────────────────────────────────────
    is_customer_scope = trigger.get("scope") == "customer" or customer is not None
    result.setdefault("cta", "open_ended")
    result.setdefault("send_as", "merchant_on_behalf" if is_customer_scope else "vera")
    result.setdefault("suppression_key", trigger.get("suppression_key", f"{trigger.get('id', 'unknown')}:composed"))
    result.setdefault("rationale", "Message composed from trigger context.")

    # ── 2. FIX send_as BASED ON SCOPE ────────────────────────────────────────
    if is_customer_scope:
        result["send_as"] = "merchant_on_behalf"
    else:
        result["send_as"] = "vera"

    # ── 3. DETECT AND STRIP PREAMBLES ────────────────────────────────────────
    body_lower = body.lower()
    for pattern in PREAMBLE_PATTERNS:
        if re.search(pattern, body_lower):
            # Strip the preamble sentence
            sentences = body.split(". ")
            if len(sentences) > 1:
                body = ". ".join(sentences[1:]).strip()
                break

    # ── 4. WARN ON GENERIC DISCOUNTS (log only, don't auto-fix as could change meaning) ──
    for pattern in GENERIC_DISCOUNT_PATTERNS:
        if re.search(pattern, body_lower):
            # If there's a service+price alternative, prefer it — but we can't auto-fix safely
            # Just add a note to rationale
            result["_validation_warning"] = result.get("_validation_warning", "") + "[generic_discount_detected]"

    # ── 5. CHECK CATEGORY TABOOS ────────────────────────────────────────────
    taboos = CATEGORY_TABOOS.get(category_slug, [])
    for taboo in taboos:
        if taboo.lower() in body_lower:
            result["_validation_warning"] = result.get("_validation_warning", "") + f"[taboo:{taboo}]"

    # ── 6. NORMALIZE CTA ────────────────────────────────────────────────────
    cta = result.get("cta", "").lower().strip()
    valid_ctas = {"binary_yes_stop", "binary", "open_ended", "none"}
    if cta not in valid_ctas:
        # Try to infer from body
        if "reply yes" in body_lower or "reply 1" in body_lower:
            result["cta"] = "binary_yes_stop"
        elif "?" in body:
            result["cta"] = "open_ended"
        else:
            result["cta"] = "none"
    # Normalize "binary" → "binary_yes_stop"
    if result.get("cta") == "binary":
        result["cta"] = "binary_yes_stop"

    # ── 7. BODY LENGTH CHECK ────────────────────────────────────────────────
    if len(body) > 800:
        # Truncate at sentence boundary
        truncated = body[:800]
        last_period = truncated.rfind(". ")
        if last_period > 400:
            body = truncated[:last_period + 1]

    # ── 8. CHECK FOR EMPTY BODY ─────────────────────────────────────────────
    if not body or len(body.strip()) < 10:
        body = _fallback_body(category, merchant, trigger, customer)
        result["_validation_warning"] = result.get("_validation_warning", "") + "[fallback_body_used]"

    result["body"] = body.strip()
    return result


def _fallback_body(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict],
) -> str:
    """Generate a minimal fallback message if LLM returned empty/invalid body."""
    merchant_name = merchant.get("identity", {}).get("name", "your business")
    owner = merchant.get("identity", {}).get("owner_first_name", "")
    trigger_kind = trigger.get("kind", "update")
    cat = category.get("display_name", "business")

    if customer:
        cust_name = customer.get("identity", {}).get("name", "")
        return f"Hi {cust_name}, this is a reminder from {merchant_name}. We'd love to see you again. Reply YES to book."

    if "renewal" in trigger_kind or "winback" in trigger_kind:
        days = merchant.get("subscription", {}).get("days_remaining", "a few")
        return f"{owner or merchant_name}, your magicpin subscription has {days} days left. Your profile visibility pauses when it lapses — want to renew? Reply YES."

    if "perf_dip" in trigger_kind:
        calls = merchant.get("performance", {}).get("calls", "?")
        return f"{owner or merchant_name}, calls from your profile dropped last week (currently {calls}/month). Want me to look at what changed? Reply YES."

    return f"{owner or merchant_name}, quick update on your {cat} profile — want the details? Reply YES."
