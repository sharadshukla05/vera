"""
conversation_handlers.py — Multi-turn conversation handler (tiebreaker feature).

Implements:
- Auto-reply detection
- Intent transition (merchant says YES → action mode)
- Hostile / not-interested → graceful exit
- Generic follow-up composition
"""

import re
import json
from typing import Optional
from pathlib import Path
from dataclasses import dataclass, field

from compose_engine import llm_client
from compose_engine.prompt_builder import SYSTEM_PROMPT


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATION STATE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    turn_number: int = 1
    auto_reply_count: int = 0
    last_bot_body: str = ""
    last_topic: str = ""
    merchant_history: list = field(default_factory=list)  # list of {"from": "merchant"|"vera", "body": str}
    context_cache: dict = field(default_factory=dict)     # category, merchant, trigger dicts


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-REPLY DETECTION
# ─────────────────────────────────────────────────────────────────────────────

AUTO_REPLY_PHRASES = [
    "thank you for contacting",
    "thanks for contacting",
    "thank you for reaching out",
    "our team will get back",
    "our team will respond",
    "we will get back to you",
    "we'll get back to you",
    "automated response",
    "automated assistant",
    "automated message",
    "i am an automated",
    "i'm an automated",
    "this is an automated",
    "aapki jaankari ke liye bahut-bahut shukriya",
    "main aapki yeh sabhi baatein",
    "team tak pahuncha deti",
    "shukriya. main aapki",
    "sorry i am busy",
    "currently unavailable",
    "will contact you shortly",
]


def is_auto_reply(message: str) -> bool:
    """Detect if a merchant message is a canned auto-reply."""
    msg_lower = message.lower().strip()
    for phrase in AUTO_REPLY_PHRASES:
        if phrase in msg_lower:
            return True
    # Very short generic acknowledgements that contain no specifics
    generic_ack = re.match(
        r'^(ok|okay|thanks|thank you|noted|sure|got it|theek hai|achha|shukriya)[.!\s]*$',
        msg_lower
    )
    if generic_ack and len(msg_lower) < 20:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# INTENT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

ACTION_INTENT_PHRASES = [
    "yes", "ok let", "ok, let", "okay let", "lets do it", "let's do it",
    "go ahead", "proceed", "confirm", "do it", "haan", "ha ji", "bilkul",
    "sounds good", "please do", "sure go ahead", "yes please", "ji haan",
    "kar lo", "kar do", "aage badho", "chalo karte", "theek hai karo",
    "what's next", "whats next", "next step", "what next",
]

NOT_INTERESTED_PHRASES = [
    "stop", "not interested", "remove me", "unsubscribe", "don't message",
    "dont message", "no thanks", "nahi chahiye", "band karo", "mat bhejo",
    "spam", "useless", "waste", "block", "stop messaging", "please stop",
    "not relevant", "not useful",
]

QUESTION_PATTERNS = [
    r"\?$",
    r"^(what|how|why|when|where|which|who)\b",
    r"^(kya|kaise|kyun|kab|kahan|kaun)\b",
    r"^(batao|bataiye|samjhao)\b",
    r"\b(tell me|explain|show me|what is|how does|how do)\b",
]


def detect_intent(message: str) -> str:
    """
    Returns: "action" | "not_interested" | "question" | "neutral"
    """
    msg_lower = message.lower().strip()

    for phrase in NOT_INTERESTED_PHRASES:
        if phrase in msg_lower:
            return "not_interested"

    for phrase in ACTION_INTENT_PHRASES:
        if phrase in msg_lower:
            return "action"

    for pattern in QUESTION_PATTERNS:
        if re.search(pattern, msg_lower):
            return "question"

    return "neutral"


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def _exit_response(reason: str) -> dict:
    """Graceful exit response."""
    if reason == "auto_reply":
        body = "Koi baat nahi — main owner/manager se directly connect kar lungi jab convenient ho. 🙂"
    elif reason == "not_interested":
        body = "Samajh gaya. Aage nahi bhejoonga. Jab bhi koi cheez chahiye, aap connect kar sakte ho. 🙂"
    else:
        body = "Theek hai, main yahan hoon jab zarurat ho. 🙂"

    return {
        "action": "end",
        "body": body,
        "cta": "none",
        "send_as": "vera",
    }


