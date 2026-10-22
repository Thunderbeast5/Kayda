"""
BNSS Procedural Law Retrieval & Reasoning Agent (Stage 3c).

Identifies and reasons over Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS) procedural
sections (bail, anticipatory bail, arrest safeguards, custody/remand, investigation)
using corpus-grounded candidate prefiltering, definition-grounded LLM reasoning,
and BNSSVerifierAgent auditing. Replicates the IPC retrieval architecture for procedural criminal law.

Key features:
  - Robust multi-stage context extraction preserving factual narrative, procedural stage,
    and requested relief from Stage 0 / Stage 1.
  - Definition-grounded reasoning: candidate sections enriched with full statutory definitions
    (up to 1500 chars) from StatuteRepository.
  - NO statutory ingredients evaluation (BNSS sections are procedural rules, not offences).
  - Procedural grounding: evaluates core relief (482/480/483), arrest safeguards (35/36),
    custody/remand (187), and conditions/bonds (484/485).
  - Independent BNSSVerifierAgent audit ensuring genuine procedural nexus without hardcoded hacks.
  - Maps BNSS sections to CrPC equivalents using Neo4j REPLACES edge.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE2
from .statute_repository import StatuteRepository
from .schemas.stage_bnss import BNSSRetrievalObject, BNSSSectionItem
from .bnss_verifier_agent import BNSSVerifierAgent


STAGE3C_BNSS_SYSTEM_PROMPT = """You are a Senior Criminal Procedural Law Specialist and Sessions Judge specializing in the Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS) and the Code of Criminal Procedure, 1973 (CrPC).

Your responsibility is to analyze the case facts, identify live procedural controversies (such as apprehension of arrest, custodial interrogation necessity, notice of appearance, and bail conditions), and evaluate candidate BNSS sections.

CRITICAL EVALUATION PRINCIPLES:
1. PROCEDURAL GROUNDING (NO OFFENCE INGREDIENTS):
   BNSS sections are procedural rules. Do NOT evaluate offence ingredients (mens rea / actus reus).
   Instead, evaluate whether the procedural provision governs the current procedural controversy, relief sought, or rights/safeguards of the parties:

   A. ANTICIPATORY BAIL & APPREHENSION OF ARREST:
      - BNSS 482 (CrPC 438 equivalent): Core substantive section for direction for grant of bail to a person apprehending arrest in a non-bailable offence.
        * MUST BE ACCEPTED if the applicant is seeking anticipatory bail, apprehends arrest, or faces non-bailable accusations before arrest.
      - BNSS 483 (CrPC 439 equivalent): Special powers of High Court or Court of Session regarding bail.

   B. ARREST SAFEGUARDS & NOTICE OF APPEARANCE:
      - BNSS 35 (CrPC 41, 41A equivalent): Power to arrest without warrant, necessity of arrest under 35(1)(b), and mandatory Notice of Appearance under 35(3) when arrest is unnecessary.
        * In an anticipatory bail plea or pre-arrest dispute, BNSS 35 is directly applicable to demonstrate whether arrest is unjustified, custodial interrogation is unnecessary, or notice of appearance should govern. ACCEPT when arrest necessity, custodial interrogation, or cooperation with police is at issue.
      - BNSS 36 (CrPC 41B) / BNSS 43 (CrPC 46): Procedure and safeguards in making arrest.

   C. CUSTODIAL INTERROGATION & REMAND:
      - BNSS 187 (CrPC 167 equivalent): Procedure when investigation cannot be completed in 24 hours (custodial interrogation, police remand, judicial remand).
        * Relevant when prosecution demands custodial interrogation or detention limits are contested.

   D. BAIL CONDITIONS & BONDS:
      - BNSS 484 / BNSS 485 / BNSS 482(2): Bail conditions (cooperating with investigation, not tampering with evidence, not leaving jurisdiction) and bond execution.
        * In bail applications, terms and conditions for release are an integral part of the procedural controversy. ACCEPT when bail conditions or undertakings are involved.

   E. REGULAR BAIL IN NON-BAILABLE OFFENCES:
      - BNSS 480 (CrPC 437 equivalent): Criteria for bail in non-bailable offences after arrest.
        * Relevant when the accused is in custody or regular bail criteria apply. If applicant is solely seeking pre-arrest anticipatory bail, BNSS 482 is primary.

