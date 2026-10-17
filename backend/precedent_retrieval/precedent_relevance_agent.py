"""
Precedent Relevance Evaluation Agent.

Implements LLM-based role-specific relevance evaluation with full case metadata enrichment.
Uses a reasoner + verifier architecture for robust precedent analysis.

Role context (prosecution/defence goals, position, focus) is derived at runtime from the
CaseRetrievalProfile built out of Stage 4 output — NOT hardcoded for any particular domain.
This means the prompts work correctly for medical negligence, property fraud, corruption,
matrimonial, or any other matter the pipeline handles.
"""

import json
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from lexigraphbe.config import get_llm
from .precedent_retrieval import PrecedentCandidate
from .schemas import (
    CaseRetrievalProfile,
    RoleSpecificRelevanceEvaluation,
    RoleSpecificPrecedentItem,
    MatchedStatuteItem,
    PropositionItem,
    CompactPrecedentSummary,
)

VALID_RELEVANCE_TYPES = {
    "DIRECTLY_SUPPORTING",
    "DIRECTLY_OPPOSING",
    "STRONGLY_SUPPORTING",
    "STRONGLY_OPPOSING",
    "DISTINGUISHABLE",
    "BACKGROUND",
    "LOW_RELEVANCE",
}


class PrecedentRelevanceReasonerAgent:
    """LLM reasoner that evaluates precedent relevance for prosecution or defense."""

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self.llm = llm or get_llm(temperature=0.1)

    def _build_enriched_case_context(self, candidate: PrecedentCandidate) -> str:
        """Build enriched case context with ALL metadata for LLM evaluation."""
        lines = [
            ("RETRIEVED_FOR_PRINCIPLE: matched on legal issue, not on facts"
             if getattr(candidate, "channel", "case") == "principle"
             else "RETRIEVED_FOR_FACTS_AND_STATUTES"),
            f"CASE: {candidate.case_name}",
            f"CASE ID: {candidate.case_id}",
            f"COURT: {candidate.court}",
            f"DECIDED ON: {candidate.decided_on}",
            f"PROCEDURAL STAGE (corpus tag): {candidate.procedural_stage} | Inferred stage: {candidate.inferred_stage}",
            "",
            "MATCHED STATUTES (Statutory Overlap with Input Case):"
        ]

        for match in candidate.matched_statutes:
            match_type = match.get("match_type", "exact")
            marker = "✓" if match_type == "exact" else "≈"
            lines.append(
                f"  {marker} {match['judgment_act']} Section {match['judgment_section']} "
                f"[{match.get('how_used', 'N/A')}] ({match_type})"
            )
            if match.get("note"):
                lines.append(f"     Note: {match['note']}")

        lines.extend([
            "",
            f"ALL STATUTES IN THIS CASE ({len(candidate.statutes)}):"
        ])

        for statute in candidate.statutes:
            lines.append(f"  - {statute.get('act')} Section {statute.get('section')} [{statute.get('how_used')}]")
            if statute.get("note"):
                lines.append(f"    Note: {statute['note']}")

        lines.extend([
            "",
            "ABSTRACT FACTS:",
            candidate.abstract_facts,
            "",
            "DISPOSITION (Final Outcome):",
            candidate.disposition,
            ""
        ])

        if candidate.issues:
            lines.append(f"ISSUES DECIDED ({len(candidate.issues)}):")
            for i, issue in enumerate(candidate.issues, 1):
                lines.append(f"{i}. Question: {issue.get('question', '')}")
                lines.append(f"   Answer: {issue.get('short_answer', '')}")
            lines.append("")

        if candidate.propositions:
            lines.append(f"LEGAL PROPOSITIONS ({len(candidate.propositions)}):")
            for prop in candidate.propositions:
                prop_id = prop.get("id", "")
                text = prop.get("text", "")
                favors = prop.get("favors", "neutral").upper()
                is_holding = prop.get("is_holding", False)
                kind = prop.get("kind", "")
                holding_marker = "[BINDING HOLDING]" if is_holding else (f"[{kind}]" if kind else "")
                lines.append(f"  [{prop_id}] {holding_marker} FAVORS: {favors}")
                lines.append(f"       {text}")
            lines.append("")

        if candidate.authorities:
            lines.append(f"AUTHORITIES CITED ({len(candidate.authorities)}):")
            for auth in candidate.authorities[:5]:
                lines.append(f"  - {auth.get('name', '')} ({auth.get('citation', '')}) [{auth.get('treatment', '')}]")
            if len(candidate.authorities) > 5:
                lines.append(f"  ... and {len(candidate.authorities) - 5} more")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _build_role_context(role: str, profile: Optional[CaseRetrievalProfile]) -> Dict[str, Any]:
        """
        Derive role-specific context from the CaseRetrievalProfile.

        This replaces the old hardcoded property-fraud strings so the same code works
        for any case type: medical negligence, corruption, matrimonial, etc.
        When no profile is supplied a generic bail-proceeding fallback is used.
        """
        if profile is None:
            # Generic fallback — no domain assumptions
            if role == "prosecution":
                return {
                    "position": "The PROSECUTION seeks to establish a prima facie case and oppose bail.",
                    "goals": [
                        "Establish prima facie case on the charged offences",
                        "Demonstrate gravity of the alleged conduct",
                        "Argue for custodial interrogation if required by the investigation",
                        "Show risk of evidence tampering or flight",
                    ],
                    "focus": "How does this precedent support the PROSECUTION in opposing bail or establishing the prima facie case?",
                }
            else:
                return {
                    "position": "The DEFENSE seeks bail and challenges the prima facie case.",
                    "goals": [
                        "Secure bail under Article 21 and applicable CrPC / BNSS provisions",
                        "Show cooperation with investigation and absence of flight risk",
                        "Challenge satisfaction of ingredients of the charged offences",
                        "Argue custodial interrogation is unnecessary",
                    ],
                    "focus": "How does this precedent support the DEFENSE in securing bail or challenging the prima facie case?",
                }

        offences_str = ", ".join(profile.offences[:5]) or "the charged offences"
        stage_str = profile.procedural_stage.replace("_", " ")

        if role == "prosecution":
            goals = profile.prosecution_themes[:5] or [
                "Establish prima facie case on the charged offences",
                "Demonstrate gravity warranting denial of bail",
                "Argue custodial interrogation is necessary",
            ]
            position = (
                f"The PROSECUTION seeks to establish prima facie guilt under "
                f"section(s) {offences_str} ({profile.legal_regime}) and oppose {stage_str}."
            )
            fact_str = "; ".join(profile.fact_patterns[:3]) or offences_str
            focus = (
                f"How does this precedent support the PROSECUTION in opposing {stage_str} "
                f"or establishing prima facie guilt for: {fact_str}?"
            )
        else:
            goals = profile.defence_themes[:5] or [
                "Secure bail under Article 21",
                "Show no flight risk and cooperation with investigation",
                "Challenge prima facie satisfaction of ingredients",
                "Argue custodial interrogation is not required",
            ]
            position = (
                f"The DEFENSE seeks {stage_str} and challenges the prima facie case "
                f"under section(s) {offences_str} ({profile.legal_regime})."
            )
            fact_str = "; ".join(profile.fact_patterns[:3]) or offences_str
            focus = (
                f"How does this precedent support the DEFENSE in securing {stage_str} "
                f"or challenging the prima facie case on: {fact_str}?"
            )

        return {"position": position, "goals": goals, "focus": focus}

    def _build_role_specific_prompt(
        self,
        role: str,
        input_case_summary: str,
        input_statutes: List[Dict],
        stage4_details: str,
        enriched_precedent: str,
        retrieval_profile: Optional[CaseRetrievalProfile] = None,
    ) -> str:
        """Build role-specific evaluation prompt derived from the retrieval profile."""
        context = self._build_role_context(role, retrieval_profile)
        goals_text = "\n".join(f"- {g}" for g in context["goals"])

        statute_lines = "\n".join(
            f"- {s.get('act')} Section {s.get('section')}" for s in input_statutes
        ) or "(see stage 4 details)"

        # Build fact-pattern / subject-matter cap guidance from the profile
        if retrieval_profile and retrieval_profile.fact_patterns:
            subject_matter = "; ".join(retrieval_profile.fact_patterns[:4])
            subject_cap_clause = (
                f"SUBJECT MATTER CAP: If the precedent concerns a domain entirely unrelated "
                f"to [{subject_matter}] (e.g. a sexual offence / matrimonial / special-statute "
                f"case when the input case is a different kind of matter), the relevance_type "
                f"is LOW_RELEVANCE regardless of how generally the principle is phrased."
            )
        else:
            subject_cap_clause = (
                "SUBJECT MATTER CAP: If the precedent concerns violence, sexual offences, "
                "matrimonial/dowry disputes, or PMLA/NDPS-type special statutes while the input "
                "case is a different kind of matter, relevance_type is LOW_RELEVANCE regardless "
                "of how generally the principle is phrased."
            )

        return f"""You are a senior legal expert evaluating precedent relevance for the {role.upper()} in an anticipatory bail proceeding in India.

ROLE CONTEXT:
{context['position']}

ROLE GOALS:
{goals_text}

═══════════════════════════════════════════════════════════════════════════════
INPUT CASE (The case you are evaluating precedents FOR)
═══════════════════════════════════════════════════════════════════════════════

CASE SUMMARY:
{input_case_summary}

STATUTES ATTRACTED (from Stage 4 Analysis):
{statute_lines}

STAGE 4 INGREDIENT EVALUATION SUMMARY:
{stage4_details}

═══════════════════════════════════════════════════════════════════════════════
PRECEDENT CASE (Evaluate relevance of THIS case to the {role.upper()})
═══════════════════════════════════════════════════════════════════════════════

{enriched_precedent}

═══════════════════════════════════════════════════════════════════════════════
EVALUATION TASK & STRICT TAXONOMY RULES
═══════════════════════════════════════════════════════════════════════════════

Evaluate this precedent STRICTLY from the {role.upper()}'s perspective:
{context['focus']}

CRITICAL DISTINCTION & ANTI-INFLATION RULES:
- DO NOT INFLATE LABELS: If factual similarity is LOW or the fact patterns clearly do not match
  the input case, you MUST NOT label as STRONGLY_SUPPORTING or DIRECTLY_SUPPORTING.
  Label as BACKGROUND (general principle only) or DISTINGUISHABLE.
- {subject_cap_clause}
- If the candidate is marked RETRIEVED_FOR_PRINCIPLE (different facts, matching legal issue),
  judge it only on whether its holding answers an issue the input actually raises; if it does,
  label SUPPORTING or OPPOSING for the side its holding favours and state which issue; if not, BACKGROUND.
- LEGAL PRINCIPLE MATCH != FACTUAL MATCH. Keep them separate. A case can share a statute but have
  completely different facts (bank fraud vs negligent death, for example); factual similarity must be
  assessed on the actual circumstances, not just the section number.
- STRONGLY_SUPPORTING or DIRECTLY_SUPPORTING requires BOTH strong procedural stage relevance AND
  meaningful factual or subject-matter similarity.
- SUPPORTING vs OPPOSING is strictly RELATIVE to {role.upper()}:
  * DEFENSE: Supporting means helps the accused get bail/relief. Opposing means helps prosecution deny bail.
  * PROSECUTION: Supporting means helps prosecution deny bail/prove guilt. Opposing means helps accused.

You MUST choose relevance_type from this exact taxonomy:
- DIRECTLY_SUPPORTING: Same procedural stage + on-point matching facts + propositions directly supporting {role.upper()}
- DIRECTLY_OPPOSING: Precedent directly cuts against {role.upper()} on same procedural stage and matching facts
- STRONGLY_SUPPORTING: Strong principle alignment AND relevant factual similarity supporting {role.upper()}
- STRONGLY_OPPOSING: Strong principle/holding cutting against {role.upper()}
- DISTINGUISHABLE: Relevant legal issues, but a MATERIAL factual difference lets {role.upper()} avoid the holding
- BACKGROUND: General principles with indirect application (principle only, low factual match)
- LOW_RELEVANCE: Unrelated facts/stage, alien domain, or marginal statutory overlap

Return ONLY valid JSON matching this schema:
{{
  "is_relevant": true,
  "relevance_type": "DIRECTLY_SUPPORTING|DIRECTLY_OPPOSING|STRONGLY_SUPPORTING|STRONGLY_OPPOSING|DISTINGUISHABLE|BACKGROUND|LOW_RELEVANCE",
  "confidence": 0.0-1.0,
  "procedural_match": "HIGH|MODERATE|LOW",
  "factual_similarity_level": "HIGH|MODERATE|LOW",
  "factual_similarity": "detailed assessment separating factual match from legal principle match",
  "legal_principle_alignment": "how principles align with or oppose {role}'s position",
  "statutory_interpretation_value": "value for {role}",
  "procedural_relevance": "relevance of procedural stage",
  "supporting_propositions": ["p1", "p2"],
  "contradicting_propositions": ["p3"],
  "usage_recommendation": "how {role} should use this precedent",
  "key_quotes": ["quote1"],
  "distinguishing_factors": ["factor1"],
  "use_for": [
    "specific argument 1 for {role}",
    "specific argument 2 for {role}"
  ],
  "against_role": [
    "point or vulnerability the opponent can argue from this case"
  ]
}}"""

    def evaluate_precedent_for_role(
        self,
        role: str,
        candidate: PrecedentCandidate,
        input_case_summary: str,
        input_statutes: List[Dict],
        stage4_summary: str,
        retrieval_profile: Optional[CaseRetrievalProfile] = None,
    ) -> Dict[str, Any]:
        """Evaluate a precedent candidate for a specific role."""
        enriched_case = self._build_enriched_case_context(candidate)
        prompt = self._build_role_specific_prompt(
            role, input_case_summary, input_statutes,
            stage4_summary, enriched_case,
            retrieval_profile=retrieval_profile,
        )

        messages = [
            SystemMessage(content="You are a senior legal expert specializing in criminal law and bail proceedings in India."),
            HumanMessage(content=prompt)
        ]

        response = self.llm.invoke(messages)
        response_text = response.content.strip()

        try:
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            evaluation = json.loads(response_text)
            evaluation["case_id"] = candidate.case_id
            evaluation["case_name"] = candidate.case_name

            rel_type = str(evaluation.get("relevance_type", "")).strip().upper()
            if rel_type not in VALID_RELEVANCE_TYPES:
                legacy_map = {
                    "STRONGLY_SUPPORTING": "STRONGLY_SUPPORTING",
                    "SUPPORTING": "STRONGLY_SUPPORTING",
                    "DISTINGUISHABLE": "DISTINGUISHABLE",
                    "CONTRADICTORY": "STRONGLY_OPPOSING",
                    "NOT_RELEVANT": "LOW_RELEVANCE"
                }
                evaluation["relevance_type"] = legacy_map.get(rel_type, "BACKGROUND")
            else:
                evaluation["relevance_type"] = rel_type

            return evaluation

        except json.JSONDecodeError as e:
            print(f"[PrecedentRelevanceReasonerAgent] JSON error for {candidate.case_id}: {e}")
            return {
                "case_id": candidate.case_id,
                "case_name": candidate.case_name,
                "is_relevant": False,
                "relevance_type": "LOW_RELEVANCE",
                "confidence": 0.0,
                "factual_similarity": "Error parsing LLM response",
                "legal_principle_alignment": "Error parsing LLM response",
                "statutory_interpretation_value": "Error parsing LLM response",
                "procedural_relevance": "Error parsing LLM response",
                "supporting_propositions": [],
                "contradicting_propositions": [],
                "usage_recommendation": "Manual review required",
                "key_quotes": [],
                "distinguishing_factors": ["LLM evaluation failed"],
                "use_for": [],
                "against_role": []
            }


