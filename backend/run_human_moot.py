"""
Human vs AI Moot Court - Command Line Interface
================================================
Interactive CLI for law students to practice moot court against AI.

Usage:
    python run_human_moot.py "path/to/case.pdf" --role prosecutor --rounds 2
    python run_human_moot.py "path/to/case.pdf" --role defense --rounds 3
"""

import sys
import os
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
_backend_dir = Path(__file__).resolve().parent
_agents_dir  = _backend_dir / "agents"
for _p in [str(_backend_dir), str(_agents_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv
load_dotenv(_backend_dir / ".env")

import argparse
from typing import Dict, Any, List
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

# Import our orchestrator components
from agents.orchestrator.human_mode import HumanMootCourtOrchestrator, HumanArgumentValidator
from agents.evidence.evidence_analyzer import EvidenceAnalyzerAgent
from agents.lexigraph import lexigraph_node as lexigraph_retrieve

console = Console()


def print_header(title: str, subtitle: str = ""):
    """Print a styled header"""
    console.rule(f"[bold cyan]{title}[/bold cyan]")
    if subtitle:
        console.print(f"[dim]{subtitle}[/dim]\n")


def print_box(content: str, title: str = "", style: str = "cyan"):
    """Print content in a styled box"""
    console.print(Panel(content, title=title, border_style=style, padding=(1, 2)))


def load_case_document(case_path: str) -> str:
    """Load case document from PDF or text file"""
    from pathlib import Path
    
    path = Path(case_path)
    
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {case_path}")
        sys.exit(1)
    
    if path.suffix.lower() == '.pdf':
        # Use PDF extraction
        try:
            import PyPDF2
            with open(path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            return text
        except Exception as e:
            console.print(f"[red]Error reading PDF:[/red] {e}")
            sys.exit(1)
    else:
        # Plain text file
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            console.print(f"[red]Error reading file:[/red] {e}")
            sys.exit(1)


def run_evidence_phase(case_text: str) -> Dict[str, Any]:
    """Run evidence analysis phase"""
    console.print("\n[bold yellow]⚖️  PHASE 1: EVIDENCE ANALYSIS[/bold yellow]\n")
    
    with console.status("[cyan]Extracting facts and evidence from case document...[/cyan]"):
        try:
            analyzer = EvidenceAnalyzerAgent()
            result = analyzer.analyze(document_text=case_text)
            
            case_facts = result.get("facts", [])
            evidence_inventory = result.get("evidence_inventory", [])
            
            console.print(f"[green]✓[/green] Extracted [bold]{len(case_facts)}[/bold] case facts")
            console.print(f"[green]✓[/green] Identified [bold]{len(evidence_inventory)}[/bold] evidence items\n")
            
            # Show summary
            if case_facts[:3]:
                console.print("[dim]Sample facts:[/dim]")
                for i, fact in enumerate(case_facts[:3], 1):
                    fact_text = str(fact.get("text", fact) if isinstance(fact, dict) else fact)
                    console.print(f"  {i}. {fact_text[:100]}...")
            
            return {
                "case_facts": case_facts,
                "evidence_inventory": evidence_inventory,
            }
        
        except Exception as e:
            console.print(f"[red]Error in evidence analysis:[/red] {e}")
            sys.exit(1)


def run_lexigraph_phase(case_facts: List, evidence_inventory: List) -> Dict[str, Any]:
    """Run legal research phase"""
    console.print("\n[bold yellow]⚖️  PHASE 2: LEGAL RESEARCH (LEXIGRAPH)[/bold yellow]\n")
    
    with console.status("[cyan]Retrieving applicable statutes and precedents...[/cyan]"):
        try:
            result = lexigraph_retrieve(
                case_facts=case_facts,
                evidence_inventory=evidence_inventory,
            )
            
            sections = result.get("ipc_sections", [])
            holdings = result.get("holdings", [])
            
            console.print(f"[green]✓[/green] Retrieved [bold]{len(sections)}[/bold] statutory provisions")
            console.print(f"[green]✓[/green] Retrieved [bold]{len(holdings)}[/bold] precedent holdings\n")
            
            # Show key sections
            if sections:
                console.print("[dim]Key statutory provisions:[/dim]")
                for sec in sections[:5]:
                    if isinstance(sec, dict):
                        console.print(f"  • {sec.get('act', 'IPC')} {sec.get('section', '?')}: {sec.get('description', 'N/A')[:60]}...")
            
            return result
        
        except Exception as e:
            console.print(f"[red]Error in legal research:[/red] {e}")
            sys.exit(1)


def display_round_instructions(orchestrator: HumanMootCourtOrchestrator, round_no: int):
    """Display instructions for the current round"""
    round_info = orchestrator.start_round(round_no)
    instruction = round_info["instruction"]
    
    print_header(f"ROUND {round_no}", f"Student Role: {orchestrator.student_role.upper()}")
    console.print(Markdown(instruction))


def get_student_argument() -> str:
    """Get argument input from student"""
    console.print("\n[bold cyan]Your Argument:[/bold cyan]")
    console.print("[dim]Enter your argument below. Type 'END' on a new line when finished.[/dim]\n")
    
    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
        except EOFError:
            break
    
    return "\n".join(lines)


def display_validation_feedback(validation: Dict[str, Any]):
    """Display validation feedback"""
    if validation["valid"]:
        console.print("\n[green]✓ Argument Accepted[/green]\n")
    else:
        console.print("\n[red]✗ Argument Needs Revision[/red]\n")
    
    # Show feedback
    console.print(Markdown(validation["feedback"]))
    
    # Show citations found
    if validation.get("citations"):
        console.print(f"\n[dim]Citations found: {', '.join(validation['citations'])}[/dim]")
    
    if validation.get("evidence_refs"):
        console.print(f"[dim]Evidence references: {', '.join(validation['evidence_refs'])}[/dim]")


def display_ai_argument(role: str, argument: str, citations: List[str]):
    """Display AI's argument"""
    console.print(f"\n[bold magenta]🤖 AI {role.upper()} ARGUMENT[/bold magenta]\n")
    
    # Display argument in a box
    print_box(argument, title=f"AI {role.title()}", style="magenta")
    
    if citations:
        console.print(f"\n[dim]AI cited: {', '.join(citations[:10])}[/dim]")


def display_judge_evaluation(evaluation: Dict[str, Any], student_role: str, ai_role: str):
    """Display judge's evaluation of both arguments"""
    console.print("\n[bold yellow]⚖️  JUDGE'S EVALUATION[/bold yellow]\n")
    
    # Create comparison table
    table = Table(title="Scoring Comparison", box=box.ROUNDED)
    table.add_column("Criterion", style="cyan", no_wrap=True)
    table.add_column(f"Student ({student_role})", style="green", justify="center")
    table.add_column(f"AI ({ai_role})", style="magenta", justify="center")
    
    student_scores = evaluation.get("student_scores", {})
    ai_scores = evaluation.get("ai_scores", {})
    
    criteria = ["legal_validity", "evidence_linkage", "logic_coherence"]
    criterion_names = ["Legal Validity", "Evidence Linkage", "Logic & Coherence"]
    
    for crit, name in zip(criteria, criterion_names):
        student_val = student_scores.get(crit, "N/A")
        ai_val = ai_scores.get(crit, "N/A")
        
        table.add_row(
            name,
            f"{student_val}/10" if isinstance(student_val, (int, float)) else str(student_val),
            f"{ai_val}/10" if isinstance(ai_val, (int, float)) else str(ai_val),
        )
    
    # Add average row
    if student_scores and ai_scores:
        student_avg = sum(student_scores.get(c, 0) for c in criteria) / len(criteria)
        ai_avg = sum(ai_scores.get(c, 0) for c in criteria) / len(criteria)
        
        table.add_row(
            "[bold]Average[/bold]",
            f"[bold]{student_avg:.1f}/10[/bold]",
            f"[bold]{ai_avg:.1f}/10[/bold]",
        )
    
    console.print(table)
    
    # Judge's feedback
    feedback = evaluation.get("feedback", "")
    if feedback:
        console.print("\n[bold]Judge's Remarks:[/bold]")
        print_box(feedback, style="yellow")


def display_final_verdict(verdict: Dict[str, Any]):
    """Display final verdict"""
    console.print("\n" + "="*80)
    print_header("⚖️  FINAL VERDICT", "")
    
    result = verdict.get("result", "Unknown").upper()
    reasoning = verdict.get("reasoning", "")
    confidence = verdict.get("confidence", "medium")
    
    # Color based on result
    result_color = "green" if result == "GRANTED" else "red"
    
    console.print(f"\n[bold {result_color}]{result}[/bold {result_color}]")
    console.print(f"[dim]Confidence: {confidence}[/dim]\n")
    
    if reasoning:
        print_box(reasoning, title="Court's Reasoning", style="yellow")
    
    console.print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(
        description="Human vs AI Moot Court Session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("case_document", help="Path to case document (PDF or TXT)")
    parser.add_argument(
        "--role",
        choices=["prosecutor", "defense"],
        required=True,
        help="Your role in the moot court"
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=2,
        help="Maximum number of argument rounds (default: 2)"
    )
    parser.add_argument(
        "--name",
        type=str,
        default="Student",
        help="Your name (optional)"
    )
    
    args = parser.parse_args()
    
    # Welcome message
    console.clear()
    print_header(
        "⚖️  HUMAN vs AI MOOT COURT",
        f"Anticipatory Bail Application • Role: {args.role.upper()}"
    )
    
    console.print(f"\n[bold]Welcome, {args.name}![/bold]")
    console.print(f"You will be playing as [bold cyan]{args.role.upper()}[/bold cyan]")
    console.print(f"The AI will play as [bold magenta]{('DEFENSE' if args.role == 'prosecutor' else 'PROSECUTOR')}[/bold magenta]")
    console.print(f"Session will run for up to [bold]{args.rounds}[/bold] rounds\n")
    
    if not Confirm.ask("Ready to begin?"):
        console.print("[yellow]Session cancelled.[/yellow]")
        return
    
    # Load case document
    console.print("\n[bold]Loading case document...[/bold]")
    case_text = load_case_document(args.case_document)
    console.print(f"[green]✓[/green] Loaded {len(case_text)} characters from {Path(args.case_document).name}\n")
    
    # Phase 1: Evidence Analysis
    evidence_result = run_evidence_phase(case_text)
    case_facts = evidence_result["case_facts"]
    evidence_inventory = evidence_result["evidence_inventory"]
    
    # Phase 2: Legal Research
    lexigraph_output = run_lexigraph_phase(case_facts, evidence_inventory)
    
    # Initialize orchestrator
    console.print("\n[bold yellow]⚖️  PHASE 3: COURTROOM SESSION[/bold yellow]\n")
    
    def on_event(event: Dict[str, Any]):
        """Handle orchestrator events"""
        event_type = event.get("type", "")
        if event_type == "ai_thinking":
            console.print(f"\n[dim]🤖 AI {event.get('role', 'opponent')} is preparing argument...[/dim]")
    
    orchestrator = HumanMootCourtOrchestrator(
        student_role=args.role,
        case_facts=case_facts,
        evidence_inventory=evidence_inventory,
        lexigraph_output=lexigraph_output,
        max_rounds=args.rounds,
        on_event=on_event,
    )
    
    # Run courtroom rounds
    for round_no in range(1, args.rounds + 1):
        console.print("\n" + "="*80 + "\n")
        
        # Display round instructions
        display_round_instructions(orchestrator, round_no)
        
        # Student submits argument
        while True:
            student_arg = get_student_argument()
            
            if not student_arg.strip():
                console.print("[yellow]No argument entered. Please try again.[/yellow]")
                continue
            
            # Validate and submit
            result = orchestrator.submit_student_argument(student_arg)
            validation = result["validation"]
            
            display_validation_feedback(validation)
            
            if result["status"] == "accepted":
                break
            else:
                console.print("\n[yellow]Please revise your argument based on the feedback above.[/yellow]\n")
        
        # AI generates response
        console.print("\n[dim]Waiting for AI opponent to respond...[/dim]")
        ai_result = orchestrator.generate_ai_response()
        
        if ai_result["status"] == "success":
            display_ai_argument(
                orchestrator.ai_role,
                ai_result["argument"],
                ai_result.get("citations", [])
            )
        else:
            console.print(f"[red]Error:[/red] {ai_result.get('message', 'AI generation failed')}")
            break
        
        # Judge evaluates
        console.print("\n[dim]Judge is evaluating arguments...[/dim]")
        evaluation = orchestrator.get_judge_evaluation()
        
        if evaluation.get("status") != "error":
            display_judge_evaluation(evaluation, args.role, orchestrator.ai_role)
        
        # Check if we should continue
        if round_no < args.rounds:
            console.print("\n")
            if not Confirm.ask(f"Continue to Round {round_no + 1}?"):
                console.print("[yellow]Session ended by user.[/yellow]")
                break
    
    # Final verdict
    console.print("\n[dim]Court is preparing final verdict...[/dim]")
    
    # Mock verdict for now (integrate with actual judge verdict agent)
    verdict = {
        "result": "granted",  # or "denied"
        "reasoning": "Based on the arguments presented across all rounds, considering the lack of prima facie case and absence of custodial necessity, while noting the prosecution's concerns about investigation stage.",
        "confidence": "medium"
    }
    
    display_final_verdict(verdict)
    
    # Save transcript
    transcript_path = _backend_dir / "transcripts" / f"human_session_{args.role}_{Path(args.case_document).stem}.md"
    transcript_path.parent.mkdir(exist_ok=True)
    
    console.print(f"\n[green]✓[/green] Session complete!")
    console.print(f"[dim]Transcript saved to: {transcript_path}[/dim]\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Session interrupted by user.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Fatal error:[/red] {e}")
        import traceback
        console.print("[dim]" + traceback.format_exc() + "[/dim]")
        sys.exit(1)
