"""
Shared LLM client config.
Respects LLM_PROVIDER env var: "openai" | "groq" | "ollama"
Import get_llm() wherever an agent needs to call the model.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

LLM_PROVIDER   = os.getenv("LLM_PROVIDER", "groq").strip().lower()
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# Default models per provider
_OPENAI_DEFAULT = "gpt-4o-mini"
_GROQ_DEFAULT   = "llama-3.3-70b-versatile"


def get_llm(temperature: float = 0.2, model_name: str = None):
    """
    Return a LangChain chat model based on LLM_PROVIDER in .env.

    Priority:
      LLM_PROVIDER=openai  → ChatOpenAI  (uses OPENAI_API_KEY)
      LLM_PROVIDER=groq    → ChatGroq    (uses GROQ_API_KEY)
      LLM_PROVIDER=ollama  → ChatOllama  (uses OLLAMA_BASE_URL)
    """

    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set in .env")
        from langchain_openai import ChatOpenAI
        chosen_model = model_name or _OPENAI_DEFAULT
        print(f"[LLM Config] Using OpenAI → {chosen_model}")
        return ChatOpenAI(
            model=chosen_model,
            api_key=OPENAI_API_KEY,
            temperature=temperature,
            max_retries=3,
            timeout=60,
        )

    elif LLM_PROVIDER == "groq":
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not set in .env")
        from langchain_groq import ChatGroq
        chosen_model = model_name or _GROQ_DEFAULT
        print(f"[LLM Config] Using Groq → {chosen_model}")
        return ChatGroq(
            model=chosen_model,
            api_key=GROQ_API_KEY,
            temperature=temperature,
            max_retries=3,
            timeout=60,
        )

    elif LLM_PROVIDER == "ollama":
        try:
            from langchain_community.chat_models import ChatOllama
        except ImportError:
            raise ImportError("Install langchain-community: pip install langchain-community")
        chosen_model = model_name or OLLAMA_MODEL
        print(f"[LLM Config] Using Ollama → {chosen_model}")
        return ChatOllama(
            model=chosen_model,
            base_url=OLLAMA_BASE_URL,
            temperature=temperature,
        )

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{LLM_PROVIDER}'. "
            "Set LLM_PROVIDER to 'openai', 'groq', or 'ollama' in .env"
        )
