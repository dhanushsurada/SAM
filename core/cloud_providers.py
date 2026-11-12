"""
SAM Core — Cloud LLM Providers & Model Intelligence

Provides high-speed cloud inference capabilities (Groq, OpenAI, Gemini, Anthropic, OpenRouter)
alongside local Ollama inference, allowing sub-second reasoning speeds (~200ms) and access
to state-of-the-art models. Manages secure local API key storage and latest model update recommendations.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger("SAM.CloudProviders")

SAM_DATA_DIR = Path.home() / ".sam_data"
API_KEYS_PATH = SAM_DATA_DIR / "config" / "api_keys.json"

SUPPORTED_PROVIDERS = {
    "groq": {
        "name": "Groq",
        "description": "Ultra-fast LPU inference (~500 tokens/sec, near-instant responses)",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "format": "openai",
        "default_model": "llama-3.3-70b-versatile",
        "models": [
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B (Recommended)", "context": 128000, "fast": True},
            {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant (Ultra-fast)", "context": 128000, "fast": True},
            {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "context": 32768, "fast": True},
        ],
    },
    "gemini": {
        "name": "Google Gemini",
        "description": "Google's fast multimodal frontier models with high free-tier rate limits",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "format": "openai",
        "default_model": "gemini-2.0-flash",
        "models": [
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash (Recommended)", "context": 1048576, "fast": True},
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "context": 1048576, "fast": True},
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "context": 2097152, "fast": False},
        ],
    },
    "openai": {
        "name": "OpenAI",
        "description": "Industry benchmark models (GPT-4o, GPT-4o-mini)",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "format": "openai",
        "default_model": "gpt-4o-mini",
        "models": [
            {"id": "gpt-4o-mini", "name": "GPT-4o mini (Fast & Affordable)", "context": 128000, "fast": True},
            {"id": "gpt-4o", "name": "GPT-4o (Frontier Multi-modal)", "context": 128000, "fast": False},
        ],
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "description": "Claude 3.5 series with advanced reasoning and tool use",
        "endpoint": "https://api.anthropic.com/v1/messages",
        "format": "anthropic",
        "default_model": "claude-3-5-haiku-20241022",
        "models": [
            {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku (Fast)", "context": 200000, "fast": True},
            {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "context": 200000, "fast": False},
        ],
    },
    "openrouter": {
        "name": "OpenRouter",
        "description": "Unified gateway to over 100+ open and proprietary AI models",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "format": "openai",
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "models": [
            {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "context": 128000, "fast": True},
            {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3", "context": 64000, "fast": True},
        ],
    },
}

# Recommendations for updates & upgrades based on current hardware/tech
RECOMMENDED_UPDATES = [
    {
        "id": "groq-llama33",
        "title": "Supercharge SAM with Groq (Free & Instant)",
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "description": "Add a free Groq API key to get instant 500 tokens/sec response speeds instead of waiting 10-15s locally.",
        "badge": "10x Speedup",
        "action_url": "https://console.groq.com/keys",
    },
    {
        "id": "gemini-flash2",
        "title": "Upgrade to Gemini 2.0 Flash",
        "provider": "gemini",
        "model": "gemini-2.0-flash",
        "description": "Google's newest Gemini 2.0 Flash model offers superior speed, reasoning, and multimodal capabilities with generous free tier limits.",
        "badge": "New Release",
        "action_url": "https://aistudio.google.com/app/apikey",
    },
    {
        "id": "ollama-qwen14b",
        "title": "Qwen 2.5 14B (Local Recommended)",
        "provider": "ollama",
        "model": "qwen2.5:14b",
        "description": "If you prefer 100% offline sovereign privacy, Qwen 2.5 14B provides exceptional tool execution on Apple Silicon.",
        "badge": "Offline Sovereign",
        "action_url": None,
    },
]


def load_api_keys() -> Dict[str, str]:
    """Read stored provider API keys from disk."""
    if not API_KEYS_PATH.exists():
        return {}
    try:
        with open(API_KEYS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to read API keys: {e}")
        return {}


def save_api_key(provider: str, key: str) -> None:
    """Store an API key securely under ~/.sam_data/config/api_keys.json."""
    provider = provider.lower().strip()
    keys = load_api_keys()
    keys[provider] = key.strip()

    API_KEYS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(API_KEYS_PATH, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2)
    os.chmod(API_KEYS_PATH, 0o600)  # User read/write only


def delete_api_key(provider: str) -> bool:
    """Remove a configured API key."""
    provider = provider.lower().strip()
    keys = load_api_keys()
    if provider in keys:
        del keys[provider]
        API_KEYS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(API_KEYS_PATH, "w", encoding="utf-8") as f:
            json.dump(keys, f, indent=2)
        return True
    return False


def get_providers_status() -> List[Dict[str, Any]]:
    """Return available cloud providers and their configuration status."""
    keys = load_api_keys()
    result = []
    for pid, meta in SUPPORTED_PROVIDERS.items():
        has_key = bool(keys.get(pid))
        masked_key = ""
        if has_key:
            raw = keys[pid]
            masked_key = (raw[:4] + "..." + raw[-4:]) if len(raw) > 8 else "****"
        result.append({
            "id": pid,
            "name": meta["name"],
            "description": meta["description"],
            "configured": has_key,
            "masked_key": masked_key,
            "default_model": meta["default_model"],
            "models": meta["models"],
        })
    return result


def get_model_update_notifications() -> List[Dict[str, Any]]:
    """Return latest model upgrade recommendations."""
    keys = load_api_keys()
    notifications = []
    for rec in RECOMMENDED_UPDATES:
        prov = rec["provider"]
        # If cloud provider isn't configured yet, recommend adding it for speed
        if prov != "ollama" and not keys.get(prov):
            notifications.append({
                **rec,
                "configured": False,
                "type": "cloud_speedup"
            })
        elif prov != "ollama" and keys.get(prov):
            notifications.append({
                **rec,
                "configured": True,
                "type": "model_ready"
            })
    return notifications


def call_cloud_chat(
    provider: str,
    model: str,
    messages: List[Dict[str, str]],
    system_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: int = 45,
) -> str:
    """
    Execute chat completion against a cloud provider.
    Returns raw assistant text (expected to be JSON format for SAM).
    """
    provider = provider.lower().strip()
    keys = load_api_keys()
    api_key = keys.get(provider)
    if not api_key:
        raise ValueError(f"No API key configured for provider '{provider}'. Add it in Settings.")

    meta = SUPPORTED_PROVIDERS.get(provider)
    if not meta:
        raise ValueError(f"Unsupported cloud provider: '{provider}'")

    if meta["format"] == "openai":
        # Format OpenAI compatible payload
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/dhanushsurada/SAM"
            headers["X-Title"] = "SAM Personal Assistant"

        payload = {
            "model": model or meta["default_model"],
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        # Groq/Gemini response_format handling
        try:
            resp = requests.post(meta["endpoint"], headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 400 and "response_format" in resp.text:
                # Fallback without explicit json_object flag if provider rejects it
                payload.pop("response_format", None)
                resp = requests.post(meta["endpoint"], headers=headers, json=payload, timeout=timeout)
        except Exception as e:
            raise RuntimeError(f"Cloud request to {provider} failed: {e}") from e

        if resp.status_code != 200:
            raise RuntimeError(f"{meta['name']} API returned HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"{meta['name']} returned an empty choices list.")
        return choices[0].get("message", {}).get("content", "").strip()

    elif meta["format"] == "anthropic":
        # Anthropic messages format
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or meta["default_model"],
            "system": system_prompt,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        resp = requests.post(meta["endpoint"], headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Anthropic API returned HTTP {resp.status_code}: {resp.text}")
        data = resp.json()
        content_blocks = data.get("content", [])
        text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
        return "".join(text_parts).strip()

    raise ValueError(f"Unknown format handler for provider: {provider}")
