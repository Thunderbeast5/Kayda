"""
BSA Verifier Agent (Stage 3b).

Audits candidate BSA sections proposed by BSARetrievalAgent.
Performs both programmatic grounding checks (ensuring live factual hooks)
and LLM-based verification to accept or reject candidates.
Suppresses noise (such as generic witness examination or judicial notice provisions)
so only live evidentiary provisions reach the final output.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE2
from .prompts import STAGE3B_VERIFIER_SYSTEM_PROMPT, STAGE3B_VERIFIER_USER_PROMPT_TEMPLATE
from .schemas.stage_bsa import BSASectionItem, BSAVerificationIssue


# Categorical disqualification / grounding checks:
# (disqualifying_categories, required_factual_keywords, rejection_reason)
_GROUNDING_RULES: List[Tuple[List[str], List[str], str]] = [
    (
        ["ELECTRONIC_RECORDS"],
        ["electronic", "digital", "email", "whatsapp", "scan", "computer", "server", "phone", "cctv", "sms", "hash"],
        "Rejected by verifier: No electronic/digital records, emails, scans, or computer outputs mentioned in case facts.",
    ),
    (
        ["HANDWRITING_SIGNATURE"],
        ["signature", "sign", "handwriting", "forg", "deed", "document", "fabricated", "examiner", "execute"],
        "Rejected by verifier: No signature verification, handwriting, or forged document execution at issue in facts.",
    ),
    (
        ["EXPERT_OPINION"],
        ["expert", "forensic", "handwriting", "examiner", "fsl", "fingerprint", "ballistic", "dna", "medical", "doctor", "signature", "forg", "opinion", "comparison", "authentic"],
        "Rejected by verifier: No expert opinion, forensic analysis, handwriting examination, or signature comparison required on facts.",
    ),

    (
        ["ADMISSIONS_CONFESSIONS"],
        ["confession", "confess", "police", "custody", "statement", "admit", "admission", "recovery"],
        "Rejected by verifier: No confession to police officer or custodial admission alleged in the facts.",
    ),
]

# Sections that are generic/tangential procedural noise unless explicitly contested
_DEFAULT_NOISE_SECTIONS = {
    "52",   # Facts of which Court must take judicial notice
    "137",  # Witness not excused from answering on ground that answer will criminate
    "145",  # Witnesses to character
    "146",  # Leading questions
    "147",  # Evidence as to matters in writing
    "150",  # Questions lawful in cross-examination
    "168",  # Judge's power to put questions or order production
}


class BSAVerifierAgent:
    """
    Stage 3b Auditor for BSA Evidence Law Section Retrieval.
    Ensures that only sections with a genuine factual hook in the live
    evidentiary controversy are verified and accepted.
    """

    def __init__(self, llm: Optional[Any] = None):
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE2)
        return self._llm

    def verify(
        self,
        facts_summary: str,
        candidates: List[BSASectionItem],
    ) -> Tuple[List[BSASectionItem], List[BSASectionItem], List[str]]:
        """
        Audits proposed BSA candidates against case facts.

        Returns:
            Tuple of:
            - accepted_sections: List[BSASectionItem] with verification_status='VERIFIED'
            - rejected_sections: List[BSASectionItem] with verification_status='REJECTED'
            - audit_notes: List[str] summarizing audit adjustments
        """
        if not candidates:
            return [], [], ["No candidate BSA sections to verify."]

        facts_lower = facts_summary.lower()
        accepted: List[BSASectionItem] = []
        rejected: List[BSASectionItem] = []
        audit_notes: List[str] = []

        pending_for_llm: List[BSASectionItem] = []

        # ── 1. Programmatic Rule-Based Auditing ────────────────────────
        for sec in candidates:
            sec_num = str(sec.section_number).strip()
            cat = (sec.relevance_category or "").upper()

            # Check noise list
            if sec_num in _DEFAULT_NOISE_SECTIONS:
                # Unless facts specifically demand this exact procedural issue
                if not any(k in facts_lower for k in ["leading question", "judicial notice", "self-incrimination"]):
                    sec.verification_status = "REJECTED"
                    sec.verification_reason = f"Rejected: BSA {sec_num} is a generic procedural provision not actively contested in case facts."
                    rejected.append(sec)
                    audit_notes.append(f"Rejected noise section BSA {sec_num} ({sec.heading})")
                    continue

            # Check categorical grounding
            failed_rule = False
            for categories, req_words, reason in _GROUNDING_RULES:
                if any(c in cat for c in categories):
                    if not any(w in facts_lower for w in req_words):
                        sec.verification_status = "REJECTED"
                        sec.verification_reason = reason
                        rejected.append(sec)
                        audit_notes.append(f"Rejected BSA {sec_num} ({sec.heading}): lacks factual grounding for {cat}")
                        failed_rule = True
                        break

            if not failed_rule:
                pending_for_llm.append(sec)

        if not pending_for_llm:
            return accepted, rejected, audit_notes

        # ── 2. LLM Verification Audit ──────────────────────────────────
        try:
            accepted_sections_json = json.dumps(
                [
                    {
                        "section_number": s.section_number,
                        "heading": s.heading,
                        "category": s.relevance_category,
                        "reasoning": s.relevance_reason,
                    }
                    for s in pending_for_llm
                ],
                indent=2,
            )

            prompt = STAGE3B_VERIFIER_USER_PROMPT_TEMPLATE.format(
                facts_summary=facts_summary[:3000],
                accepted_sections_json=accepted_sections_json,
            )

            response = self.llm.invoke([
                SystemMessage(content=STAGE3B_VERIFIER_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])

            raw_text = response.content if hasattr(response, "content") else str(response)
            parsed = extract_json_from_text(raw_text)

            audit_map: Dict[str, Dict[str, Any]] = {}
            if isinstance(parsed, dict) and "section_audits" in parsed:
                for item in parsed["section_audits"]:
                    snum = str(item.get("section_number", "")).strip()
                    audit_map[snum] = item

            for sec in pending_for_llm:
                sec_num = str(sec.section_number).strip()
                audit_info = audit_map.get(sec_num)

                if audit_info:
                    verdict = str(audit_info.get("verdict", "ACCEPT")).upper()
                    reason = audit_info.get("reason", "Audited by BSA Verifier")

                    if verdict == "REJECT":
                        sec.verification_status = "REJECTED"
                        sec.verification_reason = reason
                        rejected.append(sec)
                        audit_notes.append(f"LLM Verifier rejected BSA {sec_num}: {reason}")
                    else:
                        sec.verification_status = "VERIFIED"
                        sec.verification_reason = reason
                        sec.confidence_score = 0.95
                        accepted.append(sec)
                else:
                    # Default: accept if passed programmatic checks
                    sec.verification_status = "VERIFIED"
                    sec.verification_reason = "Passed evidentiary grounding check."
                    sec.confidence_score = 0.90
                    accepted.append(sec)

        except Exception as e:
            audit_notes.append(f"LLM verification fallback triggered ({e}); accepted {len(pending_for_llm)} programmatically verified sections.")
            for sec in pending_for_llm:
                sec.verification_status = "VERIFIED"
                sec.verification_reason = "Verified via programmatic grounding check."
                accepted.append(sec)

        return accepted, rejected, audit_notes
