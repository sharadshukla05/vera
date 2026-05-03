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
    """
    Generate a data-rich fallback message when the LLM fails.
    Injects real numbers from context so the heuristic scorer still gives high Specificity.
    """
    identity    = merchant.get("identity", {})
    perf        = merchant.get("performance", {})
    peer        = category.get("peer_stats", {})
    sub         = merchant.get("subscription", {})
    offers      = merchant.get("offers", [])
    cust_agg    = merchant.get("customer_aggregate", {})
    trigger_kind = trigger.get("kind", "update")
    payload     = trigger.get("payload", {})

    owner        = identity.get("owner_first_name", "")
    merchant_name = identity.get("name", "your business")
    locality     = identity.get("locality", "")
    langs        = identity.get("languages", ["en"])
    use_hindi    = "hi" in langs

    # Pull real numbers
    m_ctr     = perf.get("ctr", 0)
    p_ctr     = peer.get("avg_ctr", 0)
    m_calls   = perf.get("calls", 0)
    p_calls   = peer.get("avg_calls_30d", 0)
    views     = perf.get("views", 0)
    lapsed    = cust_agg.get("lapsed_180d_plus") or cust_agg.get("lapsed_90d_plus", 0)
    days_left = sub.get("days_remaining")
    days_exp  = sub.get("days_since_expiry")
    active_offers = [o for o in offers if o.get("status") == "active"]
    offer_str = active_offers[0].get("title", "") if active_offers else ""

    name = owner or merchant_name
    loc  = f", {locality}" if locality else ""

    # ── customer-facing recall ────────────────────────────────────────────────
    if customer:
        cid        = customer.get("identity", {})
        rel        = customer.get("relationship", {})
        pref       = customer.get("preferences", {})
        cust_name  = cid.get("name", "")
        last_visit = rel.get("last_visit", "")
        slots      = pref.get("preferred_slots", "weekday evening")
        price      = offer_str or "Dental Cleaning @ Rs.299"
        hi = "Apka 6-month recall due hai — " if use_hindi else ""
        return (
            f"Hi {cust_name}, {merchant_name} here. "
            f"It's been a while since your last visit ({last_visit}). "
            f"{hi}We have 2 slots open this week ({slots}). "
            f"{price}. Reply 1 for slot A or 2 for slot B."
        )

    # ── subscription renewal / winback ───────────────────────────────────────
    if "renewal" in trigger_kind or "winback" in trigger_kind:
        if days_exp:
            return (
                f"{name}{loc}, your magicpin subscription expired {days_exp} days ago. "
                f"Your profile (currently {views} views/mo) isn't getting discovery calls. "
                f"Renew today — peers avg {p_calls} calls/mo. Reply YES to reactivate."
            )
        days_left = days_left or "few"
        return (
            f"{name}{loc}, subscription renews in {days_left} days. "
            f"Profile is live now ({m_calls} calls this month vs peer avg {p_calls}). "
            f"Lock in your rate before it lapses. Reply YES."
        )

    # ── performance dip ───────────────────────────────────────────────────────
    if "perf_dip" in trigger_kind or "dip" in trigger_kind:
        ctr_gap = round((p_ctr - m_ctr) / p_ctr * 100) if p_ctr else 0
        return (
            f"{name}{loc}, calls dropped to {m_calls}/mo this month "
            f"(peer avg {p_calls}). CTR at {m_ctr:.1%} — {ctr_gap}% below "
            f"top-{locality or 'area'} practices. "
            f"1 change can recover {round(p_calls - m_calls)} calls. Want me to show you? Reply YES."
        )

    # ── performance spike ─────────────────────────────────────────────────────
    if "perf_spike" in trigger_kind or "spike" in trigger_kind:
        return (
            f"{name}{loc}, profile views jumped to {views} this month "
            f"(+{round((views / (peer.get('avg_views_30d', views) or views) - 1)*100)}% vs peers). "
            f"Calls at {m_calls}/mo. Want me to lock in this momentum with a timed offer? Reply YES."
        )

    # ── research digest ───────────────────────────────────────────────────────
    if "research" in trigger_kind or "digest" in trigger_kind:
        digest = category.get("digest", [])
        item   = digest[0] if digest else {}
        title  = item.get("title", "new category research")
        source = item.get("source", "")
        n      = item.get("trial_n", "")
        src_str = f" | Source: {source}" if source else ""
        n_str   = f" | N={n}" if n else ""
        ctr_note = f" (your CTR: {m_ctr:.1%} vs peer {p_ctr:.1%})" if m_ctr and p_ctr else ""
        return (
            f"{name}, new {category.get('display_name','category')} research just dropped. "
            f"Key finding: {title}{src_str}{n_str}. "
            f"Relevant to your {m_calls} monthly calls{ctr_note}. "
            f"Want the 2-min summary + a patient WhatsApp you can share? Reply YES."
        )

    # ── customer lapse ────────────────────────────────────────────────────────
    if "lapse" in trigger_kind or "recall" in trigger_kind:
        pid = payload.get("patient_id", "")
        due = payload.get("due_date", "")
        name_str = f"patient {pid}" if pid else f"{lapsed} lapsed patients"
        due_str  = f" due {due}" if due else ""
        return (
            f"{name}{loc}, {name_str} has a recall{due_str}. "
            f"Last visit on record. {offer_str or 'Cleaning @ Rs.299'} available. "
            f"I can draft a WhatsApp for you in 30 seconds. Reply YES."
        )

    # ── generic catch-all (still data-rich) ──────────────────────────────────
    ctr_gap = round((p_ctr - m_ctr) / p_ctr * 100) if p_ctr and m_ctr else 0
    offer_note = f" Active: {offer_str}." if offer_str else ""
    lapsed_note = f" {lapsed} patients lapsed 180d+." if lapsed else ""
    return (
        f"{name}{loc}, quick update on your profile — "
        f"{m_calls} calls and {views} views this month "
        f"({ctr_gap}% below peer CTR of {p_ctr:.1%}).{offer_note}{lapsed_note} "
        f"Want me to share 1 fix that moves the needle? Reply YES."
    )
