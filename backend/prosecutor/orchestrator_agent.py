"""
Orchestrator Agent
==================
Single responsibility: run lexigraphbe and return verified sections.

Two methods:
  run(case_text)              — full pipeline on the entire case (session start)
  query_for_fact(fact_text)   — targeted pipeline on a specific fact + context
                                (mid-session, when defense raises something new)

NO injection, NO manipulation of Stage 1.
The lexigraphbe pipeline runs exactly as it was designed to run.
"""

from __future__ import annotations
import json
import os
import re
import traceback
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from .schemas import OrchestratorInput, OrchestratorResult, VerifiedSection

console = Console()


# ─────────────────────────────────────────────────────────────
# Lexigraphbe import
# ─────────────────────────────────────────────────────────────

def _try_import_lexigraphbe_runner():
    """
    Import run_full_pipeline from lexigraphbe.runner.
    Returns the callable or None if package not installed.
    """
    try:
        # Force reset of StatuteRepository singleton to ensure fresh load
        from lexigraphbe.statute_repository import StatuteRepository
        StatuteRepository.reset_instance()
        
        from lexigraphbe.runner import run_full_pipeline
        return run_full_pipeline
    except ImportError:
        return None


# ─────────────────────────────────────────────────────────────
# Result parser — same logic regardless of which text was run
# ─────────────────────────────────────────────────────────────

def _parse_pipeline_result(raw: Dict[str, Any]) -> OrchestratorResult:
    """
    Parse the dict returned by run_full_pipeline into OrchestratorResult.
    Pulls verified sections from stage4, punishment from stage3,
    bail recommendation from stage5.
    """
    verified_sections: List[VerifiedSection] = []

    s4 = raw.get("stage4_statutory_verification", {})
    s3_offences = raw.get("stage3_chapter_identification", {}).get("verified_offences", [])

    # Build a lookup: section_number -> punishment from stage3
    punishment_lookup: Dict[str, str] = {}
    for vo in s3_offences:
        sec_num = str(vo.get("section_number", ""))
        punishment = vo.get("punishment", {})
        max_p = punishment.get("maximum", "Unknown") if isinstance(punishment, dict) else "Unknown"
        punishment_lookup[sec_num] = str(max_p)

    for vo in s4.get("verified_offences", []):
        sec_num = str(vo.get("section_number", ""))
        verified_sections.append(VerifiedSection(
            section_number=sec_num,
            statute=str(vo.get("statute", "IPC")),
            title=str(vo.get("title", "")),
            classification=str(vo.get("classification", "PRIMARY")),
            overall_status=str(vo.get("overall_status", "")),
            overall_prima_facie_strength=str(vo.get("overall_prima_facie_strength", "")),
            punishment_text=punishment_lookup.get(sec_num, "Unknown"),
            ingredient_evaluation=vo.get("ingredient_evaluation", []),
            legal_reasoning=str(vo.get("legal_reasoning", "")),
            missing_supporting_facts=vo.get("missing_supporting_facts", []),
            investigation_requirements=vo.get("investigation_requirements", []),
        ))

    s5 = raw.get("stage5_bail_reasoning", {})
    bail_rec = s5.get("overall_recommendation", {}).get("decision", "Unknown")

    manual: List[str] = []
    for stage_val in raw.values():
        if isinstance(stage_val, dict):
            manual.extend(stage_val.get("manual_review", []))

    return OrchestratorResult(
        stage0_case_context=raw.get("stage0_case_context", {}),
        stage1_legal_query=raw.get("stage1_legal_query", {}),
        stage2_subquery_mapping=raw.get("stage2_subquery_mapping", {}),
        stage3_chapter_identification=raw.get("stage3_chapter_identification", {}),
        stage4_statutory_verification=raw.get("stage4_statutory_verification", {}),
        stage5_bail_reasoning=raw.get("stage5_bail_reasoning", {}),
        stage6_precedent_retrieval=raw.get("stage6_precedent_retrieval", {}),
        verified_sections=verified_sections,
        bail_recommendation=bail_rec,
        manual_review_flags=manual,
    )


# ─────────────────────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────────────────────

