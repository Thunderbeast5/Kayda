"""
agents/orchestrator/usage_logger.py
===================================
Instrumentation usage logger for the courtroom pipeline.
Records, for EVERY LLM call, directly from the API response
(usage_metadata / response_metadata):
  - call_index
  - stage / agent name
  - model
  - input_tokens
  - output_tokens
  - cached_tokens (input_token_details.cache_read)
  - total_tokens

Outputs:
  - logs/usage_<run_label>.jsonl (one JSON line per API call)
  - logs/output_<run_label>.json (final orchestrator verified sections, holdings, bail factors, arguments, verdict, reasoning)
  - Per-stage and per-agent summary table printed via rich at completion
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
import inspect
import itertools
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any, Dict, List, Optional

# Ensure stdout/stderr handle Unicode on Windows consoles safely
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich import box
from rich.console import Console
from rich.table import Table

console = Console(safe_box=True, highlight=False)

# Feature flag: set USAGE_LOGGING=true to write JSONL logs and print usage tables.
# Default is false — no I/O overhead in normal runs.
_USAGE_LOGGING: bool = os.getenv("USAGE_LOGGING", "false").strip().lower() in ("true", "1", "yes")

# ContextVar for active stage name
_active_stage = contextvars.ContextVar("active_stage", default="unknown")

# Canonical stage ordering as requested:
STAGE_ORDER = [
    "evidence analyzer",
    "lexigraph stage 0",
    "lexigraph stage 1",
    "lexigraph stage 2",
    "lexigraph stage 3",
    "lexigraph stage 4",
    "lexigraph stage 5",
    "lexigraph stage 6",
    "prosecutor",
    "defense",
    "judge question",
    "judge evaluation",
    "voting",
    "retries/repairs",
]


@contextmanager
def track_stage(stage_name: str):
    """Context manager to scope all subsequent LLM calls to stage_name."""
    token = _active_stage.set(stage_name)
    try:
        yield
    finally:
        _active_stage.reset(token)


def set_stage(stage_name: str):
    """Set the active stage name directly."""
    return _active_stage.set(stage_name)


def get_current_stage() -> str:
    """Get active stage name or infer from call stack."""
    st = _active_stage.get()
    if st and st != "unknown":
        return st

    # Inspect call stack frames as fallback
    try:
        stack = inspect.stack()
        for frame_info in stack[2:25]:
            fn = frame_info.function.lower()
            mod = frame_info.filename.lower()
            if "voting" in mod or "voting" in fn or "decide" in fn:
                return "voting"
            if "stage0" in mod or "stage0" in fn or "intake" in fn:
                return "lexigraph stage 0"
            if "stage1" in mod or "stage1" in fn:
                return "lexigraph stage 1"
            if "stage2" in mod or "stage2" in fn:
                return "lexigraph stage 2"
            if "stage3" in mod or "stage3" in fn:
                return "lexigraph stage 3"
            if "stage4" in mod or "stage4" in fn:
                return "lexigraph stage 4"
            if "stage5" in mod or "stage5" in fn:
                return "lexigraph stage 5"
            if "stage6" in mod or "stage6" in fn:
                return "lexigraph stage 6"
            if "accused" in mod or "accused" in fn:
                return "judge question"
            if "judge" in mod and ("score" in fn or "evaluate" in fn):
                return "judge evaluation"
            if "prosecutor" in mod or "prosecutor" in fn:
                if "repair" in fn or "correction" in fn:
                    return "retries/repairs"
                return "prosecutor"
            if "defense" in mod or "defense" in fn:
                if "repair" in fn or "correction" in fn:
                    return "retries/repairs"
                return "defense"
            if "evidence" in mod or "evidence" in fn:
                return "evidence analyzer"
    except Exception:
        pass

    return "unknown"


class UsageLogger:
    _instance: Optional[UsageLogger] = None

    def __init__(self, run_label: str = "default_run", logs_dir: Optional[Path] = None):
        self.run_label = run_label
        self.backend_dir = Path(__file__).resolve().parent.parent.parent
        self.logs_dir = logs_dir or (self.backend_dir / "logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.logs_dir / f"usage_{self.run_label}.jsonl"
        self._counter = itertools.count(1)
        self.records: List[Dict[str, Any]] = []
        self.sanitizer_events: List[Dict[str, Any]] = []
        self._installed = False

        # Clear existing log file for this run label if starting fresh
        if _USAGE_LOGGING and self.jsonl_path.exists():
            self.jsonl_path.unlink()

    @classmethod
    def get_instance(cls, run_label: Optional[str] = None) -> UsageLogger:
        if cls._instance is None:
            label = run_label or os.getenv("RUN_LABEL") or "default_run"
            cls._instance = cls(run_label=label)
        elif run_label and cls._instance.run_label != run_label:
            cls._instance = cls(run_label=run_label)
        return cls._instance

    def record_sanitizer_event(self, action: str, agent: str, citation: str, reason: str = ""):
        """Record sanitizer repair or redaction event."""
        evt = {
            "action": action,      # "repair" or "redact"
            "agent": agent,        # "prosecutor" or "defense"
            "citation": citation,
            "reason": reason,
        }
        self.sanitizer_events.append(evt)

    def log_call(
        self,
        stage: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int,
        raw_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        idx = next(self._counter)
        total = input_tokens + output_tokens
        record = {
            "call_index": idx,
            "stage": stage,
            "model": model,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "cached_tokens": int(cached_tokens),
            "total_tokens": int(total),
        }
        self.records.append(record)

        # Write to JSONL only when usage logging is explicitly enabled
        if _USAGE_LOGGING:
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

        return record

    def install(self):
        """Install monkey-patch on LangChain ChatOpenAI._generate and _agenerate."""
        if self._installed:
            return

        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            return

        logger_self = self
        orig_generate = ChatOpenAI._generate
        orig_agenerate = getattr(ChatOpenAI, "_agenerate", None)

        def patched_generate(self_llm, messages, stop=None, run_manager=None, **kwargs):
            stage = get_current_stage()
            try:
                chat_result = orig_generate(self_llm, messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as exc:
                print(f"\n[UsageLogger ERROR] LLM API call failed in stage '{stage}': {exc}", file=sys.stderr)
                traceback.print_exc()
                # Stop immediately and never fall back to simulated numbers
                raise

            # Extract usage from generation
            try:
                gen_msg = chat_result.generations[0].message if chat_result.generations else None
                usage_meta = getattr(gen_msg, "usage_metadata", None) or {}
                resp_meta = getattr(gen_msg, "response_metadata", None) or {}
                llm_out = chat_result.llm_output or {}

                # 1. input_tokens
                inp = usage_meta.get("input_tokens")
                if inp is None:
                    inp = resp_meta.get("token_usage", {}).get("prompt_tokens")
                if inp is None:
                    inp = llm_out.get("token_usage", {}).get("prompt_tokens", 0)

                # 2. output_tokens
                out = usage_meta.get("output_tokens")
                if out is None:
                    out = resp_meta.get("token_usage", {}).get("completion_tokens")
                if out is None:
                    out = llm_out.get("token_usage", {}).get("completion_tokens", 0)

                # 3. cached_tokens (input_token_details.cache_read)
                cached = (
                    usage_meta.get("input_token_details", {}).get("cache_read")
                    or resp_meta.get("token_usage", {}).get("prompt_tokens_details", {}).get("cached_tokens")
                    or llm_out.get("token_usage", {}).get("prompt_tokens_details", {}).get("cached_tokens")
                    or 0
                )

                # 4. model
                model_name = (
                    resp_meta.get("model_name")
                    or llm_out.get("model_name")
                    or getattr(self_llm, "model_name", None)
                    or getattr(self_llm, "model", "unknown")
                )

                logger_self.log_call(
                    stage=stage,
                    model=str(model_name),
                    input_tokens=int(inp or 0),
                    output_tokens=int(out or 0),
                    cached_tokens=int(cached or 0),
                    raw_metadata=resp_meta,
                )
            except Exception:
                pass  # silently ignore metadata parse failures

            return chat_result

        ChatOpenAI._generate = patched_generate

        if orig_agenerate:
            async def patched_agenerate(self_llm, messages, stop=None, run_manager=None, **kwargs):
                stage = get_current_stage()
                try:
                    chat_result = await orig_agenerate(self_llm, messages, stop=stop, run_manager=run_manager, **kwargs)
                except Exception as exc:
                    print(f"\n[UsageLogger ERROR] LLM async API call failed in stage '{stage}': {exc}", file=sys.stderr)
                    traceback.print_exc()
                    raise

                try:
                    gen_msg = chat_result.generations[0].message if chat_result.generations else None
                    usage_meta = getattr(gen_msg, "usage_metadata", None) or {}
                    resp_meta = getattr(gen_msg, "response_metadata", None) or {}
                    llm_out = chat_result.llm_output or {}

                    inp = usage_meta.get("input_tokens") or resp_meta.get("token_usage", {}).get("prompt_tokens") or 0
                    out = usage_meta.get("output_tokens") or resp_meta.get("token_usage", {}).get("completion_tokens") or 0
                    cached = (
                        usage_meta.get("input_token_details", {}).get("cache_read")
                        or resp_meta.get("token_usage", {}).get("prompt_tokens_details", {}).get("cached_tokens")
                        or 0
                    )
                    model_name = resp_meta.get("model_name") or getattr(self_llm, "model_name", "unknown")

                    logger_self.log_call(
                        stage=stage,
                        model=str(model_name),
                        input_tokens=int(inp),
                        output_tokens=int(out),
                        cached_tokens=int(cached),
                    )
                except Exception:
                    pass  # silently ignore metadata parse failures

                return chat_result

            ChatOpenAI._agenerate = patched_agenerate

        self._installed = True

    def print_summary_table(self):
        """Print rich summary table grouped per-stage and per-agent."""
        if not _USAGE_LOGGING:
            return
        table = Table(
            title=f"LLM TOKEN USAGE SUMMARY - Run: {self.run_label}",
            title_style="bold cyan",
            box=box.ROUNDED,
            show_footer=True,
            border_style="bright_blue",
        )
        table.add_column("Stage / Agent", style="bold white", footer="TOTAL")
        table.add_column("Calls", justify="right", style="cyan")
        table.add_column("Input Tokens", justify="right", style="green")
        table.add_column("Output Tokens", justify="right", style="magenta")
        table.add_column("Cached Tokens", justify="right", style="yellow")
        table.add_column("Total Tokens", justify="right", style="bold white")

        # Group records by stage
        by_stage: Dict[str, Dict[str, int]] = {}
        for s in STAGE_ORDER:
            by_stage[s] = {"calls": 0, "input": 0, "output": 0, "cached": 0, "total": 0}

        for r in self.records:
            st = r.get("stage", "unknown")
            if st not in by_stage:
                by_stage[st] = {"calls": 0, "input": 0, "output": 0, "cached": 0, "total": 0}
            by_stage[st]["calls"] += 1
            by_stage[st]["input"] += r.get("input_tokens", 0)
            by_stage[st]["output"] += r.get("output_tokens", 0)
            by_stage[st]["cached"] += r.get("cached_tokens", 0)
            by_stage[st]["total"] += r.get("total_tokens", 0)

        tot_calls = sum(v["calls"] for v in by_stage.values())
        tot_inp = sum(v["input"] for v in by_stage.values())
        tot_out = sum(v["output"] for v in by_stage.values())
        tot_cached = sum(v["cached"] for v in by_stage.values())
        tot_all = sum(v["total"] for v in by_stage.values())

        table.columns[1].footer = str(tot_calls)
        table.columns[2].footer = f"{tot_inp:,}"
        table.columns[3].footer = f"{tot_out:,}"
        table.columns[4].footer = f"{tot_cached:,}"
        table.columns[5].footer = f"{tot_all:,}"

        # Display rows in canonical order first, then any extra
        displayed_stages = list(STAGE_ORDER)
        for k in by_stage:
            if k not in displayed_stages:
                displayed_stages.append(k)

        for s in displayed_stages:
            stats = by_stage.get(s, {"calls": 0, "input": 0, "output": 0, "cached": 0, "total": 0})
            table.add_row(
                s,
                str(stats["calls"]),
                f"{stats['input']:,}",
                f"{stats['output']:,}",
                f"{stats['cached']:,}",
                f"{stats['total']:,}",
            )

        console.print("\n")
        console.print(table)
        console.print(f"Log written to: [underline]{self.jsonl_path}[/underline]\n")

    def save_orchestrator_output(self, state: Dict[str, Any]):
        """Save structured orchestrator run output to logs/output_<run_label>.json."""
        if not _USAGE_LOGGING:
            return
        out_file = self.logs_dir / f"output_{self.run_label}.json"

        # Verified sections
        lexi = state.get("lexigraph_output") or {}
        raw_sections = lexi.get("ipc_sections") or []
        verified_sections = []
        for s in raw_sections:
            if isinstance(s, dict):
                verified_sections.append(s.get("section") or s.get("offense") or "")
            elif isinstance(s, str):
                verified_sections.append(s)

        # Precedents / Holdings
        raw_holdings = state.get("holdings") or lexi.get("holdings") or []
        holdings = []
        for h in raw_holdings:
            if hasattr(h, "to_dict"):
                holdings.append(h.to_dict())
            elif isinstance(h, dict):
                holdings.append(h)
            else:
                holdings.append(str(h))

        # Verdict & Bail factors
        verdict = state.get("verdict") or {}
        bail_factors = verdict.get("factors") or []
        reasoning = verdict.get("reasoning") or verdict.get("raw_explanation") or ""

        # Arguments per round
        arguments = []
        for t in state.get("transcript") or []:
            if isinstance(t, dict):
                arguments.append({
                    "speaker": t.get("speaker"),
                    "round_no": t.get("round_no"),
                    "citations": t.get("citations", []),
                    "evidence_refs": t.get("evidence_refs", []),
                    "content": t.get("content", ""),
                })

        output_payload = {
            "run_label": self.run_label,
            "verified_sections": verified_sections,
            "holdings": holdings,
            "bail_factors": bail_factors,
            "arguments": arguments,
            "verdict": verdict,
            "reasoning": reasoning,
            "sanitizer_events": self.sanitizer_events,
            "citation_repair_metrics": state.get("_citation_repair_metrics", {}),
            "total_calls": len(self.records),
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, indent=2, default=str)

        print(f"[UsageLogger] Saved orchestrator output to: {out_file}")
