"""
Moot Court Terminal Runner
==========================
Entry point for the virtual moot court session on the terminal.

Flow:
  1. Student inputs case (PDF path / text file path / paste text)
  2. Student chooses role: prosecutor or defense
  3. If student = defense  → AI plays prosecutor (this file drives it)
     If student = prosecutor → future build (defense agent mirror)
  4. Prosecutor gives opening argument (4 pillars)
  5. Student types defense argument
  6. Prosecutor rebuts (non-repetitive, queries orchestrator only if needed)
  7. Loop until student types 'quit' or 'end'

Usage:
  python -m mootcourt_agents.runner
  python -m mootcourt_agents.runner --file case.pdf
  python -m mootcourt_agents.runner --text "Case facts here..."
"""

from __future__ import annotations
import argparse
import os
import sys
import textwrap
from pathlib import Path

# Load .env file from backend directory BEFORE any other imports
from dotenv import load_dotenv
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from .prosecutor_agent import ProsecutorAgent, load_case_text
from .schemas import SessionState

console = Console()

QUIT_COMMANDS = {"quit", "exit", "end", "q"}


# ─────────────────────────────────────────────────────────────
# Input helpers
# ─────────────────────────────────────────────────────────────

def _get_case_source() -> str:
    """
    Prompt the student to provide the case.
    Accepts: PDF path, .txt path, or pasted text.
    """
    console.print()
    console.print(Panel(
        "[bold white]VIRTUAL MOOT COURT[/bold white]\n"
        "[dim]Anticipatory Bail Hearing Simulator[/dim]",
        border_style="blue",
        padding=(1, 4),
    ))
    console.print()
    console.print("[bold cyan]How would you like to provide the case?[/bold cyan]")
    console.print("  [yellow]1[/yellow] — Enter path to a PDF or .txt file")
    console.print("  [yellow]2[/yellow] — Paste case facts directly")
    console.print()

    choice = Prompt.ask("Enter choice", choices=["1", "2"], default="1")

    if choice == "1":
        while True:
            path_str = Prompt.ask("[cyan]File path[/cyan]").strip()
            p = Path(path_str)
            if p.exists() and p.suffix.lower() in (".pdf", ".txt"):
                return str(p)
            if p.exists():
                console.print(f"[red]Unsupported file type '{p.suffix}'. Use .pdf or .txt[/red]")
            else:
                console.print(f"[red]File not found: {path_str}[/red]")
    else:
        console.print(
            "[dim]Paste the case facts below. "
            "When done, enter a line with just END on its own line.[/dim]"
        )
        lines = []
        while True:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
        text = "\n".join(lines).strip()
        if not text:
            console.print("[red]No case text provided. Exiting.[/red]")
            sys.exit(1)
        return text


def _get_student_role() -> str:
    console.print()
    console.print("[bold cyan]Choose your role in this hearing:[/bold cyan]")
    console.print("  [yellow]1[/yellow] — Defense (AI will argue as Prosecutor)")
    console.print("  [yellow]2[/yellow] — Prosecutor (AI will argue as Defense) [dim]— coming soon[/dim]")
    console.print()
    choice = Prompt.ask("Enter choice", choices=["1", "2"], default="1")
    if choice == "2":
        console.print(
            "[yellow]Defense AI agent is not yet built. "
            "Defaulting to Defense role for you.[/yellow]"
        )
    return "defense"


def _get_defense_argument(turn_number: int) -> str:
    """
    Prompt the student to type their defense argument.
    Multi-line: ends when student enters a line with just END.
    Returns empty string if student types quit/exit.
    """
    console.print()
    console.print(Panel(
        "[bold white]YOUR TURN — Defense Argument[/bold white]\n"
        "[dim]Type your argument. Enter END on its own line when done.\n"
        "Type QUIT to end the session.[/dim]",
        border_style="green",
        padding=(0, 2),
    ))
    console.print()

    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().upper() in {c.upper() for c in QUIT_COMMANDS}:
            return ""
        if line.strip().upper() == "END":
            break
        lines.append(line)

    return "\n".join(lines).strip()


