"""
Prompt Builder — constructs the full LLM prompt from 4 contexts + strategy.
Targets all 5 judge scoring dimensions explicitly.
"""

import json
from typing import Optional
from .trigger_router import TriggerStrategy


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Vera — magicpin's merchant WhatsApp AI assistant.
You compose short, specific, high-engagement WhatsApp messages for Indian merchants.

You are scored on EXACTLY these 5 dimensions (each out of 10):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. DECISION QUALITY — Pick the BEST signal for this moment.
   Great outputs combine trigger + merchant state + category fit
   BEFORE writing. Show in best_signal which angle you chose and why.
   A perf_dip trigger + negative review theme = more powerful combined.

2. SPECIFICITY — Use real numbers, offers, dates, local facts.
   Anchor on 1+ verifiable fact from the data.
   "CTR 2.1% vs peer 3.0%" beats "your CTR is low".
   "Haircut @ Rs.99 since Mar 1" beats "you have an active offer".
   "38% lower, JIDA Oct 2026 p.14, n=2100" beats "new research".

3. CATEGORY FIT — Tone must match the business type exactly.
   Dentists: clinical, peer-to-peer, use "Dr. X", technical vocab OK.
   Salons: warm, visual, practical, booking-focused.
   Restaurants: operator-to-operator, timely, footfall/food specific.
   Gyms: coaching, motivational, retention/churn data-driven.
   Pharmacies: trustworthy, precise, compliance-first.

4. MERCHANT FIT — Personalize to THIS merchant's data and history.
   Use their name, city, actual CTR, real offer titles + prices.
   If they replied before: build on it, never restart the conversation.
   Honor language: Hindi-English mix when languages includes "hi".

5. ENGAGEMENT COMPULSION — One strong reason to reply NOW.
   Use exactly ONE compulsion lever per message:
   loss_aversion | curiosity | social_proof | effort_externalization
   Single low-effort CTA at the very last line.
   "Reply YES" / "Reply 1" / "Want to see?" — not multiple choices.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HARD RULES — violations lose points:
- No fabricated data. Only use numbers/names/dates from context.
- No generic % discounts. Use service+price: "Haircut @ Rs.99", not "20% off".
- No multiple CTAs. Exactly one at the very last line.
- No preambles: "I hope you are doing well..." — start with the hook.
- No re-introducing Vera after the first message.
- No verbatim repeat of a previous message.
- No TABOO words for the category (listed in context).

