"""
agents/orchestrator/__main__.py
Entry point for the orchestrator package.

Usage (from backend/):
    python -m agents.orchestrator                          # demo case, 2 rounds
    python -m agents.orchestrator my_case.txt              # file input
    python -m agents.orchestrator my_case.txt --rounds 3   # custom rounds

In production the case text comes from the frontend via WebSocket / REST
(see app_orchestrator.py). This file is the CLI harness with rich visual display.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ── Demo / fallback case ──────────────────────────────────────────────────────
DEMO_CASE = (
    "The accused, Ramesh Kumar, allegedly stabbed the victim Suresh Gupta "
    "with a kitchen knife outside a restaurant on 12 March 2026. "
    "Two eyewitnesses were present. The victim was hospitalized and survived. "
    "A blood-stained kitchen knife was recovered from the accused's bag."
)

AGENT_COLORS = {
    "prosecutor": "red",
    "defense": "cyan",
    "judge": "gold1",
    "accused": "green",
    "evidence_analyzer": "magenta",
    "lexigraph": "purple",
}


def _print_event(evt: dict) -> None:
    etype = evt.get("type", "")

    if etype == "phase_change":
        phase = evt.get("phase", "")
        sid = evt.get("session_id", "")
        sid_str = f" · Session {sid[:8]}" if sid else ""
        console.rule(f"[bold cyan]PHASE: {phase}{sid_str}")
        return

    if etype == "judge_scores":
        p = evt.get("prosecution", {})
        d = evt.get("defense", {})
        rnd = evt.get("round", 1)
        overall = evt.get("overall", 0)

        tbl = Table(
            title=f"⚖️  JUDGE EVALUATION SCORES · Round {rnd}",
            title_style="bold gold1",
            box=box.ROUNDED,
            border_style="bright_blue",
            show_footer=True,
        )
        tbl.add_column("Scoring Metric", style="bold white", footer="Average (0–10)")
        tbl.add_column(
            "Prosecution",
            style="red",
            justify="center",
            footer=f"[bold red]{p.get('average', 0)}/10[/] ([dim]Tot: {p.get('total', 0)}/30[/])",
        )
        tbl.add_column(
            "Defense",
            style="cyan",
            justify="center",
            footer=f"[bold cyan]{d.get('average', 0)}/10[/] ([dim]Tot: {d.get('total', 0)}/30[/])",
        )

        tbl.add_row("Legal Validity", f"{p.get('legal_validity', 0)}/10", f"{d.get('legal_validity', 0)}/10")
        tbl.add_row("Evidence Linkage", f"{p.get('evidence_linkage', 0)}/10", f"{d.get('evidence_linkage', 0)}/10")
        tbl.add_row("Logic Coherence", f"{p.get('logic_coherence', 0)}/10", f"{d.get('logic_coherence', 0)}/10")

        console.print(tbl)
        console.print(
            f"  [dim]Overall Debate Quality:[/] [bold]{overall}/10[/bold]  "
            f"[dim](Sufficiency Threshold: 6.0)[/dim]\n"
        )
        return

    if etype == "agent_message":
        agent = evt.get("agent", "")
        rnd = evt.get("round", "")
        cits = evt.get("citations", [])
        evs = evt.get("evidence_refs", [])
        grounded = evt.get("grounded", None)
        unverified = evt.get("unverified", [])
        color = AGENT_COLORS.get(agent, "white")

        # Filter citations: remove N/A placeholders and single-char tokens
        _NA_VALS = {"n/a", "not applicable", "na", "", "none"}
        cits_clean = [
            c for c in (cits or [])
            if isinstance(c, str) and len(c.strip()) > 1 and c.strip().lower() not in _NA_VALS
        ]
        # Filter unverified the same way (guards against the 'o'/'m' per-char bug)
        unverified_clean = [
            u for u in (unverified or [])
            if isinstance(u, str) and len(u.strip()) > 1 and u.strip().lower() not in _NA_VALS
        ]

        # For lexigraph: prefer the structured subtitle sent by the node
        if agent == "lexigraph" and evt.get("subtitle"):
            subtitle = evt["subtitle"]
        else:
            cits_str = f"Citations: {', '.join(cits_clean)}" if cits_clean else ""
            unv_str = f"[red]Unverified: {', '.join(unverified_clean)}[/]" if unverified_clean else ""
            evs_str = f"Evidence: {', '.join(evs)}" if evs else ""
            meta_parts = [p for p in (cits_str, unv_str, evs_str) if p]
            subtitle = " · ".join(meta_parts) if meta_parts else None

        grounded_badge = ""
        if grounded is True:
            grounded_badge = " [green]✓ grounded[/]"
        elif grounded is False:
            if unverified_clean:
                grounded_badge = f" [red bold]⚠ ungrounded ({len(unverified_clean)} unverified)[/]"
            else:
                grounded_badge = " [red bold]⚠ ungrounded fallback[/]"
        elif isinstance(grounded, str) and grounded:
            grounded_badge = f" [red bold]⚠ {grounded}[/]"

        raw_content = str(evt.get("content", "")).strip()

        # Word boundary truncation to avoid clipping mid-word
        def _truncate_word_boundary(text: str, max_chars: int = 350) -> str:
            text = text.strip()
            if len(text) <= max_chars:
                return text
            cut = text[:max_chars]
            last_space = max(cut.rfind(" "), cut.rfind("\n"))
            if last_space > int(max_chars * 0.6):
                cut = cut[:last_space]
            return cut.rstrip() + "\n\n[dim italic]… [Full argument saved to transcript][/dim italic]"

        preview = _truncate_word_boundary(raw_content, 350)
        # Put metadata inside panel body to wrap cleanly and prevent border clipping (e.g. CrPC 7─)
        body = f"[dim]{subtitle}[/dim]\n\n{preview}" if subtitle else preview

        console.print(
            Panel(
                body,
                title=f"[{color} bold]{agent.upper()}[/] · Round {rnd}{grounded_badge}",
                border_style=color,
                box=box.ROUNDED,
            )
        )
        return


    if etype == "judge_question":
        q = evt.get("question", "")
        console.print(
            Panel(
                f"[bold yellow]{q}[/]",
                title="[bold gold1]⚖️  JUDICIAL INQUIRY TO ACCUSED[/]",
                border_style="gold1",
                box=box.DOUBLE,
            )
        )
        return

    if etype == "verdict":
        res = str(evt.get("result", "")).upper()
        conf_str = str(evt.get("confidence_label") or evt.get("confidence") or "medium").upper()
        expl = str(evt.get("explanation", "")).strip()
        statutes = evt.get("statutes", [])
        precedents = evt.get("precedents", [])
        holdings = evt.get("holdings_relied", [])

        valid_v = evt.get("valid_votes")
        total_v = evt.get("total_votes")
        agree_c = evt.get("agree_count")
        tally_info = f" ({agree_c}/{valid_v} agree, {valid_v}/{total_v} valid)" if valid_v and total_v else ""

        verdict_body_parts = []
        if statutes:
            verdict_body_parts.append(f"[bold]Statutes Applied:[/] {', '.join(statutes)}")
        if precedents:
            verdict_body_parts.append(f"[bold]Precedents Relied On:[/] {', '.join(precedents)}")
        if holdings:
            verdict_body_parts.append(f"[bold]Holdings Applied:[/] {', '.join(holdings)}")
        if verdict_body_parts:
            verdict_body_parts.append("")
        verdict_body_parts.append(expl)

        full_expl = "\n".join(verdict_body_parts)

        if res == "GRANTED":
            v_color = "bold green"
            b_style = box.DOUBLE
        elif res == "DENIED":
            v_color = "bold red"
            b_style = box.HEAVY
        elif res == "INTERIM":
            v_color = "bold cyan"
            b_style = box.ROUNDED
        else:  # NO_OPINION
            v_color = "bold yellow"
            b_style = box.ASCII_DOUBLE_HEAD

        console.print(
            Panel(
                full_expl,
                title=f"[{v_color}]FINAL COURT ORDER: {res} ({conf_str} CONFIDENCE{tally_info})[/]",
                border_style=v_color.split()[-1],
                box=b_style,
            )
        )
        return


    if etype == "error":
        console.print(f"[bold red][ERROR][/] {evt.get('message', '')}")
        return


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m agents.orchestrator",
        description="Run the MootCourt orchestrator pipeline from the CLI.",
    )
    parser.add_argument(
        "case_file",
        nargs="?",
        help="Path to a .txt/.pdf case file. If omitted, the built-in demo case is used.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=2,
        help="Maximum courtroom argument rounds (default: 2).",
    )
    parser.add_argument(
        "--role",
        choices=["prosecutor", "prosecution", "defense", "defence", "auto"],
        default=None,
        help="Human role in AI vs Human mode ('prosecutor' or 'defense'). 'auto' runs AI vs AI simulation.",
    )
    parser.add_argument(
        "--mode",
        choices=["ai_vs_human", "ai_vs_ai"],
        default=None,
        help="Courtroom mode: 'ai_vs_human' (default) or 'ai_vs_ai'.",
    )
    parser.add_argument(
        "--argument",
        type=str,
        default=None,
        help="Optional initial argument text for the human turn.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed diagnostic and graph node mapping dumps.",
    )
    args = parser.parse_args()

    import os
    if args.verbose:
        os.environ["VERBOSE"] = "1"

    # ── Role selection for AI vs Human ───────────────────────────────────────
    chosen_role = args.role
    chosen_mode = args.mode

    if chosen_role == "auto":
        chosen_role = None
        chosen_mode = "ai_vs_ai"
    elif not chosen_role and not chosen_mode and sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
        console.print()
        console.print(
            Panel(
                "[bold cyan]SELECT PROCEDURAL CAPACITY (AI vs Human)[/bold cyan]\n"
                "[bold yellow][1][/bold yellow] Public Prosecutor  [dim]— You vs AI Defense Counsel[/dim]\n"
                "[bold yellow][2][/bold yellow] Defense Counsel    [dim]— You vs AI Public Prosecutor[/dim]\n"
                "[bold yellow][3][/bold yellow] Auto Simulation   [dim]— Full AI vs AI courtroom debate[/dim]",
                title="⚖️  MOOT COURT ROLE SELECTION",
                border_style="bright_blue",
                box=box.ROUNDED,
            )
        )
        try:
            from rich.prompt import Prompt
            choice = Prompt.ask("Choose your standing", choices=["1", "2", "3"], default="1")
            if choice == "1":
                chosen_role = "prosecutor"
                chosen_mode = "ai_vs_human"
            elif choice == "2":
                chosen_role = "defense"
                chosen_mode = "ai_vs_human"
            else:
                chosen_role = None
                chosen_mode = "ai_vs_ai"
        except Exception:
            chosen_role = "prosecutor"
            chosen_mode = "ai_vs_human"

    def cli_human_input(speaker: str, round_no: int, state: dict) -> str:
        role_label = "PUBLIC PROSECUTOR" if speaker == "prosecutor" else "DEFENSE COUNSEL"
        console.print()
        console.print(
            Panel(
                f"[bold yellow]Turn: YOUR {role_label} SUBMISSION (Round {round_no})[/bold yellow]\n"
                f"[dim]Deliver your legal submissions on record. Reference applicable facts and laws.[/dim]\n"
                f"[dim](Type your submission and press Enter. End with an empty line or press Ctrl+D/Z)[/dim]",
                title="⚖️  COUNSEL SUBMISSION",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
        lines = []
        try:
            while True:
                line = input()
                if not line and lines:
                    break
                lines.append(line)
        except EOFError:
            pass
        return "\n".join(lines).strip()

    # ── Resolve case text or file path ────────────────────────────────────────
    if args.case_file:
        p = Path(args.case_file)
        if not p.exists():
            console.print(f"[bold red]Error:[/] File not found: {p}", file=sys.stderr)
            sys.exit(1)
        ext = p.suffix.lower()
        if ext in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
            # Pass absolute file path directly for Evidence Analyzer PDF/OCR pipeline
            case_input = str(p.resolve())
            console.print(f"[dim]Loaded case document ({ext.upper()}) from {p}[/dim]")
        else:
            case_input = p.read_text(encoding="utf-8", errors="ignore").strip()
            console.print(f"[dim]Loaded text case from {p} ({len(case_input)} chars)[/dim]")
    else:
        case_input = DEMO_CASE
        console.print("[dim]No file provided — running built-in DEMO_CASE.[/dim]")

    # ── Import late so package __init__ stays lazy ────────────────────────────
    from agents.orchestrator.orchestrator_graph import run_orchestrator

    result = run_orchestrator(
        case_id=case_input,
        max_rounds=args.rounds,
        on_event=_print_event,
        user_role=chosen_role,
        mode=chosen_mode,
        human_argument=args.argument,
        human_input_fn=cli_human_input,
    )


    sid = result.get("session_id", "session")
    verdict = result.get("verdict") or {}
    errors  = result.get("errors", [])

    # Transcript export file locations
    transcripts_dir = Path(__file__).resolve().parent.parent.parent / "transcripts"
    md_file = transcripts_dir / f"transcript_{sid}.md"
    json_file = transcripts_dir / f"transcript_{sid}.json"

    export_info = ""
    if md_file.exists():
        export_info = f"\n\n[bold green]Full Transcripts Saved:[/] \n  • Markdown: [underline]{md_file}[/underline]\n  • JSON    : [underline]{json_file}[/underline]"

    raw_conf = verdict.get('confidence', 0.5)
    conf_map = {"low": "30%", "medium": "60%", "high": "90%"}
    if isinstance(raw_conf, str) and raw_conf.lower() in conf_map:
        conf_display = f"{raw_conf.capitalize()} ({conf_map[raw_conf.lower()]})"
    else:
        try:
            conf_val = float(raw_conf)
            conf_display = f"{int(conf_val * 100)}%" if conf_val <= 1.0 else f"{int(conf_val)}%"
        except (ValueError, TypeError):
            conf_display = str(raw_conf)

    console.print(
        Panel(
            f"[bold]Decision[/]   : {verdict.get('decision', 'N/A').upper()}\n"
            f"[bold]Confidence[/] : {conf_display}\n"
            f"[bold]Laws Applied[/]: {', '.join(verdict.get('laws_applied', []))}"
            f"{export_info}",
            title=f"⚖️  MOOT COURT SUMMARY · Session {sid[:8]}",
            border_style="bright_blue",
            box=box.ROUNDED,
        )
    )

    if errors:
        console.print(f"\n[bold red]Errors encountered ({len(errors)}):[/]")
        for e in errors:
            console.print(f"  • [red]{e}[/]")


if __name__ == "__main__":
    main()

