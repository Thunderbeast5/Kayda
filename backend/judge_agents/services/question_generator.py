"""
QuestionGenerator service — Phase 2

Responsible for:
  1. Gap detection — identifies what is missing or contradictory
     in the current hearing state without calling the LLM.
  2. Question generation — uses the LLM to produce targeted,
     case-specific clarification questions from the detected gaps.
  3. Max-questions guard — never exceeds MAX_QUESTIONS_PER_HEARING.
  4. Question routing — assigns each question to the correct target
     (Defence / Prosecution / IO Agent).

Design principle: gap detection is deterministic (no LLM);
question wording is LLM-generated (precise, formal, one-sentence).
"""

import re
from typing import Optional

from ..llm_config import get_llm
from ..models.question_model import JudgeQuestion, QuestionTarget
from ..models.hearing_state import HearingContext
from ..prompts.question_generation import QUESTION_GENERATION_PROMPT
from ..prompts.system_prompt import JUDGE_SYSTEM_PROMPT

MAX_QUESTIONS_PER_HEARING = 5


# ── Gap detection (deterministic) ─────────────────────────────────────────────

class GapDetector:
    """
    Identifies specific gaps in the current hearing state.
    Runs without any LLM calls — pure logic on structured inputs.

    Gap categories
    --------------
    EVIDENCE_MISSING     : key evidence referenced but not present
    INGREDIENT_UNPROVEN  : legal ingredient for a section not addressed
    CONTRADICTION        : two pieces of information directly contradict
    IO_STATUS_UNCLEAR    : investigation status, recovery, weapon unclear
    CUSTODIAL_NEED_UNARGUED : neither side addressed custodial interrogation need
    FLIGHT_RISK_UNARGUED : flight risk not addressed by defence
    ANTECEDENTS_UNCLEAR  : prior criminal record not confirmed
    """

    def detect(
        self,
        evidence_context: dict,
        legal_context_package: dict,
        defence_arguments: str,
        prosecution_arguments: str,
        investigation_report: str,
        bail_assessment_report: dict,
    ) -> list[dict]:
        """
        Returns a list of gap dicts:
          {
            "category": str,
            "description": str,   — human-readable description
            "target": str,        — "Defence" / "Prosecution" / "IO Agent"
            "priority": int,      — 1 (critical) to 3 (minor)
          }
        """
        gaps: list[dict] = []
        combined_args = (defence_arguments + " " + prosecution_arguments).lower()
        io_lower = investigation_report.lower()

        # ── 1. Missing weapon / physical evidence ───────────────────────────
        weapon = (evidence_context.get("weapon") or "").strip()
        if weapon and "not seized" in io_lower and "weapon" not in combined_args:
            gaps.append({
                "category": "IO_STATUS_UNCLEAR",
                "description": f"Weapon ({weapon}) mentioned in evidence but seizure status unclear.",
                "target": "IO Agent",
                "priority": 1,
            })

        # ── 2. Missing forensic / medical evidence ───────────────────────────
        missing_evid = evidence_context.get("missing_evidence") or []
        for item in missing_evid:
            item_l = item.lower()
            if "forensic" in item_l or "report" in item_l:
                gaps.append({
                    "category": "EVIDENCE_MISSING",
                    "description": f"Missing evidence not addressed: {item}",
                    "target": "IO Agent",
                    "priority": 2,
                })

        # ── 3. Contradictions in evidence ────────────────────────────────────
        contradictions = evidence_context.get("contradictions") or []
        for c in contradictions:
            if c.strip():
                gaps.append({
                    "category": "CONTRADICTION",
                    "description": f"Contradiction detected: {c}",
                    "target": "Defence" if "witness" in c.lower() else "Prosecution",
                    "priority": 1,
                })

        # ── 4. Custodial interrogation need not argued ───────────────────────
        custodial_keywords = ["custodial", "custody", "interrogation", "remand"]
        custodial_addressed = any(kw in combined_args for kw in custodial_keywords)
        if not custodial_addressed:
            gaps.append({
                "category": "CUSTODIAL_NEED_UNARGUED",
                "description": "Neither side addressed whether custodial interrogation is necessary.",
                "target": "IO Agent",
                "priority": 1,
            })

        # ── 5. Flight risk not addressed by defence ──────────────────────────
        flight_keywords = ["flight risk", "passport", "absconding", "leave country",
                           "resident", "ties", "domicile"]
        flight_addressed = any(kw in (defence_arguments or "").lower()
                               for kw in flight_keywords)
        if not flight_addressed:
            gaps.append({
                "category": "FLIGHT_RISK_UNARGUED",
                "description": "Defence has not addressed flight risk.",
                "target": "Defence",
                "priority": 2,
            })

        # ── 6. Antecedents not confirmed ─────────────────────────────────────
        antecedent_keywords = ["antecedent", "prior", "previous", "conviction",
                               "criminal record", "FIR"]
        antecedents_addressed = any(kw in combined_args for kw in antecedent_keywords)
        bail_antecedents = str(
            bail_assessment_report.get("antecedents") or ""
        ).strip().lower()
        if not antecedents_addressed and bail_antecedents in ("", "unknown"):
            gaps.append({
                "category": "ANTECEDENTS_UNCLEAR",
                "description": "Prior criminal antecedents of accused not confirmed.",
                "target": "IO Agent",
                "priority": 2,
            })

        # ── 7. Ingredient not addressed ──────────────────────────────────────
        sections = legal_context_package.get("recommended_sections") or []
        for sec in sections[:3]:  # check top 3 sections only
            title = (sec.get("title") or "").lower()
            applicability = (sec.get("applicability") or "").lower()
            # Mens rea check for offences that require it
            if ("intention" in applicability or "intent" in title) and \
               "intent" not in combined_args and "mens rea" not in combined_args:
                gaps.append({
                    "category": "INGREDIENT_UNPROVEN",
                    "description": (
                        f"Ingredient 'intention/mens rea' for {sec.get('section')} "
                        f"not addressed by either party."
                    ),
                    "target": "Prosecution",
                    "priority": 1,
                })
                break  # one mens rea question is enough

        # Deduplicate by category (keep highest priority per category)
        seen_categories: dict[str, dict] = {}
        for g in gaps:
            cat = g["category"]
            if cat not in seen_categories or g["priority"] < seen_categories[cat]["priority"]:
                seen_categories[cat] = g
        return sorted(seen_categories.values(), key=lambda x: x["priority"])


