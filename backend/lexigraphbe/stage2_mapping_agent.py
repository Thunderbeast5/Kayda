"""
Stage 2 Sub-Query to Chapter Candidate Mapping Agent.
Maps decomposed sub-queries from Stage 1 to candidate statutory chapters and sections
using local StatuteClassifierPrefilter candidates in ONE single batched LLM request.

Key design principle: definition-grounded reasoning.
Every candidate sent to the LLM is enriched with its actual statutory definition text
so the LLM reasons from what the law says, not from section title keywords.
A scope check (also definition-grounded, not hardcoded) pre-screens candidates whose
definitions categorically exclude the case facts before they ever reach the LLM.

Model: gpt-4o-mini (MODEL_STAGE2).
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE2
from .classifier_prefilter import StatuteClassifierPrefilter
from .prompts import STAGE2_MAPPING_SYSTEM_PROMPT, STAGE2_MAPPING_USER_PROMPT_TEMPLATE
from .batch_utils import Stage2BatchedMappingResponse
from .schemas.stage1 import LegalQueryObject
from .statute_repository import StatuteRepository


# Candidates at or above this score are high-confidence hits where the prefilter
# is almost certainly correct. Scope check runs only below this threshold —
# these are the borderline candidates where wrong sections slip through.
_SCOPE_CHECK_SCORE_CEILING = 0.90

# Maximum chars of statutory definition to include in the LLM prompt per candidate.
# 1500 chars allows full statutory text + explanation + illustrations from ipc.json
# while keeping token budget reasonable for 15-20 candidates.
_DEFINITION_TRUNCATION_CHARS = 1500


class Stage2SubQueryMappingAgent:
    """
    Stage 2 Agent mapping sub-queries to candidate statutory chapters and sections.
    Integrates local StatuteClassifierPrefilter (0 API calls) with batched LLM request.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        prefilter: Optional[StatuteClassifierPrefilter] = None,
    ):
        self._llm = llm
        self.prefilter = prefilter or StatuteClassifierPrefilter()

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE2)
        return self._llm

    # ------------------------------------------------------------------
    # Statutory definition enrichment
    # ------------------------------------------------------------------

    def _enrich_candidates_with_statutory_text(
        self,
        candidates: List[Dict[str, Any]],
        statute_type: str,
    ) -> List[Dict[str, Any]]:
        """
        Attaches the actual statutory definition text to each candidate entry.

        This is the core of definition-grounded reasoning. Instead of giving the
        LLM only a section number and title (a few words), we give it the actual
        legal text of the section so it can reason about scope — whether the
        definition's essential requirements can be satisfied by the case facts.

        Works for any section in the database. No hardcoding needed.
        """
        repo = StatuteRepository.get_instance()
        enriched = []

        for candidate in candidates:
            sec_num = candidate.get("section_number", "")
            statute = candidate.get("statute", statute_type)
            enriched_candidate = dict(candidate)

            details = repo.get_section_details(sec_num, statute)
            definition = repo.get_statutory_definition(sec_num, statute)
            if definition:
                enriched_candidate["statutory_definition"] = (
                    definition[:_DEFINITION_TRUNCATION_CHARS]
                    if len(definition) > _DEFINITION_TRUNCATION_CHARS
                    else definition
                )
            else:
                enriched_candidate["statutory_definition"] = None

            if details and details.get("key_elements"):
                enriched_candidate["definitional_prerequisites"] = details["key_elements"]

            enriched.append(enriched_candidate)

        return enriched

    # ------------------------------------------------------------------
    # Definition-grounded scope check
    # ------------------------------------------------------------------

    def _check_scope_compatibility(
        self,
        section_number: str,
        statute: str,
        facts_text: str,
    ) -> Tuple[bool, str]:
        """
        Asks the LLM to read the section's own statutory definition and decide
        whether the case facts can possibly satisfy it.

        Returns:
            (is_compatible: bool, reason: str)

        This is definition-grounded, not hardcoded. It works for any section
        in the database without case-specific rules. The LLM reads the actual
        legal text and determines whether the facts fit the definition's scope.

        If no definition is available in the database, the candidate passes
        through unchecked — fail-safe, not fail-fast.
        """
        repo = StatuteRepository.get_instance()
        definition = repo.get_statutory_definition(section_number, statute)

        if not definition:
            # No definition on record — don't block, let the mapping LLM handle it
            return True, "No statutory definition available; passing through scope check."

        prompt = f"""You are a statutory scope checker. Your only job is to decide whether
case facts can POSSIBLY satisfy the essential scope of a section's statutory definition.

STATUTORY DEFINITION OF SECTION {section_number} ({statute}):
\"\"\"{definition}\"\"\"

CASE FACTS:
\"\"\"{facts_text[:800]}\"\"\"

A section is NOT compatible if its statutory definition requires a person, relationship,
or circumstance that is entirely and categorically absent from the case facts. Examples:
- Definition says "being indebted" or "to prevent distribution among creditors"
  but facts involve no debt or creditor relationship.
- Definition says "property of a person deceased" but the property owner is alive.
- Definition says "public servant" or "banker" or "agent" but accused is a private individual.
- Definition says "husband or relative of husband" but parties are not in a matrimonial relationship.

IMPORTANT: Intent and mens rea CAN be inferred from conduct described in facts.
- If facts describe "fraudulent deed", "dishonest transfer", "forged documents", this 
  implies intent to deceive/cheat even if not explicitly stated.
- If facts describe "struck with weapon", "knowing injuries were likely", this implies
  intent to cause harm even if not explicitly stated.
- Do NOT reject sections merely because intent is not EXPLICITLY stated word-for-word.

A section IS compatible if the facts could plausibly satisfy the definition's scope
even if not all ingredients are proven yet. Doubt favours compatibility — only mark
incompatible when the scope exclusion is categorical and unambiguous.

Respond ONLY with this JSON (no other text):
{{
  "compatible": true or false,
  "reason": "one sentence citing the specific language in the definition that confirms or excludes compatibility"
}}"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            text = response.content if hasattr(response, "content") else str(response)
            result = extract_json_from_text(text)
            compatible = bool(result.get("compatible", True))
            reason = result.get("reason", "Scope check completed.")
            return compatible, reason
        except Exception as e:
            # Never let scope check break the pipeline — fail open
            return True, f"Scope check encountered an error ({e}); passing through."

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        correction_feedback: Optional[str] = None,
    ) -> Stage2BatchedMappingResponse:
        """
        Runs Stage 2 Batched Sub-Query Mapping on LegalQueryObject.

        Args:
            legal_query: Verified LegalQueryObject from Stage 1.
            correction_feedback: Feedback from verifier if retrying.

        Returns:
            Stage2BatchedMappingResponse instance.
        """
        if isinstance(legal_query, LegalQueryObject):
            query_obj = legal_query
            query_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            query_obj = LegalQueryObject.model_validate(legal_query)
            query_json_str = json.dumps(legal_query, indent=2)
        else:
            query_obj = LegalQueryObject.model_validate(json.loads(str(legal_query)))
            query_json_str = str(legal_query)

        # Step 1: Extract combined facts text from LegalQueryObject
        facts_text_parts = []
        if query_obj.important_facts:
            facts_dict = query_obj.important_facts.model_dump()
            for v in facts_dict.values():
                if isinstance(v, str) and v:
                    facts_text_parts.append(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str) and item:
                            facts_text_parts.append(item)
        for concept_item in query_obj.legal_concepts:
            if concept_item.concept:
                facts_text_parts.append(concept_item.concept)
        for sq in query_obj.sub_queries:
            facts_text_parts.append(sq.query)
            if sq.concept:
                facts_text_parts.append(sq.concept)
        if hasattr(query_obj, "case_summary") and query_obj.case_summary:
            facts_text_parts.append(query_obj.case_summary)
        facts_text = " ".join(facts_text_parts)

        regime = query_obj.legal_regime or "IPC + CrPC"
        regime_upper = regime.upper()
        regime_was_explicit = query_obj.legal_regime is not None
        
        if "BNS" in regime_upper or "BNSS" in regime_upper:
            statute_type = "BNS"
        else:
            statute_type = "IPC"

        # Step 2: Run local StatuteClassifierPrefilter (0 API calls)
        prefiltered_matches = []
        for concept_item in query_obj.legal_concepts:
            if concept_item.concept:
                matches = self.prefilter.prefilter_candidates(
                    query_text=concept_item.concept,
                    statute_type=statute_type,
                    top_k=10,
                )
                prefiltered_matches.extend(matches)

        # Run prefilter for each sub-query text and concept so every sub-query gets relevant candidate sections
        for sq in query_obj.sub_queries:
            if sq.query:
                matches = self.prefilter.prefilter_candidates(
                    query_text=sq.query,
                    statute_type=statute_type,
                    top_k=10,
                )
                prefiltered_matches.extend(matches)
            if sq.concept:
                matches = self.prefilter.prefilter_candidates(
                    query_text=sq.concept,
                    statute_type=statute_type,
                    top_k=10,
                )
                prefiltered_matches.extend(matches)

        # Step 3: Detect factual triggers
        trigger_suggestions = self.prefilter.detect_factual_triggers(
            facts_text=facts_text,
            statute_type=statute_type,
        )

        # Step 4: Deduplicate and evaluate fatal disqualification (prefilter-level)
        dedup_dict: Dict[str, Dict[str, Any]] = {}
        for m in prefiltered_matches:
            statute_str = getattr(m, "statute", getattr(m, "statute_type", "IPC"))
            sec_num = getattr(m, "section_number", "")
            title_str = getattr(m, "title", getattr(m, "section_title", ""))
            chap_str = getattr(m, "chapter", getattr(m, "chapter_name", ""))
            score_val = getattr(m, "score", 0.0)

            is_not_triggered, elim_reason, missing_mands = self.prefilter.evaluate_fatal_disqualification(
                sec_num, statute_str, facts_text
            )

            k = f"{statute_str}_{sec_num}"
            if k not in dedup_dict or score_val > dedup_dict[k]["score"]:
                dedup_dict[k] = {
                    "statute": statute_str,
                    "section_number": sec_num,
                    "section_title": title_str,
                    "chapter_name": chap_str,
                    "score": round(score_val, 4),
                    "not_triggered": is_not_triggered,
                    "not_triggered_reason": elim_reason,
                    "missing_mandatory_ingredients": missing_mands,
                }

        for ts in trigger_suggestions:
            k = f"{ts['statute']}_{ts['section_number']}"
            if k not in dedup_dict:
                dedup_dict[k] = {
                    "statute": ts["statute"],
                    "section_number": ts["section_number"],
                    "section_title": ts["section_title"],
                    "chapter_name": "Suggested Statutory Chapter",
                    "score": 0.85,
                    "suggested_tier": ts["candidate_type"],
                    "trigger_note": ts["trigger"],
                    "not_triggered": False,
                    "not_triggered_reason": None,
                }

        # Step 5: Definition-grounded scope check on borderline candidates.
        #
        # Only runs on candidates that:
        #   (a) are not already flagged not_triggered by the prefilter, AND
        #   (b) have a score below _SCOPE_CHECK_SCORE_CEILING
        #
        # High-confidence candidates (score >= ceiling) are assumed correct —
        # running scope check on them would add latency for no benefit.
        #
        # This replaces all hardcoded keyword rules in the verifier. A section
        # whose definition categorically excludes the facts is flagged here,
        # regardless of which section it is, without needing a case-specific rule.
        for k, candidate in dedup_dict.items():
            if candidate.get("not_triggered"):
                continue  # Already disqualified by prefilter
            if candidate.get("score", 1.0) >= _SCOPE_CHECK_SCORE_CEILING:
                continue  # High-confidence hit — trust the prefilter

            sec_num = candidate["section_number"]
            statute = candidate["statute"]
            compatible, reason = self._check_scope_compatibility(
                section_number=sec_num,
                statute=statute,
                facts_text=facts_text,
            )
            if not compatible:
                candidate["not_triggered"] = True
                candidate["not_triggered_reason"] = (
                    f"Definition-grounded scope check: {reason}"
                )

        # Step 6: Split candidates into active and not_triggered.
        # Only active candidates get enriched with statutory text and sent to the LLM.
        # not_triggered sections are kept separately for transparency in the final output.
        active_candidates = [c for c in dedup_dict.values() if not c.get("not_triggered")]
        not_triggered_candidates = [c for c in dedup_dict.values() if c.get("not_triggered")]

        # Enrich active candidates with their statutory definition.
        # The LLM uses this text to reason about whether facts satisfy the section —
        # not just whether the title keyword matches.
        enriched_active_candidates = self._enrich_candidates_with_statutory_text(
            active_candidates,
            statute_type,
        )

        prefilter_json_str = json.dumps(enriched_active_candidates, indent=2)

        feedback_section = ""
        if correction_feedback:
            feedback_section = (
                f"\nATTENTION - PREVIOUS STAGE 2 MAPPING AUDIT FEEDBACK:\n{correction_feedback}\n"
            )

        user_prompt = STAGE2_MAPPING_USER_PROMPT_TEMPLATE.format(
            legal_query_json=query_json_str,
            prefilter_candidates_json=prefilter_json_str,
            correction_feedback_section=feedback_section,
        )

        messages = [
            SystemMessage(content=STAGE2_MAPPING_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        extracted_dict = extract_json_from_text(response_text)

        mapping_response = Stage2BatchedMappingResponse.model_validate(extracted_dict)
        
        # Validation: Remove hallucinated sections and restrict strictly to ipc.json
        repo = StatuteRepository.get_instance()
        valid_section_numbers = set()
        for c in enriched_active_candidates:
            sec = c.get("section_number", "")
            if repo.is_in_ipc_json(sec) or repo.is_in_bnss_json(sec):
                valid_section_numbers.add(sec)
        for c in not_triggered_candidates:
            sec = c.get("section_number", "")
            if repo.is_in_ipc_json(sec) or repo.is_in_bnss_json(sec):
                valid_section_numbers.add(sec)
        
        # Filter each mapping to remove non-ipc.json / hallucinated sections
        if valid_section_numbers:
            for mapping in mapping_response.mappings:
                # Filter primary candidates
                mapping.primary_candidate_sections = [
                    s for s in mapping.primary_candidate_sections
                    if s.section_number in valid_section_numbers
                ]
                # Filter secondary candidates
                mapping.secondary_candidate_sections = [
                    s for s in mapping.secondary_candidate_sections
                    if s.section_number in valid_section_numbers
                ]
                # Filter conditional candidates
                mapping.conditional_candidate_sections = [
                    s for s in getattr(mapping, "conditional_candidate_sections", [])
                    if s.section_number in valid_section_numbers
                ]
                # Filter not_triggered sections
                mapping.not_triggered_sections = [
                    s for s in mapping.not_triggered_sections
                    if s.section_number in valid_section_numbers
                ]
                # Update candidate_sections list
                mapping.candidate_sections = [
                    s for s in mapping.candidate_sections
                    if s in valid_section_numbers
                ]

        # Factual Trigger Recovery: Guarantee that all high-confidence factual triggers
        # (e.g. Section 468, 467, 471, 420, 423) identified from facts are present in at least one mapping
        from .batch_utils import SectionMappingCandidate
        all_mapped_sections = set()
        for m in mapping_response.mappings:
            for s in m.primary_candidate_sections:
                all_mapped_sections.add(s.section_number)
            for s in m.secondary_candidate_sections:
                all_mapped_sections.add(s.section_number)
            for s in getattr(m, "conditional_candidate_sections", []):
                all_mapped_sections.add(s.section_number)
            for s in m.not_triggered_sections:
                all_mapped_sections.add(s.section_number)

        for ts in trigger_suggestions:
            ts_sec = ts.get("section_number")
            # If a triggered section was not mapped to ANY subquery and not marked as not_triggered
            if ts_sec and ts_sec not in all_mapped_sections and ts_sec in valid_section_numbers:
                # Find the most relevant subquery using generic word token overlap
                ts_title = ts.get("section_title", "")
                ts_trig = ts.get("trigger", "")
                ts_tokens = set(re.findall(r"\w+", (ts_title + " " + ts_trig).lower())) - {"section", "ipc", "bns", "the", "and", "for", "of", "in", "to", "a"}
                best_score = 0
                target_mapping = None
                for m in mapping_response.mappings:
                    sq_tokens = set(re.findall(r"\w+", (m.sub_query_text or "").lower()))
                    overlap = len(ts_tokens & sq_tokens)
                    if overlap > best_score:
                        best_score = overlap
                        target_mapping = m

                if target_mapping is None and mapping_response.mappings:
                    target_mapping = mapping_response.mappings[0]

                if target_mapping:
                    cand = SectionMappingCandidate(
                        section_number=ts_sec,
                        section_title=ts.get("section_title", f"Section {ts_sec}"),
                        statute=ts.get("statute", "IPC"),
                        candidate_type=ts.get("candidate_type", "CONDITIONAL"),
                        score=0.85,
                        score_breakdown={
                            "ingredient_match": 0.85,
                            "classifier_score": 0.85,
                            "keyword_match": 0.85,
                            "semantic_similarity": 0.85,
                        },
                        ingredients_matched=[f"Factual trigger detected: {ts.get('trigger', '')}"],
                        missing_facts=[f"Requires full factual verification under Section {ts_sec}"],
                        relevance_reasoning=f"Recovered from factual trigger detection: {ts.get('trigger', '')}",
                    )
                    if not hasattr(target_mapping, "conditional_candidate_sections") or target_mapping.conditional_candidate_sections is None:
                        target_mapping.conditional_candidate_sections = []
                    target_mapping.conditional_candidate_sections.append(cand)
                    if ts_sec not in target_mapping.candidate_sections:
                        target_mapping.candidate_sections.append(ts_sec)
                    all_mapped_sections.add(ts_sec)

        return mapping_response