def _display_sections(result: OrchestratorResult, label: str = "") -> None:
    console.print()
    if label:
        console.rule(f"[bold blue]{label}[/bold blue]")

    t = Table(
        box=box.ROUNDED, show_header=True,
        header_style="bold white on blue", padding=(0, 1),
    )
    t.add_column("§",        style="bold yellow", width=6)
    t.add_column("Statute",  style="cyan",        width=6)
    t.add_column("Title",    style="white",        width=36)
    t.add_column("Status",   style="green",        width=24)
    t.add_column("Strength", style="bold",         width=10)
    t.add_column("Punishment", style="red",        width=14)

    for vs in result.verified_sections:
        sc = ("green" if vs.overall_prima_facie_strength == "Strong"
              else "yellow" if vs.overall_prima_facie_strength == "Moderate"
              else "red")
        t.add_row(
            vs.section_number, vs.statute,
            vs.title[:34] + ("…" if len(vs.title) > 34 else ""),
            vs.overall_status,
            f"[{sc}]{vs.overall_prima_facie_strength}[/{sc}]",
            vs.punishment_text,
        )
    console.print(t)

    if result.bail_recommendation:
        color = "red" if "reject" in result.bail_recommendation.lower() else "green"
        console.print(
            f"  [bold]Lexigraphbe Bail Recommendation:[/bold] [{color}]{result.bail_recommendation}[/{color}]"
        )
    console.print()


# ─────────────────────────────────────────────────────────────
# OrchestratorAgent
# ─────────────────────────────────────────────────────────────

class OrchestratorAgent:
    """
    Thin wrapper around lexigraphbe's run_full_pipeline.
    Does NOT manipulate lexigraphbe inputs in any way.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "") or os.environ.get("OLLAMA_API_KEY", "")
        default_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b") if os.getenv("LLM_PROVIDER", "ollama").lower() == "ollama" else "gpt-4o-mini"
        self.model   = model or default_model
        self._run_full_pipeline = _try_import_lexigraphbe_runner()

    def _run_pipeline(self, text: str, label: str) -> OrchestratorResult:
        """
        Internal: run lexigraphbe on `text`, display result, return OrchestratorResult.
        Falls back to GPT simulation if lexigraphbe not installed.
        """
        console.rule(f"[bold blue]ORCHESTRATOR — {label}[/bold blue]")
        console.print(f"[dim]Running lexigraphbe on {len(text)} chars of text…[/dim]")

        if self._run_full_pipeline:
            try:
                # Debug: Log the function being called
                import inspect
                func_file = inspect.getfile(self._run_full_pipeline)
                console.print(f"[dim]→ Calling run_full_pipeline from: {func_file}[/dim]")
                
                raw = self._run_full_pipeline(text=text)
                
                # Debug: Log Stage 2 output
                s2 = raw.get("stage2_subquery_mapping", {})
                if s2:
                    mappings = s2.get("mappings", [])
                    console.print(f"[dim]→ Stage 2 returned {len(mappings)} mappings[/dim]")
                    for m in mappings:
                        primary = [s.get("section_number") for s in m.get("primary_candidate_sections", [])]
                        console.print(f"[dim]  {m.get('sub_query_id')}: primary={primary}[/dim]")
                
                result = _parse_pipeline_result(raw)
                _display_sections(result, label="VERIFIED SECTIONS")
                return result
            except Exception as e:
                console.print(f"[red]lexigraphbe error: {e}[/red]")
                traceback.print_exc()
                console.print("[yellow]Falling back to GPT simulation…[/yellow]")

        # Fallback simulation
        result = self._simulate(text)
        _display_sections(result, label="SIMULATED SECTIONS")
        return result

    def run(self, orchestrator_input: OrchestratorInput) -> OrchestratorResult:
        """
        Full pipeline on the entire case text. Called once at session start.
        """
        return self._run_pipeline(
            text=orchestrator_input.case_text,
            label="FULL CASE PIPELINE",
        )

    def query_for_fact(
        self,
        fact_text: str,
        context_text: str,
        existing_section_numbers: List[str],
    ) -> OrchestratorResult:
        """
        Targeted pipeline for a specific unaddressed fact raised mid-session.

        Args:
            fact_text:               The specific fact for which no section exists.
            context_text:            2-3 surrounding sentences from the original case
                                     for Stage 0 CaseIntakeAgent to have enough context.
            existing_section_numbers: Sections already in session — returned result
                                      will exclude these so only NEW sections come back.

        Returns OrchestratorResult containing only sections NOT already in session.
        """
        # Compose a focused query text: fact + context
        query_text = (
            f"RELEVANT CASE CONTEXT:\n{context_text}\n\n"
            f"SPECIFIC FACT REQUIRING LEGAL ANALYSIS:\n{fact_text}"
        )
        result = self._run_pipeline(
            text=query_text,
            label=f"TARGETED FACT QUERY",
        )

        # Filter out sections already retrieved
        new_sections = [
            vs for vs in result.verified_sections
            if vs.section_number not in existing_section_numbers
        ]
        result.verified_sections = new_sections

        if new_sections:
            console.print(
                f"[green]  → {len(new_sections)} new section(s) found: "
                f"{[vs.section_number for vs in new_sections]}[/green]"
            )
        else:
            console.print(
                "[dim]  → No new sections found beyond what is already retrieved.[/dim]"
            )

        return result

    # ── GPT simulation fallback ──────────────────────────────

    def _simulate(self, text: str) -> OrchestratorResult:
        """Simulation fallback when lexigraphbe is not installed."""
        import re as _re
        from langchain_core.messages import SystemMessage, HumanMessage

        system = """You are a legal AI simulating lexigraphbe Stages 0-6 for Indian criminal law.