2. STRICTLY REJECT NOISE:
   - REJECT court administrative hierarchy (BNSS 6-15) and general prosecutorial appointments (BNSS 18-20) unless specifically challenged.
   - REJECT statutory default bail (BNSS 479) unless the accused has already been in custody past statutory time limits.

3. STRUCTURED OUTPUT:
   For EACH candidate section, return:
   - "section_number": String
   - "is_applicable": true or false
   - "relevance_category": One of ["ANTICIPATORY_BAIL", "ARREST_PROCEDURE", "NOTICE_OF_APPEARANCE", "CUSTODY_REMAND", "REGULAR_BAIL", "BAIL_CONDITIONS", "INVESTIGATION", "GENERAL_PROCEDURE"]
   - "procedural_reasoning": Specific, fact-grounded explanation of why this procedural section is accepted or rejected based on the case facts and procedural posture.

Output ONLY valid JSON.
"""

STAGE3C_BNSS_USER_PROMPT_TEMPLATE = """Evaluate the following candidate BNSS Procedural Law sections against the case facts and procedural posture.

---
CASE SUMMARY & FACTUAL NARRATIVE:
{facts_summary}
---

PROCEDURAL CONTEXT & ISSUES:
{procedural_issues}
---

CANDIDATE BNSS SECTIONS (WITH OPERATIVE DEFINITIONS):
{candidate_sections_text}
---

Evaluate every candidate section. For each section, decide if it should be ACCEPTED (is_applicable: true) or REJECTED (is_applicable: false).
Remember: In an Anticipatory Bail matter, BNSS 482 is the governing relief provision, and arrest safeguards (BNSS 35) and conditions (BNSS 484/485) form part of the live procedural framework.

