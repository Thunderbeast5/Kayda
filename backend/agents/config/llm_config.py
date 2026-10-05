"""
Shared LLM client config. Uses Groq.
Import get_llm() wherever an agent needs to call the model.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_groq import ChatGroq

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").lower()

# Models that do NOT support the temperature parameter.
# Passing temperature to these models causes empty API responses.
_MODELS_WITHOUT_TEMPERATURE = {
    "gpt-5.4-mini",
    "gpt-5.4",
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


def get_llm(temperature: float = 0.2, model_name: str = "gpt-5.4-mini"):
    """
    Get LLM instance. Defaults to OpenAI gpt-5.4-mini when OPENAI_API_KEY is present or LLM_PROVIDER is openai.
    Falls back to Groq if configured.
    """
    if (LLM_PROVIDER == "openai" or not GROQ_API_KEY) and OPENAI_API_KEY:
        from langchain_openai import ChatOpenAI
        target_model = OPENAI_MODEL if (not model_name or "llama" in model_name.lower()) else model_name
        return ChatOpenAI(**_openai_kwargs(target_model, temperature, OPENAI_API_KEY))

    if GROQ_API_KEY:
        try:
            return ChatGroq(
                model=model_name if "llama" in model_name else "llama-3.1-8b-instant",
                api_key=GROQ_API_KEY,
                temperature=temperature,
                max_retries=3,
                timeout=30,  # Add timeout to catch connection issues faster
            )
        except Exception as e:
            print(f"[LLM] Primary model {model_name} failed: {e}")
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

    if OPENAI_API_KEY:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(**_openai_kwargs(OPENAI_MODEL, temperature, OPENAI_API_KEY))

    # Last resort fallback if neither is available
    return ChatGroq(
        model="llama-3.1-8b-instant",
        api_key=GROQ_API_KEY or "missing_key",
        temperature=temperature,
    )

