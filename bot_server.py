"""
bot_server.py — HTTP server that the judge_simulator.py talks to.

Exposes 5 endpoints:
  GET  /v1/healthz       — health check
  GET  /v1/metadata      — team info
  POST /v1/context       — receive + store category/merchant/trigger contexts
  POST /v1/tick          — receive trigger IDs, return composed actions
  POST /v1/reply         — receive merchant reply, return next action

Run:
    python bot_server.py

Configure LLM via environment variables:
    set LLM_PROVIDER=gemini
    set LLM_API_KEY=your_key_here
    python bot_server.py
"""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8080))
TEAM_NAME = "ShortlistMe"
BOT_VERSION = "1.0.0"

# ─────────────────────────────────────────────────────────────────────────────
# IN-MEMORY CONTEXT STORE
# ─────────────────────────────────────────────────────────────────────────────

# Stores all context pushed via /v1/context
# structure: contexts["category"]["dentists"] = {...}
#            contexts["merchant"]["m_001_..."] = {...}
#            contexts["trigger"]["trg_001_..."] = {...}
#            contexts["customer"]["c_001_..."] = {...}
contexts: dict[str, dict] = {
    "category": {},
    "merchant": {},
    "trigger": {},
    "customer": {},
}

# Conversation states for multi-turn
conversation_states: dict = {}

# ─────────────────────────────────────────────────────────────────────────────
# LAZY IMPORTS (after sys.path is set)
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent))

from bot import compose
from compose_engine import llm_client
from conversation_handlers import (
    ConversationState,
    get_or_create_state,
    respond,
    is_auto_reply,
    detect_intent,
)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _json_response(handler, status: int, data: dict):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def _resolve_trigger_contexts(trigger: dict) -> tuple[Optional[dict], Optional[dict], Optional[dict]]:
    """Given a trigger dict, look up its merchant, category, and optional customer."""
    merchant_id = trigger.get("merchant_id") or trigger.get("payload", {}).get("merchant_id")
    customer_id = trigger.get("customer_id") or trigger.get("payload", {}).get("customer_id")

    merchant = contexts["merchant"].get(merchant_id) if merchant_id else None
    customer = contexts["customer"].get(customer_id) if customer_id else None

    category = None
    if merchant:
        cat_slug = merchant.get("category_slug", "")
        category = contexts["category"].get(cat_slug)

    return merchant, category, customer


