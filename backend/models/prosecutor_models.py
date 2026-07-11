"""
Prosecutor Data Models
=======================
Typed structures for prosecutor input / internal context / output.
Used for validation and serialisation throughout the pipeline.

Input contract
--------------
The orchestrator passes two things to the prosecutor node:
  • session_id        : str   — unique case session identifier
  • structured_facts  : dict  — output of evidence_analyzer

This module defines Pydantic models that validate that contract,
normalize inconsistencies from the Evidence Analyzer, and produce
a clean ProsecutionContext for downstream steps.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# ── Sub-models matching Evidence Analyzer output ─────────────────────────────


class WhoBlock(BaseModel):
    """Parties involved in the case."""

    complainant: Optional[str] = None
    accused: List[str] = Field(default_factory=list)
    victims: List[str] = Field(default_factory=list)


class IncidentBlock(BaseModel):
    """Details of the incident."""

    summary: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    place: Optional[str] = None


class VehicleItem(BaseModel):
    """A vehicle entry from the property block."""

    type: Optional[str] = None
    registration_no: Optional[str] = None
    make_model: Optional[str] = None
    engine_chassis_no: Optional[str] = None
    estimated_value: Optional[str] = None


class PropertyBlock(BaseModel):
    """Property / loss details."""

    cash: Optional[str] = None
    gold: Optional[str] = None
    documents: Optional[str] = None
    vehicles: List[VehicleItem] = Field(default_factory=list)
    other_property: List[str] = Field(default_factory=list)
    estimated_loss: Optional[str] = None


class StructuredFacts(BaseModel):
    """
    Typed mirror of the Evidence Analyzer's output dict.

    Normalisation rules (applied automatically by the model_validator):
      • Missing top-level keys → default empty sub-models.
      • 'nan' / whitespace-only strings → None.
      • accused / victims / sections always lists, never None.
    """

    who: WhoBlock = Field(default_factory=WhoBlock)
    incident: IncidentBlock = Field(default_factory=IncidentBlock)
    property: PropertyBlock = Field(default_factory=PropertyBlock)
    sections: List[str] = Field(default_factory=list)

    # -- normalise dodgy strings coming from OCR / CSV pipelines -----------
    @model_validator(mode="before")
    @classmethod
    def _clean_nan_strings(cls, values: Any) -> Any:
        """Replace 'nan' / empty-whitespace strings with None recursively.
        In lists, None entries are dropped (List[str] can't hold None)."""
        if isinstance(values, dict):
            return {k: cls._clean_nan_strings(v) for k, v in values.items()}
        if isinstance(values, list):
            cleaned = [cls._clean_nan_strings(i) for i in values]
            return [item for item in cleaned if item is not None]
        if isinstance(values, str):
            stripped = values.strip()
            if stripped.lower() in ("nan", "none", "null", ""):
                return None
            return stripped
        return values

    @model_validator(mode="after")
    def _normalize_accused(self) -> "StructuredFacts":
        """If the accused list is empty, default to ['Unknown Person'] for prosecution context."""
        if not self.who.accused:
            self.who.accused = ["Unknown Person"]
        return self


# ── Input contract ───────────────────────────────────────────────────────────


class ProsecutorInput(BaseModel):
    """
    What the orchestrator passes to the prosecutor node.

    Required:
      • session_id       — non-empty string
      • structured_facts — dict with at least who.accused (≥ 1) and
                           incident.summary (non-empty)

    Optional (added later in the pipeline):
      • lexigraph_result — filled after LexiGraph retrieval
    """

    session_id: str = Field(
        ..., min_length=1, description="Unique session identifier."
    )
    structured_facts: StructuredFacts
    lexigraph_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="LexiGraph retrieval output (filled in a later step).",
    )

    @model_validator(mode="after")
    def _require_minimum_facts(self) -> "ProsecutorInput":
        """Ensure the case has at least one accused and an incident summary."""
        errors: List[str] = []

        if not self.structured_facts.who.accused:
            errors.append("structured_facts.who.accused must contain at least one name.")

        if not self.structured_facts.incident.summary:
            errors.append("structured_facts.incident.summary is required (cannot be empty/null).")

        if errors:
            raise ValueError(
                "Prosecutor input validation failed:\n  • " + "\n  • ".join(errors)
            )

        return self


# ── Internal context object ──────────────────────────────────────────────────


