"""
Console Formatter — Pretty terminal output for Moot Court Simulation
=====================================================================
Provides buffered, structured output helpers so that agent nodes
can collect their logs and print them atomically (no interleaving).
"""

import io
import os
import sys
import textwrap
import json
from contextlib import contextmanager
from datetime import datetime

# ── Force UTF-8 on Windows stdout ─────────────────────────────────────────────
if sys.platform == "win32":
    # Reconfigure stdout to UTF-8 so ANSI / Unicode chars don't crash on cp1252
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    # Enable Windows Virtual Terminal Processing for ANSI escape codes
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass

# ── Constants ─────────────────────────────────────────────────────────────────
WIDTH = 80
THIN  = "-"
THICK = "="
DOT   = "*"

# ANSI color codes (work on Windows Terminal, PowerShell 7+, VS Code terminal)
# Detect if terminal supports ANSI
def _supports_ansi() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("TERM") == "dumb":
        return False
    # If stdout is redirected to a file/pipe, skip colors
    if not hasattr(sys.stdout, "isatty"):
        return False
    if not sys.stdout.isatty():
        return False
    return True

_ANSI = _supports_ansi()

class C:
    RESET     = "\033[0m"   if _ANSI else ""
    BOLD      = "\033[1m"   if _ANSI else ""
    DIM       = "\033[2m"   if _ANSI else ""
    CYAN      = "\033[36m"  if _ANSI else ""
    GREEN     = "\033[32m"  if _ANSI else ""
    YELLOW    = "\033[33m"  if _ANSI else ""
    RED       = "\033[31m"  if _ANSI else ""
    MAGENTA   = "\033[35m"  if _ANSI else ""
    BLUE      = "\033[34m"  if _ANSI else ""
    WHITE     = "\033[97m"  if _ANSI else ""
    B_CYAN    = "\033[96m"  if _ANSI else ""
    B_GREEN   = "\033[92m"  if _ANSI else ""
    B_YELLOW  = "\033[93m"  if _ANSI else ""
    B_RED     = "\033[91m"  if _ANSI else ""
    B_MAGENTA = "\033[95m"  if _ANSI else ""
    B_BLUE    = "\033[94m"  if _ANSI else ""


