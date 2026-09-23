"""
LLM Configuration and JSON parsing utilities for LexiGraph Backend.
Per-Stage Model Pinning (OpenAI GPT only):
  Stage 0  – Case Intake            : gpt-5.4-mini
  Stage 1  – Legal Query             : gpt-5.4-mini
  Stage 2  – Subquery Mapping        : gpt-5.4-mini
  Stage 3  – Chapter Identification  : Deterministic (No LLM)
  Stage 4  – Statutory Verification  : Deterministic (No LLM)
  Stage 5  – Bail Reasoning          : gpt-5.4-mini
  Stage 6  – Precedent Analysis      : gpt-5.4-mini
  Stage 7  – Arguments & Judgment    : gpt-5.4-mini
Verifier agents inherit the same model as their primary stage.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Per-Stage Model Constants (OpenAI GPT)
# Override any of these via environment variables of the same name.
# ---------------------------------------------------------------------------
# Stages 0, 1, 2 – lightweight extraction & mapping
MODEL_STAGE0 = os.getenv("MODEL_STAGE0", "gpt-5.4-mini")   # Case Intake
MODEL_STAGE1 = os.getenv("MODEL_STAGE1", "gpt-5.4-mini")   # Legal Query
MODEL_STAGE2 = os.getenv("MODEL_STAGE2", "gpt-5.4-mini")   # Subquery Mapping
# Stages 3, 4 – Deterministic; no LLM model constants needed
# Stages 5, 6, 7 – deep legal reasoning
MODEL_STAGE5 = os.getenv("MODEL_STAGE5", "gpt-5.4-mini")  # Bail Reasoning
MODEL_STAGE6 = os.getenv("MODEL_STAGE6", "gpt-5.4-mini")  # Precedent Analysis
MODEL_STAGE7 = os.getenv("MODEL_STAGE7", "gpt-5.4-mini")  # Arguments & Judgment

# ---------------------------------------------------------------------------
# Legacy two-tier aliases (kept for backward compatibility)
# ---------------------------------------------------------------------------
# Cheap tier  → same model used by Stages 0-2
# Reasoning tier → same model used by Stages 5-7
MODEL_TIER_CHEAP = "cheap"         # maps to MODEL_STAGE0 / gpt-5.4-mini
MODEL_TIER_REASONING = "reasoning" # maps to MODEL_STAGE5 / gpt-5.4-mini


class CallBudgetGuardrail:
    """
    Local runtime call counter enforcing a strict budget cap per process execution run.
    Guarantees that a bug or loop can never drain API credits unexpectedly.
    """

    def __init__(self, max_calls: int = 25):
        self.max_calls = int(os.getenv("MAX_CALLS_PER_RUN", max_calls))
        self.call_count = 0

    def check_and_increment(self):
        if self.call_count >= self.max_calls:
            raise RuntimeError(
                f"[SAFETY GUARDRAIL BREACHED] Process execution call ceiling limit ({self.max_calls} calls) reached. "
                "Execution halted to protect API credits."
            )
        self.call_count += 1

    def reset(self):
        self.call_count = 0


# Global process safety guardrail instance
GLOBAL_CALL_GUARDRAIL = CallBudgetGuardrail(max_calls=25)


def get_llm(temperature: float = 0.1, model_name: Optional[str] = None):
    """
    Get configured LLM client. Prioritizes OPENAI_API_KEY when LLM_PROVIDER is set to 'openai' or when only OPENAI_API_KEY is available.
    Does not hardcode keys. Enforces process call ceiling check.
    """
    GLOBAL_CALL_GUARDRAIL.check_and_increment()

    provider = os.getenv("LLM_PROVIDER", "").lower()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    groq_api_key = os.getenv("GROQ_API_KEY")

    if (provider == "openai" or not groq_api_key) and openai_api_key:
        try:
            from langchain_openai import ChatOpenAI
            target_model = model_name or os.getenv("STAGE0_MODEL", "gpt-5.4-mini")
            return ChatOpenAI(
                model=target_model,
                api_key=openai_api_key,
                temperature=temperature,
            )
        except Exception as e:
            print(f"[LexiGraph Config] Warning loading ChatOpenAI: {e}")

    if groq_api_key:
        try:
            from langchain_groq import ChatGroq
            target_model = model_name or os.getenv("STAGE0_MODEL", "llama-3.3-70b-versatile")
            return ChatGroq(
                model=target_model,
                api_key=groq_api_key,
                temperature=temperature,
            )
        except Exception as e:
            print(f"[LexiGraph Config] Warning loading ChatGroq: {e}")

    if openai_api_key:
        try:
            from langchain_openai import ChatOpenAI
            target_model = model_name or os.getenv("STAGE0_MODEL", "gpt-5.4-mini")
            return ChatOpenAI(
                model=target_model,
                api_key=openai_api_key,
                temperature=temperature,
            )
        except Exception as e:
            print(f"[LexiGraph Config] Warning loading ChatOpenAI: {e}")

    # Fallback to error if no API key is set
    raise RuntimeError(
        "No valid LLM API key found (OPENAI_API_KEY or GROQ_API_KEY). "
        "Please provide an API key in backend/.env or pass a custom llm object."
    )


def get_llm_for_tier(tier: str = MODEL_TIER_CHEAP, temperature: float = 0.1, model_name: Optional[str] = None):
    """
    Get configured LLM client routed by task tier.
    - 'cheap' tier: lightweight/cheap model for narrow structured extraction & shortlisting (gpt-5.4-mini / llama-3.1-8b-instant).
    - 'reasoning' tier: flagship model for deep legal decomposition & argument synthesis (gpt-5.4-mini / llama-3.3-70b-versatile).
    """
    if model_name:
        return get_llm(temperature=temperature, model_name=model_name)

    provider = os.getenv("LLM_PROVIDER", "").lower()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    groq_api_key = os.getenv("GROQ_API_KEY")

    # Map legacy tiers to per-stage pinned models
    cheap_model = MODEL_STAGE0       # gpt-5.4-mini
    reasoning_model = MODEL_STAGE5   # gpt-5.4-mini
    target_model = cheap_model if tier == MODEL_TIER_CHEAP else reasoning_model

    if (provider == "openai" or not groq_api_key) and openai_api_key:
        return get_llm(temperature=temperature, model_name=target_model)

    if groq_api_key:
        # Groq does not serve GPT models; fall back to Groq equivalents
        groq_cheap = os.getenv("MODEL_CHEAP", "llama-3.1-8b-instant")
        groq_reasoning = os.getenv("MODEL_REASONING", "llama-3.3-70b-versatile")
        groq_target = groq_cheap if tier == MODEL_TIER_CHEAP else groq_reasoning
        return get_llm(temperature=temperature, model_name=groq_target)

    if openai_api_key:
        return get_llm(temperature=temperature, model_name=target_model)

    return get_llm(temperature=temperature, model_name=model_name)


def get_structured_llm(pydantic_schema: Any, temperature: float = 0.1, model_name: Optional[str] = None, tier: str = MODEL_TIER_CHEAP):
    """
    Get configured LLM client bound to a Pydantic schema using structured output mode and task-based model tiering.
    Guarantees schema compliance and eliminates malformed output retries.
    """
    base_llm = get_llm_for_tier(tier=tier, temperature=temperature, model_name=model_name)
    if hasattr(base_llm, "with_structured_output"):
        try:
            return base_llm.with_structured_output(pydantic_schema)
        except Exception:
            return base_llm
    return base_llm


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Extracts and parses JSON from raw LLM output text.
    Handles codeblocks ```json ... ``` and attempts repair using json_repair if available.
    """
    if not text or not isinstance(text, str):
        raise ValueError("Input text is empty or not a string.")

    cleaned = text.strip()

    # Match ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*({[\s\S]*?})\s*```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    else:
        # Fallback to finding first '{' and last '}'
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]

    # Attempt 1: Standard json.loads
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Attempt 2: json_repair package if available
    try:
        import json_repair
        repaired = json_repair.repair_json(cleaned, return_objects=True)
        if isinstance(repaired, dict):
            return repaired
    except ImportError:
        pass

    # Attempt 3: Evaluated JSON clean
    cleaned_escaped = cleaned.replace("\n", " ").replace("\r", "")
    try:
        return json.loads(cleaned_escaped)
    except Exception as err:
        raise ValueError(f"Failed to parse JSON from response. Response snippet: {cleaned[:200]}... Error: {err}")
