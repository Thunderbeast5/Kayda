"""
Orchestrator Agent
==================
Main backbone of the moot court system.

Flow:
1. Ask user for case input
2. Ask user to choose role: Prosecution or Defense
3. Run lexigraphbe 7-stage pipeline to retrieve statutory sections
4. Pass sections to prosecutor_agent or defense_agent based on user role
5. Facilitate back-and-forth arguments between student and LLM

The orchestrator coordinates the entire moot court session.
"""

from __future__ import annotations
import json
import os
import sys
import re
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box

# Add backend directory to path for imports
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from schemas import OrchestratorInput, OrchestratorResult, VerifiedSection

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
    Main orchestrator for the moot court system.
    Coordinates between user input, lexigraphbe pipeline, and argument agents.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model   = model
        self._run_full_pipeline = _try_import_lexigraphbe_runner()
        
        self.case_text: Optional[str] = None
        self.student_role: Optional[Literal["prosecution", "defense"]] = None
        self.llm_role: Optional[Literal["prosecution", "defense"]] = None
        self.sections: Optional[OrchestratorResult] = None
        self.turn_count: int = 0

    def get_case_input(self) -> str:
        """Ask user for case input via CLI."""
        console.print()
        console.print(Panel(
            "[bold cyan]VIRTUAL MOOT COURT - ANTICIPATORY BAIL HEARING[/bold cyan]\n"
            "[dim]Step 1: Case Input[/dim]",
            border_style="cyan", padding=(1, 2)
        ))
        
        choice = Prompt.ask(
            "\nHow would you like to input the case?",
            choices=["text", "file"],
            default="file"
        )
        
        if choice == "file":
            file_path = Prompt.ask("\nEnter the path to case file (PDF/TXT)")
            try:
                if file_path.lower().endswith(".pdf"):
                    # Use existing PDF reader from prosecutor_agent
                    from prosecutor_agent import read_pdf
                    case_text = read_pdf(file_path)
                else:
                    case_text = Path(file_path).read_text(encoding="utf-8")
                console.print(f"[green]✓ Loaded {len(case_text)} characters from {file_path}[/green]")
                return case_text
            except Exception as e:
                console.print(f"[red]✗ Error reading file: {e}[/red]")
                console.print("[yellow]Falling back to text input...[/yellow]")
        
        console.print("\n[bold]Enter case facts[/bold] (press Ctrl+D or Ctrl+Z when done):")
        console.print("[dim]Tip: Paste your case text and press Enter, then Ctrl+D (Unix) or Ctrl+Z (Windows)[/dim]\n")
        
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
        
        case_text = "\n".join(lines).strip()
        if case_text:
            console.print(f"\n[green]✓ Received {len(case_text)} characters[/green]")
        else:
            console.print("[red]✗ No case text entered![/red]")
        
        return case_text

    def get_role_choice(self) -> Literal["prosecution", "defense"]:
        """Ask user which role they want to play."""
        console.print()
        console.print(Panel(
            "[bold cyan]Step 2: Role Selection[/bold cyan]",
            border_style="cyan", padding=(1, 2)
        ))
        
        role = Prompt.ask(
            "\nWhich role do you want to play?",
            choices=["prosecution", "defense"],
            default="defense"
        )
        
        opposite = "defense" if role == "prosecution" else "prosecution"
        console.print(f"\n[bold green]✓ You will play: {role.upper()}[/bold green]")
        console.print(f"[dim]The AI will play: {opposite.upper()}[/dim]")
        
        return role  # type: ignore

    def run_lexigraphbe_pipeline(self, case_text: str) -> OrchestratorResult:
        """
        Run the complete 7-stage lexigraphbe pipeline on case text.
        Returns verified sections.
        """
        console.print()
        console.print(Panel(
            "[bold cyan]Step 3: Running Lexigraphbe 7-Stage Pipeline[/bold cyan]\n"
            "[dim]Analyzing case and retrieving applicable statutory sections...[/dim]",
            border_style="cyan", padding=(1, 2)
        ))

        if self._run_full_pipeline:
            try:
                console.print("[dim]→ Stage 0: Case Intake...[/dim]")
                console.print("[dim]→ Stage 1: Legal Query Understanding...[/dim]")
                console.print("[dim]→ Stage 2: Sub-query Mapping...[/dim]")
                console.print("[dim]→ Stage 3: Chapter Identification...[/dim]")
                console.print("[dim]→ Stage 4: Statutory Verification...[/dim]")
                console.print("[dim]→ Stage 5: Bail Reasoning...[/dim]")
                console.print("[dim]→ Stage 6: Precedent Retrieval...[/dim]")
                
                raw = self._run_full_pipeline(text=case_text)
                result = _parse_pipeline_result(raw)
                
                _display_sections(result, label="VERIFIED STATUTORY SECTIONS")
                
                console.print(f"[bold green]✓ Retrieved {len(result.verified_sections)} statutory sections[/bold green]")
                return result
                
            except Exception as e:
                console.print(f"[red]✗ Lexigraphbe error: {e}[/red]")
                traceback.print_exc()
                console.print("[yellow]⚠ Falling back to GPT simulation...[/yellow]")
        
        # Fallback simulation
        return self._simulate_lexigraphbe(case_text)

    def _simulate_lexigraphbe(self, text: str) -> OrchestratorResult:
        """GPT-4o-mini simulation when lexigraphbe is not installed."""
        from openai import OpenAI
        
        client = OpenAI(api_key=self.api_key)
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
        resp = client.chat.completions.create(
            model=self.model, temperature=0.0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": f"CASE TEXT:\n{text}"},
            ],
        )
        raw_text = resp.choices[0].message.content.strip()
        cleaned  = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
        cleaned  = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
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
        
        result = OrchestratorResult(
            verified_sections=sections,
            bail_recommendation=data.get("bail_recommendation", "Unknown"),
            manual_review_flags=data.get("manual_review_flags", []),
        )
        
        _display_sections(result, label="SIMULATED SECTIONS")
        return result

    def initialize_agent(self, role: Literal["prosecution", "defense"]):
        """Initialize prosecutor or defense agent with sections and case."""
        console.print()
        console.print(Panel(
            f"[bold cyan]Step 4: Initializing {role.upper()} Agent[/bold cyan]\n"
            "[dim]Preparing arguments with retrieved sections...[/dim]",
            border_style="cyan", padding=(1, 2)
        ))
        
        if role == "prosecution":
            from prosecutor_agent import ProsecutorAgent
            from schemas import SessionState, RetrievedSection
            
            agent = ProsecutorAgent(api_key=self.api_key, model=self.model)
            
            # Convert sections to the format ProsecutorAgent expects
            retrieved_sections = {}
            for vs in self.sections.verified_sections:
                retrieved_sections[vs.section_number] = RetrievedSection(
                    section_number=vs.section_number,
                    statute=vs.statute,
                    title=vs.title,
                    classification=vs.classification,
                    overall_status=vs.overall_status,
                    overall_prima_facie_strength=vs.overall_prima_facie_strength,
                    punishment_text=vs.punishment_text,
                    ingredient_evaluation=vs.ingredient_evaluation,
                    legal_reasoning=vs.legal_reasoning,
                    missing_supporting_facts=vs.missing_supporting_facts,
                    investigation_requirements=vs.investigation_requirements,
                    retrieved_at_turn=0,
                )
            
            # Initialize prosecutor extraction and planning
            console.print("[dim]→ Prosecutor analyzing case and sections...[/dim]")
            p_output = agent._extract_case(self.case_text, retrieved_sections)
            usage_plan = agent._build_usage_plan(self.case_text, p_output, retrieved_sections)
            
            # Create session state
            session = SessionState(
                session_id="orchestrator",
                case_id="moot_court",
                case_text=self.case_text,
                student_role=self.student_role,
                retrieved_sections=retrieved_sections,
                prosecutor_output=p_output,
                section_usage_plan=usage_plan,
                turn_history=[],
            )
            
            return {"agent": agent, "session": session}
        else:
            from defense import DefenseAgent
            
            agent = DefenseAgent()
            
            # Initialize defense analysis
            console.print("[dim]→ Defense analyzing case and sections...[/dim]")
            agent.analyze_case(self.case_text)
            
            return {"agent": agent, "session": None}

    def run_moot_court_session(self):
        """
        Main entry point: orchestrate complete moot court session.
        1. Get case input
        2. Get role choice  
        3. Run lexigraphbe
        4. Initialize agents
        5. Run argument rounds
        """
        # Step 1: Get case input
        self.case_text = self.get_case_input()
        if not self.case_text:
            console.print("[red]✗ Cannot proceed without case text![/red]")
            return
        
        # Step 2: Get role choice
        self.student_role = self.get_role_choice()
        self.llm_role = "defense" if self.student_role == "prosecution" else "prosecution"
        
        # Step 3: Run lexigraphbe
        self.sections = self.run_lexigraphbe_pipeline(self.case_text)
        
        # Step 4: Initialize agent for LLM side
        llm_agent = self.initialize_agent(self.llm_role)
        
        # Step 5: Run argument rounds
        console.print()
        console.print(Panel(
            "[bold cyan]Step 5: Moot Court Session Started[/bold cyan]\n"
            f"[bold]Student Role:[/bold] {self.student_role.upper()}\n"
            f"[bold]AI Role:[/bold] {self.llm_role.upper()}",
            border_style="cyan", padding=(1, 2)
        ))
        
        self._run_argument_rounds(llm_agent)

    def _run_argument_rounds(self, llm_agent_wrapper):
        """Run back-and-forth arguments between student and LLM."""
        # Opening argument from prosecution (whoever that is)
        if self.student_role == "prosecution":
            # Student goes first (prosecution)
            student_opening = self._get_student_argument("opening")
            # LLM defense responds
            llm_rebuttal = self._get_llm_argument(llm_agent_wrapper, "rebuttal", student_opening)
            # Continue rounds
            while True:
                student_rebuttal = self._get_student_argument("rebuttal", llm_rebuttal)
                if not student_rebuttal:
                    break
                llm_counter = self._get_llm_argument(llm_agent_wrapper, "rebuttal", student_rebuttal)
        else:
            # LLM goes first (prosecution)
            llm_opening = self._get_llm_argument(llm_agent_wrapper, "opening")
            # Student defense responds
            student_rebuttal = self._get_student_argument("rebuttal", llm_opening)
            # Continue rounds
            while True:
                if not student_rebuttal:
                    break
                llm_counter = self._get_llm_argument(llm_agent_wrapper, "rebuttal", student_rebuttal)
                student_rebuttal = self._get_student_argument("rebuttal", llm_counter)

    def _get_student_argument(self, arg_type: str, previous_argument: str = None) -> str:
        """Get argument from student via CLI."""
        self.turn_count += 1
        
        console.print()
        console.print(Panel(
            f"[bold yellow]Turn {self.turn_count}: YOUR {arg_type.upper()}[/bold yellow]\n"
            f"[dim]Role: {self.student_role.upper()}[/dim]",
            border_style="yellow", padding=(1, 2)
        ))
        
        if previous_argument:
            console.print(f"\n[bold]Opposing Argument:[/bold]")
            console.print(Panel(previous_argument, border_style="dim", padding=(0, 1)))
        
        console.print(f"\n[bold]Enter your {arg_type}:[/bold] (or type 'done' to end session)")
        console.print("[dim]Tip: Reference sections from the retrieved list above[/dim]\n")
        
        lines = []
        try:
            while True:
                line = input()
                if line.strip().lower() == 'done':
                    return ""
                lines.append(line)
                if line.strip() == "":  # Empty line ends input
                    break
        except EOFError:
            pass
        
        argument = "\n".join(lines).strip()
        return argument

    def _get_llm_argument(self, agent_wrapper, arg_type: str, previous_argument: str = None) -> str:
        """Get argument from LLM agent."""
        self.turn_count += 1
        
        console.print()
        console.print(Panel(
            f"[bold red]Turn {self.turn_count}: AI {arg_type.upper()}[/bold red]\n"
            f"[dim]Role: {self.llm_role.upper()}[/dim]",
            border_style="red", padding=(1, 2)
        ))
        
        console.print("[dim]→ AI is formulating argument...[/dim]\n")
        
        agent = agent_wrapper["agent"]
        session = agent_wrapper.get("session")
        
        # Call appropriate agent method
        if arg_type == "opening":
            # Opening argument
            if self.llm_role == "prosecution":
                # ProsecutorAgent
                session = agent.opening_argument(session)
                argument = session.turn_history[-1].argument
            else:
                # DefenseAgent
                result = agent.build_opening_argument()
                argument = result.get("opening_statement", "")
        else:
            # Rebuttal
            if self.llm_role == "prosecution":
                # ProsecutorAgent
                session = agent.rebuttal(session, previous_argument)
                argument = session.turn_history[-1].argument
            else:
                # DefenseAgent
                result = agent.handle_rebuttal(previous_argument)
                # Extract rebuttal text from nested structure
                argument = result.get("defense_response", {}).get("rebuttal", "")
        
        # Update session in wrapper if it exists
        if session:
            agent_wrapper["session"] = session
        
        console.print(Panel(argument, border_style="green", padding=(1, 2)))
        
        return argument


# ─────────────────────────────────────────────────────────────
# Legacy methods for compatibility
# ─────────────────────────────────────────────────────────────

    def run(self, orchestrator_input: OrchestratorInput) -> OrchestratorResult:
        """
        Legacy method for compatibility.
        Full pipeline on the entire case text. Called once at session start.
        """
        return self.run_lexigraphbe_pipeline(orchestrator_input.case_text)

    def query_for_fact(
        self,
        fact_text: str,
        context_text: str,
        existing_section_numbers: List[str],
    ) -> OrchestratorResult:
        """
        Legacy method for compatibility.
        Targeted pipeline for a specific unaddressed fact raised mid-session.
        """
        # Compose a focused query text: fact + context
        query_text = (
            f"RELEVANT CASE CONTEXT:\n{context_text}\n\n"
            f"SPECIFIC FACT REQUIRING LEGAL ANALYSIS:\n{fact_text}"
        )
        result = self.run_lexigraphbe_pipeline(query_text)

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
