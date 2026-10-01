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


def get_llm(temperature: float = 0.2, model_name: str = "llama-3.1-8b-instant"):
    """
    Get LLM instance. Defaults to Groq (llama-3.1-8b-instant / llama-3.3-70b-versatile).
    Falls back to OpenAI if GROQ_API_KEY is not set or fails.
    """
    if GROQ_API_KEY:
        try:
            return ChatGroq(
                model=model_name,
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
        return ChatOpenAI(
            model="gpt-4o-mini",
            api_key=OPENAI_API_KEY,
            temperature=temperature,
        )

    # Last resort fallback if neither is available
    return ChatGroq(
        model=model_name,
        api_key=GROQ_API_KEY or "missing_key",
        temperature=temperature,
    )

