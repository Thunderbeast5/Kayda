"""
BNSS Verifier Agent (Stage 3c).

Audits candidate BNSS procedural sections proposed by BNSSRetrievalAgent.
Replicates the Stage 2 / Stage 4 IPC verifier architecture:
- Definition-grounded procedural scope checks.
- Audits both proposed accepted sections and proposed rejected candidates to catch false rejections.
- NO hardcoded keyword lists or brittle string hacks.
- Ensures only verified procedural provisions with genuine procedural nexus reach downstream stages.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE2
from .schemas.stage_bnss import BNSSSectionItem


STAGE3C_BNSS_VERIFIER_SYSTEM_PROMPT = """You are the Senior BNSS Procedural Criminal Law Verification Auditor.
Your responsibility is to audit candidate Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS) procedural sections
(dealing with bail, anticipatory bail, arrest safeguards, custody, remand, and investigation) proposed for the case.

AUDIT & VERIFICATION PRINCIPLES (DEFINITION-GROUNDED):
1. PROCEDURAL NEXUS & SCOPE:
   - Anticipatory Bail (BNSS 482, 483):
     * If the case facts or procedural posture involve apprehension of arrest, seeking anticipatory bail, or pre-arrest protection in a non-bailable offence, BNSS 482 MUST BE ACCEPTED.
     * BNSS 483 (High Court / Sessions Court bail powers) is applicable where court discretion or interim protection is sought.
   - Arrest Safeguards & Notice of Appearance (BNSS 35, 36, 43):
     * If allegations involve power to arrest without warrant, whether arrest is necessary, cooperation with investigation, or notice of appearance (35(3) / CrPC 41A), ACCEPT.
   - Custody & Remand (BNSS 187):
     * If custodial interrogation or police remand is in controversy, ACCEPT.
     * If accused is not in custody and seeking anticipatory bail where no remand is yet sought, it may be rejected unless custodial interrogation is actively argued.
   - Regular Bail (BNSS 480):
     * If accused is in post-arrest custody seeking release in non-bailable offences, ACCEPT. If purely pre-arrest anticipatory bail, BNSS 482 is the applicable bail provision.
   - Bail Conditions & Bonds (BNSS 484, 485):
     * Imposition of conditions (cooperation, non-tampering, bond/sureties) is an integral statutory aspect of granting bail. ACCEPT if bail is being sought or considered.

2. FALSE REJECTION RESCUE:
   - Carefully review candidate sections that the Reasoner marked as REJECTED.
   - If a section was rejected solely due to a misconception (e.g. rejecting BNSS 482 in an anticipatory bail matter, or rejecting BNSS 35 because the accused is not handcuffed yet), RESCUE and ACCEPT the section.

3. NOISE SUPPRESSION:
   - REJECT generic court administration hierarchy (BNSS 6-25) or prosecutorial appointment provisions (BNSS 18-20) unless specifically challenged.

Return your audit verdict in valid JSON.
"""

STAGE3C_BNSS_VERIFIER_USER_PROMPT_TEMPLATE = """Audit the proposed BNSS procedural sections against the case facts and procedural posture.

---
CASE FACTS & PROCEDURAL POSTURE:
{facts_summary}
---

PROPOSED ACCEPTED BNSS SECTIONS:
{accepted_sections_json}
---

PROPOSED REJECTED BNSS SECTIONS:
{rejected_sections_json}
---

For each section, designate ACCEPT or REJECT with a concise audit reason.
Ensure that core procedural provisions governing the live controversy (e.g., BNSS 482 / 35 in anticipatory bail) are ACCEPTED, and administrative noise is REJECTED.