class PrecedentRelevanceVerifierAgent:
    """Verifier agent that validates precedent relevance evaluations."""

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self.llm = llm or get_llm(temperature=0.0)

    def verify_evaluation(self, role: str, candidate: PrecedentCandidate,
                          evaluation: Dict[str, Any]) -> Dict[str, Any]:
        """Verify a precedent relevance evaluation for quality and consistency."""
        issues = []

        is_relevant = evaluation.get("is_relevant", False)
        relevance_type = evaluation.get("relevance_type", "")

        if is_relevant and relevance_type == "LOW_RELEVANCE":
            pass
        elif not is_relevant and relevance_type in ["DIRECTLY_SUPPORTING", "STRONGLY_SUPPORTING"]:
            issues.append(f"Inconsistency: is_relevant=False but relevance_type='{relevance_type}'")

        confidence = evaluation.get("confidence", 0.0)
        if not (0.0 <= confidence <= 1.0):
            issues.append(f"Invalid confidence: {confidence}")

        valid_prop_ids = {p.get("id") for p in candidate.propositions}
        for key in ("supporting_propositions", "contradicting_propositions"):
            ids = evaluation.get(key, []) or []
            kept = [i for i in ids if i in valid_prop_ids]
            if len(kept) != len(ids):
                evaluation[key] = kept
                evaluation.setdefault("_sanitized", []).append(f"{key}: dropped {sorted(set(ids) - set(kept))}")

        b_fact = float((candidate.score_breakdown or {}).get("fact", 0.0))
        fact_level = str(evaluation.get("factual_similarity_level", "")).upper()
        is_low_fact = fact_level == "LOW" or b_fact < 0.3
        is_principle = getattr(candidate, "channel", "case") == "principle"

        if is_low_fact and not is_principle:
            if relevance_type in ("DIRECTLY_SUPPORTING", "STRONGLY_SUPPORTING"):
                evaluation["relevance_type"] = "BACKGROUND"
                relevance_type = "BACKGROUND"
                evaluation["factual_similarity_level"] = "LOW"
            elif relevance_type in ("DIRECTLY_OPPOSING", "STRONGLY_OPPOSING"):
                evaluation["relevance_type"] = "DISTINGUISHABLE"
                relevance_type = "DISTINGUISHABLE"
                evaluation["factual_similarity_level"] = "LOW"

        verified = len(issues) == 0
        feedback = "Evaluation verified successfully" if verified else f"Found {len(issues)} issues"

        return {
            "verified": verified,
            "issues": issues,
            "feedback": feedback,
            "evaluation": evaluation
        }


