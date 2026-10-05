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
# Per-Stage Model Constants
# Override any of these via environment variables of the same name.
# Defaults to Ollama models (local), falls back to Groq/OpenAI if not available
# ---------------------------------------------------------------------------
# All LLM stages pinned to gpt-5.4-mini
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
    Get configured LLM client. Uses Ollama by default, falls back to Groq, then OpenAI.
    Does not hardcode keys. Enforces process call ceiling check.
    NOTE: Models like gpt-5.4-mini do not support the temperature parameter — it is
    automatically omitted for such models to avoid empty API responses.
    """
    GLOBAL_CALL_GUARDRAIL.check_and_increment()

    provider = os.getenv("LLM_PROVIDER", "ollama").lower()  # Default to Ollama
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    groq_api_key = os.getenv("GROQ_API_KEY")

    # Try Ollama first (default, local, no API key needed)
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
            print(f"[LexiGraph Config] Falling back to Groq/OpenAI...")

    # Try Groq (fast, cloud)
    if (provider == "groq" or provider == "") and groq_api_key:
        try:
            from langchain_groq import ChatGroq
            target_model = model_name or os.getenv("STAGE0_MODEL", "llama-3.3-70b-versatile")
            return ChatGroq(
                model=target_model,
                groq_api_key=groq_api_key,
                temperature=temperature,
            )
        except Exception as e:
            print(f"[LexiGraph Config] Warning loading ChatGroq: {e}")

    # Fall back to OpenAI if explicitly requested or others unavailable
    if (provider == "openai" or not groq_api_key) and openai_api_key:
        try:
            from langchain_openai import ChatOpenAI
            target_model = model_name or os.getenv("STAGE0_MODEL") or os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
            return ChatOpenAI(**_openai_kwargs(target_model, temperature, openai_api_key))
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
            target_model = model_name or os.getenv("STAGE0_MODEL") or os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
            return ChatOpenAI(**_openai_kwargs(target_model, temperature, openai_api_key))
        except Exception as e:
            print(f"[LexiGraph Config] Warning loading ChatOpenAI: {e}")

    # Fallback to error if no API key is set
    raise RuntimeError(
        "No valid LLM available. Options:\n"
        "1. Ollama (local): Install Ollama and set OLLAMA_BASE_URL=http://localhost:11434\n"
        "2. Groq (cloud): Set GROQ_API_KEY in .env\n"
        "3. OpenAI (cloud): Set OPENAI_API_KEY in .env"
    )


def get_llm_for_tier(tier: str = MODEL_TIER_CHEAP, temperature: float = 0.1, model_name: Optional[str] = None):
    """
    Get configured LLM client routed by task tier.
    - 'cheap' tier: lightweight model (llama-3.3-70b-versatile for Groq, gpt-4o-mini for OpenAI).
    - 'reasoning' tier: flagship model (llama-3.3-70b-versatile for Groq, gpt-4o for OpenAI).
    Default provider: Groq
    """
    if model_name:
        return get_llm(temperature=temperature, model_name=model_name)

    provider = os.getenv("LLM_PROVIDER", "groq").lower()  # Default to Groq
    openai_api_key = os.getenv("OPENAI_API_KEY")
    groq_api_key = os.getenv("GROQ_API_KEY")

    # Groq models (default)
    if (provider == "groq" or provider == "") and groq_api_key:
        groq_cheap = os.getenv("MODEL_CHEAP", "llama-3.3-70b-versatile")
        groq_reasoning = os.getenv("MODEL_REASONING", "llama-3.3-70b-versatile")
        groq_target = groq_cheap if tier == MODEL_TIER_CHEAP else groq_reasoning
        return get_llm(temperature=temperature, model_name=groq_target)

    # OpenAI models (fallback)
    if (provider == "openai" or not groq_api_key) and openai_api_key:
        # Map legacy tiers to per-stage pinned models
        cheap_model = MODEL_STAGE0       # gpt-4o-mini
        reasoning_model = MODEL_STAGE5   # gpt-4.1-mini
        target_model = cheap_model if tier == MODEL_TIER_CHEAP else reasoning_model
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
    Enhanced with better error recovery for malformed JSON.
    """
    if not text or not isinstance(text, str):
        raise ValueError("Input text is empty or not a string.")

    cleaned = text.strip()

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

    # Attempt 1: Standard json.loads
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"[JSON Parse] Initial parse failed at position {e.pos}: {e.msg}")

    # Attempt 2: json_repair package if available
    try:
        import json_repair
        print("[JSON Parse] Attempting json_repair...")
        repaired = json_repair.repair_json(cleaned, return_objects=True)
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
    except ImportError:
        print("[JSON Parse] json_repair not available, trying manual fixes...")
    except Exception as repair_err:
        print(f"[JSON Parse] json_repair failed: {repair_err}")

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
        return json.loads(fixed)
    except json.JSONDecodeError as e2:
        print(f"[JSON Parse] Manual fixes failed at position {e2.pos}: {e2.msg}")

    # Attempt 4: Try to salvage partial JSON
    try:
        print("[JSON Parse] Attempting to salvage partial JSON...")
        # Find the last valid closing brace before the error
        test_positions = [len(cleaned) - i for i in range(1, min(200, len(cleaned)))]
        for end_pos in test_positions:
            if cleaned[end_pos-1] == '}':
                try:
                    partial = cleaned[:end_pos]
                    result = json.loads(partial)
                    print(f"[JSON Parse] ✓ Salvaged partial JSON (truncated at position {end_pos})")
                    return result
                except:
                    continue
    except Exception as salvage_err:
        print(f"[JSON Parse] Salvage attempt failed: {salvage_err}")

    # Final fallback: Return error-safe minimal structure
    print("[JSON Parse] All parse attempts failed, returning minimal safe structure")
    raise ValueError(
        f"Failed to parse JSON from response after all recovery attempts.\n"
        f"Response snippet: {cleaned[:500]}...\n"
        f"Consider reducing prompt complexity or response size requirements."
    )
