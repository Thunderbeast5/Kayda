"""
Shared LLM client config. Uses OpenAI gpt-5.4-mini across all agents and stages.
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

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

DEFAULT_MODEL = "gpt-5.4-mini"
OPENAI_MODEL = DEFAULT_MODEL
MODEL_STRONG = DEFAULT_MODEL
MODEL_CHEAP = DEFAULT_MODEL
MODEL_COURTROOM = DEFAULT_MODEL
LLM_PROVIDER = "openai"

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


def get_llm(temperature: float = 0.2, model_name: Optional[str] = None):
    """
    Get LLM instance. Pinned to OpenAI gpt-5.4-mini for all LLM stages.
    Fails explicitly if OpenAI is unconfigured or fails to initialize.
    No silent fallback to other providers or models.
    """
    env_temp = os.getenv("LLM_TEMPERATURE")
    if env_temp is not None:
        try:
            temperature = float(env_temp)
        except ValueError:
            pass

    api_key = os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured in .env. OpenAI provider (gpt-5.4-mini) is required."
        )

    if ChatOpenAI is None:
        raise RuntimeError("langchain_openai is not installed; install via: pip install langchain-openai")

    # Enforce gpt-5.4-mini consistently across all callers
    target_model = DEFAULT_MODEL
    kwargs = _openai_kwargs(target_model, temperature, api_key)

    try:
        return ChatOpenAI(**kwargs)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize OpenAI client with model '{target_model}': {e}")
