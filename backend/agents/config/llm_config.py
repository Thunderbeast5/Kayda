"""
Shared LLM client config. Uses OpenAI.
Import get_llm() wherever an agent needs to call the model.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def get_llm(temperature: float = 0.2, model_name: str = "gpt-4o-mini"):
    """
    Get LLM instance. Defaults to gpt-4o-mini.
    """
    try:
        return ChatOpenAI(
            model=model_name,
            api_key=OPENAI_API_KEY,
            temperature=temperature,
            max_retries=3,
            timeout=30,
        )
    except Exception as e:
        print(f"[LLM] Primary model {model_name} failed: {e}")
        print("[LLM] Falling back to gpt-4o-mini...")
        return ChatOpenAI(
            model="gpt-4o-mini",
            api_key=OPENAI_API_KEY,
            temperature=temperature,
            max_retries=3,
            timeout=30,
        )