def _print_session_summary(session: SessionState) -> None:
    console.print()
    console.rule("[bold white on red]  SESSION SUMMARY  [/bold white on red]")
    console.print()

    total = len(session.turns)
    p_turns = [t for t in session.turns if t.speaker == "prosecutor"]
    d_turns = [t for t in session.turns if t.speaker == "defense"]

    console.print(f"  [bold cyan]Total turns:[/bold cyan]      {total}")
    console.print(f"  [bold cyan]Prosecutor turns:[/bold cyan] {len(p_turns)}")
    console.print(f"  [bold cyan]Defense turns:[/bold cyan]    {len(d_turns)}")

    console.print()
    console.print(f"  [bold cyan]IPC Sections Retrieved:[/bold cyan]")
    for sec_num, sec in session.retrieved_sections.items():
        console.print(
            f"    [yellow]§{sec_num}[/yellow] {sec.statute} — {sec.title} "
            f"[dim](retrieved at turn {sec.retrieved_at_turn})[/dim]"
        )

    console.print()
    console.print(f"  [bold cyan]Pillars Argued:[/bold cyan]")
    for p in session.pillars_argued:
        console.print(f"    [magenta]•[/magenta] {p}")

    console.print()
    console.print(f"  [bold cyan]Prosecution Positions Taken:[/bold cyan]")
    for pos in session.prosecutor_positions:
        console.print(f"    [red]→[/red] {pos}")

    console.print()
    console.print(f"  [bold cyan]Defense Positions Taken:[/bold cyan]")
    for pos in session.defense_positions:
        console.print(f"    [green]→[/green] {pos}")

    from .prosecutor_agent import _session_path
    console.print()
    console.print(
        f"  [dim]Session saved: {_session_path(session.session_id)}[/dim]"
    )
    console.print()


# ─────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────

def run_session(
    source: str = None,
    student_role: str = None,
    api_key: str = None,
    model: str = "gpt-4o-mini",
) -> None:
    """
    Full terminal session loop.
    Can be called programmatically or via CLI.
    """
    api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        console.print(
            "[red]Error: OPENAI_API_KEY not set. "
            "Export it or pass --api-key.[/red]"
        )
        sys.exit(1)

    # ── Get case source if not provided ──
    if not source:
        source = _get_case_source()

    # ── Get student role if not provided ──
    if not student_role:
        student_role = _get_student_role()

    # ── Build agent ──
    agent = ProsecutorAgent(api_key=api_key, model=model)

    # ── Start session — extracts case, calls orchestrator, writes session file ──
    session = agent.start_session(source=source, student_role=student_role)

    # ── Opening argument — prosecutor goes first ──
    session = agent.opening_argument(session)

    # ── Main debate loop ──
    round_number = 1
    while True:
        console.print()
        console.print(
            f"[dim]Round {round_number} complete. "
            f"Sections in memory: {list(session.retrieved_sections.keys())} | "
            f"Pillars argued: {session.pillars_argued}[/dim]"
        )
        console.print()

        # Defense turn (human)
        defense_arg = _get_defense_argument(session.current_turn + 1)

        if not defense_arg:
            # Student typed quit
            console.print()
            console.print("[yellow]Session ended by student.[/yellow]")
            break

        if len(defense_arg.strip()) < 10:
            console.print("[yellow]Argument too short — please provide a substantive response.[/yellow]")
            continue

        # Prosecutor rebuttal (AI)
        session = agent.rebuttal(session, defense_argument=defense_arg)
        round_number += 1

        # Check if all pillars are fully argued and we've had enough rounds
        if (
            len(session.pillars_argued) == 4
            and round_number > 4
        ):
            console.print()
            console.print(Panel(
                "[bold white]All 4 prosecution pillars have been argued and "
                "we have completed multiple rounds.\n"
                "You may continue or type QUIT to end the session.[/bold white]",
                border_style="yellow",
                padding=(1, 2),
            ))

    # ── Session summary ──
    _print_session_summary(session)


def main():
    parser = argparse.ArgumentParser(
        description="Virtual Moot Court — Anticipatory Bail Hearing Simulator"
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--file", "-f", type=str, help="Path to .pdf or .txt case file")
    src.add_argument("--text", "-t", type=str, help="Case facts as a plain string")
    parser.add_argument("--role",    type=str,  default=None,
                        choices=["defense", "prosecutor"],
                        help="Your role (default: prompts you to choose)")
    parser.add_argument("--model",   type=str,  default="gpt-4o-mini",
                        help="OpenAI model (default: gpt-4o-mini)")
    parser.add_argument("--api-key", type=str,  default=None,
                        help="OpenAI API key (or set OPENAI_API_KEY)")
    args = parser.parse_args()

    source = args.file or args.text or None

    run_session(
        source=source,
        student_role=args.role,
        api_key=args.api_key,
        model=args.model,
    )


if __name__ == "__main__":
    main()