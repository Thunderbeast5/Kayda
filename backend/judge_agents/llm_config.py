"""
LLM configuration for Judge Agents module.

Provider priority (controlled by LLM_PROVIDER env var):
  1. "ollama"  — local Ollama (default, development)  → llama3.2:3b
  2. "openai"  — OpenAI API (production switch)        → gpt-4o-mini

Set in judge_agents/.env:
    LLM_PROVIDER=ollama          # or openai
    OLLAMA_BASE_URL=http://localhost:11434   # optional, default shown
    OPENAI_API_KEY=sk-...        # only needed when LLM_PROVIDER=openai

To switch to OpenAI later, just change LLM_PROVIDER=openai in .env.
No code changes required.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from judge_agents folder first, then fall back to backend/.env
_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env", override=False)
load_dotenv(_HERE.parent / ".env", override=False)

LLM_PROVIDER     = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL     = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL     = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def get_llm(temperature: float = 0.1):
    """
    Return an LLM instance based on LLM_PROVIDER env var.

    Ollama (default / development)
    --------------------------------
    - Requires Ollama running locally: https://ollama.com
    - Pull model once: ollama pull llama3.2:3b
    - Set LLM_PROVIDER=ollama in .env (or leave unset)

    OpenAI (production)
    --------------------------------
    - Set LLM_PROVIDER=openai
    - Set OPENAI_API_KEY=sk-...
    - Set OPENAI_MODEL=gpt-4o-mini (or gpt-4o for higher quality)
    """
    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise EnvironmentError(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is not set. "
                "Add it to judge_agents/.env"
            )
        from langchain_openai import ChatOpenAI
        print(f"[LLM] Provider: OpenAI | Model: {OPENAI_MODEL}")
        return ChatOpenAI(
            model=OPENAI_MODEL,
            api_key=OPENAI_API_KEY,
            temperature=temperature,
        )

    # Default: Ollama
    try:
        from langchain_ollama import ChatOllama
        print(f"[LLM] Provider: Ollama | Model: {OLLAMA_MODEL} | URL: {OLLAMA_BASE_URL}")
        return ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=temperature,
        )
    except ImportError:
        raise ImportError(
            "langchain-ollama is not installed. Run: pip install langchain-ollama"
        )
    except Exception as e:
        raise RuntimeError(
            f"Ollama connection failed: {e}\n"
            f"Make sure Ollama is running: ollama serve\n"
            f"And model is pulled: ollama pull {OLLAMA_MODEL}"
        )