class RetrievedSection(BaseModel):
    """A single IPC/BNS section returned by LexiGraph."""

    section: str = Field(..., description="Section number, e.g. '302' or '379A'.")
    description: str = Field(default="", description="Full section text.")
    punishment: str = Field(default="", description="Prescribed punishment.")
    offense: str = Field(default="", description="Short offense name.")
    source: str = Field(default="", description="Retrieval source, e.g. 'neo4j:crime_node+pinecone'.")
    score: float = Field(default=0.0, description="Relevance score (0-1).")


class LexiGraphResult(BaseModel):
    """Typed mirror of the dict returned by lexigraph.retrieve()."""

    ipc_sections: List[RetrievedSection] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    neo4j_count: int = 0
    pinecone_count: int = 0
    query_used: str = ""
    rewritten: bool = False


class ProsecutionContext(BaseModel):
    """
    Clean internal object that all downstream prosecutor steps consume.

    Built from ProsecutorInput after validation + normalisation.
    No raw dicts past this point.

    Lifecycle:
      Step 1  accept()          → sets core fields (accused, incident, etc.)
      Step 2  retrieve_laws()   → sets retrieval_query, retrieved_laws,
                                   formatted_laws_for_prompt, retrieval_empty
      Step 3  (future)          → sets prosecution_argument, guardrail_passed
    """

    # ── Step 1 fields (set by accept) ────────────────────────────────
    session_id: str
    accused: List[str]
    complainant: Optional[str]
    victims: List[str]
    incident_summary: str
    incident_date: Optional[str]
    incident_time: Optional[str]
    incident_place: Optional[str]
    property_details: PropertyBlock
    known_sections: List[str] = Field(
        default_factory=list,
        description="IPC/BNS sections already identified by Evidence Analyzer.",
    )

    # ── Step 2 fields (set by retrieve_laws) ─────────────────────────
    retrieval_query: Optional[str] = Field(
        default=None,
        description="The natural-language query sent to LexiGraph.",
    )
    retrieved_laws: Optional[LexiGraphResult] = Field(
        default=None,
        description="Full typed LexiGraph retrieval result (metadata, counts, etc.).",
    )
    retrieved_sections: List[RetrievedSection] = Field(
        default_factory=list,
        description=(
            "Structured list of retrieved IPC/BNS sections. "
            "Guardrails use this to verify citations — never parse the formatted string."
        ),
    )
    valid_section_numbers: List[str] = Field(
        default_factory=list,
        description=(
            "Flat list of section numbers, e.g. ['379', '411', '302']. "
            "Guardrails can do `if cited_section in ctx.valid_section_numbers`."
        ),
    )
    formatted_laws_for_prompt: Optional[str] = Field(
        default=None,
        description="Pre-formatted string ready to inject into the LLM prompt.",
    )
    retrieval_empty: bool = Field(
        default=True,
        description="True if LexiGraph returned zero applicable sections.",
    )

    # ── Step 3+ fields (future) ──────────────────────────────────────
    system_prompt: Optional[str] = Field(
        default=None,
        description="The system prompt template used for generation.",
    )
    user_prompt: Optional[str] = Field(
        default=None,
        description="The compiled user prompt containing case facts and retrieved laws.",
    )
    prompt_messages: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="The final message list payload sent to the LLM client.",
    )
    draft_argument: Optional[str] = Field(
        default=None,
        description="The drafted prosecution argument from Step 3.",
    )
    llm_response: Optional[str] = Field(
        default=None,
        description="The raw response from the LLM.",
    )
    generation_status: Optional[str] = Field(
        default=None,
        description="Status of the generation process, e.g., 'success', 'failed'.",
    )
    retry_count: int = Field(
        default=0,
        description="Number of retries needed during generation.",
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="List of validation errors from failed attempts.",
    )
    guardrail_passed: Optional[bool] = Field(
        default=None,
        description="Whether the final generated argument passed the guardrail check.",
    )
    final_argument: Optional[str] = Field(
        default=None,
        description="The validated final prosecution argument.",
    )


# ── Output models (kept for future steps) ────────────────────────────────────


class ChargeItem(BaseModel):
    """A single charge in the prosecution argument."""

    section: str = Field(..., description="IPC/BNS section number, e.g. 'IPC 302'.")
    offence: str = Field(..., description="Name of the offence.")
    factual_basis: str = Field(
        ..., description="How the case facts satisfy this section's ingredients."
    )
    punishment_sought: Optional[str] = None


class ProsecutorOutput(BaseModel):
    """Final structured output of the prosecutor agent."""

    charges: List[ChargeItem] = Field(default_factory=list)
    full_argument: str = Field(..., description="Complete prosecution argument text.")
    sections_cited: List[str] = Field(default_factory=list)
    guardrail_passed: bool = True