Return your response in the following JSON format ONLY:
{{
  "procedural_analysis": "Concise summary of the key procedural questions in this case",
  "evaluated_sections": [
    {{
      "section_number": "482",
      "heading": "Direction for grant of bail to person apprehending arrest",
      "is_applicable": true,
      "relevance_category": "ANTICIPATORY_BAIL",
      "procedural_reasoning": "Directly applies because applicant seeks pre-arrest protection and apprehends arrest in a non-bailable matter."
    }},
    {{
      "section_number": "35",
      "heading": "When police may arrest without warrant",
      "is_applicable": true,
      "relevance_category": "ARREST_PROCEDURE",
      "procedural_reasoning": "Applies because police power of arrest in cognizable offences and necessity of arrest or custodial interrogation are at issue."
    }}
  ]
}}
"""


class BNSSRetrievalAgent:
    """
    Stage 3c BNSS Procedural Law Section Retrieval & Reasoning Agent.

    Replicates the IPC section retrieval architecture:
    1. Robust case narrative & procedural context extraction across Stage 0 / Stage 1 contracts.
    2. Zero-API-call candidate prefiltering against the BNSS corpus using textual & conceptual relevance.
    3. Definition enrichment (providing full statutory text up to 1500 chars so subsections like Notice of Appearance and bail conditions are intact).
    4. Definition-grounded LLM reasoning over live procedural controversies.
    5. BNSSVerifierAgent audit ensuring genuine procedural grounding without hardcoded hacks.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        verifier: Optional[BNSSVerifierAgent] = None,
        top_k: int = 8,
        use_nomination: bool = True,
        nominator: Optional[Any] = None,
    ):
        self._llm = llm
        self.verifier = verifier or BNSSVerifierAgent(llm=self._llm)
        self.top_k = top_k
        self.use_nomination = use_nomination
        self._nominator = nominator

    def _nominate(self, query_obj: Dict[str, Any], procedural_meta: Dict[str, Any],
                  verified_offences: Optional[List[Dict[str, Any]]]) -> Optional[List[BNSSSectionItem]]:
        from .act_nominator import ActSectionNominator, facts_block_from, offences_block_from
        nominator = self._nominator or ActSectionNominator("BNSS", llm=self._llm)
        context = "\n".join([
            f"  Procedural stage: {procedural_meta.get('procedural_stage') or query_obj.get('case_type') or 'not stated'}",
            f"  Relief sought: {procedural_meta.get('requested_relief') or 'not stated'}",
            "  Offences under consideration:\n" + offences_block_from(verified_offences),
        ])
        noms = nominator.run(facts_block_from(query_obj), context)
        if not noms:
            return None
        repo = StatuteRepository.get_instance()
        items = []
        for n in noms[: self.top_k]:
            rec = n["record"]
            items.append(BNSSSectionItem(
                section_number=n["section"],
                heading=rec.get("title") or "",
                chapter_number=rec.get("chapter_number") or "",
                chapter_title=rec.get("chapter_title") or "",
                relevance_category=n["category"],
                relevance_reason=f"{n['applies_to']}: {n['reason']}".strip(": "),
                replaces_CrPC=rec.get("replaces_CrPC") or repo.get_bnss_crpc_equivalent(n["section"]),
                statutory_text=(rec.get("raw_section") or {}).get("text", "")[:500],
                applicability=n["applicability"],
                verification_status="VERIFIED",
                verification_reason=f"Nominated from the complete BNSS list ({n['applicability']}); governs {n['applies_to'] or 'the relief sought'}.",
            ))
        return items

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE2)
        return self._llm

    def _extract_case_text_and_context(
        self,
        legal_query: Union[Dict[str, Any], Any],
        case_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Extracts complete factual narrative and procedural context from Stage 0 / Stage 1.
        Mirroring Stage 2 extraction so no factual or procedural cues are lost.
        """
        query_obj = legal_query if isinstance(legal_query, dict) else (
            legal_query.model_dump() if hasattr(legal_query, "model_dump") else {}
        )

        facts_parts: List[str] = []
        procedural_meta: Dict[str, Any] = {
            "requested_relief": "",
            "procedural_stage": "",
            "case_type": query_obj.get("case_type", ""),
            "events": query_obj.get("procedural_events", []),
        }

        # 1. Extract from case_context (Stage 0 CaseProfile / VerificationResult)
        if case_context:
            ctx_dict = case_context if isinstance(case_context, dict) else (
                case_context.model_dump() if hasattr(case_context, "model_dump") else {}
            )
            cp = ctx_dict.get("case_profile")
            if isinstance(cp, dict):
                for k in ["case_facts", "raw_text", "requested_relief", "procedural_stage", "regime_notes"]:
                    v = cp.get(k)
                    if isinstance(v, str) and v.strip():
                        facts_parts.append(v.strip())
                if cp.get("requested_relief"):
                    procedural_meta["requested_relief"] = str(cp["requested_relief"])
                if cp.get("procedural_stage"):
                    procedural_meta["procedural_stage"] = str(cp["procedural_stage"])
            elif hasattr(cp, "case_facts"):
                for k in ["case_facts", "raw_text", "requested_relief", "procedural_stage", "regime_notes"]:
                    v = getattr(cp, k, None)
                    if isinstance(v, str) and v.strip():
                        facts_parts.append(v.strip())
                if getattr(cp, "requested_relief", None):
                    procedural_meta["requested_relief"] = str(getattr(cp, "requested_relief"))
                if getattr(cp, "procedural_stage", None):
                    procedural_meta["procedural_stage"] = str(getattr(cp, "procedural_stage"))

            for k in ["case_facts", "raw_text", "documents_text", "text", "user_query"]:
                v = ctx_dict.get(k)
                if isinstance(v, str) and v.strip():
                    facts_parts.append(v.strip())
            if ctx_dict.get("requested_relief") and not procedural_meta["requested_relief"]:
                procedural_meta["requested_relief"] = str(ctx_dict["requested_relief"])
            if ctx_dict.get("procedural_stage") and not procedural_meta["procedural_stage"]:
                procedural_meta["procedural_stage"] = str(ctx_dict["procedural_stage"])

        # 2. Extract from legal_query (Stage 1 LegalQueryObject)
        for raw_key in ["case_facts", "raw_text", "text", "user_query", "raw_case_text", "case_summary"]:
            val = query_obj.get(raw_key)
            if isinstance(val, str) and val.strip():
                facts_parts.append(val.strip())

        if query_obj.get("case_type"):
            facts_parts.append(f"Case Type / Relief: {query_obj['case_type']}")
            if not procedural_meta["requested_relief"]:
                procedural_meta["requested_relief"] = query_obj["case_type"]

        imp = query_obj.get("important_facts") or {}
        if isinstance(imp, dict):
            for v in imp.values():
                if isinstance(v, str) and v.strip():
                    facts_parts.append(v.strip())
                elif isinstance(v, list):
                    facts_parts.extend(str(x).strip() for x in v if str(x).strip())

        for pe in query_obj.get("procedural_events", []):
            if isinstance(pe, str) and pe.strip():
                facts_parts.append(pe.strip())

        for concept in query_obj.get("legal_concepts", []):
            c = concept.get("concept", "") if isinstance(concept, dict) else getattr(concept, "concept", "")
            if c:
                facts_parts.append(c)

        for sq in query_obj.get("sub_queries", []):
            q = sq.get("query", "") if isinstance(sq, dict) else getattr(sq, "query", "")
            if q:
                facts_parts.append(q)

        combined_facts = " ".join(facts_parts).strip()
        return combined_facts, procedural_meta

    def _prefilter_bnss_candidates(
        self,
        facts_text: str,
        procedural_meta: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Prefilters BNSS candidates against the statutory corpus using definition
        and title matching, replicating StatuteClassifierPrefilter for BNSS.
        """
        repo = StatuteRepository.get_instance()
        facts_lower = facts_text.lower()
        query_tokens = set(re.findall(r"\w+", facts_lower))

        scored_candidates: List[Tuple[float, Dict[str, Any]]] = []
        seen_secs: Set[str] = set()

        # Core procedural anchor sections evaluated in criminal disputes
        anchor_sections = ["35", "36", "43", "187", "479", "480", "482", "483", "484", "485"]

        if any(term in facts_lower for term in ["search", "seiz", "recover", "raid", "device", "laptop", "phone"]):
            anchor_sections.extend(["94", "105", "106"])

        # Score sections in bnss_sections_db
        for sec_entry in repo.bnss_sections_db:
            sec_num = str(sec_entry.get("section_number", "")).strip()
            if not sec_num or sec_num in seen_secs:
                continue

            heading = sec_entry.get("title", "")
            heading_lower = heading.lower()
            crpc_eq = sec_entry.get("replaces_CrPC") or repo.get_bnss_crpc_equivalent(sec_num)

            # Filter out administrative court hierarchy noise (sections 6-25) unless anchor
            if sec_num.isdigit() and 6 <= int(sec_num) <= 25 and sec_num not in anchor_sections:
                continue

            score = 0.0
            heading_tokens = set(re.findall(r"\w+", heading_lower))

            # Overlap with heading
            overlap = query_tokens.intersection(heading_tokens)
            if overlap:
                score += len(overlap) * 2.0

            # Procedural stage & relief routing table (Issue Section 7.4)
            # Route using Stage 0 procedural_stage and requested_relief, not ad-hoc substring scanning
            relief_str = str(procedural_meta.get("requested_relief") or "").upper()
            stage_str = str(procedural_meta.get("procedural_stage") or "").upper()

            # Identify primary procedural route
            if "ANTICIPATORY" in relief_str or "ANTICIPATORY" in stage_str or re.search(r"\b(anticipatory\s+bail|apprehend(?:ing)?\s+arrest)\b", facts_lower):
                if sec_num in ["482", "483"]:
                    score += 15.0
                if sec_num in ["35", "36"]:
                    score += 8.0
                if sec_num in ["484", "485"]:
                    score += 6.0
            elif "REGULAR" in relief_str or "REGULAR" in stage_str or (("BAIL" in relief_str or "BAIL" in stage_str) and re.search(r"\b(custody|arrested|in\s+jail)\b", facts_lower)):
                if sec_num in ["480", "483"]:
                    score += 15.0
                if sec_num in ["484", "485", "487"]:
                    score += 8.0
            elif "BAIL" in relief_str or "BAIL" in stage_str or re.search(r"\bbail\b", facts_lower):
                if sec_num in ["482", "480", "483"]:
                    score += 12.0
                if sec_num in ["484", "485"]:
                    score += 6.0

            if re.search(r"\b(custodial\s+interrogation|police\s+remand|judicial\s+remand|remand)\b", facts_lower):
                if sec_num in ["35", "187"]:
                    score += 10.0

            if re.search(r"\b(search|seizure|seized|recovery\s+memo|raid)\b", facts_lower):
                if sec_num in ["94", "105", "185"]:
                    score += 10.0

            if sec_num in anchor_sections:
                score += 5.0

            if score > 0.0:
                seen_secs.add(sec_num)
                rec = repo.get_bnss_section_details(sec_num) or {}
                full_text = rec.get("full_text") or sec_entry.get("raw_section", {}).get("text", "")

                scored_candidates.append((
                    score,
                    {
                        "section_number": sec_num,
                        "heading": heading or rec.get("section_title", f"BNSS Section {sec_num}"),
                        "chapter_number": sec_entry.get("chapter_number") or rec.get("chapter_number", ""),
                        "chapter_title": sec_entry.get("chapter_title") or rec.get("chapter_title", ""),
                        "replaces_CrPC": crpc_eq,
                        # Enrich with definition up to 1500 chars (like IPC Stage 2)
                        "statutory_text": full_text[:1500] if full_text else "",
                    }
                ))

        # Sort by score descending and take top candidates
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored_candidates[:12]]

    def run(
        self,
        legal_query: Union[Dict[str, Any], Any],
        case_context: Optional[Dict[str, Any]] = None,
        verified_offences: Optional[List[Dict[str, Any]]] = None,
    ) -> BNSSRetrievalObject:
        """
        Executes definition-grounded BNSS procedural retrieval and verification.
        """
        notes: List[str] = []

        # ── 1. Extract case narrative and procedural context ───────────
        facts_text, procedural_meta = self._extract_case_text_and_context(legal_query, case_context)

        query_obj = legal_query if isinstance(legal_query, dict) else (
            legal_query.model_dump() if hasattr(legal_query, "model_dump") else {}
        )
        legal_regime: Optional[str] = query_obj.get("legal_regime")

        # ── 1a. Nomination over the complete BNSS (1 LLM call); the prefilter below is the fallback ──
        if self.use_nomination:
            nominated = self._nominate(query_obj, procedural_meta, verified_offences)
            if nominated is not None:
                return BNSSRetrievalObject(
                    relevant_sections=nominated,
                    retrieval_notes=[f"{len(nominated)} BNSS sections nominated from the complete Sanhita (validated against bnss.json)."],
                    legal_regime=legal_regime,
                )
            notes.append("BNSS nomination unavailable; used prefilter retrieval.")

        # ── 2. Corpus Candidate Prefilter & Definition Enrichment ──────
        candidates_info = self._prefilter_bnss_candidates(facts_text, procedural_meta)

        if not candidates_info:
            notes.append("No BNSS candidates identified from case facts.")
            return BNSSRetrievalObject(
                retrieval_notes=notes,
                legal_regime=legal_regime,
            )

        # ── 3. Definition-Grounded LLM Procedural Reasoning ───────────
        candidate_text_lines = []
        for c in candidates_info:
            crpc_str = f" [Replaces CrPC {c['replaces_CrPC']}]" if c['replaces_CrPC'] else ""
            candidate_text_lines.append(
                f"- BNSS Section {c['section_number']}: {c['heading']}{crpc_str}\n"
                f"  Statutory definition & operative text:\n{c['statutory_text']}\n"
            )
        candidate_sections_text = "\n".join(candidate_text_lines)

        relief_str = procedural_meta.get("requested_relief") or "Criminal Proceeding / Bail"
        stage_str = procedural_meta.get("procedural_stage") or "Investigation / Pre-trial"

        procedural_issues_summary = (
            f"Relief sought: {relief_str} | Procedural Stage: {stage_str}\n"
            f"Key case issues: {facts_summary_short(facts_text)}"
        )

        proposed_accepted: List[BNSSSectionItem] = []
        proposed_rejected: List[BNSSSectionItem] = []

        try:
            prompt = STAGE3C_BNSS_USER_PROMPT_TEMPLATE.format(
                facts_summary=facts_text[:3500],
                procedural_issues=procedural_issues_summary,
                candidate_sections_text=candidate_sections_text,
            )

            response = self.llm.invoke([
                SystemMessage(content=STAGE3C_BNSS_SYSTEM_PROMPT),
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
                category = str(item.get("relevance_category", "PROCEDURE")).upper()
                reasoning = str(item.get("procedural_reasoning", ""))

                sec_item = BNSSSectionItem(
                    section_number=s_num,
                    heading=c_info["heading"],
                    chapter_number=c_info["chapter_number"],
                    chapter_title=c_info["chapter_title"],
                    relevance_category=category,
                    relevance_reason=reasoning,
                    replaces_CrPC=c_info["replaces_CrPC"],
                    statutory_text=c_info["statutory_text"][:500],
                    verification_status="VERIFIED" if is_applicable else "REJECTED",
                    verification_reason=reasoning,
                )

                if is_applicable:
                    proposed_accepted.append(sec_item)
                else:
                    proposed_rejected.append(sec_item)

        except Exception as e:
            notes.append(f"LLM reasoning fallback ({e}); using definition baseline candidates.")
            for c in candidates_info[:4]:
                sec_item = BNSSSectionItem(
                    section_number=c["section_number"],
                    heading=c["heading"],
                    chapter_number=c["chapter_number"],
                    chapter_title=c["chapter_title"],
                    relevance_category="PROCEDURE",
                    relevance_reason="Relevant procedural provision for current dispute.",
                    replaces_CrPC=c["replaces_CrPC"],
                    statutory_text=c["statutory_text"][:500],
                    verification_status="VERIFIED",
                )
                proposed_accepted.append(sec_item)

        # ── 4. Definition-Grounded Verifier Agent Audit ────────────────
        verified_accepted, verifier_rejected, verifier_notes = self.verifier.verify(
            facts_summary=facts_text,
            procedural_meta=procedural_meta,
            accepted_candidates=proposed_accepted,
            rejected_candidates=proposed_rejected,
        )
        notes.extend(verifier_notes)

        # Distinguish the provision governing the relief sought from general procedural machinery
        # (e.g. bond sections 484/485 are not provisions "governing" anticipatory bail).
        relief = f"{procedural_meta.get('requested_relief', '')} {procedural_meta.get('procedural_stage', '')}".lower()
        if "anticipatory" in relief:
            direct = {"ANTICIPATORY_BAIL"}
        elif "bail" in relief:
            direct = {"REGULAR_BAIL", "DEFAULT_BAIL"}
        elif "remand" in relief or "custody" in relief:
            direct = {"CUSTODY_REMAND"}
        else:
            direct = set()
        for s in verified_accepted:
            cat = (s.relevance_category or "").upper()
            if cat in direct:
                s.applicability = "DIRECT"
            elif cat in {"BAIL_CONDITIONS", "GENERAL_PROCEDURE"}:
                s.applicability = "ANCILLARY"
            else:
                s.applicability = "CONTEXTUAL"
        tier_rank = {"DIRECT": 0, "CONTEXTUAL": 1, "ANCILLARY": 2}
        verified_accepted.sort(key=lambda s: tier_rank.get(s.applicability, 1))

        final_accepted = verified_accepted[: self.top_k]

        # BNSS -> CrPC equivalents are resolved once, after Stage 4 (runner.run_equivalence_mapping).
        return BNSSRetrievalObject(
            relevant_sections=final_accepted,
            rejected_sections=verifier_rejected,
            retrieval_notes=notes,
            legal_regime=legal_regime,
        )


def facts_summary_short(facts: str) -> str:
    """Returns a short snippet of facts highlighting procedural terms."""
    words = facts.split()
    return " ".join(words[:60]) + ("..." if len(words) > 60 else "")
