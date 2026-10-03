"""
session_store.py  —  Virtual Moot Court

Session JSON lives at: sessions/session_<uuid>.json

What is stored (full, for history / frontend):
  - case_text, case_summary, accused, victim
  - bail_relevant_facts (with citations)
  - retrieved_concepts, retrieval_cache
  - full pipeline output (stage0–6)
  - full argument texts (for display)

What the LLM receives per turn (compact):
  - argument_summaries: 3-5 bullet summaries, NOT full texts
  - positions_taken: bail factors the prosecution already argued
  - retrieved_concepts: so prosecutor knows what law is already in hand

This distinction keeps LLM context lean and prevents repetition.

To migrate to MongoDB/PostgreSQL: replace _load_raw() and _save_raw().
The rest of the code is backend-agnostic.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SESSIONS_DIR = Path("sessions")
SCHEMA_VERSION = "1.0"


@dataclass
class MootCourtSession:
    session_id: str
    schema_version: str
    created_at: str

    # ── Case-level (set once) ──────────────────────────────────
    case_text: str = ""
    case_summary: str = ""
    accused: str = ""
    victim: str = ""
    nature_of_offence: str = ""

    # ── Extracted facts (with citations) ──────────────────────
    bail_relevant_facts: List[Dict] = field(default_factory=list)
    smart_subqueries: List[Dict] = field(default_factory=list)
    bail_factors_present: List[str] = field(default_factory=list)

    # ── Pipeline outputs ───────────────────────────────────────
    full_pipeline_output: Optional[Dict] = None   # stage0–6 from initial run

    # ── Retrieval cache ────────────────────────────────────────
    # { "normalised_concept": { ...full pipeline output... } }
    retrieval_cache: Dict[str, Any] = field(default_factory=dict)
    retrieved_concepts: List[str] = field(default_factory=list)

    # ── Argument history (full — for display / frontend) ───────
    turns: List[Dict] = field(default_factory=list)

    # ── Compact reasoning state (sent to LLM) ─────────────────
    argument_summaries: List[str] = field(default_factory=list)  # "Round N [role]: bullet | bullet"
    positions_taken: List[str] = field(default_factory=list)     # bail factors argued by prosecution
    defense_positions: List[str] = field(default_factory=list)   # positions defense has taken

    round_number: int = 0

    # ──────────────────────────────────────────────────────────
    # Mutation helpers
    # ──────────────────────────────────────────────────────────

    def add_turn(
        self,
        role: str,                   # "prosecutor" | "defense"
        full_text: str,
        summary_bullets: List[str],
        positions: Optional[List[str]] = None,
        concepts_used: Optional[List[str]] = None,
    ) -> None:
        self.round_number += 1
        turn = {
            "round": self.round_number,
            "role": role,
            "full_argument": full_text,
            "summary_bullets": summary_bullets,
            "positions": positions or [],
            "concepts_used": concepts_used or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.turns.append(turn)

        # Update compact state
        label = f"[Round {self.round_number} — {role.capitalize()}]"
        self.argument_summaries.append(label + " " + " | ".join(summary_bullets))

        if role == "prosecutor" and positions:
            for p in positions:
                if p not in self.positions_taken:
                    self.positions_taken.append(p)

        if role == "defense" and positions:
            for p in positions:
                if p not in self.defense_positions:
                    self.defense_positions.append(p)

    def mark_concept_retrieved(self, concept: str) -> None:
        if concept not in self.retrieved_concepts:
            self.retrieved_concepts.append(concept)

    def update_cache(self, cache: Dict[str, Any]) -> None:
        self.retrieval_cache.update(cache)

    def get_llm_summary(self) -> Dict[str, Any]:
        """
        Compact dict sent to LLM for reasoning. NOT full argument texts.
        Keeps context window lean regardless of how many turns have passed.
        """
        return {
            "case_summary": self.case_summary,
            "accused": self.accused,
            "victim": self.victim,
            "argument_summaries": self.argument_summaries,   # compact bullets only
            "positions_taken": self.positions_taken,
            "defense_positions": self.defense_positions,
            "retrieved_concepts": self.retrieved_concepts,
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SessionStore:
    """
    File-backed session store.
    Swap _load_raw() / _save_raw() to move to MongoDB/PostgreSQL.
    """

    def __init__(self, sessions_dir: str = "sessions"):
        self._dir = Path(sessions_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._session: Optional[MootCourtSession] = None

    # ── Backend abstraction ────────────────────────────────────

    def _path(self, session_id: str) -> Path:
        return self._dir / f"session_{session_id}.json"

    def _load_raw(self, session_id: str) -> Optional[Dict]:
        p = self._path(session_id)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def _save_raw(self, data: Dict, session_id: str) -> None:
        self._path(session_id).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── Public API ─────────────────────────────────────────────

    def new_session(self) -> MootCourtSession:
        s = MootCourtSession(
            session_id=str(uuid.uuid4()),
            schema_version=SCHEMA_VERSION,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._session = s
        return s

    def load(self, session_id: str) -> MootCourtSession:
        raw = self._load_raw(session_id)
        if raw is None:
            raise FileNotFoundError(f"Session {session_id} not found.")
        s = MootCourtSession(
            session_id=raw["session_id"],
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
            created_at=raw["created_at"],
            case_text=raw.get("case_text", ""),
            case_summary=raw.get("case_summary", ""),
            accused=raw.get("accused", ""),
            victim=raw.get("victim", ""),
            nature_of_offence=raw.get("nature_of_offence", ""),
            bail_relevant_facts=raw.get("bail_relevant_facts", []),
            smart_subqueries=raw.get("smart_subqueries", []),
            bail_factors_present=raw.get("bail_factors_present", []),
            full_pipeline_output=raw.get("full_pipeline_output"),
            retrieval_cache=raw.get("retrieval_cache", {}),
            retrieved_concepts=raw.get("retrieved_concepts", []),
            turns=raw.get("turns", []),
            argument_summaries=raw.get("argument_summaries", []),
            positions_taken=raw.get("positions_taken", []),
            defense_positions=raw.get("defense_positions", []),
            round_number=raw.get("round_number", 0),
        )
        self._session = s
        return s

    def save(self, session: Optional[MootCourtSession] = None) -> None:
        s = session or self._session
        if s is None:
            raise ValueError("No session to save.")
        self._save_raw(s.to_dict(), s.session_id)

    @property
    def session(self) -> MootCourtSession:
        if self._session is None:
            raise ValueError("No session loaded.")
        return self._session