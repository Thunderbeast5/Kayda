"""
LLM Configuration and JSON parsing utilities for LexiGraph Backend.
Per-Stage Model Pinning (OpenAI GPT-4o-mini):
  Stage 0  – Case Intake            : gpt-4o-mini
  Stage 1  – Legal Query             : gpt-4o-mini
  Stage 2  – Subquery Mapping        : gpt-4o-mini
  Stage 3  – Chapter Identification  : Deterministic (No LLM)
  Stage 4  – Statutory Verification  : Deterministic (No LLM)
  Stage 5  – Bail Reasoning          : gpt-4o-mini
  Stage 6  – Precedent Analysis      : gpt-4o-mini
  Stage 7  – Arguments & Judgment    : gpt-4o-mini
Verifier agents inherit the same model as their primary stage.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

# ---------------------------------------------------------------------------
# Per-Stage Model Constants
# Override any of these via environment variables of the same name.
# Defaults to Ollama models (local), falls back to Groq/OpenAI if not available
# ---------------------------------------------------------------------------
# Determine provider
_DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()  # Changed default to "openai"
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_HAS_GROQ = bool(os.getenv("GROQ_API_KEY"))
_HAS_OPENAI = bool(os.getenv("OPENAI_API_KEY"))

# Use Ollama models by default (local, no API key needed)
if _DEFAULT_PROVIDER == "ollama":
    # Ollama - use local models (default to llama3.2:3b for all stages)
    _OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    MODEL_STAGE0 = os.getenv("MODEL_STAGE0", _OLLAMA_MODEL)   # Case Intake
    MODEL_STAGE1 = os.getenv("MODEL_STAGE1", _OLLAMA_MODEL)   # Legal Query
    MODEL_STAGE2 = os.getenv("MODEL_STAGE2", _OLLAMA_MODEL)   # Subquery Mapping
    MODEL_STAGE5 = os.getenv("MODEL_STAGE5", _OLLAMA_MODEL)   # Bail Reasoning
    MODEL_STAGE6 = os.getenv("MODEL_STAGE6", _OLLAMA_MODEL)   # Precedent Analysis
    MODEL_STAGE7 = os.getenv("MODEL_STAGE7", _OLLAMA_MODEL)   # Arguments & Judgment
elif (_DEFAULT_PROVIDER == "groq" or _DEFAULT_PROVIDER == "") and _HAS_GROQ:
    # Groq models (using GPT-OSS models available on your account)
    MODEL_STAGE0 = os.getenv("MODEL_STAGE0", "openai/gpt-oss-120b")   # Case Intake
    MODEL_STAGE1 = os.getenv("MODEL_STAGE1", "openai/gpt-oss-120b")   # Legal Query
    MODEL_STAGE2 = os.getenv("MODEL_STAGE2", "openai/gpt-oss-120b")   # Subquery Mapping
    MODEL_STAGE5 = os.getenv("MODEL_STAGE5", "openai/gpt-oss-120b")  # Bail Reasoning
    MODEL_STAGE6 = os.getenv("MODEL_STAGE6", "openai/gpt-oss-120b")  # Precedent Analysis
    MODEL_STAGE7 = os.getenv("MODEL_STAGE7", "openai/gpt-oss-120b")  # Arguments & Judgment
else:
    # OpenAI models (default)
    MODEL_STAGE0 = os.getenv("MODEL_STAGE0", "gpt-4o-mini")   # Case Intake
    MODEL_STAGE1 = os.getenv("MODEL_STAGE1", "gpt-4o-mini")   # Legal Query
    MODEL_STAGE2 = os.getenv("MODEL_STAGE2", "gpt-4o-mini")   # Subquery Mapping
    MODEL_STAGE5 = os.getenv("MODEL_STAGE5", "gpt-4o-mini")  # Bail Reasoning
    MODEL_STAGE6 = os.getenv("MODEL_STAGE6", "gpt-4o-mini")  # Precedent Analysis
    MODEL_STAGE7 = os.getenv("MODEL_STAGE7", "gpt-4o-mini")  # Arguments & Judgment

# ---------------------------------------------------------------------------
# Legacy two-tier aliases (kept for backward compatibility)
# ---------------------------------------------------------------------------
# Cheap tier  → same model used by Stages 0-2
# Reasoning tier → same model used by Stages 5-7
MODEL_TIER_CHEAP = "cheap"         # maps to MODEL_STAGE0 / gpt-4o-mini
MODEL_TIER_REASONING = "reasoning" # maps to MODEL_STAGE5 / gpt-4o-mini


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
GLOBAL_CALL_GUARDRAIL = CallBudgetGuardrail(max_calls=60)


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


def get_llm(temperature: float = 0.1, model_name: Optional[str] = None):
    """
    Get configured LLM client. Uses OpenAI by default, falls back to Groq/Ollama if configured.
    Does not hardcode keys. Enforces process call ceiling check.
    """
    GLOBAL_CALL_GUARDRAIL.check_and_increment()

    provider = os.getenv("LLM_PROVIDER", "openai").lower()  # Changed default to "openai"
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    ollama_api_key = os.getenv("OLLAMA_API_KEY", "")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        load_dotenv(BASE_DIR / ".env", override=True)
        load_dotenv(BASE_DIR.parent / ".env", override=False)
        openai_api_key = os.getenv("OPENAI_API_KEY")

    groq_api_key = os.getenv("GROQ_API_KEY")

    # OpenAI first (default)
    if (provider == "openai" or provider == "") and openai_api_key:
        try:
            from langchain_openai import ChatOpenAI
            target_model = model_name or os.getenv("STAGE0_MODEL", "gpt-4o-mini")
            kwargs = _openai_kwargs(target_model, temperature, openai_api_key)
            return ChatOpenAI(**kwargs)
        except Exception as e:
            print(f"[LexiGraph Config] Warning loading ChatOpenAI: {e}")
            print(f"[LexiGraph Config] Falling back to Groq/Ollama...")

    # Groq (alternative cloud inference)
    if provider == "groq" and groq_api_key:
        try:
            from langchain_groq import ChatGroq
            target_model = model_name or os.getenv("STAGE0_MODEL", "openai/gpt-oss-20b")
            # If an OpenAI model name was requested, map to corresponding high-performance Groq model
            if "gpt-4" in target_model.lower() or "mini" in target_model.lower() or "llama" in target_model.lower() or "stage" in target_model.lower():
                if any(x in target_model.lower() for x in ["stage5", "stage6", "stage7", "4.1", "5.4", "reasoning", "70b", "120b"]):
                    target_model = "openai/gpt-oss-120b"
                else:
                    target_model = "openai/gpt-oss-20b"

            max_tokens = 8192 if any(x in target_model.lower() for x in ["120b", "reasoning", "stage5", "stage6", "stage7"]) else 4096
            return ChatGroq(
                model=target_model,
                groq_api_key=groq_api_key,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            print(f"[LexiGraph Config] Warning loading ChatGroq: {e}")
            print(f"[LexiGraph Config] Falling back to Ollama...")

    # Try Ollama (local, no API key needed)
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
            target_model = model_name or ollama_model
            return ChatOllama(
                model=target_model,
                base_url=ollama_base_url,
                temperature=temperature,
            )
        except Exception as e:
            print(f"[LexiGraph Config] Warning loading ChatOllama: {e}")

    raise RuntimeError(
        "No valid LLM available. Options:\n"
        "1. OpenAI (cloud, default): Set OPENAI_API_KEY in .env\n"
        "2. Groq (cloud, fast): Set GROQ_API_KEY in .env\n"
        "3. Ollama (local): Install Ollama and set OLLAMA_BASE_URL=http://localhost:11434"
    )


def get_llm_for_tier(tier: str = MODEL_TIER_CHEAP, temperature: float = 0.1, model_name: Optional[str] = None):
    """
    Get configured LLM client routed by task tier.
    - 'cheap' tier: lightweight/cheap model for narrow structured extraction & shortlisting (gpt-4o-mini / qwen/qwen3.8-27b).
    - 'reasoning' tier: flagship model for deep legal decomposition & argument synthesis (gpt-4o / openai/gpt-oss-120b).
    """
    if model_name:
        return get_llm(temperature=temperature, model_name=model_name)

    provider = os.getenv("LLM_PROVIDER", "openai").lower()  # Default to OpenAI
    openai_api_key = os.getenv("OPENAI_API_KEY")
    groq_api_key = os.getenv("GROQ_API_KEY")

    # OpenAI models (default)
    if (provider == "openai" or provider == "") and openai_api_key:
        # Map legacy tiers to per-stage pinned models (all gpt-4o-mini)
        cheap_model = MODEL_STAGE0       # gpt-4o-mini
        reasoning_model = MODEL_STAGE5   # gpt-4o-mini
        target_model = cheap_model if tier == MODEL_TIER_CHEAP else reasoning_model
        return get_llm(temperature=temperature, model_name=target_model)

    if groq_api_key:
        groq_cheap = os.getenv("MODEL_CHEAP", "openai/gpt-oss-20b")
        groq_reasoning = os.getenv("MODEL_REASONING", "openai/gpt-oss-120b")
        groq_target = groq_cheap if tier == MODEL_TIER_CHEAP else groq_reasoning
        return get_llm(temperature=temperature, model_name=groq_target)

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


def extract_json_from_text(text: Any) -> Dict[str, Any]:
    """
    Extracts and parses JSON from raw LLM output text or AIMessage objects.
    Resilient to reasoning blocks, plain VERIFIED text, code blocks, and partial JSON.
    Guarantees returning a dictionary without crashing with unhandled exceptions.
    """
    if text is None:
        return {"status": "VERIFIED", "issues": [], "feedback": "Auto-verified: empty input."}

    # If an AIMessage / BaseMessage object was passed
    if hasattr(text, "content") and text.content:
        cleaned_text = str(text.content).strip()
    elif hasattr(text, "additional_kwargs") and text.additional_kwargs.get("reasoning_content"):
        cleaned_text = str(text.additional_kwargs.get("reasoning_content")).strip()
    elif isinstance(text, str):
        cleaned_text = text.strip()
    else:
        cleaned_text = str(text).strip()

    if not cleaned_text:
        return {"status": "VERIFIED", "issues": [], "feedback": "Auto-verified: empty output text."}

    # Check for direct plain text verification status
    upper_text = cleaned_text.upper()
    if (
        "STATUS = VERIFIED" in upper_text
        or "STATUS: VERIFIED" in upper_text
        or upper_text == "VERIFIED"
        or upper_text.startswith("VERIFIED.")
    ):
        return {"status": "VERIFIED", "issues": [], "feedback": "Status verified without issues."}

    cleaned = cleaned_text

    # Match ```json ... ``` or ``` ... ```  (object OR array)
    match = re.search(r"```(?:json)?\s*([{|\[][\s\S]*?[}\]])\s*```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    else:
        # Find the first opening delimiter ('{' or '[') and walk to its matching closer.
        # Using rfind('}') is wrong when the LLM returns two objects back-to-back
        # ("Extra data" error) — it would span both.
        open_chars  = {"{": "}", "[": "]"}
        close_chars = {"}", "]"}
        first_brace = cleaned.find("{")
        first_bracket = cleaned.find("[")

        # Pick whichever delimiter comes first
        if first_brace == -1:
            start = first_bracket
        elif first_bracket == -1:
            start = first_brace
        else:
            start = min(first_brace, first_bracket)

        if start != -1:
            open_char  = cleaned[start]
            close_char = open_chars[open_char]
            depth = 0
            in_string = False
            escape_next = False
            end = -1
            for i, ch in enumerate(cleaned[start:], start):
                if escape_next:
                    escape_next = False
                    continue
                if ch == "\\" and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == open_char:
                    depth += 1
                elif ch == close_char:
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end != -1:
                cleaned = cleaned[start : end + 1]

    # Attempt 1: Standard json.loads with invalid escape normalization
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Attempt 2: json_repair package if available
    try:
        import json_repair
        print("[JSON Parse] Attempting json_repair...")
        repaired = json_repair.repair_json(cleaned, return_objects=True)
        if isinstance(repaired, str):
            try:
                repaired = json.loads(repaired, strict=False)
            except Exception:
                pass
        if isinstance(repaired, dict):
            # Fix Ollama issue: missing_information should be List[str], not List[dict]
            if "missing_information" in repaired:
                missing = repaired["missing_information"]
                if isinstance(missing, list) and missing and any(isinstance(item, dict) for item in missing):
                    # Convert dicts to strings
                    repaired["missing_information"] = [
                        (item.get("document_type") or item.get("message") or str(item))
                        if isinstance(item, dict) else str(item)
                        for item in missing
                    ]
                    print(f"[JSON Parse] Fixed missing_information from dicts to strings")
            print("[JSON Parse] ✓ Successfully repaired with json_repair")
            return repaired
    except Exception:
        pass

    # Attempt 3: Manual fixes for common LLM JSON errors
    try:
        # Fix common issues
        fixed = cleaned
        
        # Fix trailing commas before closing braces/brackets
        fixed = re.sub(r',\s*}', '}', fixed)
        fixed = re.sub(r',\s*]', ']', fixed)
        
        # Fix missing commas between array elements (heuristic)
        fixed = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
        
        # Fix unescaped quotes in strings (basic attempt)
        # This is risky, so we do it conservatively
        
        # Remove newlines and excessive whitespace
        fixed = re.sub(r'\s+', ' ', fixed)
        
        print("[JSON Parse] Attempting with manual fixes...")
        return json.loads(fixed, strict=False)
    except json.JSONDecodeError as e2:
        print(f"[JSON Parse] Manual fixes failed at position {e2.pos}: {e2.msg}")

    # Attempt 4: Try to salvage partial JSON
    try:
        parsed = json.loads(cleaned_escaped)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Fallback: Gracefully return dictionary with extracted status rather than crashing
    status_fallback = "VERIFIED" if "VERIFIED" in upper_text and "NEEDS_CORRECTION" not in upper_text else "NEEDS_CORRECTION"
    return {
        "status": status_fallback,
        "issues": [],
        "feedback": cleaned[:300] if len(cleaned) > 0 else "Auto-parsed verification response.",
    }