def _wait_response(wait_seconds: int = 3600) -> dict:
    """Wait and try again later."""
    return {
        "action": "wait",
        "wait_seconds": wait_seconds,
        "body": "",
        "cta": "none",
        "send_as": "vera",
    }


def _action_mode_response(state: ConversationState, merchant_message: str) -> dict:
    """Merchant said YES — jump to concrete next action."""
    merchant = state.context_cache.get("merchant", {})
    owner = merchant.get("identity", {}).get("owner_first_name", "")
    name = merchant.get("identity", {}).get("name", "your business")
    topic = state.last_topic or "your profile"

    # Try LLM for a good action-mode response
    system = SYSTEM_PROMPT
    prompt = f"""## SITUATION
The merchant just confirmed they want to proceed. Switch to ACTION MODE immediately.
DO NOT ask qualifying questions. Jump to the concrete next step.

Merchant said: "{merchant_message}"
Last bot message was about: "{topic}"
Merchant: {owner or name}
Last bot message: "{state.last_bot_body[:200]}"

## TASK
Reply confirming you're on it / what you're doing right now / what they'll see next.
Be concrete and specific. Max 2-3 sentences.
Use Hindi-English mix if appropriate.

Return JSON: {{"body": "...", "cta": "none", "send_as": "vera"}}"""

    try:
        result = llm_client.complete_json(prompt, system)
        result["action"] = "send"
        return result
    except Exception:
        body = f"Perfect {owner}! Main abhi {topic} set up kar rahi hoon. Aapko 5 minute mein update milega. ✅"
        return {"action": "send", "body": body, "cta": "none", "send_as": "vera"}


def _question_response(state: ConversationState, merchant_message: str) -> dict:
    """Merchant asked a question — answer it from context."""
    merchant = state.context_cache.get("merchant", {})
    category = state.context_cache.get("category", {})
    owner = merchant.get("identity", {}).get("owner_first_name", "")

    system = SYSTEM_PROMPT
    prompt = f"""## SITUATION
The merchant asked a follow-up question. Answer it specifically from the context.

Merchant question: "{merchant_message}"
Merchant: {owner or merchant.get('identity', {}).get('name', '?')}
Category: {category.get('display_name', '?')}
Merchant performance: {json.dumps(merchant.get('performance', {}), ensure_ascii=False)}
Active offers: {[o['title'] for o in merchant.get('offers', []) if o.get('status') == 'active']}
Signals: {merchant.get('signals', [])}
Conversation context: {state.last_topic}

## TASK  
Answer the merchant's question directly. Be specific. Max 3 sentences.
End with a light follow-up question or a next step.
Use Hindi-English mix if appropriate.

Return JSON: {{"body": "...", "cta": "open_ended", "send_as": "vera"}}"""

    try:
        result = llm_client.complete_json(prompt, system)
        result["action"] = "send"
        return result
    except Exception:
        return {
            "action": "send",
            "body": f"Achha sawaal {owner}! Main details check karke turant bata deti hoon.",
            "cta": "open_ended",
            "send_as": "vera",
        }