Return valid JSON:
{{
  "verdict_status": "VERIFIED",
  "audit_summary": "Summary of procedural audit decisions",
  "section_audits": [
    {{
      "section_number": "482",
      "verdict": "ACCEPT",
      "category": "ANTICIPATORY_BAIL",
      "reason": "Directly applies because the applicant seeks anticipatory bail and apprehends arrest in a non-bailable matter."
    }},
    {{
      "section_number": "35",
      "verdict": "ACCEPT",
      "category": "ARREST_PROCEDURE",
      "reason": "Applies because police power of arrest in cognizable offences and necessity of arrest or custodial interrogation are at issue."
    }}
  ]
}}
"""


class BNSSVerifierAgent:
    """
    Stage 3c Auditor for BNSS Procedural Criminal Law Section Retrieval.
    Audits candidates against procedural facts and statutory definitions,
    replicating the Stage 2 / Stage 4 IPC verification model.
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
        procedural_meta: Optional[Dict[str, Any]] = None,
        accepted_candidates: Optional[List[BNSSSectionItem]] = None,
        rejected_candidates: Optional[List[BNSSSectionItem]] = None,
        candidates: Optional[List[BNSSSectionItem]] = None,
    ) -> Tuple[List[BNSSSectionItem], List[BNSSSectionItem], List[str]]:
        """
        Audits proposed BNSS candidates against case facts.

        Returns:
            Tuple of:
            - accepted_sections: List[BNSSSectionItem] with verification_status='VERIFIED'
            - rejected_sections: List[BNSSSectionItem] with verification_status='REJECTED'
            - audit_notes: List[str] summarizing audit adjustments
        """
        accepted_list = accepted_candidates or (candidates or [])
        rejected_list = rejected_candidates or []

        if not accepted_list and not rejected_list:
            return [], [], ["No candidate BNSS sections to verify."]

        all_candidates_map: Dict[str, BNSSSectionItem] = {}
        for s in accepted_list:
            all_candidates_map[str(s.section_number).strip()] = s
        for s in rejected_list:
            all_candidates_map[str(s.section_number).strip()] = s

        accepted_sections_json = json.dumps(
            [
                {
                    "section_number": s.section_number,
                    "heading": s.heading,
                    "category": s.relevance_category,
                    "reasoning": s.relevance_reason,
                }
                for s in accepted_list
            ],
            indent=2,
        )

        rejected_sections_json = json.dumps(
            [
                {
                    "section_number": s.section_number,
                    "heading": s.heading,
                    "category": s.relevance_category,
                    "reasoning": s.relevance_reason,
                }
                for s in rejected_list
            ],
            indent=2,
        )

        final_accepted: List[BNSSSectionItem] = []
        final_rejected: List[BNSSSectionItem] = []
        audit_notes: List[str] = []

        try:
            prompt = STAGE3C_BNSS_VERIFIER_USER_PROMPT_TEMPLATE.format(
                facts_summary=facts_summary[:3500],
                accepted_sections_json=accepted_sections_json,
                rejected_sections_json=rejected_sections_json,
            )

            response = self.llm.invoke([
                SystemMessage(content=STAGE3C_BNSS_VERIFIER_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])

            raw_text = response.content if hasattr(response, "content") else str(response)
            parsed = extract_json_from_text(raw_text)

            audit_map: Dict[str, Dict[str, Any]] = {}
            if isinstance(parsed, dict) and "section_audits" in parsed:
                for item in parsed["section_audits"]:
                    snum = str(item.get("section_number", "")).strip()
                    audit_map[snum] = item

            # Process all evaluated candidate sections
            evaluated_sec_nums = set()
            for snum, audit_info in audit_map.items():
                sec = all_candidates_map.get(snum)
                if not sec:
                    continue

                evaluated_sec_nums.add(snum)
                verdict = str(audit_info.get("verdict", "ACCEPT")).upper()
                reason = str(audit_info.get("reason", "Audited by BNSS Verifier"))
                cat = str(audit_info.get("category", sec.relevance_category or "PROCEDURE")).upper()

                sec.relevance_category = cat
                sec.verification_reason = reason

                if verdict == "ACCEPT":
                    sec.verification_status = "VERIFIED"
                    sec.confidence_score = 0.95
                    final_accepted.append(sec)
                    audit_notes.append(f"Verifier ACCEPTED BNSS {snum} ({sec.heading}): {reason}")
                else:
                    sec.verification_status = "REJECTED"
                    sec.confidence_score = 0.20
                    final_rejected.append(sec)
                    audit_notes.append(f"Verifier REJECTED BNSS {snum}: {reason}")

            # Keep any candidates not in audit_map with original verdict
            for snum, sec in all_candidates_map.items():
                if snum not in evaluated_sec_nums:
                    if sec in accepted_list:
                        final_accepted.append(sec)
                    else:
                        final_rejected.append(sec)

        except Exception as e:
            audit_notes.append(f"LLM verification audit fallback ({e}); using proposed candidate status.")
            final_accepted = list(accepted_list)
            final_rejected = list(rejected_list)

        return final_accepted, final_rejected, audit_notes