# ── Agent banner colors ───────────────────────────────────────────────────────
AGENT_COLORS = {
    "EVIDENCE ANALYZER":  C.B_CYAN,
    "LEXIGRAPH":          C.B_BLUE,
    "PROSECUTOR":         C.B_RED,
    "DEFENSE LAWYER":     C.B_GREEN,
    "JUDGE":              C.B_MAGENTA,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _color(text: str, color: str) -> str:
    return f"{color}{text}{C.RESET}"


def _bold(text: str) -> str:
    return f"{C.BOLD}{text}{C.RESET}"


def _dim(text: str) -> str:
    return f"{C.DIM}{text}{C.RESET}"


def header(agent_name: str, subtitle: str = "") -> str:
    """Return a prominent agent header block."""
    color = AGENT_COLORS.get(agent_name.upper(), C.WHITE)
    lines = []
    lines.append("")
    lines.append(_color(THICK * WIDTH, color))
    lines.append(_color(f"  >>  {agent_name.upper()}", color) + (f"  {_dim(subtitle)}" if subtitle else ""))
    lines.append(_color(THICK * WIDTH, color))
    return "\n".join(lines)


def subheader(title: str) -> str:
    """A lighter sub-section header."""
    return f"\n  {_bold(THIN * 3 + '  ' + title + '  ' + THIN * (WIDTH - len(title) - 8))}"


def kv(key: str, value, indent: int = 4) -> str:
    """Format a key-value pair."""
    prefix = " " * indent
    return f"{prefix}{_dim(key + ':'):<{22 + len(C.DIM) + len(C.RESET)}} {value}"


def bullet(text: str, indent: int = 6) -> str:
    """Bullet-point line."""
    prefix = " " * indent
    return f"{prefix}{DOT} {text}"


def status(emoji: str, message: str) -> str:
    """A status line with emoji prefix."""
    return f"  {emoji}  {message}"


def wrap_text(text: str, indent: int = 6, width: int = WIDTH - 8) -> str:
    """Wrap long text nicely, preserving paragraph breaks."""
    prefix = " " * indent
    paragraphs = text.strip().split("\n")
    wrapped_lines = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            wrapped_lines.append("")
            continue
        wrapped_lines.append(
            textwrap.fill(para, width=width, initial_indent=prefix, subsequent_indent=prefix)
        )
    return "\n".join(wrapped_lines)


def truncate(text: str, max_lines: int = 30) -> str:
    """Truncate multi-line text and indicate if cut."""
    lines = text.strip().splitlines()
    if len(lines) <= max_lines:
        return text.strip()
    kept = lines[:max_lines]
    kept.append(f"\n      {_dim(f'... ({len(lines) - max_lines} more lines omitted)')}")
    return "\n".join(kept)


def json_compact(data: dict, indent: int = 6) -> str:
    """Pretty-print JSON with controlled indent."""
    prefix = " " * indent
    raw = json.dumps(data, indent=2, ensure_ascii=False)
    lines = raw.splitlines()
    return "\n".join(f"{prefix}{line}" for line in lines)


def section_complete(agent_name: str) -> str:
    """Completion line for an agent."""
    color = AGENT_COLORS.get(agent_name.upper(), C.WHITE)
    return f"\n  {_color('[OK]', C.B_GREEN)}  {agent_name} completed.\n"


def divider() -> str:
    return _dim(THIN * WIDTH)


def final_banner() -> str:
    """The final simulation-complete banner."""
    lines = []
    lines.append("")
    lines.append(_color(THICK * WIDTH, C.B_YELLOW))
    lines.append(_color("  [*]  MOOT COURT SIMULATION COMPLETE", C.B_YELLOW))
    lines.append(_color(THICK * WIDTH, C.B_YELLOW))
    return "\n".join(lines)


def session_banner(session_id: str, file_path: str) -> str:
    """Opening session banner."""
    lines = []
    lines.append("")
    lines.append(_color(THICK * WIDTH, C.B_YELLOW))
    lines.append(_color("  [MOOT COURT SIMULATION]", C.B_YELLOW))
    lines.append(_color(THICK * WIDTH, C.B_YELLOW))
    lines.append(kv("Session", session_id))
    lines.append(kv("Document", file_path))
    lines.append(kv("Started", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    lines.append("")
    return "\n".join(lines)


def verdict_box(verdict: str, reasoning: str, order: str) -> str:
    """A nicely boxed verdict display."""
    v_upper = verdict.upper()
    if v_upper in ("GUILTY",):
        v_color = C.B_RED
    elif v_upper in ("ACQUITTED",):
        v_color = C.B_GREEN
    elif v_upper in ("DEFERRED",):
        v_color = C.B_YELLOW
    else:
        v_color = C.B_MAGENTA

    lines = []
    lines.append("")
    lines.append(f"    +{'-' * (WIDTH - 6)}+")
    verdict_text = f"VERDICT: {v_upper}"
    pad = WIDTH - 6 - len(verdict_text)
    lines.append(f"    | {_color(_bold(verdict_text), v_color)}{' ' * max(0, pad - 1)}|")
    lines.append(f"    +{'-' * (WIDTH - 6)}+")
    lines.append("")
    lines.append(f"    {_bold('Reasoning:')}")
    lines.append(wrap_text(reasoning, indent=6, width=WIDTH - 10))
    lines.append("")
    lines.append(f"    {_bold('Order:')}")
    lines.append(wrap_text(order, indent=6, width=WIDTH - 10))
    return "\n".join(lines)


def summary_table(result: dict) -> str:
    """Final summary table."""
    facts = result.get("structured_facts", {})
    verdict_data = result.get("judge_verdict", {})
    who = facts.get("who", {})

    lines = []
    lines.append(kv("Session ID", result.get("session_id", "N/A")))
    lines.append(kv("Complainant", who.get("complainant", "N/A")))
    lines.append(kv("Accused", ", ".join(who.get("accused", ["N/A"]))))
    lines.append(kv("IPC Sections", ", ".join(facts.get("sections", ["N/A"]))))
    lines.append(kv("Verdict", verdict_data.get("verdict", "N/A").upper()))
    lines.append("")
    return "\n".join(lines)


# ── Buffered output context manager ──────────────────────────────────────────

import threading

_print_lock = threading.Lock()
_real_stdout = sys.stdout


@contextmanager
def buffered_output():
    """
    Context manager that collects all print() output into a buffer
    and flushes it atomically under a lock when the block exits.
    This is thread-safe: parallel agents won't interleave their output.
    """
    buffer = io.StringIO()
    # Each thread gets its own buffer; we swap sys.stdout per-thread via
    # threading.local if needed, but simpler: just pass buffer as a callable.
    # We override print to write to our buffer instead.
    import builtins
    original_print = builtins.print
    tid = threading.get_ident()

    def _buffered_print(*args, **kwargs):
        # Only intercept prints from our own thread
        if threading.get_ident() == tid:
            kwargs["file"] = buffer
            original_print(*args, **kwargs)
        else:
            original_print(*args, **kwargs)

    builtins.print = _buffered_print
    try:
        yield buffer
    finally:
        builtins.print = original_print
        output = buffer.getvalue()
        if output:
            with _print_lock:
                _real_stdout.write(output)
                _real_stdout.flush()
