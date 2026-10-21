"""
Session Input Manager
=====================
Thread-safe registry for handling turn-based human inputs in AI vs Human moot court simulations.
Enables frontend (WebSocket, SSE, REST API) or CLI to supply user arguments asynchronously
during the courtroom debate loop.
"""

from __future__ import annotations
import threading
import time
from typing import Dict, Optional, Tuple, Any


def normalize_role(role: Optional[str]) -> Optional[str]:
    """
    Normalize role string into canonical 'prosecutor' or 'defense'.
    Returns None if role cannot be determined.
    """
    if not role:
        return None
    r = str(role).strip().lower()
    if r in ("defense", "defence", "def", "d", "accused_counsel", "respondent"):
        return "defense"
    if r in ("prosecutor", "prosecution", "pros", "p", "state", "public_prosecutor", "applicant"):
        return "prosecutor"
    return None


def normalize_mode(mode: Optional[str], user_role: Optional[str]) -> str:
    """
    Normalize simulation mode into 'ai_vs_human' or 'ai_vs_ai'.
    """
    if mode:
        m = str(mode).strip().lower()
        if m in ("ai_vs_ai", "ai", "auto", "simulation"):
            return "ai_vs_ai"
        if m in ("ai_vs_human", "human_vs_ai", "human", "interactive"):
            return "ai_vs_human"
    return "ai_vs_human" if user_role else "ai_vs_ai"


def get_ai_role(user_role: Optional[str], mode: str) -> Optional[str]:
    """
    Determine the AI opponent's role based on user_role and mode.
    """
    if mode == "ai_vs_ai":
        return "both"
    if user_role == "prosecutor":
        return "defense"
    if user_role == "defense":
        return "prosecutor"
    return "both"


import sys

# Process-wide shared storage to guarantee single-instance semantics across any import path
if not hasattr(sys, "_mootcourt_session_input_store"):
    sys._mootcourt_session_input_store = {
        "pending_events": {},
        "arguments": {},
        "lock": threading.Lock(),
    }


class SessionInputManager:
    """
    Thread-safe registry for pending human input requests and incoming submissions.
    Guaranteed singleton process-wide across all module import paths.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    @property
    def _pending_events(self) -> Dict[str, threading.Event]:
        return sys._mootcourt_session_input_store["pending_events"]

    @property
    def _arguments(self) -> Dict[str, Tuple[str, str, int]]:
        return sys._mootcourt_session_input_store["arguments"]

    @property
    def _registry_lock(self) -> threading.Lock:
        return sys._mootcourt_session_input_store["lock"]

    def submit_argument(
        self,
        session_id: str,
        argument: str,
        role: Optional[str] = None,
        round_no: Optional[int] = None,
    ) -> bool:
        """
        Submit a human argument from REST/WebSocket for a specific session.
        Wakes up any waiting thread.
        """
        norm_r = normalize_role(role) or (role or "")
        clean_text = (argument or "").strip()
        with self._registry_lock:
            self._arguments[session_id] = (norm_r, clean_text, round_no or 0)
            evt = self._pending_events.get(session_id)
            if evt:
                evt.set()
                return True
            return False

    def wait_for_argument(
        self,
        session_id: str,
        role: str,
        round_no: int,
        timeout: float = 60.0,
    ) -> Optional[str]:
        """
        Wait for a human argument to arrive for session_id.
        Returns the argument text, or None on timeout.
        """
        norm_r = normalize_role(role) or role
        with self._registry_lock:
            # Check if an argument was already submitted for this session
            if session_id in self._arguments:
                arg_role, arg_text, arg_round = self._arguments[session_id]
                if (not arg_round or arg_round == round_no) and (not arg_role or arg_role == norm_r):
                    del self._arguments[session_id]
                    return arg_text

            evt = threading.Event()
            self._pending_events[session_id] = evt

        signaled = evt.wait(timeout=timeout)

        with self._registry_lock:
            self._pending_events.pop(session_id, None)
            if signaled and session_id in self._arguments:
                arg_role, arg_text, arg_round = self._arguments.pop(session_id)
                return arg_text
        return None

    def clear(self, session_id: str) -> None:
        """Clear state for a concluded session."""
        with self._registry_lock:
            self._pending_events.pop(session_id, None)
            self._arguments.pop(session_id, None)


session_input_manager = SessionInputManager()
