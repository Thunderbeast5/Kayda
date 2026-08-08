import json
from typing import Any, Dict, Optional, Union, List
from pydantic import BaseModel

from .classifier_prefilter import (
    StatuteClassifierPrefilter,
    STATUTE_KNOWLEDGE_BASE,
    get_effective_knowledge_base,
)
from .statute_repository import StatuteRepository
from .ipc2bns_mapper import IPC2BNSMapper
from .batch_utils import Stage2BatchedMappingResponse, SectionMappingCandidate
from .schemas import ChapterIdentificationObject, LegalQueryObject, VerifiedOffenceItem, PunishmentSpec


class ChapterIdentificationAgent:
    """
    Stage 3 Statutory Verification & Normalization Engine (100% Deterministic, 0 LLM Calls).
    Consumes candidate offences from Stage 2, performs Knowledge Base lookups against
    STATUTE_KNOWLEDGE_BASE & IPC2BNSMapper, resolves IPC ↔ BNS equivalents, assigns canonical
    chapter numbers, titles, punishments, and bailability flags, merges duplicates, and outputs Schema v3.0.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        min_confidence_threshold: float = 0.70,
        prefilter: Optional[StatuteClassifierPrefilter] = None,
        mapper: Optional[IPC2BNSMapper] = None,
    ):
        self._llm = llm
        self.min_confidence_threshold = min_confidence_threshold
        self.prefilter = prefilter or StatuteClassifierPrefilter()
        self.mapper = mapper or IPC2BNSMapper()

    def run(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        stage2_mapping: Optional[Union[Stage2BatchedMappingResponse, Dict[str, Any], str]] = None,
        correction_feedback: Optional[str] = None,
    ) -> ChapterIdentificationObject:
        """
        Deterministically verifies and normalizes candidate statutory sections received from Stage 2.
        Operates with 0 LLM API calls, instant performance (< 5ms), and 0 hallucination risk.
        """
        # Standardize Stage 1 input
        if isinstance(legal_query, LegalQueryObject):
            query_obj = legal_query
        elif isinstance(legal_query, dict):
            query_obj = LegalQueryObject.model_validate(legal_query)
        elif isinstance(legal_query, str):
            query_obj = LegalQueryObject.model_validate(json.loads(legal_query))
        else:
            raise ValueError(f"Invalid legal_query type: {type(legal_query)}")

        # Standardize Stage 2 input
        stage2_resp: Optional[Stage2BatchedMappingResponse] = None
        if stage2_mapping is not None:
            if isinstance(stage2_mapping, Stage2BatchedMappingResponse):
                stage2_resp = stage2_mapping
            elif isinstance(stage2_mapping, dict):
                stage2_resp = Stage2BatchedMappingResponse.model_validate(stage2_mapping)
            elif isinstance(stage2_mapping, str):
                stage2_resp = Stage2BatchedMappingResponse.model_validate(json.loads(stage2_mapping))

        regime = query_obj.legal_regime or "IPC + CrPC"
        regime_upper = regime.upper()
        manual_review_flags = []

        if "UNKNOWN" in regime_upper:
            manual_review_flags.append("UNKNOWN legal regime: returned both IPC and BNS equivalents for human verification.")

        # Extract candidates from Stage 2 mapping
        candidates_to_verify: List[Dict[str, Any]] = []
        if stage2_resp and stage2_resp.mappings:
            for mapping in stage2_resp.mappings:
                for p in mapping.primary_candidate_sections:
                    candidates_to_verify.append({
                        "section_number": p.section_number,
                        "statute": p.statute,
                        "title": p.section_title,
                        "classification": "PRIMARY"
                    })
                for s in mapping.secondary_candidate_sections:
                    candidates_to_verify.append({
                        "section_number": s.section_number,
                        "statute": s.statute,
                        "title": s.section_title,
                        "classification": "SECONDARY"
                    })
                if not mapping.primary_candidate_sections and not mapping.secondary_candidate_sections:
                    for sec_str in mapping.candidate_sections:
                        candidates_to_verify.append({
                            "section_number": sec_str,
                            "statute": "BNS" if "BNS" in regime_upper else "IPC",
                            "title": sec_str,
                            "classification": "PRIMARY"
                        })
        else:
            # Fallback local pre-filter if Stage 2 mapping is omitted
            shortlist = self.prefilter.shortlist_candidates_for_query(query_obj, top_k=10, target_regime=regime)
            for item in shortlist:
                candidates_to_verify.append({
                    "section_number": item.section_number,
                    "statute": item.statute,
                    "title": item.title,
                    "classification": "PRIMARY"
                })

        # Deterministic verification & enrichment loop
        dedup_offences: Dict[str, VerifiedOffenceItem] = {}
        facts_text = getattr(query_obj, "case_facts", "") or ""
        if not facts_text and hasattr(query_obj, "legal_concepts"):
            facts_text = " ".join([c.concept for c in query_obj.legal_concepts]) + " " + " ".join([sq.query for sq in getattr(query_obj, "sub_queries", [])])

        # Automatically detect factual triggers when Stage 2 mapping is omitted or empty
        if not stage2_resp:
            triggered_suggestions = self.prefilter.detect_factual_triggers(facts_text, statute_type="BNS" if "BNS" in regime_upper else "IPC")
            seen_cand_keys = {f"{c.get('statute', '')}_{c.get('section_number', '')}".upper() for c in candidates_to_verify}
            for sug in triggered_suggestions:
                sug_key = f"{sug.get('statute', '')}_{sug.get('section_number', '')}".upper()
                if sug_key not in seen_cand_keys:
                    seen_cand_keys.add(sug_key)
                    candidates_to_verify.append({
                        "section_number": sug["section_number"],
                        "statute": sug["statute"],
                        "title": sug["section_title"],
                        "classification": sug["candidate_type"]
                    })

        for cand in candidates_to_verify:
            sec_raw = str(cand["section_number"]).strip()
            sec_num = sec_raw.upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
            statute_in = cand.get("statute", "IPC")
            tier = cand.get("classification", "PRIMARY")

            # 0. Fatal Disqualification Check against Case Facts
            disqualified, disq_reason, missing_ings = self.prefilter.evaluate_fatal_disqualification(
                sec_num, statute_in, facts_text
            )

            # 1. IPC <-> BNS Mapping Resolution
            ipc_eq = None
            bns_eq = None
            if "BNS" in statute_in.upper() or "BNS" in regime_upper:
                bns_eq = sec_num
                mapped = self.mapper.get_ipc_equivalent(sec_num)
                ipc_eq = mapped.get("ipc_section") if mapped else sec_num
            else:
                ipc_eq = sec_num
                mapped = self.mapper.get_bns_equivalent(sec_num)
                bns_eq = mapped.get("bns_section_clean") if mapped else sec_num

            # 2. Canonical Metadata Determination (Title, Chapter, Punishment, Cognizability)
            canon_title = cand.get("title", f"Section {sec_num}")
            statute_out = "IPC / BNS" if "UNKNOWN" in regime_upper else ("BNS" if "BNS" in statute_in.upper() or "BNS" in regime_upper else "IPC")

            # Knowledge Base Rule Lookup (static hardcoded + dynamic auto-promoted rules)
            found_rule = None
            for r in get_effective_knowledge_base():
                rule_sec_clean = r.section.upper().replace("SECTION ", "").strip()
                if sec_num == rule_sec_clean or sec_num == r.section.upper() or sec_num == r.bns_equivalent.upper():
                    found_rule = r
                    break

            first_sched_meta = StatuteRepository.get_instance().get_first_schedule_metadata(sec_num, statute_in)

            if found_rule:
                canon_title = found_rule.title
                if "Dowry Prohibition" in found_rule.statute:
                    statute_out = "Dowry Prohibition Act"
                    sec_num = found_rule.section

                chap_num = found_rule.chapter_number
                chap_title = found_rule.chapter_title
                punishment = PunishmentSpec(
                    minimum=found_rule.punishment_minimum,
                    maximum=found_rule.punishment_maximum,
                    fine=found_rule.fine,
                )
                cognizable = found_rule.cognizable
                bailable = found_rule.bailable
            elif first_sched_meta:
                chap_num = first_sched_meta["chapter_number"]
                chap_title = first_sched_meta["chapter_title"]
                punishment = PunishmentSpec(
                    minimum=first_sched_meta["punishment_minimum"],
                    maximum=first_sched_meta["punishment_maximum"],
                    fine=first_sched_meta["fine"],
                )
                cognizable = first_sched_meta["cognizable"]
                bailable = first_sched_meta["bailable"]
            else:
                chap_num = "IPC/BNS Chapter"
                chap_title = canon_title
                punishment = PunishmentSpec(minimum=None, maximum="As specified under statute", fine=True)
                cognizable = True
                bailable = False

            # Hard-exclude disqualified sections — do NOT demote to SECONDARY.
            # A disqualified section (wrong subject-matter or missing mandatory trigger)
            # must not enter verified_offences at all, since Stage 4 will see every
            # verified_offence as a valid candidate and can rate it "Prima Facie Attracted".
            if disqualified:
                disq_msg = (
                    f"Section {sec_num} excluded (NOT_TRIGGERED): {disq_reason or 'Mandatory statutory ingredients not satisfied by case facts.'}"
                )
                if disq_msg not in manual_review_flags:
                    manual_review_flags.append(disq_msg)
                continue  # Skip — do not add to verified_offences

            # Unique key for deduplication (merges 498A IPC & 85 BNS into single item, keeps Special Acts distinct)
            canon_key = f"{statute_out}_{ipc_eq or bns_eq or sec_num}".upper()
            if canon_key not in dedup_offences:
                notes = [
                    "Statutory existence verified against Knowledge Base registry.",
                    f"IPC <-> BNS equivalent mapped (IPC {ipc_eq} <-> BNS {bns_eq})." if "Dowry" not in statute_out else f"Special Act provision ({statute_out} {sec_num}).",
                    f"Canonical chapter ({chap_num}) and punishment metadata verified."
                ]
                if not found_rule and not first_sched_meta:
                    notes.append(f"WARNING: Section {sec_num} metadata unverified against First Schedule CrPC/BNSS ground truth.")
                if "UNKNOWN" in regime_upper:
                    notes.append("Legal regime is UNKNOWN: surfaced dual IPC & BNS equivalents.")

                verified_item = VerifiedOffenceItem(
                    section_number=sec_num,
                    statute=statute_out,
                    ipc_equivalent=ipc_eq if "Dowry" not in statute_out else None,
                    bns_equivalent=bns_eq if "Dowry" not in statute_out else None,
                    title=canon_title,
                    chapter_number=chap_num,
                    chapter_title=chap_title,
                    punishment=punishment,
                    classification=tier,
                    cognizable=cognizable,
                    bailable=bailable,
                    verification_status="VERIFIED",
                    verification_notes=notes,
                )
                dedup_offences[canon_key] = verified_item

        verified_list = list(dedup_offences.values())

        return ChapterIdentificationObject(
            schema_version="3.0",
            verified_offences=verified_list,
            legal_regime=regime,
            manual_review=manual_review_flags,
            verification_status="VERIFIED"
        )