"""
Shared LLM client config. Uses Groq.
Import get_llm() wherever an agent needs to call the model.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


def get_llm(temperature: float = 0.2):
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not found in backend/.env")

    from langchain_groq import ChatGroq

    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=GROQ_API_KEY,
        temperature=temperature,
    )
