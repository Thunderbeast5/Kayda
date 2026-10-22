"""
BSA Retrieval & Reasoning Agent (Stage 3b).

Identifies and reasons over Bharatiya Sakshya Adhiniyam, 2023 (BSA) evidence-law
sections relevant to the current case facts using definition-grounded LLM reasoning,
followed by verification and acceptance/rejection auditing by BSAVerifierAgent.

Key features:
  - Definition-grounded LLM reasoning over live evidentiary issues (forged signatures,
    primary vs. secondary evidence, electronic records, expert opinion, burden of proof).
  - Suppression of generic/broad noise (BSA 137 witness privilege, BSA 52 judicial notice).
  - Independent BSAVerifierAgent audit ensuring every accepted section has a live factual hook.
  - Sourced directly from bsa.json with Neo4j REPLACES mapping to IEA.
  - Resolves Stage 3 verified offences from IPC to BNS via Neo4j REPLACED_BY mappings.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE2
from .statute_repository import StatuteRepository
from .schemas.stage_bsa import BSARetrievalObject, BSASectionItem
from .prompts import STAGE3B_BSA_SYSTEM_PROMPT, STAGE3B_BSA_USER_PROMPT_TEMPLATE
from .bsa_verifier_agent import BSAVerifierAgent


# ──────────────────────────────────────────────────────────────
# Evidentiary Clusters & Target BSA Section Candidates
# ──────────────────────────────────────────────────────────────

import re

def _matches_keyword(kw: str, text: str) -> bool:
    """Token-aware word-boundary matching so words like 'sign' do not match 'assigned'."""
    pattern = r"\b" + re.escape(kw) + r"(?:s|es)?\b"  # tolerate plurals ("reports", "witnesses")
    return bool(re.search(pattern, text, re.IGNORECASE))


_EVIDENCE_CLUSTERS: Dict[str, Dict[str, Any]] = {
    "HANDWRITING_SIGNATURE": {
        "keywords": ["signature", "handwriting", "forged", "forgery", "signed", "false signature", "thumb impression", "examiner", "specimen writing"],
        "target_sections": ["41", "65", "72", "39"],
        "description": "Proof of handwriting and signatures, comparison with admitted writing, and expert opinion on forged documents.",
    },
    "PRIMARY_SECONDARY_EVIDENCE": {
        "keywords": ["original", "photocopy", "xerox", "copy", "secondary evidence", "fabricated", "record", "deed", "missing original", "loss of document", "photograph", "register", "report"],
        "target_sections": ["56", "57", "58", "59", "60"],
        "description": "Proof of document contents by primary evidence (original document) vs. secondary evidence (photocopies/copies).",
    },
    "ELECTRONIC_RECORDS": {
        "keywords": ["electronic", "digital", "scan", "scanned", "email", "whatsapp", "phone", "computer", "server", "cctv", "sms", "hash", "electronic record", "digital evidence", "footage", "video", "audio", "recording", "call record", "cdr"],
        "target_sections": ["61", "62", "63", "66", "73", "90"],
        "description": "Admissibility and special provisions relating to electronic/digital records, electronic scans, and messages.",
    },
    "EXPERT_OPINION": {
        "keywords": ["expert", "forensic", "fsl", "handwriting expert", "fingerprint", "ballistic", "dna", "medical expert", "doctor opinion",
                     "engineer", "inspection report", "technical report", "analysis report", "examination report", "structural",
                     "post-mortem", "autopsy", "medical report", "valuation report", "surveyor"],
        "target_sections": ["39", "40", "45"],
        "description": "Admissibility of expert opinion (science, art, engineering, medicine), facts bearing on it, and the grounds of opinion.",
    },
    "ORAL_EVIDENCE": {
        "keywords": ["witness", "eyewitness", "eye-witness", "testimony", "deposition", "witness statement", "statements from"],
        "target_sections": ["54", "55"],
        "description": "Proof of facts by oral evidence and the rule that oral evidence must be direct.",
    },
    "CONTRACTS_DISPOSITIONS": {
        "keywords": ["sale deed", "deed", "contract", "agreement", "disposition", "registered document", "title deed"],
        "target_sections": ["94", "95", "96", "102"],
        "description": "Evidence of terms of contracts, grants, and dispositions of property reduced to documentary form.",
    },
    "ADMISSIONS_CONFESSIONS": {
        "keywords": ["confession", "confess", "confessed", "police officer", "police custody", "custodial", "recovery", "disclosure"],
        "target_sections": ["22", "23", "24"],
        "description": "Admissibility of statements, confessions made to police, and recovery under police custody.",
    },
    "BURDEN_OF_PROOF": {
        "keywords": ["burden of proof", "burden", "presume", "presumption", "onus", "special knowledge", "innocent", "fraud"],
        "target_sections": ["104", "105", "106", "113", "114", "119"],
        "description": "Allocation of burden of proof, special knowledge, and judicial presumptions.",
    },
}

# Always consider core evidentiary baseline sections for any criminal dispute involving documents
_BASELINE_CANDIDATE_SECTIONS: List[str] = ["56", "57", "58", "60", "94", "104", "105"]


class BSARetrievalAgent:
    """
    Stage 3b BSA Evidence Law Section Retrieval & Reasoning Agent.

    Uses LLM reasoning against statutory definitions from bsa.json, followed by
    verification by BSAVerifierAgent to produce highly accurate, grounded BSA sections.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        verifier: Optional[BSAVerifierAgent] = None,
        top_k: int = 10,
    ):
        self._llm = llm
        self.verifier = verifier or BSAVerifierAgent(llm=self._llm)
        self.top_k = top_k

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE2)
        return self._llm

    def run(
        self,
        legal_query: Union[Dict[str, Any], Any],
        verified_offences: Optional[List[Dict[str, Any]]] = None,
    ) -> BSARetrievalObject:
        """
        Executes definition-grounded BSA retrieval and verification.

        Args:
            legal_query: LegalQueryObject (or dict) from Stage 1.
            verified_offences: Verified offences from Stage 3 ChapterIdentificationObject.

        Returns:
            BSARetrievalObject containing verified relevant sections, rejected sections,
            and IPC → BNS mapping.
        """
        repo = StatuteRepository.get_instance()
        notes: List[str] = []

        # ── 1. Extract case narrative and evidence cues ────────────────
        query_obj = legal_query if isinstance(legal_query, dict) else (
            legal_query.model_dump() if hasattr(legal_query, "model_dump") else {}
        )

        facts_parts: List[str] = []
        imp = query_obj.get("important_facts") or {}
        if isinstance(imp, dict):
            for v in imp.values():
                if isinstance(v, str) and v:
                    facts_parts.append(v)
                elif isinstance(v, list):
                    facts_parts.extend(str(x) for x in v if x)

        for concept in query_obj.get("legal_concepts", []):
            c = concept.get("concept", "") if isinstance(concept, dict) else getattr(concept, "concept", "")
            if c:
                facts_parts.append(c)

        for sq in query_obj.get("sub_queries", []):
            q = sq.get("query", "") if isinstance(sq, dict) else getattr(sq, "query", "")
            if q:
                facts_parts.append(q)

        for raw_key in ["case_facts", "raw_text", "text", "user_query", "raw_case_text"]:
            val = query_obj.get(raw_key)
            if isinstance(val, str) and val:
                facts_parts.append(val)

        case_summary = query_obj.get("case_summary", "") or ""
        if case_summary:
            facts_parts.append(case_summary)

        legal_regime: Optional[str] = query_obj.get("legal_regime")

        facts_text = " ".join(facts_parts)
        facts_lower = facts_text.lower()

        # ── 2. Select Candidates via Evidentiary Clusters ──────────────
        active_clusters: List[str] = []
        # Candidates come only from evidentiary categories the facts actually raise; no sections are
        # added to every case regardless of facts.
        candidate_sec_nums: Set[str] = set()

        for cluster_name, cluster_data in _EVIDENCE_CLUSTERS.items():
            if any(_matches_keyword(kw, facts_lower) for kw in cluster_data["keywords"]):
                active_clusters.append(cluster_name)
                candidate_sec_nums.update(cluster_data["target_sections"])

        # Prepare rich candidate descriptions for LLM
        candidates_info: List[Dict[str, Any]] = []
        for sec_num in sorted(candidate_sec_nums, key=lambda x: int(x) if x.isdigit() else 999):
            rec = repo.get_bsa_section_details(sec_num)
            if not rec:
                continue
            if rec.get("is_omitted") or rec.get("is_repealed"):
                continue

            heading = rec.get("section_title", "")
            full_text = rec.get("full_text", "")
            replaces_iea = rec.get("replaces_IEA") or repo.get_bsa_iea_equivalent(sec_num)
            chapter_number = rec.get("chapter_number", "")
            chapter_title = rec.get("chapter_title", "")

            # Truncate statutory text for prompt
            stat_snippet = full_text[:400] if full_text else ""

            candidates_info.append({
                "section_number": sec_num,
                "heading": heading,
                "chapter_number": chapter_number,
                "chapter_title": chapter_title,
                "replaces_IEA": replaces_iea,
                "statutory_text": stat_snippet,
            })

        if not candidates_info:
            notes.append("No BSA candidates identified from case facts.")
            return BSARetrievalObject(
                retrieval_notes=notes,
                legal_regime=legal_regime,
            )

        # ── 3. LLM Evidentiary Reasoning ──────────────────────────────
        candidate_text_lines = []
        for c in candidates_info:
            iea_str = f" [Replaces IEA {c['replaces_IEA']}]" if c['replaces_IEA'] else ""
            candidate_text_lines.append(
                f"- BSA Section {c['section_number']}: {c['heading']}{iea_str}\n"
                f"  Statutory text: {c['statutory_text']}\n"
            )
        candidate_sections_text = "\n".join(candidate_text_lines)

        evidentiary_issues_summary = (
            f"Active evidentiary clusters detected: {', '.join(active_clusters) if active_clusters else 'General documentary issues'}.\n"
            f"Key factual cues: {facts_summary_short(facts_text)}"
        )

        proposed_accepted: List[BSASectionItem] = []
        llm_rejected: List[BSASectionItem] = []

        try:
            prompt = STAGE3B_BSA_USER_PROMPT_TEMPLATE.format(
                facts_summary=facts_text[:2500],
                evidentiary_issues=evidentiary_issues_summary,
                candidate_sections_text=candidate_sections_text,
            )

            response = self.llm.invoke([
                SystemMessage(content=STAGE3B_BSA_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])

            raw_text = response.content if hasattr(response, "content") else str(response)
            parsed = extract_json_from_text(raw_text)

            eval_list = parsed.get("evaluated_sections", []) if isinstance(parsed, dict) else []

            for item in eval_list:
                s_num = str(item.get("section_number", "")).strip()
                c_info = next((c for c in candidates_info if c["section_number"] == s_num), None)
                if not c_info:
                    continue

                is_applicable = bool(item.get("is_applicable", False))
                category = str(item.get("relevance_category", "DOCUMENTS")).upper()
                reasoning = str(item.get("evidentiary_reasoning", ""))

                sec_item = BSASectionItem(
                    section_number=s_num,
                    heading=c_info["heading"],
                    chapter_number=c_info["chapter_number"],
                    chapter_title=c_info["chapter_title"],
                    relevance_category=category,
                    relevance_reason=reasoning,
                    replaces_IEA=c_info["replaces_IEA"],
                    statutory_text=c_info["statutory_text"],
                    verification_status="VERIFIED" if is_applicable else "REJECTED",
                    verification_reason=reasoning,
                )

                if is_applicable:
                    proposed_accepted.append(sec_item)
                else:
                    llm_rejected.append(sec_item)

        except Exception as e:
            notes.append(f"LLM reasoning fallback triggered ({e}); evaluating candidates via heuristic rules.")
            # Fallback heuristic
            for c in candidates_info:
                sec_item = BSASectionItem(
                    section_number=c["section_number"],
                    heading=c["heading"],
                    chapter_number=c["chapter_number"],
                    chapter_title=c["chapter_title"],
                    relevance_category="DOCUMENTS",
                    relevance_reason="Relevant to documentary evidence in dispute.",
                    replaces_IEA=c["replaces_IEA"],
                    statutory_text=c["statutory_text"],
                    verification_status="VERIFIED",
                )
                proposed_accepted.append(sec_item)

        # ── 4. Verifier Agent Audit (Accept / Reject) ─────────────────
        verified_accepted, verifier_rejected, verifier_notes = self.verifier.verify(
            facts_summary=facts_text,
            candidates=proposed_accepted,
        )
        notes.extend(verifier_notes)

        # Combine all rejected sections (from LLM reasoning + verifier)
        all_rejected: List[BSASectionItem] = list(llm_rejected)
        all_rejected.extend(verifier_rejected)

        # Limit to top_k accepted sections
        final_accepted = verified_accepted[: self.top_k]

        # ── 5. Resolve Stage 3 IPC offences to BNS via Neo4j ───────────
        ipc_to_bns: Dict[str, str] = {}
        if verified_offences:
            for offence in verified_offences:
                raw_sec = str(
                    offence.get("ipc_equivalent")
                    or offence.get("section_number")
                    or ""
                ).strip()
                clean_sec = raw_sec.upper().replace("IPC_", "").replace("SECTION ", "").strip()
                if not clean_sec:
                    continue

                bns_eq = repo.get_ipc_bns_equivalent(clean_sec)
                if bns_eq:
                    ipc_to_bns[clean_sec] = bns_eq
                    continue

                bns_from_dict = str(offence.get("bns_equivalent") or "").strip()
                if bns_from_dict and bns_from_dict.upper() not in ("NONE", "N/A", ""):
                    ipc_to_bns[clean_sec] = bns_from_dict

        return BSARetrievalObject(
            relevant_sections=final_accepted,
            rejected_sections=all_rejected,
            ipc_to_bns_map=ipc_to_bns,
            retrieval_notes=notes,
            legal_regime=legal_regime,
        )


def facts_summary_short(facts: str) -> str:
    """Returns a short snippet of facts highlighting evidence terms."""
    words = facts.split()
    return " ".join(words[:60]) + ("..." if len(words) > 60 else "")