class PrecedentRelevanceBatchEvaluator:
    """Batch evaluator for multiple precedent candidates across both roles."""

    def __init__(self, reasoner=None, verifier=None):
        self.reasoner = reasoner or PrecedentRelevanceReasonerAgent()
        self.verifier = verifier or PrecedentRelevanceVerifierAgent()

    def _extract_stage4_summary(self, stage4_result: Dict) -> str:
        """Extract human-readable summary from Stage 4 result."""
        lines = []
        for offence in stage4_result.get("verified_offences", []):
            section = offence.get("section_number", "")
            statute = offence.get("statute", "IPC")
            title = offence.get("title", "")
            strength = offence.get("overall_prima_facie_strength", "")
            lines.append(f"- {statute} Section {section}: {title}")
            lines.append(f"  Prima Facie Strength: {strength}")
        return "\n".join(lines) if lines else "No detailed evaluation available"

    def evaluate_candidates_for_both_roles(
        self,
        candidates: List[PrecedentCandidate],
        input_case_summary: str,
        input_statutes: List[Dict],
        stage4_result: Dict,
        retrieval_profile: Optional[CaseRetrievalProfile] = None,
    ) -> Dict[str, List[Dict]]:
        """
        Evaluate all candidates for both prosecution and defense roles.

        Pass retrieval_profile (from build_case_retrieval_profile) to give the LLM
        evaluator domain-aware role context derived from Stage 4 — not hardcoded strings.
        """
        stage4_summary = self._extract_stage4_summary(stage4_result)
        prosecution_precedents = []
        defense_precedents = []

        print(f"\n[PrecedentRelevanceBatchEvaluator] Evaluating {len(candidates)} candidates...")

        for i, candidate in enumerate(candidates, 1):
            print(f"\n  Candidate {i}/{len(candidates)}: {candidate.case_name}")

            print(f"    -> Evaluating for PROSECUTION...")
            prosecution_eval = self.reasoner.evaluate_precedent_for_role(
                "prosecution", candidate, input_case_summary, input_statutes,
                stage4_summary, retrieval_profile=retrieval_profile,
            )
            prosecution_verification = self.verifier.verify_evaluation(
                "prosecution", candidate, prosecution_eval)

            if prosecution_eval.get("is_relevant", False) and prosecution_eval.get("relevance_type") != "LOW_RELEVANCE":
                p_eval = prosecution_verification.get("evaluation", prosecution_eval)
                prosecution_precedents.append({
                    "candidate": candidate,
                    "evaluation": p_eval,
                    "verification": prosecution_verification
                })
                print(f"       [+] Relevant ({p_eval.get('relevance_type')})")
            else:
                print(f"       [-] Not relevant ({prosecution_eval.get('relevance_type')})")

            print(f"    -> Evaluating for DEFENSE...")
            defense_eval = self.reasoner.evaluate_precedent_for_role(
                "defense", candidate, input_case_summary, input_statutes,
                stage4_summary, retrieval_profile=retrieval_profile,
            )
            defense_verification = self.verifier.verify_evaluation(
                "defense", candidate, defense_eval)

            if defense_eval.get("is_relevant", False) and defense_eval.get("relevance_type") != "LOW_RELEVANCE":
                d_eval = defense_verification.get("evaluation", defense_eval)
                defense_precedents.append({
                    "candidate": candidate,
                    "evaluation": d_eval,
                    "verification": defense_verification
                })
                print(f"       [+] Relevant ({d_eval.get('relevance_type')})")
            else:
                print(f"       [-] Not relevant ({defense_eval.get('relevance_type')})")

        print(f"\n[PrecedentRelevanceBatchEvaluator] Results:")
        print(f"  Prosecution: {len(prosecution_precedents)} relevant precedents")
        print(f"  Defense: {len(defense_precedents)} relevant precedents")

        return {"prosecution": prosecution_precedents, "defense": defense_precedents}

    # Role-utility multipliers: how useful is this precedent TO THIS ROLE?
    # OPPOSING/DISTINGUISHABLE cases are useful adversarially but scored much lower as "for this role"
    # because neither side can "use" a case that cuts against them the way they use supporting cases.
    # This prevents the same case appearing at 9.37 for prosecution AND 10.00 for defence.
    _ROLE_UTILITY_MULTIPLIER = {
        "DIRECTLY_SUPPORTING":  1.20,
        "STRONGLY_SUPPORTING":  1.10,
        "DISTINGUISHABLE":      0.90,  # usable but limited — side can distinguish away the holding
        "BACKGROUND":           0.50,  # general principle only
        "STRONGLY_OPPOSING":    0.30,  # cuts against this role
        "DIRECTLY_OPPOSING":    0.30,  # cuts directly against this role
        "LOW_RELEVANCE":        0.10,
    }

    def _calculate_calibrated_score(self, candidate: PrecedentCandidate, evaluation: Dict[str, Any], role: str) -> float:
        """
        Two-phase scoring:
        1. overall_relevance  — role-agnostic base quality of the case for this matter
                                (stage × fact × statutory fit, weighted)
        2. role_utility_score — overall_relevance × role_utility_multiplier
                                (how useful is it SPECIFICALLY for this role?)

        This means an OPPOSING case that is factually on-point will score high on
        overall_relevance (it IS a relevant case) but low on role_utility (it helps
        the OTHER side, not this one). The final_relevance_score uses role_utility_score
        so sorting and selection reflect role utility, not just generic relevance.
        """
        breakdown = candidate.score_breakdown or {}
        stage_sim = float(breakdown.get("stage", 0.5))
        fact_sim = float(breakdown.get("fact", 0.3))
        stat_sim = float(breakdown.get("statutory", 0.5))

        rel_type = str(evaluation.get("relevance_type", "BACKGROUND")).upper()
        llm_conf = float(evaluation.get("confidence", 0.8))
        fact_level = str(evaluation.get("factual_similarity_level", "")).upper()

        # Reconcile LLM factual assessment with retrieval score
        # (LLM may have better factual context than BM25 alone)
        if fact_level == "HIGH":
            fact_sim = max(fact_sim, 0.6)
        elif fact_level == "MODERATE":
            fact_sim = max(fact_sim, 0.35)
        elif fact_level == "LOW":
            fact_sim = min(fact_sim, 0.4)

        # Phase 1: role-agnostic base quality — how relevant is this case to the MATTER?
        overall_relevance = (
            0.35 * stage_sim +
            0.35 * fact_sim +
            0.30 * stat_sim
        )

        # Confidence adjustment — wider band so low-confidence evaluations are penalised
        # meaningfully. At conf=0.55: factor=0.843 (-16%). At conf=1.0: factor=1.0 (+0%).
        # This prevents a 9+ score from a 0.55-confidence DIRECTLY_SUPPORTING evaluation.
        conf_factor = 0.65 + 0.35 * llm_conf

        # Phase 2: role-specific utility multiplier
        role_utility_multiplier = self._ROLE_UTILITY_MULTIPLIER.get(rel_type, 0.50)

        # Channel discount: cases kept on principle/procedural grounds are less directly
        # on-point than cases kept on factual similarity; apply a modest discount so they
        # rank below facts-channel cases of equal stance, without being discarded entirely.
        channel = str(evaluation.get("channel", "facts")).lower()
        channel_multiplier = 1.0 if channel == "facts" else 0.85

        role_utility_score = overall_relevance * conf_factor * role_utility_multiplier * channel_multiplier * 10.0

        # Hard cap: low-confidence evaluations cannot reach top scores regardless of
        # statutory / factual match, because the LLM wasn't certain about the evaluation.
        # conf < 0.6 → cap at 7.0; conf < 0.5 → cap at 5.5
        if llm_conf < 0.5:
            role_utility_score = min(role_utility_score, 5.5)
        elif llm_conf < 0.6:
            role_utility_score = min(role_utility_score, 7.0)

        # Store both for transparency (pipeline can report overall_relevance if needed)
        evaluation["_overall_relevance_score"] = round(min(10.0, max(0.0, overall_relevance * 10.0)), 2)

        return round(min(10.0, max(0.0, role_utility_score)), 2)

    def build_role_specific_precedent_items(self, role_precedents: List[Dict], role: str) -> List[RoleSpecificPrecedentItem]:
        items = []

        for prec_data in role_precedents:
            candidate: PrecedentCandidate = prec_data["candidate"]
            evaluation: Dict[str, Any] = prec_data["evaluation"]

            final_score = self._calculate_calibrated_score(candidate, evaluation, role)

            matched_statutes = [MatchedStatuteItem(**m) for m in candidate.matched_statutes]
            propositions = [
                PropositionItem(
                    id=p.get("id", ""), text=p.get("text", ""),
                    favors=p.get("favors", "neutral"), speaker=p.get("speaker"),
                    kind=p.get("kind"), is_holding=p.get("is_holding"),
                    binding_level=p.get("binding_level")
                )
                for p in candidate.propositions
            ]

            relevance_eval = RoleSpecificRelevanceEvaluation(
                case_id=evaluation.get("case_id", candidate.case_id),
                case_name=evaluation.get("case_name", candidate.case_name),
                is_relevant=evaluation.get("is_relevant", True),
                relevance_type=evaluation.get("relevance_type", "BACKGROUND"),
                confidence=float(evaluation.get("confidence", 0.8)),
                factual_similarity=evaluation.get("factual_similarity", ""),
                legal_principle_alignment=evaluation.get("legal_principle_alignment", ""),
                statutory_interpretation_value=evaluation.get("statutory_interpretation_value", ""),
                procedural_relevance=evaluation.get("procedural_relevance", ""),
                supporting_propositions=evaluation.get("supporting_propositions", []),
                contradicting_propositions=evaluation.get("contradicting_propositions", []),
                usage_recommendation=evaluation.get("usage_recommendation", ""),
                key_quotes=evaluation.get("key_quotes", []),
                distinguishing_factors=evaluation.get("distinguishing_factors", [])
            )

            stat_matches = [m.get("judgment_section", "") for m in candidate.matched_statutes if m.get("judgment_section")]
            supports_role = bool(evaluation.get("supports_role")) or evaluation.get("relevance_type") in (
                "DIRECTLY_SUPPORTING", "STRONGLY_SUPPORTING")

            b_stage = float((candidate.score_breakdown or {}).get("stage", 0.0))
            # HIGH only for directly comparable stages (score >= 0.85, i.e. exact or near-exact match).
            # MODERATE for related but not identical stages (0.5–0.84), e.g. anticipatory_cancel
            # for a pre_arrest input — useful by analogy but a different legal question.
            # LOW for cross-stage comparisons (< 0.5).
            proc_match = "HIGH" if b_stage >= 0.85 else ("MODERATE" if b_stage >= 0.5 else "LOW")

            b_fact = float((candidate.score_breakdown or {}).get("fact", 0.0))
            fact_match = "HIGH" if b_fact >= 0.6 else ("MODERATE" if b_fact >= 0.3 else "LOW")

            # Pop the overall score stored by _calculate_calibrated_score for logging/transparency.
            # final_score = role_utility_score (role-specific utility).
            # overall_relevance_score = role-agnostic base quality.
            overall_relevance_score = evaluation.pop("_overall_relevance_score", final_score)

            compact_summary = CompactPrecedentSummary(
                case_id=candidate.case_id,
                case_name=candidate.case_name,
                procedural_match=proc_match,
                factual_match=fact_match,
                statutory_match=sorted(list(set(stat_matches))),
                role=role.upper(),
                supports_role=supports_role,
                use_for=evaluation.get("use_for", [evaluation.get("usage_recommendation", "")]),
                against_role=evaluation.get("against_role", evaluation.get("distinguishing_factors", [])),
                binding_level="binding",
                relevance_score=final_score,
            )

            item = RoleSpecificPrecedentItem(
                case_id=candidate.case_id,
                case_name=candidate.case_name,
                court=candidate.court,
                decided_on=candidate.decided_on,
                citation=candidate.citation,
                procedural_stage=candidate.inferred_stage or candidate.procedural_stage,
                disposition=candidate.disposition,
                matched_statutes=matched_statutes,
                match_score=candidate.match_score,
                abstract_facts=candidate.abstract_facts,
                all_statutes=candidate.statutes,
                propositions=propositions,
                relevance_evaluation=relevance_eval,
                final_relevance_score=final_score,
                compact_summary=compact_summary,
            )
            # Attach both scores for transparency (not in the frozen schema).
            # final_relevance_score = role_utility_score (sorts & ranks on this)
            # overall_relevance_score = role-agnostic base quality
            try:
                object.__setattr__(item, "overall_relevance_score", overall_relevance_score)
            except (AttributeError, TypeError):
                item.__dict__["overall_relevance_score"] = overall_relevance_score

            items.append(item)

        items.sort(key=lambda x: x.final_relevance_score, reverse=True)
        return items