OUTPUT FORMAT — return ONLY valid JSON, no markdown fences:
{
  "best_signal": "<1 sentence: which signal angle you picked and why>",
  "body": "<the WhatsApp message text>",
  "cta": "<binary_yes_stop | open_ended | none>",
  "send_as": "<vera | merchant_on_behalf>",
  "suppression_key": "<string>",
  "rationale": "<1-2 sentences: what this achieves, which lever used>"
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL SCORER — surfaced before compose for Decision Quality
# ─────────────────────────────────────────────────────────────────────────────

def _signal_analysis(category: dict, merchant: dict, trigger: dict, customer: Optional[dict]) -> str:
    lines = []
    lines.append("## STEP 1 — DECISION QUALITY: PICK THE BEST SIGNAL")
    lines.append("Analyze all signals below. Choose the most powerful angle.")
    lines.append("")

    # Primary trigger
    lines.append(f"PRIMARY TRIGGER: kind={trigger.get('kind')} urgency={trigger.get('urgency')}/5 source={trigger.get('source')}")
    lines.append(f"  payload: {json.dumps(trigger.get('payload', {}), ensure_ascii=False)}")
    lines.append("")

    # Merchant state signals
    lines.append("MERCHANT STATE (combine with trigger for best angle):")
    signals = merchant.get("signals", [])
    for s in signals:
        lines.append(f"  signal: {s}")

    perf     = merchant.get("performance", {})
    peer     = category.get("peer_stats", {})
    m_ctr    = perf.get("ctr", 0)
    p_ctr    = peer.get("avg_ctr", 0)
    m_calls  = perf.get("calls", 0)
    p_calls  = peer.get("avg_calls_30d", 0)

    if p_ctr and m_ctr:
        gap = (m_ctr - p_ctr) / p_ctr * 100
        lines.append(f"  perf: CTR {m_ctr} vs peer {p_ctr} = {gap:+.0f}% vs peers")
    if p_calls and m_calls:
        gap = (m_calls - p_calls) / p_calls * 100
        lines.append(f"  perf: calls {m_calls}/mo vs peer avg {p_calls}/mo = {gap:+.0f}%")

    delta = perf.get("delta_7d", {})
    vp = delta.get("views_pct", 0) * 100
    cp = delta.get("calls_pct", 0) * 100
    if abs(vp) > 8:
        lines.append(f"  perf: views 7d trend {vp:+.0f}%")
    if abs(cp) > 8:
        lines.append(f"  perf: calls 7d trend {cp:+.0f}%")

    for rt in merchant.get("review_themes", []):
        sent = rt.get("sentiment", "?")
        cq = rt.get("common_quote", "")
        q = f' — quote: "{cq}"' if cq else ""
        lines.append(f"  review [{sent.upper()}]: {rt.get('theme')} x{rt.get('occurrences_30d')}/30d{q}")

    history = merchant.get("conversation_history", [])
    if history:
        last = history[-1]
        lines.append(f"  last_conv: from={last.get('from')} engagement={last.get('engagement')} body={last.get('body','')[:80]}")

    sub = merchant.get("subscription", {})
    if sub.get("days_remaining") and sub["days_remaining"] < 30:
        lines.append(f"  subscription: EXPIRING in {sub['days_remaining']} days")
    if sub.get("days_since_expiry"):
        lines.append(f"  subscription: EXPIRED {sub['days_since_expiry']} days ago")

    if customer:
        lines.append(f"  customer: {customer.get('identity',{}).get('name')} state={customer.get('state')} visits={customer.get('relationship',{}).get('visits_total')}")

    beats = category.get("seasonal_beats", [])
    if beats:
        lines.append(f"  seasonal: {beats[0].get('note')}")

    cust_agg = merchant.get("customer_aggregate", {})
    if cust_agg.get("lapsed_180d_plus"):
        lines.append(f"  customers: {cust_agg['lapsed_180d_plus']} lapsed 180d+")
    if cust_agg.get("lapsed_90d_plus"):
        lines.append(f"  customers: {cust_agg['lapsed_90d_plus']} lapsed 90d+")

    lines.append("")
    lines.append("-> PICK the single angle that combines trigger + merchant state + category most powerfully.")
    lines.append("-> Write your choice in best_signal. Then write body anchored on that angle.")
    lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict],
    strategy: TriggerStrategy,
) -> str:
    parts = []

    # ── STEP 1: DECISION QUALITY ──────────────────────────────────────────────
    parts.append(_signal_analysis(category, merchant, trigger, customer))

    # ── STEP 2: FULL CONTEXT ─────────────────────────────────────────────────
    parts.append("## STEP 2 — FULL CONTEXT (use only data from here, no fabrication)")
    parts.append("")

    # CATEGORY
    parts.append("### CATEGORY CONTEXT")
    voice = category.get("voice", {})
    parts.append(f"Category: {category.get('display_name', category.get('slug'))}")
    parts.append(f"Tone: {voice.get('tone')} | Register: {voice.get('register')} | Code-mix: {voice.get('code_mix')}")

    allowed = voice.get("vocab_allowed", [])
    if allowed:
        parts.append(f"Vocab ALLOWED: {', '.join(allowed[:10])}")
    taboo = voice.get("vocab_taboo", [])
    if taboo:
        parts.append(f"TABOO words (never use): {', '.join(taboo)}")
    examples = voice.get("tone_examples", [])
    if examples:
        parts.append(f"Tone examples: {' | '.join(examples[:2])}")
    salutations = voice.get("salutation_examples", [])
    if salutations:
        parts.append(f"Salutation: {', '.join(salutations)}")

    peer = category.get("peer_stats", {})
    if peer:
        parts.append(f"\nPeer benchmarks ({peer.get('scope', 'national')}):")
        parts.append(
            f"  avg_ctr={peer.get('avg_ctr')} | avg_calls={peer.get('avg_calls_30d')}/mo"
            f" | avg_views={peer.get('avg_views_30d')}/mo | avg_reviews={peer.get('avg_review_count')}"
            f" | avg_post_freq=every {peer.get('avg_post_freq_days')} days"
        )

    digest = category.get("digest", [])
    if digest:
        parts.append(f"\nCategory digest ({len(digest)} items):")
        for item in digest:
            line = f"  [{item.get('id')}] [{item.get('kind','').upper()}] {item.get('title','')}"
            if item.get("source"):
                line += f" | Source: {item['source']}"
            if item.get("trial_n"):
                line += f" | N={item['trial_n']}"
            parts.append(line)
            if item.get("summary"):
                parts.append(f"    Summary: {item['summary']}")
            if item.get("actionable"):
                parts.append(f"    Action: {item['actionable']}")
            if item.get("date"):
                parts.append(f"    Date/Time: {item['date']}")

    beats = category.get("seasonal_beats", [])
    if beats:
        beats_str = " | ".join([f"{b.get('month_range')}: {b.get('note')}" for b in beats])
        parts.append(f"\nSeasonal beats: {beats_str}")

    trends = category.get("trend_signals", [])
    if trends:
        trends_str = " | ".join([f"{t.get('query')} +{t.get('delta_yoy',0)*100:.0f}%YoY (age {t.get('segment_age')})" for t in trends[:3]])
        parts.append(f"Trend signals: {trends_str}")

    parts.append("")

    # MERCHANT
    parts.append("### MERCHANT CONTEXT")
    identity = merchant.get("identity", {})
    langs = identity.get("languages", ["en"])
    parts.append(
        f"Name: {identity.get('name')} | Owner: {identity.get('owner_first_name')}"
        f" | {identity.get('locality')}, {identity.get('city')}"
        f" | Verified GBP: {identity.get('verified')} | Est: {identity.get('established_year')}"
    )
    parts.append(f"Languages: {', '.join(langs)}" + (" -> USE Hindi-English code-mix naturally" if "hi" in langs else ""))

    sub = merchant.get("subscription", {})
    parts.append(f"\nSubscription: status={sub.get('status')} | plan={sub.get('plan')} | days_remaining={sub.get('days_remaining', 'N/A')}")
    if sub.get("days_since_expiry"):
        parts.append(f"  days_since_expiry={sub['days_since_expiry']}")

    perf = merchant.get("performance", {})
    if perf:
        p_ctr   = category.get("peer_stats", {}).get("avg_ctr", 0)
        p_calls = category.get("peer_stats", {}).get("avg_calls_30d", 0)
        m_ctr   = perf.get("ctr", 0)
        m_calls = perf.get("calls", 0)
        ctr_note   = f" ({(m_ctr-p_ctr)/p_ctr*100:+.0f}% vs peer)" if p_ctr else ""
        calls_note = f" ({(m_calls-p_calls)/p_calls*100:+.0f}% vs peer)" if p_calls else ""
        delta = perf.get("delta_7d", {})
        parts.append(
            f"\nPerformance (30d): views={perf.get('views')} | calls={perf.get('calls')}{calls_note}"
            f" | directions={perf.get('directions')} | ctr={perf.get('ctr')}{ctr_note} | leads={perf.get('leads')}"
        )
        if delta:
            parts.append(f"  7d delta: views={delta.get('views_pct',0)*100:+.0f}% | calls={delta.get('calls_pct',0)*100:+.0f}%")

    offers = merchant.get("offers", [])
    active_offers  = [o for o in offers if o.get("status") == "active"]
    expired_offers = [o for o in offers if o.get("status") == "expired"]
    if active_offers:
        active_str = " | ".join([f"{o['title']} (since {o.get('started','?')})" for o in active_offers])
        parts.append(f"\nActive offers: {active_str}")
    if expired_offers:
        expired_str = " | ".join([f"{o['title']} (ended {o.get('ended','?')})" for o in expired_offers[:3]])
        parts.append(f"Expired offers: {expired_str}")
    if not active_offers:
        catalog = category.get("offer_catalog", [])
        if catalog:
            parts.append(f"\nNo active offers. Category catalog options:")
            for o in catalog[:3]:
                parts.append(f"  {o.get('title')} (audience: {o.get('audience')})")

    cust_agg = merchant.get("customer_aggregate", {})
    if cust_agg:
        parts.append(f"\nCustomer aggregate: {json.dumps(cust_agg, ensure_ascii=False)}")

    signals = merchant.get("signals", [])
    if signals:
        parts.append(f"\nDerived signals: {', '.join(signals)}")

    themes = merchant.get("review_themes", [])
    if themes:
        parts.append("\nReview themes:")
        for rt in themes:
            cq = rt.get("common_quote", "")
            q = f' Quote: "{cq}"' if cq else ""
            parts.append(f"  [{rt.get('sentiment','?').upper()}] {rt.get('theme')}: {rt.get('occurrences_30d')} mentions/30d.{q}")

    history = merchant.get("conversation_history", [])
    if history:
        parts.append(f"\nConversation history ({len(history)} turns) — DO NOT repeat, DO NOT re-introduce Vera:")
        for turn in history[-4:]:
            eng = f" [{turn.get('engagement')}]" if turn.get("engagement") else ""
            parts.append(f"  {turn.get('from','?').upper()}{eng}: {turn.get('body','')[:150]}")

    parts.append("")

    # TRIGGER
    parts.append("### TRIGGER CONTEXT")
    parts.append(
        f"id={trigger.get('id')} | kind={trigger.get('kind')} | scope={trigger.get('scope')}"
        f" | source={trigger.get('source')} | urgency={trigger.get('urgency')}/5 | expires={trigger.get('expires_at')}"
    )
    parts.append(f"\nTrigger payload:\n{json.dumps(trigger.get('payload', {}), indent=2, ensure_ascii=False)}")

    # Resolve digest reference
    payload = trigger.get("payload", {})
    ref_id = payload.get("top_item_id") or payload.get("digest_item_id") or payload.get("alert_id")
    if ref_id:
        for item in category.get("digest", []):
            if item.get("id") == ref_id:
                parts.append(f"\nRESOLVED DIGEST ITEM '{ref_id}':\n{json.dumps(item, indent=2, ensure_ascii=False)}")
                break

    parts.append("")

    # CUSTOMER
    if customer:
        parts.append("### CUSTOMER CONTEXT (message is sent FROM merchant TO this customer)")
        cid  = customer.get("identity", {})
        rel  = customer.get("relationship", {})
        pref = customer.get("preferences", {})
        con  = customer.get("consent", {})
        parts.append(f"Name: {cid.get('name')} | Language: {cid.get('language_pref')} | Age: {cid.get('age_band')}")
        parts.append(f"State: {customer.get('state')} | Visits: {rel.get('visits_total')} | LTV: Rs.{rel.get('lifetime_value')}")
        parts.append(f"First visit: {rel.get('first_visit')} | Last visit: {rel.get('last_visit')}")
        svcs = rel.get("services_received", [])
        if svcs:
            parts.append(f"Services: {', '.join(str(s) for s in svcs[:6])}")
        if pref.get("preferred_slots"):
            parts.append(f"Preferred slots: {pref['preferred_slots']}")
        if rel.get("favourite_dish"):
            parts.append(f"Favourite: {rel['favourite_dish']}")
        if rel.get("chronic_conditions"):
            parts.append(f"Chronic conditions: {', '.join(rel['chronic_conditions'])}")
        parts.append(f"Consent scope: {', '.join(con.get('scope', []))}")
        parts.append("")

    # STRATEGY
    parts.append("### COMPOSITION STRATEGY")
    parts.append(f"Framing: {strategy['framing']}")
    parts.append(f"Compulsion lever: {', '.join(strategy['compulsion_levers'][:2])}")
    parts.append(f"CTA style: {strategy['cta_style']}")
    parts.append(f"Voice note: {strategy['voice_note']}")
    parts.append("")

    # STEP 3: WRITE
    is_customer_facing = trigger.get("scope") == "customer" or customer is not None
    send_as = "merchant_on_behalf" if is_customer_facing else "vera"

    parts.append("## STEP 3 — COMPOSE THE MESSAGE")
    parts.append(f"send_as='{send_as}' | cta_style='{strategy['cta_style']}'")
    parts.append("")
    parts.append("Self-check before responding:")
    parts.append("  [DECISION QUALITY] Did I combine trigger + merchant state + category for the sharpest angle?")
    parts.append("  [SPECIFICITY] Does my message contain >=1 real number / date / price / source?")
    parts.append(f"  [CATEGORY FIT] Is the tone right for '{category.get('slug')}'? No taboo words?")
    parts.append("  [MERCHANT FIT] Did I use their actual name, locality, real CTR, real offer title?")
    parts.append("  [ENGAGEMENT] Is there exactly ONE low-effort CTA at the very last line?")
    parts.append("")
    parts.append("Return ONLY valid JSON — no markdown, no text outside the JSON.")

    return "\n".join(parts)