# ── LLM question wording ───────────────────────────────────────────────────────

def _parse_generated_questions(raw: str) -> list[dict]:
    """
    Parse the pipe-separated question lines from the LLM.
    Expected format per line:
        TARGET: <target> | ISSUE: <issue> | QUESTION: <question>
    """
    questions = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or "NO QUESTIONS NEEDED" in line.upper():
            continue
        target_m = re.search(r"TARGET\s*:\s*([^|]+)", line, re.IGNORECASE)
        issue_m  = re.search(r"ISSUE\s*:\s*([^|]+)", line, re.IGNORECASE)
        q_m      = re.search(r"QUESTION\s*:\s*(.+)", line, re.IGNORECASE)
        if target_m and q_m:
            questions.append({
                "target":   target_m.group(1).strip(),
                "issue":    issue_m.group(1).strip() if issue_m else "Unspecified",
                "question": q_m.group(1).strip(),
            })
    return questions


def _map_target(raw_target: str) -> QuestionTarget:
    t = raw_target.lower()
    if "defence" in t or "defense" in t:
        return QuestionTarget.DEFENCE
    if "prosecution" in t or "prosecutor" in t:
        return QuestionTarget.PROSECUTION
    return QuestionTarget.IO_AGENT


# ── QuestionGenerator ─────────────────────────────────────────────────────────

class QuestionGenerator:
    """
    Full Phase 2 question generation pipeline.

    Usage
    -----
    gen = QuestionGenerator()
    questions = gen.generate(
        context,               # HearingContext (tracks question budget)
        evidence_context,
        legal_context_package,
        defence_arguments,
        prosecution_arguments,
        investigation_report,
        bail_assessment_report,
    )

    Returns a list of JudgeQuestion objects (may be empty if no gaps found
    or question budget is exhausted).
    """

    def __init__(self):
        self.llm          = get_llm(temperature=0.1)
        self.gap_detector = GapDetector()

    def generate(
        self,
        context: HearingContext,
        evidence_context: dict,
        legal_context_package: dict,
        defence_arguments: str,
        prosecution_arguments: str,
        investigation_report: str,
        bail_assessment_report: dict,
        debate_round: int = 1,
    ) -> list[JudgeQuestion]:
        """
        Detect gaps → generate questions → apply budget guard.

        Parameters
        ----------
        context              : HearingContext — tracks budget
        debate_round         : current round number (for JudgeQuestion.round)

        Returns
        -------
        list[JudgeQuestion] — empty if no gaps or budget exhausted
        """
        # ── Budget check ──
        remaining = MAX_QUESTIONS_PER_HEARING - context.questions_asked_count
        if remaining <= 0:
            print(f"[QuestionGenerator] Budget exhausted ({MAX_QUESTIONS_PER_HEARING} max).")
            return []

        # ── Gap detection ──
        gaps = self.gap_detector.detect(
            evidence_context      = evidence_context,
            legal_context_package = legal_context_package,
            defence_arguments     = defence_arguments,
            prosecution_arguments = prosecution_arguments,
            investigation_report  = investigation_report,
            bail_assessment_report = bail_assessment_report,
        )

        # Take only top-priority gaps up to the remaining budget
        top_gaps = gaps[:remaining]

        if not top_gaps:
            print("[QuestionGenerator] No gaps detected — no questions needed.")
            return []

        gap_descriptions = "\n".join(
            f"  [{g['category']}] {g['description']} → Ask: {g['target']}"
            for g in top_gaps
        )

        # ── LLM question wording ──
        prompt = QUESTION_GENERATION_PROMPT.format(
            system_prompt         = JUDGE_SYSTEM_PROMPT,
            gaps                  = gap_descriptions,
            defence_arguments     = defence_arguments,
            prosecution_arguments = prosecution_arguments,
            investigation_report  = investigation_report,
            max_questions         = min(remaining, len(top_gaps)),
        )

        raw = self.llm.invoke(prompt).content
        raw_questions = _parse_generated_questions(raw)

        # ── Build JudgeQuestion objects ──
        questions: list[JudgeQuestion] = []
        for rq in raw_questions[:remaining]:
            questions.append(JudgeQuestion(
                target=_map_target(rq["target"]),
                issue=rq["issue"],
                question=rq["question"],
                round=debate_round,
            ))

        # ── Update budget ──
        context.questions_asked_count += len(questions)

        print(
            f"[QuestionGenerator] Generated {len(questions)} question(s) "
            f"| Gaps found: {len(gaps)} | Budget remaining: "
            f"{MAX_QUESTIONS_PER_HEARING - context.questions_asked_count}"
        )

        return questions
