"""
Shared LLM client config. Supports Groq (default) and Ollama.
Import get_llm() wherever an agent needs to call the model.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_groq import ChatGroq

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


def get_llm(temperature: float = 0.2, model_name: str = "llama-3.1-8b-instant", provider: str = "groq"):
    """
    Get LLM instance.

    Parameters
    ----------
    temperature : float
        Sampling temperature (default 0.2).
    model_name : str
        Model identifier. Defaults to llama-3.1-8b-instant for Groq.
        For Ollama use model tags such as "llama3.1:8b".
    provider : str
        "groq" (default) or "ollama". Ollama runs locally via http://localhost:11434.
    """
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=model_name,
                temperature=temperature,
            )
        except ImportError:
            raise ImportError(
                "langchain_ollama is not installed. "
                "Run: pip install langchain-ollama"
            )

    # Default: Groq
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not found in .env")

    try:
        return ChatGroq(
            model=model_name,
            api_key=GROQ_API_KEY,
            temperature=temperature,
            max_retries=3,
            timeout=30,
        )
    except Exception as e:
        print(f"[LLM] Primary model {model_name} failed: {e}")
        print("[LLM] Falling back to llama-3.1-8b-instant...")
        return ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=GROQ_API_KEY,
            temperature=temperature,
            max_retries=3,
            timeout=30,
        )