def _compose_for_trigger(trigger_id: str) -> Optional[dict]:
    """Compose a message for one trigger. Returns action dict or None."""
    trigger = contexts["trigger"].get(trigger_id)
    if not trigger:
        return None

    merchant, category, customer = _resolve_trigger_contexts(trigger)
    if not merchant or not category:
        return None

    start = time.time()
    try:
        result = compose(category, merchant, trigger, customer)
    except Exception as e:
        print(f"  [WARN] compose failed for {trigger_id}: {e}", flush=True)
        return None

    elapsed = (time.time() - start) * 1000
    print(f"  [OK] {trigger_id[:40]} → {len(result.get('body',''))} chars ({elapsed:.0f}ms)", flush=True)

    return {
        "trigger_id": trigger_id,
        "merchant_id": merchant.get("merchant_id", ""),
        "customer_id": trigger.get("customer_id"),
        "body": result.get("body", ""),
        "cta": result.get("cta", "open_ended"),
        "send_as": result.get("send_as", "vera"),
        "suppression_key": result.get("suppression_key", trigger_id),
        "rationale": result.get("rationale", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST HANDLER
# ─────────────────────────────────────────────────────────────────────────────

class VeraHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Custom compact logging
        print(f"[{self.command}] {self.path} — {args[1] if len(args) > 1 else ''}", flush=True)

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/v1/healthz":
            _json_response(self, 200, {
                "status": "ok",
                "provider": llm_client.provider_name(),
                "contexts_loaded": {k: len(v) for k, v in contexts.items()},
            })

        elif path == "/v1/metadata":
            _json_response(self, 200, {
                "team_name": TEAM_NAME,
                "model": llm_client.provider_name(),
                "version": BOT_VERSION,
                "features": ["compose", "multi_turn", "auto_reply_detection", "intent_routing"],
            })

        else:
            _json_response(self, 404, {"error": "Not found"})

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        path = urlparse(self.path).path

        try:
            body = _read_body(self)
        except Exception as e:
            _json_response(self, 400, {"error": f"Bad request body: {e}"})
            return

        if path == "/v1/context":
            self._handle_context(body)
        elif path == "/v1/tick":
            self._handle_tick(body)
        elif path == "/v1/reply":
            self._handle_reply(body)
        else:
            _json_response(self, 404, {"error": "Not found"})

    # ── /v1/context ──────────────────────────────────────────────────────────

    def _handle_context(self, body: dict):
        scope = body.get("scope", "")        # "category" | "merchant" | "trigger" | "customer"
        context_id = body.get("context_id", "")
        payload = body.get("payload", {})

        if scope not in contexts:
            contexts[scope] = {}

        if context_id and payload:
            contexts[scope][context_id] = payload
            _json_response(self, 200, {"accepted": True, "scope": scope, "id": context_id})
        else:
            _json_response(self, 400, {"accepted": False, "error": "Missing context_id or payload"})

    # ── /v1/tick ─────────────────────────────────────────────────────────────

    def _handle_tick(self, body: dict):
        available_triggers = body.get("available_triggers", [])
        print(f"\n[TICK] {len(available_triggers)} trigger(s) received", flush=True)

        actions = []
        for trigger_id in available_triggers:
            action = _compose_for_trigger(trigger_id)
            if action:
                actions.append(action)

        _json_response(self, 200, {
            "actions": actions,
            "skipped": len(available_triggers) - len(actions),
        })

    # ── /v1/reply ────────────────────────────────────────────────────────────

    def _handle_reply(self, body: dict):
        conv_id = body.get("conversation_id", "default")
        merchant_id = body.get("merchant_id", "")
        customer_id = body.get("customer_id")
        message = body.get("message", "")
        turn = body.get("turn_number", 2)

        print(f"\n[REPLY] conv={conv_id} turn={turn} msg=\"{message[:60]}\"", flush=True)

        # Get or create conversation state
        state = get_or_create_state(conv_id, merchant_id)
        state.turn_number = turn
        state.customer_id = customer_id

        # Inject latest merchant context into state
        if merchant_id in contexts["merchant"]:
            merchant = contexts["merchant"][merchant_id]
            state.context_cache["merchant"] = merchant
            cat_slug = merchant.get("category_slug", "")
            if cat_slug in contexts["category"]:
                state.context_cache["category"] = contexts["category"][cat_slug]

        # Get the response
        result = respond(state, message)
        state.last_bot_body = result.get("body", "")

        print(f"[REPLY] action={result.get('action')} body=\"{result.get('body','')[:60]}\"", flush=True)
        _json_response(self, 200, result)


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────────────────────────────────────

def preload_dataset():
    """Optionally preload all dataset contexts at startup."""
    dataset_dir = Path(__file__).parent / "dataset"

    # Try expanded dataset first, fall back to seed files
    expanded = dataset_dir / "expanded"
    if expanded.exists():
        print("[PRELOAD] Loading expanded dataset...", flush=True)
        _load_expanded(expanded)
    else:
        print("[PRELOAD] Loading seed dataset (run dataset/generate_dataset.py for full dataset)...", flush=True)
        _load_seeds(dataset_dir)


def _load_expanded(expanded_dir: Path):
    # Categories
    for f in (expanded_dir / "categories").glob("*.json"):
        with open(f) as fp:
            data = json.load(fp)
            contexts["category"][data["slug"]] = data

    # Merchants
    merchants_dir = expanded_dir / "merchants"
    if merchants_dir.exists():
        for f in merchants_dir.glob("*.json"):
            with open(f) as fp:
                data = json.load(fp)
                contexts["merchant"][data["merchant_id"]] = data

    # Customers
    customers_dir = expanded_dir / "customers"
    if customers_dir.exists():
        for f in customers_dir.glob("*.json"):
            with open(f) as fp:
                data = json.load(fp)
                contexts["customer"][data["customer_id"]] = data

    # Triggers
    triggers_dir = expanded_dir / "triggers"
    if triggers_dir.exists():
        for f in triggers_dir.glob("*.json"):
            with open(f) as fp:
                data = json.load(fp)
                contexts["trigger"][data["id"]] = data

    print(
        f"[PRELOAD] categories={len(contexts['category'])} merchants={len(contexts['merchant'])} "
        f"customers={len(contexts['customer'])} triggers={len(contexts['trigger'])}",
        flush=True
    )


def _load_seeds(dataset_dir: Path):
    # Categories
    for f in (dataset_dir / "categories").glob("*.json"):
        with open(f) as fp:
            data = json.load(fp)
            contexts["category"][data["slug"]] = data

    # Seed merchants
    with open(dataset_dir / "merchants_seed.json") as fp:
        for m in json.load(fp)["merchants"]:
            contexts["merchant"][m["merchant_id"]] = m

    # Seed customers
    with open(dataset_dir / "customers_seed.json") as fp:
        for c in json.load(fp)["customers"]:
            contexts["customer"][c["customer_id"]] = c

    # Seed triggers
    with open(dataset_dir / "triggers_seed.json") as fp:
        for t in json.load(fp)["triggers"]:
            contexts["trigger"][t["id"]] = t

    print(
        f"[PRELOAD] categories={len(contexts['category'])} merchants={len(contexts['merchant'])} "
        f"customers={len(contexts['customer'])} triggers={len(contexts['trigger'])}",
        flush=True
    )


def main():
    print("=" * 60, flush=True)
    print(f"  Vera Bot Server v{BOT_VERSION}", flush=True)
    print(f"  Team: {TEAM_NAME}", flush=True)
    print(f"  LLM:  {llm_client.provider_name()}", flush=True)
    print(f"  Port: {PORT}", flush=True)
    print("=" * 60, flush=True)

    # Validate API key
    if llm_client.PROVIDER != "ollama" and not llm_client.API_KEY:
        print("\n[ERROR] LLM_API_KEY is not set!", flush=True)
        print("Set it via environment variable:", flush=True)
        print("  Windows:  set LLM_API_KEY=your_key_here", flush=True)
        print("  Linux/Mac: export LLM_API_KEY=your_key_here", flush=True)
        print("\nOr edit compose_engine/llm_client.py — set API_KEY directly.", flush=True)
        sys.exit(1)

    preload_dataset()

    server = HTTPServer((HOST, PORT), VeraHandler)
    print(f"\n[READY] Listening on http://localhost:{PORT}", flush=True)
    print("[READY] Run judge_simulator.py in another terminal\n", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP] Server stopped.", flush=True)


if __name__ == "__main__":
    main()