def _neutral_followup(state: ConversationState, merchant_message: str) -> dict:
    """Neutral merchant message — compose a contextual follow-up."""
    merchant = state.context_cache.get("merchant", {})
    category = state.context_cache.get("category", {})
    owner = merchant.get("identity", {}).get("owner_first_name", "")

    system = SYSTEM_PROMPT
    prompt = f"""## SITUATION
Continue a merchant conversation naturally. Do NOT re-introduce Vera.
DO NOT repeat what was already said.

Merchant message: "{merchant_message}"
Previous bot message: "{state.last_bot_body[:200]}"
Topic so far: "{state.last_topic}"
Turn number: {state.turn_number}
Merchant: {owner or merchant.get('identity', {}).get('name', '?')}
Category: {category.get('display_name', '?')}
Signals: {merchant.get('signals', [])}

## TASK
Write a SHORT follow-up (2-3 sentences max). Move the conversation forward.
If you've nudged twice with no action, offer to leave them to it gracefully.
Use Hindi-English mix if appropriate.

Return JSON: {{"body": "...", "cta": "open_ended", "send_as": "vera"}}"""

    try:
        result = llm_client.complete_json(prompt, system)
        result["action"] = "send"
        return result
    except Exception:
        return {
            "action": "send",
            "body": f"Noted {owner}! Koi aur help chahiye to bata dena. 🙂",
            "cta": "none",
            "send_as": "vera",
        }


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────────────────────────

def respond(state: ConversationState, merchant_message: str) -> dict:
    """
    Given the conversation state + latest merchant message, produce a reply.

    Returns dict with keys: action, body, cta, send_as
    action: "send" | "wait" | "end"
    """
    state.turn_number += 1
    state.merchant_history.append({"from": "merchant", "body": merchant_message})

    # ── AUTO-REPLY CHECK ─────────────────────────────────────────────────────
    if is_auto_reply(merchant_message):
        state.auto_reply_count += 1
        if state.auto_reply_count >= 2:
            # Second auto-reply → exit
            return _exit_response("auto_reply")
        else:
            # First auto-reply → try once more with a direct human appeal
            merchant = state.context_cache.get("merchant", {})
            owner = merchant.get("identity", {}).get("owner_first_name", "")
            body = f"Samajh gayi — yeh auto-reply lag raha hai. {owner or 'Owner'} ji, main aapko directly 1 baat share karna chahti thi. 2 min? Reply haan ya naa mein. 🙏"
            return {
                "action": "send",
                "body": body,
                "cta": "binary_yes_stop",
                "send_as": "vera",
            }

    # ── INTENT DETECTION ─────────────────────────────────────────────────────
    intent = detect_intent(merchant_message)

    if intent == "not_interested":
        return _exit_response("not_interested")

    if intent == "action":
        result = _action_mode_response(state, merchant_message)
        state.last_bot_body = result.get("body", "")
        return result

    if intent == "question":
        result = _question_response(state, merchant_message)
        state.last_bot_body = result.get("body", "")
        return result

    # ── NEUTRAL / DEFAULT ────────────────────────────────────────────────────
    # After 3 unanswered nudges, gracefully exit
    if state.turn_number > 6 and state.auto_reply_count == 0:
        merchant = state.context_cache.get("merchant", {})
        owner = merchant.get("identity", {}).get("owner_first_name", "")
        return {
            "action": "end",
            "body": f"Sab clear {owner}! Baad mein kisi time connect karte hain. 🙂",
            "cta": "none",
            "send_as": "vera",
        }

    result = _neutral_followup(state, merchant_message)
    state.last_bot_body = result.get("body", "")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATION STATE REGISTRY (used by bot_server.py)
# ─────────────────────────────────────────────────────────────────────────────

_conversations: dict[str, ConversationState] = {}


def get_or_create_state(conversation_id: str, merchant_id: str) -> ConversationState:
    if conversation_id not in _conversations:
        _conversations[conversation_id] = ConversationState(
            conversation_id=conversation_id,
            merchant_id=merchant_id,
        )
    return _conversations[conversation_id]


def update_state_context(conversation_id: str, scope: str, context_id: str, payload: dict):
    """Update the context cache for an existing conversation."""
    for state in _conversations.values():
        if state.merchant_id == context_id and scope == "merchant":
            state.context_cache["merchant"] = payload
