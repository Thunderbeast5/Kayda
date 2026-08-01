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

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env")


def get_llm(temperature: float = 0.2, model_name: str = "llama-3.1-8b-instant"):
    """
    Get LLM instance. Defaults to llama-3.1-8b-instant (faster, higher rate limits).
    Use llama-3.3-70b-versatile for more complex reasoning when needed.
    """
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
        return ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=GROQ_API_KEY,
            temperature=temperature,
            max_retries=3,
            timeout=30,
        )

