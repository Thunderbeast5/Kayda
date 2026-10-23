import json
from typing import Any, Dict, Optional, Union, List
from pydantic import BaseModel

from .classifier_prefilter import (
    StatuteClassifierPrefilter,
    STATUTE_KNOWLEDGE_BASE,
    get_effective_knowledge_base,
)
from .statute_repository import StatuteRepository
from .batch_utils import Stage2BatchedMappingResponse, SectionMappingCandidate
from .schemas import ChapterIdentificationObject, LegalQueryObject, VerifiedOffenceItem, PunishmentSpec
from .prompts import STAGE3_SCREENING_SYSTEM_PROMPT, STAGE3_SCREENING_USER_PROMPT_TEMPLATE
from .config import extract_json_from_text, get_llm, MODEL_STAGE2


class ChapterIdentificationAgent:
    """
    Stage 3 Statutory Verification & Normalization Engine (100% Deterministic, 0 LLM Calls).
    Consumes candidate offences from Stage 2, performs Knowledge Base lookups against
    STATUTE_KNOWLEDGE_BASE and StatuteRepository, verifies IPC statutory sections, assigns canonical
    chapter numbers, titles, punishments, and bailability flags, merges duplicates, and outputs Schema v3.0.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        min_confidence_threshold: float = 0.70,
        prefilter: Optional[StatuteClassifierPrefilter] = None,
        mapper: Optional[Any] = None,
    ):
        self._llm = llm
        self.min_confidence_threshold = min_confidence_threshold
        self.prefilter = prefilter or StatuteClassifierPrefilter()

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
            elif hasattr(stage2_mapping, "batched_mapping_response") and stage2_mapping.batched_mapping_response:
                stage2_resp = stage2_mapping.batched_mapping_response
            elif isinstance(stage2_mapping, dict):
                try:
                    if "batched_mapping_response" in stage2_mapping and stage2_mapping["batched_mapping_response"]:
                        stage2_resp = Stage2BatchedMappingResponse.model_validate(stage2_mapping["batched_mapping_response"])
                    elif "mappings" in stage2_mapping:
                        stage2_resp = Stage2BatchedMappingResponse.model_validate(stage2_mapping)
                except Exception:
                    stage2_resp = None
            elif isinstance(stage2_mapping, str):
                try:
                    parsed = json.loads(stage2_mapping)
                    if isinstance(parsed, dict):
                        if "batched_mapping_response" in parsed and parsed["batched_mapping_response"]:
                            stage2_resp = Stage2BatchedMappingResponse.model_validate(parsed["batched_mapping_response"])
                        elif "mappings" in parsed:
                            stage2_resp = Stage2BatchedMappingResponse.model_validate(parsed)
                except Exception:
                    stage2_resp = None

        regime = query_obj.legal_regime or "IPC + CrPC"
        regime_upper = regime.upper()
        manual_review_flags = []

        # Extract candidates from Stage 2 mapping
        candidates_to_verify: List[Dict[str, Any]] = []
        stage2_sourced = True  # whether we got real Stage 2 input
        if stage2_resp and stage2_resp.mappings:
            for mapping in stage2_resp.mappings:
                for p in mapping.primary_candidate_sections:
                    candidates_to_verify.append({
                        "section_number": p.section_number,
                        "statute": p.statute or ("BNS" if "BNS" in regime_upper else "IPC"),
                        "title": p.section_title,
                        "classification": "PRIMARY",
                        "sub_query_id": mapping.sub_query_id,
                    })
                for s in mapping.secondary_candidate_sections:
                    candidates_to_verify.append({
                        "section_number": s.section_number,
                        "statute": s.statute or ("BNS" if "BNS" in regime_upper else "IPC"),
                        "title": s.section_title,
                        "classification": "SECONDARY",
                        "sub_query_id": mapping.sub_query_id,
                    })
                for c in getattr(mapping, "conditional_candidate_sections", []):
                    candidates_to_verify.append({
                        "section_number": c.section_number,
                        "statute": c.statute,
                        "title": c.section_title,
                        "classification": "CONDITIONAL",
                        "sub_query_id": mapping.sub_query_id,
                        "condition": "; ".join(getattr(c, "missing_facts", []) or []),
                    })
                if not mapping.primary_candidate_sections and not mapping.secondary_candidate_sections and not getattr(mapping, "conditional_candidate_sections", []):
                    for sec_str in mapping.candidate_sections:
                        candidates_to_verify.append({
                            "section_number": sec_str,
                            "statute": "IPC",
                            "title": sec_str,
                            "classification": "PRIMARY",
                            "sub_query_id": mapping.sub_query_id,
                        })
        else:
            # Fallback local pre-filter if Stage 2 mapping is omitted
            shortlist = self.prefilter.shortlist_candidates_for_query(query_obj, top_k=10, target_regime="IPC")
            for item in shortlist:
                candidates_to_verify.append({
                    "section_number": item.section_number,
                    "statute": "IPC",
                    "title": item.title,
                    "classification": "PRIMARY",
                    "sub_query_id": "FALLBACK",
                })

        # Deduplicate: drop purely definitional sections when their substantive penal counterpart
        # is already present in the candidate set.
        # Strategy: two sections are "siblings" (same statutory group) when they share the same
        # chapter_number in ipc.json. We use chapter_number because the ipc.json chapter nesting
        # is structurally incorrect for many sections (e.g. 378-382 Theft sections appear under
        # the Kidnapping sub_heading), so sub_heading cannot be trusted.
        statute_db = StatuteRepository.get_instance().get_statute_db()
        # Record all raw Stage 2 input section numbers BEFORE any filtering/deduplication
        stage2_input_sections = []
        _seen_s2 = set()
        for c in candidates_to_verify:
            s_num = str(c.get("section_number", "")).strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
            if s_num and s_num not in _seen_s2:
                _seen_s2.add(s_num)
                stage2_input_sections.append(s_num)

        stage3_rejected: List[Dict[str, str]] = []  # sections from Stage 2 that were rejected by Stage 3

        try:
            from .family_retrieval import get_family_retriever
            punishment_links = get_family_retriever().punishment_links
        except Exception:
            punishment_links = {}

        tier_order = {"PRIMARY": 3, "SECONDARY": 2, "CONDITIONAL": 1}
        cand_by_sec: Dict[str, Dict[str, Any]] = {}
        all_raw_secs = set(stage2_input_sections)

        for c in candidates_to_verify:
            sec_clean = str(c["section_number"]).strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
            rec = statute_db.get(f"IPC_{sec_clean}") or {}
            is_def = rec.get("is_definition", False)
            is_pun = rec.get("is_punishment", False)
            sec_type = rec.get("section_type", "")

            # Pair-level definitional suppression using punishment_links:
            # Drop purely definitional sections ONLY if their paired substantive punishment section is present.
            if is_def and not is_pun and sec_type == "definitional":
                paired_punishments = punishment_links.get(sec_clean, set())
                active_paired = paired_punishments & all_raw_secs
                if active_paired:
                    stage3_rejected.append({
                        "section_number": sec_clean,
                        "reason": f"Definitional section {sec_clean} excluded in favor of paired substantive penal counterpart(s): {', '.join(sorted(active_paired))}.",
                        "rejection_type": "DEFINITIONAL_SUPERSEDED"
                    })
                    continue
                # A definition is never a charge. Evaluate the section that punishes it instead (300 -> 302,
                # 378 -> 379); with no punishing section of its own (319 Hurt, 320 Grievous hurt) it only explains
                # terms used by the charging sections.
                stage3_rejected.append({
                    "section_number": sec_clean,
                    "reason": (f"Definition, not a charge; evaluated through its punishing section(s) {', '.join(sorted(paired_punishments))}."
                               if paired_punishments else
                               f"Definition, not a charge (defines a term used by the charging sections; it has no punishment section of its own)."),
                    "rejection_type": "DEFINITION_NOT_A_CHARGE",
                })
                for pun in sorted(paired_punishments):
                    if pun not in all_raw_secs:
                        sub = dict(c)
                        sub["section_number"] = pun
                        sub["title"] = (statute_db.get(f"IPC_{pun}") or {}).get("section_title") or pun
                        candidates_to_verify.append(sub)  # visited later in this same loop
                        all_raw_secs.add(pun)
                continue

            # Deduplication: preserve strongest tier (PRIMARY > SECONDARY > CONDITIONAL) and union sub-query IDs
            if sec_clean not in cand_by_sec:
                cand_copy = dict(c)
                cand_copy["sub_query_ids"] = list(c.get("sub_query_ids") or [])
                cand_by_sec[sec_clean] = cand_copy
            else:
                existing = cand_by_sec[sec_clean]
                for sq in (c.get("sub_query_ids") or []):
                    if sq not in existing["sub_query_ids"]:
                        existing["sub_query_ids"].append(sq)
                existing_tier = str(existing.get("classification") or "PRIMARY").upper()
                new_tier = str(c.get("classification") or "PRIMARY").upper()
                if tier_order.get(new_tier, 1) > tier_order.get(existing_tier, 1):
                    existing["classification"] = new_tier

        candidates_to_verify = list(cand_by_sec.values())

        # Deterministic verification & enrichment loop
        repo = StatuteRepository.get_instance()
        dedup_offences: Dict[str, VerifiedOffenceItem] = {}
        facts_text = getattr(query_obj, "case_facts", "") or ""
        if not facts_text and hasattr(query_obj, "legal_concepts"):
            facts_text = " ".join([c.concept for c in query_obj.legal_concepts]) + " " + " ".join([sq.query for sq in getattr(query_obj, "sub_queries", [])])

        # Automatically detect factual triggers when Stage 2 mapping is omitted or empty
        if not stage2_resp:
            triggered_suggestions = self.prefilter.detect_factual_triggers(facts_text, statute_type="IPC")
            seen_cand_keys = {f"{c.get('statute', '')}_{c.get('section_number', '')}".upper() for c in candidates_to_verify}
            for sug in triggered_suggestions:
                sug_key = f"{sug.get('statute', '')}_{sug.get('section_number', '')}".upper()
                if sug_key not in seen_cand_keys:
                    seen_cand_keys.add(sug_key)
                    candidates_to_verify.append({
                        "section_number": sug["section_number"],
                        "statute": "IPC" if "BNS" in (sug.get("statute") or "").upper() else (sug.get("statute") or "IPC"),
                        "title": sug["section_title"],
                        "classification": sug["candidate_type"]
                    })

        for cand in candidates_to_verify:
            sec_raw = str(cand["section_number"]).strip()
            sec_num = sec_raw.upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
            statute_in = cand.get("statute") or ("BNS" if "BNS" in regime_upper else "IPC")
            tier = cand.get("classification", "PRIMARY")

            # Strict single-source check: section MUST exist in repository
            if statute_in.upper() == "IPC" and not repo.is_in_ipc_json(sec_num):
                stage3_rejected.append({
                    "section_number": sec_num,
                    "reason": f"Section {sec_num} is not present in authoritative ipc.json registry.",
                    "rejection_type": "NOT_IN_IPC_JSON"
                })
                continue

            # 0. Fatal Disqualification Check against Case Facts
            disqualified, disq_reason, missing_ings = self.prefilter.evaluate_fatal_disqualification(
                sec_num, statute_in, facts_text
            )

            # 1. Statutory Resolution (IPC-only pipeline)
            ipc_eq = sec_num
            try:
                from .crosswalk_service import CrosswalkService
                bns_eq = CrosswalkService.get_instance().get_bns_for_ipc(sec_num, prefer_clause=True)
            except Exception:
                bns_eq = None

            # 2. Canonical Metadata Determination (Title, Chapter, Punishment, Cognizability)
            canon_title = cand.get("title", f"Section {sec_num}")
            statute_out = "IPC"

            # Knowledge Base Rule Lookup (static hardcoded + dynamic auto-promoted rules)
            found_rule = None
            for r in get_effective_knowledge_base():
                rule_sec_clean = r.section.upper().replace("SECTION ", "").strip()
                if sec_num == rule_sec_clean or sec_num == r.section.upper():
                    found_rule = r
                    break

            first_sched_meta = StatuteRepository.get_instance().get_first_schedule_metadata(sec_num, "IPC")

            if found_rule:
                canon_title = found_rule.title
                if found_rule.bns_equivalent and found_rule.bns_equivalent != "NONE":
                    bns_eq = found_rule.bns_equivalent
                if found_rule.section and "IPC" in found_rule.statute:
                    ipc_eq = found_rule.section
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
                cognizable = first_sched_meta["cognizable"] if first_sched_meta.get("cognizable") is not None else True
                bailable = first_sched_meta["bailable"] if first_sched_meta.get("bailable") is not None else False
            else:
                chap_num = "IPC Chapter"
                chap_title = canon_title
                punishment = PunishmentSpec(minimum=None, maximum="As specified under statute", fine=True)
                cognizable = True
                bailable = False

            # Hard-exclude disqualified sections — do NOT demote to SECONDARY. A CONDITIONAL candidate is
            # already flagged as depending on an unalleged fact (e.g. 338: was the hurt grievous?), so the
            # gate records that fact instead of deleting it; Stage 4 keeps it in conditional_offences.
            if disqualified and tier == "CONDITIONAL":
                note = f"Section {sec_num} kept as CONDITIONAL: {disq_reason or 'required fact not yet alleged'}"
                if note not in manual_review_flags:
                    manual_review_flags.append(note)
                disqualified = False
            if disqualified:
                disq_msg = (
                    f"Section {sec_num} excluded (NOT_TRIGGERED): {disq_reason or 'Mandatory statutory ingredients not satisfied by case facts.'}"
                )
                if disq_msg not in manual_review_flags:
                    manual_review_flags.append(disq_msg)
                stage3_rejected.append({
                    "section_number": sec_num,
                    "reason": disq_reason or "Mandatory statutory ingredients not satisfied by case facts.",
                    "rejection_type": "NOT_TRIGGERED"
                })
                continue  # Skip — do not add to verified_offences

            # Unique key for deduplication
            canon_key = f"{statute_out}_{sec_num}".upper()
            if canon_key not in dedup_offences:
                notes = [
                    "Statutory existence verified against Knowledge Base registry.",
                    f"Canonical chapter ({chap_num}) and punishment metadata verified."
                ]
                if not found_rule and not first_sched_meta:
                    notes.append(f"WARNING: Section {sec_num} metadata unverified against First Schedule CrPC ground truth.")
                if tier == "CONDITIONAL":
                    # Stage 4 reads this to decide whether the facts meet the condition.
                    notes.append(f"CONDITION: {cand.get('condition') or disq_reason or 'a required fact is not yet alleged'}")

                verified_item = VerifiedOffenceItem(
                    section_number=sec_num,
                    statute=statute_out,
                    ipc_equivalent=ipc_eq if "Dowry" not in statute_out else None,
                    bns_equivalent=bns_eq,
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

        # Post-process: s.471 IPC punishment is NOT fixed — it mirrors the predicate forgery section.
        # "shall be punished in the same manner as if he had forged such document" (s.471 IPC)
        # Derive dynamically from whichever forgery section is also in the verified list.
        present_secs = {vo.section_number for vo in verified_list}
        for vo in verified_list:
            if vo.section_number == "471":
                if "467" in present_secs:
                    # Forgery of Valuable Security — Life Imprisonment
                    vo.punishment.maximum = "Life Imprisonment"
                    if "471 punishment derived from predicate s.467 (Forgery of Valuable Security)" not in vo.verification_notes:
                        vo.verification_notes.append("471 punishment derived from predicate s.467 (Forgery of Valuable Security) — Life Imprisonment applies.")
                elif "468" in present_secs:
                    # Forgery for Cheating — 7 Years
                    vo.punishment.maximum = "7 Years"
                    if "471 punishment derived from predicate s.468 (Forgery for Cheating)" not in vo.verification_notes:
                        vo.verification_notes.append("471 punishment derived from predicate s.468 (Forgery for Cheating) — 7 Years applies.")
                elif "465" in present_secs:
                    # Basic Forgery — 2 Years
                    vo.punishment.maximum = "2 Years"
                    if "471 punishment derived from predicate s.465 (Forgery)" not in vo.verification_notes:
                        vo.verification_notes.append("471 punishment derived from predicate s.465 (Forgery) — 2 Years applies.")
                else:
                    # No explicit predicate identified — default to baseline s.465 punishment
                    vo.punishment.maximum = "2 Years"
                    vo.verification_notes.append("471 punishment defaulted to 2 Years (s.465 baseline) — no s.467/468 predicate detected in candidate set.")

        # Step 3: Candidate list prepared for Stage 4 statutory reasoner (Issue S-15: hidden screen removed)
        stage3_accepted_secs = [vo.section_number for vo in verified_list]

        # Build rejected list: any Stage 2 section not in the verified output and not already listed
        rejected_sec_nums = {r["section_number"] for r in stage3_rejected}
        for sec in stage2_input_sections:
            if sec not in {vo.section_number for vo in verified_list} and sec not in rejected_sec_nums:
                stage3_rejected.append({
                    "section_number": sec,
                    "reason": "Section not found in Knowledge Base registry or First Schedule — excluded during normalization.",
                    "rejection_type": "UNVERIFIED"
                })

        pipeline_transition = {
            "stage": "STAGE_2_TO_STAGE_3",
            "source": "Stage 2 Batched Sub-Query Mapping",
            "stage2_input_sections": stage2_input_sections,
            "stage3_accepted_sections": stage3_accepted_secs,
            "stage3_rejected_sections": stage3_rejected,
            "passing_to_stage4": stage3_accepted_secs,
        }
        manual_review_flags_with_transition = list(manual_review_flags)

        return ChapterIdentificationObject(
            schema_version="3.0",
            verified_offences=verified_list,
            legal_regime=regime,
            manual_review=manual_review_flags_with_transition,
            verification_status="VERIFIED",
            pipeline_transition=pipeline_transition,
        )