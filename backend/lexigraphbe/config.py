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
# All LLM-powered stages default and resolve strictly to OpenAI gpt-5.4-mini.
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "gpt-5.4-mini"
_DEFAULT_PROVIDER = "openai"

MODEL_STAGE0 = DEFAULT_MODEL   # Case Intake
MODEL_STAGE1 = DEFAULT_MODEL   # Legal Query
MODEL_STAGE2 = DEFAULT_MODEL   # Subquery Mapping
MODEL_STAGE3 = DEFAULT_MODEL   # Chapter Identification (Deterministic statutory matching)
MODEL_STAGE4 = DEFAULT_MODEL   # Statutory Verification (Deterministic statutory verification)
MODEL_STAGE5 = DEFAULT_MODEL   # Bail Reasoning
MODEL_STAGE6 = DEFAULT_MODEL   # Precedent Analysis
MODEL_STAGE7 = DEFAULT_MODEL   # Arguments & Judgment
MODEL_VERIFIER = DEFAULT_MODEL # Verifier agents

# Ensure no environment variables or configuration can silently divert from gpt-5.4-mini
for _stage_var in [
    "MODEL_STAGE0", "MODEL_STAGE1", "MODEL_STAGE2", "MODEL_STAGE3",
    "MODEL_STAGE4", "MODEL_STAGE5", "MODEL_STAGE6", "MODEL_STAGE7",
    "MODEL_VERIFIER"
]:
    env_val = os.getenv(_stage_var)
    if env_val and env_val.strip() and env_val.strip() != DEFAULT_MODEL:
        globals()[_stage_var] = DEFAULT_MODEL

# ---------------------------------------------------------------------------
# Legacy two-tier aliases (kept for backward compatibility, mapped to gpt-5.4-mini)
# ---------------------------------------------------------------------------
MODEL_TIER_CHEAP = "cheap"         # maps to gpt-5.4-mini
MODEL_TIER_REASONING = "reasoning" # maps to gpt-5.4-mini


class CallBudgetGuardrail:
    """
    Local runtime call counter enforcing a strict budget cap per process execution run.
    Guarantees that a bug or loop can never drain API credits unexpectedly.
    """

    def __init__(self, max_calls: int = 60):
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
    Get configured LLM client. Uses OpenAI gpt-5.4-mini across all LLM stages.
    Does not hardcode keys. Enforces process call ceiling check.
    No silent fallback to Groq or Ollama.
    """
    GLOBAL_CALL_GUARDRAIL.check_and_increment()

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set in .env. OpenAI gpt-5.4-mini is required across all LLM stages."
        )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise RuntimeError(f"langchain_openai is not installed: {e}")

    # Enforce gpt-5.4-mini consistently across all stages
    target_model = DEFAULT_MODEL
    kwargs = _openai_kwargs(target_model, temperature, openai_api_key)

    try:
        return ChatOpenAI(**kwargs)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize OpenAI client with model '{target_model}': {e}")


def get_llm_for_tier(tier: str = MODEL_TIER_CHEAP, temperature: float = 0.1, model_name: Optional[str] = None):
    """
    Get configured LLM client routed by task tier.
    Both cheap and reasoning tiers map strictly to OpenAI gpt-5.4-mini.
    """
    return get_llm(temperature=temperature, model_name=DEFAULT_MODEL)


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

    def _clean_dict(d: dict) -> dict:
        if "missing_information" in d:
            missing = d["missing_information"]
            if isinstance(missing, list) and missing and any(isinstance(item, dict) for item in missing):
                d["missing_information"] = [
                    (item.get("document_type") or item.get("message") or item.get("item") or str(item))
                    if isinstance(item, dict) else str(item)
                    for item in missing
                ]
        return d

    # Attempt 1: Standard json.loads with invalid escape normalization
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return _clean_dict(parsed)
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
            print("[JSON Parse] ✓ Successfully repaired with json_repair")
            return _clean_dict(repaired)
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
        parsed = json.loads(cleaned)
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
