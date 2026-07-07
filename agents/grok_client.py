"""
Groq API Client (console.groq.com)
Uses Groq's OpenAI-compatible chat completions endpoint:
  POST https://api.groq.com/openai/v1/chat/completions

Free tier supports models like llama-3.3-70b-versatile, mixtral-8x7b, gemma2-9b.
All agents import from here — one place for model, key, and retry logic.

Docs: https://console.groq.com/docs/openai
"""

import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
import requests

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
_BASE_URL    = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT     = 60  # seconds

# Available free-tier models on Groq (for reference)
AVAILABLE_MODELS = {
    "llama-3.3-70b-versatile": "Best overall — fast + smart (recommended)",
    "llama-3.1-8b-instant":    "Fastest, lightweight tasks",
    "mixtral-8x7b-32768":      "Long context (32k tokens), good for legal docs",
    "gemma2-9b-it":            "Google Gemma, solid reasoning",
}


def _headers() -> dict:
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        raise ValueError(
            "GROQ_API_KEY is not set. Add it to your .env file.\n"
            "Get your key at https://console.groq.com/keys"
        )
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}",
    }


def chat(
    input_text: str,
    system_prompt: str = None,
    model: str = None,
    temperature: float = 0.3,
    max_output_tokens: int = 2048,
    retries: int = 2,
) -> str:
    """
    Sends a chat completion request to Groq and returns the assistant text.

    Args:
        input_text:        The user message / prompt.
        system_prompt:     Optional system-level instruction.
        model:             Override the default model from .env.
        temperature:       Sampling temperature (lower = more deterministic).
        max_output_tokens: Max tokens in the response.
        retries:           Number of automatic retries on transient errors.

    Returns:
        Assistant response as a plain string.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": input_text})

    payload = {
        "model": model or GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }

    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                _BASE_URL,
                headers=_headers(),
                json=payload,
                timeout=_TIMEOUT,
            )

            # Surface auth/billing errors immediately
            if resp.status_code in (401, 403):
                body = resp.json() if resp.content else {}
                err  = body.get("error", {})
                msg  = err.get("message", resp.text) if isinstance(err, dict) else str(err)
                raise RuntimeError(
                    f"Groq API {resp.status_code}: {msg}\n"
                    "Check your key at https://console.groq.com/keys"
                )

            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

        except RuntimeError:
            raise  # re-raise auth errors immediately

        except requests.HTTPError as e:
            status = e.response.status_code if e.response else 0
            # Retry on rate-limit or transient server errors
            if status in (429, 500, 502, 503, 504) and attempt < retries:
                wait = int(e.response.headers.get("retry-after", 2 ** attempt))
                print(f"[Groq] Rate limited. Retrying in {wait}s...")
                time.sleep(wait)
                last_error = e
                continue
            body = e.response.json() if e.response and e.response.content else {}
            err_msg = body.get("error", {}).get("message", str(e))
            raise RuntimeError(f"Groq API error {status}: {err_msg}") from e

        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                last_error = e
                continue
            raise RuntimeError(f"Groq request failed: {e}") from e

    raise RuntimeError(f"Groq API failed after {retries+1} attempts: {last_error}")


def chat_json(
    input_text: str,
    system_prompt: str = None,
    **kwargs,
) -> str:
    """
    Calls chat() with a JSON-enforcing instruction added to the system prompt.
    Returns the raw string — caller should json.loads() it.
    """
    json_note = "\n\nIMPORTANT: Reply ONLY with valid JSON. No markdown, no code fences, no extra text."
    combined  = (system_prompt or "") + json_note
    return chat(input_text, system_prompt=combined.strip(), **kwargs)


def chat_with_history(
    messages: list[dict],
    system_prompt: str = None,
    model: str = None,
    temperature: float = 0.3,
    max_output_tokens: int = 2048,
) -> str:
    """
    Multi-turn conversation — accepts a full message history list.
    Used for accused testimony loop and multi-round judge debates.

    Args:
        messages:      List of {"role": "user"|"assistant", "content": "..."} dicts.
        system_prompt: Optional system instruction prepended.
    """
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    payload = {
        "model": model or GROQ_MODEL,
        "messages": full_messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }

    resp = requests.post(
        _BASE_URL,
        headers=_headers(),
        json=payload,
        timeout=_TIMEOUT,
    )

    if resp.status_code in (401, 403):
        body = resp.json() if resp.content else {}
        raise RuntimeError(
            f"Groq API {resp.status_code}: {body.get('error', resp.text)}"
        )

    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ── Quick smoke test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Model  : {GROQ_MODEL}")
    print(f"Key    : {GROQ_API_KEY[:12]}...")
    print("Sending test request to Groq API...\n")

    reply = chat(
        input_text="In one sentence, what is IPC Section 302?",
        system_prompt="You are an expert in Indian law. Be concise.",
    )
    print(f"Response: {reply}")

    # JSON mode test
    print("\nTesting JSON mode...")
    raw = chat_json(
        input_text='Return a JSON object with keys "status" and "model".',
    )
    print(f"JSON response: {raw}")