Given case facts, identify the correct IPC sections and return ONLY valid JSON:
{
  "verified_sections": [
    {
      "section_number": "...",
      "statute": "IPC",
      "title": "...",
      "classification": "PRIMARY",
      "overall_status": "Prima Facie Attracted",
      "overall_prima_facie_strength": "Strong",
      "punishment_text": "...",
      "ingredient_evaluation": [
        {"ingredient": "...", "matched_fact": "...", "status": "Satisfied", "reason": "..."}
      ],
      "legal_reasoning": "...",
      "missing_supporting_facts": [],
      "investigation_requirements": ["..."]
    }
  ],
  "bail_recommendation": "Reject Anticipatory Bail",
  "manual_review_flags": []
}"""
        try:
            from lexigraphbe.config import get_llm, extract_json_from_text
            llm = get_llm(temperature=0.0, model_name=self.model)
            resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=f"CASE TEXT:\n{text}")])
            raw_text = resp.content.strip() if hasattr(resp, "content") else str(resp).strip()
            data = extract_json_from_text(raw_text)
        except Exception:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            resp = client.chat.completions.create(
                model=self.model, temperature=0.0,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": f"CASE TEXT:\n{text}"},
                ],
            )
            raw_text = resp.choices[0].message.content.strip()
            cleaned  = _re.sub(r"^```(?:json)?\s*", "", raw_text, flags=_re.MULTILINE)
            cleaned  = _re.sub(r"\s*```$", "", cleaned, flags=_re.MULTILINE)
            data     = json.loads(cleaned.strip())

        sections = [
            VerifiedSection(
                section_number=str(vs.get("section_number", "")),
                statute=str(vs.get("statute", "IPC")),
                title=str(vs.get("title", "")),
                classification=str(vs.get("classification", "PRIMARY")),
                overall_status=str(vs.get("overall_status", "")),
                overall_prima_facie_strength=str(vs.get("overall_prima_facie_strength", "")),
                punishment_text=str(vs.get("punishment_text", "")),
                ingredient_evaluation=vs.get("ingredient_evaluation", []),
                legal_reasoning=str(vs.get("legal_reasoning", "")),
                missing_supporting_facts=vs.get("missing_supporting_facts", []),
                investigation_requirements=vs.get("investigation_requirements", []),
            )
            for vs in data.get("verified_sections", [])
        ]
        return OrchestratorResult(
            verified_sections=sections,
            bail_recommendation=data.get("bail_recommendation", "Unknown"),
            manual_review_flags=data.get("manual_review_flags", []),
        )