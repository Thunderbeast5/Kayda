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
from langchain_openai import ChatOpenAI

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

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


def get_llm(temperature: float = 0.2, model_name: Optional[str] = None):
    """
    Get LLM instance. Respects LLM_PROVIDER env var:
    - "ollama" (default): Local/remote Ollama instance
    - "groq": Fast cloud models
    - "openai": OpenAI GPT models
    """
    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    ollama_api_key = os.getenv("OLLAMA_API_KEY", "")

    # 1. Ollama (default or when provider == "ollama")
    if provider == "ollama" or (provider != "groq" and provider != "openai"):
        target_model = model_name or ollama_model
        if any(p in target_model.lower() for p in ["gpt", "o1", "o3", "o4"]):
            target_model = ollama_model

        client_kwargs = {}
        if ollama_api_key:
            client_kwargs["headers"] = {"Authorization": f"Bearer {ollama_api_key}"}

        try:
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=target_model,
                base_url=ollama_base_url,
                temperature=temperature,
                client_kwargs=client_kwargs,
            )
        except Exception as e:
            print(f"[LLM] Warning loading ChatOllama: {e}")
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model=target_model,
                    base_url=f"{ollama_base_url.rstrip('/')}/v1",
                    api_key=ollama_api_key or "ollama",
                    temperature=temperature,
                )
            except Exception as e2:
                print(f"[LLM] Warning loading OpenAI-compatible endpoint for Ollama: {e2}")

    # 2. OpenAI
    if provider == "openai" and OPENAI_API_KEY:
        from langchain_openai import ChatOpenAI
        target_model = OPENAI_MODEL if (not model_name or "llama" in model_name.lower()) else model_name
        return ChatOpenAI(**_openai_kwargs(target_model, temperature, OPENAI_API_KEY))

    # 3. Groq
    if GROQ_API_KEY:
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                model=model_name if "llama" in (model_name or "") else "llama-3.1-8b-instant",
                api_key=GROQ_API_KEY,
                temperature=temperature,
                max_retries=3,
                timeout=30,
            )
        except Exception as e:
            print(f"[LLM] Primary Groq model {model_name} failed: {e}")

    # Fallback attempt with Ollama
    try:
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=ollama_model,
            base_url=ollama_base_url,
            temperature=temperature,
        )
    except Exception:
        pass

    # Fallback to OpenAI if key exists
    if OPENAI_API_KEY:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(**_openai_kwargs(OPENAI_MODEL, temperature, OPENAI_API_KEY))

    raise RuntimeError(
        f"Unable to initialize LLM provider '{provider}'. "
        f"Ensure Ollama is running at {ollama_base_url} or configure GROQ_API_KEY / OPENAI_API_KEY."
    )

