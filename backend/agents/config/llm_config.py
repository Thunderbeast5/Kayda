"""
Shared LLM client config. Uses OpenAI.
Shared LLM client config.
Respects LLM_PROVIDER env var: "openai" | "groq" | "ollama"
Import get_llm() wherever an agent needs to call the model.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").lower()

# Models that do NOT support the temperature parameter.
# Passing temperature to these models causes empty API responses.
_MODELS_WITHOUT_TEMPERATURE = {
    "o1",
    "o1-mini",
    "o1-preview",
    "o3",
    "o3-mini",
    "o4-mini",
}


def _openai_kwargs(model: str, temperature: float, api_key: str) -> dict:
    """Build ChatOpenAI kwargs, omitting temperature for models that don't support it."""
    kwargs: dict = {"model": model, "api_key": api_key}
    if not any(m in model.lower() for m in _MODELS_WITHOUT_TEMPERATURE):
        kwargs["temperature"] = temperature
    return kwargs


def get_llm(temperature: float = 0.2, model_name: str = "gpt-4o-mini"):
    """
    Get LLM instance. Defaults to OpenAI when OPENAI_API_KEY is present or LLM_PROVIDER is openai.
    Falls back to Groq if configured.
    """
    if (LLM_PROVIDER == "openai" or not GROQ_API_KEY) and OPENAI_API_KEY:
        try:
            target_model = OPENAI_MODEL if (not model_name or "llama" in model_name.lower()) else model_name
            return ChatOpenAI(**_openai_kwargs(target_model, temperature, OPENAI_API_KEY))
        except Exception as e:
            print(f"[LLM] Primary model {model_name} failed: {e}")

    if GROQ_API_KEY and ChatGroq is not None:
        try:
            groq_model = model_name if (model_name and "llama" in model_name.lower()) else "llama-3.1-8b-instant"
            return ChatGroq(
                model=groq_model,
                api_key=GROQ_API_KEY,
                temperature=temperature,
                max_retries=3,
                timeout=30,
            )
        except Exception as e:
            print(f"[LLM] Primary Groq model failed: {e}")
            print("[LLM] Falling back to llama-3.1-8b-instant...")
            try:
                return ChatGroq(
                    model="llama-3.1-8b-instant",
                    api_key=GROQ_API_KEY,
                    temperature=temperature,
                    max_retries=3,
                    timeout=30,
                )
            except Exception as e2:
                print(f"[LLM] Groq fallback failed: {e2}")

    # Fallback to OpenAI if key exists
    if OPENAI_API_KEY:
        try:
            return ChatOpenAI(**_openai_kwargs(OPENAI_MODEL, temperature, OPENAI_API_KEY))
        except Exception as e:
            print(f"[LLM] OpenAI fallback failed: {e}")

    # Fallback to Groq if available
    if GROQ_API_KEY and ChatGroq is not None:
        return ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=GROQ_API_KEY,
            temperature=temperature,
        )

    # Return a safe dummy or mock if neither key works
    raise RuntimeError("No working LLM configured. Please check OPENAI_API_KEY or GROQ_API_KEY in .env")

