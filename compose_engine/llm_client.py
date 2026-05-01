"""
LLM Client — unified interface for multiple LLM providers.
Configure via environment variables or config.py.

Supported providers: gemini, openai, anthropic, groq, deepseek, ollama
"""

import json
import os
import re
from urllib import request as urlrequest
from urllib import error as urlerror
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — set via environment variables or edit directly
# ─────────────────────────────────────────────────────────────────────────────

PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")      # gemini | openai | anthropic | groq | deepseek | ollama
API_KEY  = os.environ.get("LLM_API_KEY", "")             # your API key
MODEL    = os.environ.get("LLM_MODEL", "")               # leave blank for provider default

TIMEOUT = 45  # seconds

# Provider defaults
DEFAULTS = {
    "gemini":    "gemini-1.5-flash",
    "openai":    "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "groq":      "llama-3.1-70b-versatile",
    "deepseek":  "deepseek-chat",
    "ollama":    "llama3",
}


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER IMPLEMENTATIONS
# ─────────────────────────────────────────────────────────────────────────────

def _post(url: str, headers: dict, body: dict) -> str:
    """Generic POST helper."""
    req = urlrequest.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST"
    )
    resp = urlrequest.urlopen(req, timeout=TIMEOUT)
    return resp.read().decode("utf-8")


def _call_gemini(prompt: str, system: str, model: str, api_key: str) -> str:
    full = f"{system}\n\n{prompt}" if system else prompt
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": full}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1200}
    }
    data = json.loads(_post(url, {}, body))
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_openai(prompt: str, system: str, model: str, api_key: str) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {"model": model, "messages": messages, "temperature": 0.0, "max_tokens": 1200}
    headers = {"Authorization": f"Bearer {api_key}"}
    data = json.loads(_post("https://api.openai.com/v1/chat/completions", headers, body))
    return data["choices"][0]["message"]["content"]


def _call_anthropic(prompt: str, system: str, model: str, api_key: str) -> str:
    body = {
        "model": model,
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": prompt}]
    }
    if system:
        body["system"] = system
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    data = json.loads(_post("https://api.anthropic.com/v1/messages", headers, body))
    return data["content"][0]["text"]


def _call_groq(prompt: str, system: str, model: str, api_key: str) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {"model": model, "messages": messages, "temperature": 0.0, "max_tokens": 1200}
    headers = {"Authorization": f"Bearer {api_key}"}
    data = json.loads(_post("https://api.groq.com/openai/v1/chat/completions", headers, body))
    return data["choices"][0]["message"]["content"]


def _call_deepseek(prompt: str, system: str, model: str, api_key: str) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {"model": model, "messages": messages, "temperature": 0.0, "max_tokens": 1200}
    headers = {"Authorization": f"Bearer {api_key}"}
    data = json.loads(_post("https://api.deepseek.com/v1/chat/completions", headers, body))
    return data["choices"][0]["message"]["content"]


def _call_ollama(prompt: str, system: str, model: str, _: str) -> str:
    full = f"{system}\n\n{prompt}" if system else prompt
    body = {"model": model, "prompt": full, "stream": False, "options": {"temperature": 0.0}}
    data = json.loads(_post("http://localhost:11434/api/generate", {}, body))
    return data["response"]


_CALLERS = {
    "gemini":    _call_gemini,
    "openai":    _call_openai,
    "anthropic": _call_anthropic,
    "groq":      _call_groq,
    "deepseek":  _call_deepseek,
    "ollama":    _call_ollama,
}


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────────────────────────

def complete(prompt: str, system: str = "") -> str:
    """Call the configured LLM and return the raw text response."""
    provider = PROVIDER.lower()
    model = MODEL or DEFAULTS.get(provider, "")
    api_key = API_KEY

    caller = _CALLERS.get(provider)
    if not caller:
        raise ValueError(f"Unknown LLM provider: {provider}. Choose from: {list(_CALLERS.keys())}")
    if provider != "ollama" and not api_key:
        raise ValueError(f"LLM_API_KEY is not set. Set it via environment variable or edit compose_engine/llm_client.py")

    return caller(prompt, system, model, api_key)


def complete_json(prompt: str, system: str = "") -> dict:
    """Call the LLM and parse JSON from the response. Robust extraction."""
    raw = complete(prompt, system)
    
    # Try direct parse first
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Extract first JSON object from response
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Remove markdown fences and try again
    cleaned = re.sub(r'```(?:json)?\s*', '', raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    raise ValueError(f"Could not parse JSON from LLM response: {raw[:200]}")


def provider_name() -> str:
    """Return human-readable provider + model string."""
    model = MODEL or DEFAULTS.get(PROVIDER, "unknown")
    return f"{PROVIDER}/{model}"
