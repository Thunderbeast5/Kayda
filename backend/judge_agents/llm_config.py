"""
LLM configuration for Judge Agents module.
Uses OpenAI gpt-5.4-mini consistently across all judge components.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env", override=False)
load_dotenv(_HERE.parent / ".env", override=False)

LLM_PROVIDER   = "openai"
DEFAULT_MODEL  = "gpt-5.4-mini"
OPENAI_MODEL   = DEFAULT_MODEL
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

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


def get_llm(temperature: float = 0.1, model_name: str = None):
    """
    Return ChatOpenAI instance locked to gpt-5.4-mini.
    Fails explicitly if OPENAI_API_KEY is not set.
    No silent fallback to other providers or models.
    """
    api_key = os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. OpenAI gpt-5.4-mini is required."
        )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise RuntimeError(f"langchain_openai is not installed: {e}")

    target_model = DEFAULT_MODEL
    kwargs = _openai_kwargs(target_model, temperature, api_key)

    try:
        return ChatOpenAI(**kwargs)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize OpenAI client with model '{target_model}': {e}")
