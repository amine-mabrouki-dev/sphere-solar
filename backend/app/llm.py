"""
Ollama Cloud client. Reads the API key from the OLLAMA_API_KEY env var only —
never hardcode it. Get/rotate keys at https://ollama.com (Keys page).

Env:
  OLLAMA_API_KEY   required to enable the assistant/forecast features
  OLLAMA_HOST      default https://ollama.com  (cloud)
  OLLAMA_MODEL     default gpt-oss:120b
  OLLAMA_TIMEOUT   default 60 (seconds)
"""

import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

OLLAMA_HOST    = os.getenv("OLLAMA_HOST", "https://ollama.com").rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "60"))


class LLMNotConfigured(RuntimeError):
    """Raised when OLLAMA_API_KEY is missing."""


def is_configured() -> bool:
    return bool(OLLAMA_API_KEY)


async def chat(messages: list[dict], temperature: float = 0.3) -> str:
    """Send a chat completion to Ollama Cloud and return the assistant text."""
    if not OLLAMA_API_KEY:
        raise LLMNotConfigured("OLLAMA_API_KEY is not set")

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}"}

    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        r = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()

    return (data.get("message") or {}).get("content", "") or ""


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of an LLM reply (handles ``` fences)."""
    cleaned = re.sub(r"```(?:json)?|```", "", text).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        m = re.search(r"\{.*\}", cleaned, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None
