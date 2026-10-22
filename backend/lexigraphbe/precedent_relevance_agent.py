"""
Precedent Relevance Evaluation Agent for LexiGraphBE Stage 5.

Implements LLM-based role-specific relevance evaluation with full case metadata enrichment.
Uses a reasoner + verifier architecture for robust precedent analysis.
"""

import json
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from .config import get_llm
from .precedent_retrieval import PrecedentCandidate
from .schemas.stage5_precedent import (
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
            ("RETRIEVED_FOR_PRINCIPLE: matched on legal issue, not on facts" if getattr(candidate, "channel", "case") == "principle" else "RETRIEVED_FOR_FACTS_AND_STATUTES"),
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
            if match.get('note'):
                lines.append(f"     Note: {match['note']}")
        
        lines.extend([
            "",
            f"ALL STATUTES IN THIS CASE ({len(candidate.statutes)}):"
        ])
        
        for statute in candidate.statutes:
            lines.append(f"  - {statute.get('act')} Section {statute.get('section')} [{statute.get('how_used')}]")
            if statute.get('note'):
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
                
                holding_marker = "[BINDING HOLDING]" if is_holding else f"[{kind}]" if kind else ""
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
    
    def _build_role_specific_prompt(self, role: str, input_case_summary: str,
                                   input_statutes: List[Dict], stage4_details: str,
                                   enriched_precedent: str) -> str:
        """Build role-specific evaluation prompt."""
        
        role_context = {
            "prosecution": {
                "position": "The PROSECUTION seeks to establish prima facie guilt, oppose anticipatory bail, and argue need for custodial interrogation",
                "goals": [
                    "Oppose anticipatory bail by emphasizing gravity, economic offence nature, and need for custodial interrogation",
                    "Highlight use of forged documents, deception, and inducement",
                    "Argue against treating fraudulent conduct as a mere civil dispute",
                    "Demonstrate necessity of custodial investigation to trace documents/funds"
                ],
                "focus": "How does this precedent support the PROSECUTION in denying bail or establishing prima facie offences? (Or is it opposing/distinguishable?)"
            },
            "defense": {
                "position": "The DEFENSE seeks grant of anticipatory bail and argues absence of dishonest intention / civil commercial dispute",
                "goals": [
                    "Argue for anticipatory bail under Article 21, showing cooperation with investigation and absence of flight risk",
                    "Demonstrate commercial/contractual dispute being given a criminal colour",
                    "Show absence of fraudulent intention at the inception",
                    "Establish custodial interrogation is unnecessary when documents are already with the police"
                ],
                "focus": "How does this precedent support the DEFENSE in securing anticipatory bail or showing lack of criminal criminality? (Or is it opposing/distinguishable?)"
            }
        }
        
        context = role_context[role]
        
        return f"""You are a senior legal expert evaluating precedent relevance for the {role.upper()} in an anticipatory bail proceeding in India.

ROLE CONTEXT:
{context['position']}

ROLE GOALS:
{chr(10).join(f'- {g}' for g in context['goals'])}

═══════════════════════════════════════════════════════════════════════════════
INPUT CASE (The case you are evaluating precedents FOR)
═══════════════════════════════════════════════════════════════════════════════

CASE SUMMARY:
{input_case_summary}

STATUTES ATTRACTED (from Stage 4 Analysis):
{chr(10).join(f"- {s.get('act')} Section {s.get('section')}" for s in input_statutes)}

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
- DO NOT INFLATE LABELS: If factual similarity is LOW or DISTINGUISHABLE (e.g. money laundering/economic offence, bank loans, absconding, or public funds vs private commercial property transaction), you MUST NOT label as STRONGLY_SUPPORTING or DIRECTLY_SUPPORTING. Label as BACKGROUND (general principle only) or DISTINGUISHABLE.
- SUBJECT MATTER CAP: if the precedent concerns violence, sexual offences, matrimonial/dowry disputes or PMLA/NDPS-type special statutes while the input case is a private property/forgery dispute, the relevance_type is LOW_RELEVANCE regardless of how generally the principle is phrased.
- If the candidate is marked RETRIEVED_FOR_PRINCIPLE below (different facts, matching legal issue), judge it only on whether its holding answers an issue the input actually raises; if it does, label it SUPPORTING or OPPOSING for the side its holding favours and say which issue; if not, BACKGROUND.
- LEGAL PRINCIPLE MATCH != FACTUAL MATCH. Keep them separate.
  For example, if a case rules on general custodial interrogation principles or IPC 420 deceit principles but the facts concern bank loans, money laundering, absconding, or foreign exchange rather than property/land sale deed forgery, the factual similarity level is LOW and relevance_type must be BACKGROUND or DISTINGUISHABLE, NEVER DIRECTLY_SUPPORTING or STRONGLY_SUPPORTING.
- STRONGLY_SUPPORTING or DIRECTLY_SUPPORTING requires BOTH strong procedural stage relevance AND meaningful factual or subject-matter similarity (property, land, deed forgery, commercial transfer dispute).
- SUPPORTING vs OPPOSING is strictly RELATIVE to {role.upper()}:
  * DEFENSE: Supporting means helps the accused get bail/relief. Opposing means helps prosecution deny bail.
  * PROSECUTION: Supporting means helps prosecution deny bail/prove guilt. Opposing means helps accused.

You MUST choose relevance_type from this exact taxonomy:
- DIRECTLY_SUPPORTING: Same procedural stage + ON-POINT matching property/forgery facts + propositions directly supporting {role.upper()}
- DIRECTLY_OPPOSING: Precedent directly cuts against {role.upper()} on same procedural stage and matching facts (critical adverse authority)
- STRONGLY_SUPPORTING: Strong principle alignment AND relevant factual similarity supporting {role.upper()}
- STRONGLY_OPPOSING: Strong principle/holding cutting against {role.upper()}
- DISTINGUISHABLE: Relevant legal issues, but you can name a MATERIAL factual difference that lets {role.upper()} avoid the holding. If the stage and facts match and the holding cuts against {role.upper()}, it is NOT distinguishable: use DIRECTLY_OPPOSING (critical adverse authority)
- BACKGROUND: General principles of law or criminal jurisprudence with indirect application (principle only, low factual match)
- LOW_RELEVANCE: Unrelated facts/stage or marginal statutory overlap

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
  "procedural_relevance": "relevance of procedural stage (anticipatory bail vs regular vs quashing)",
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
    
    def evaluate_precedent_for_role(self, role: str, candidate: PrecedentCandidate,
                                   input_case_summary: str, input_statutes: List[Dict],
                                   stage4_summary: str) -> Dict[str, Any]:
        """Evaluate a precedent candidate for a specific role."""
        
        enriched_case = self._build_enriched_case_context(candidate)
        prompt = self._build_role_specific_prompt(role, input_case_summary, input_statutes,
                                                  stage4_summary, enriched_case)
        
        messages = [
            SystemMessage(content="You are a senior legal expert specializing in criminal law and anticipatory bail proceedings in India."),
            HumanMessage(content=prompt)
        ]
        
        response = self.llm.invoke(messages)
        response_text = response.content.strip()
        
        try:
            # Extract JSON
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
            
            # Normalize relevance_type
            rel_type = str(evaluation.get("relevance_type", "")).strip().upper()
            if rel_type not in VALID_RELEVANCE_TYPES:
                # Map legacy values
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
        
        # Check relevance type consistency
        is_relevant = evaluation.get("is_relevant", False)
        relevance_type = evaluation.get("relevance_type", "")
        
        if is_relevant and relevance_type == "LOW_RELEVANCE":
            # Allowed as background / low relevance note
            pass
        elif not is_relevant and relevance_type in ["DIRECTLY_SUPPORTING", "STRONGLY_SUPPORTING"]:
            issues.append(f"Inconsistency: is_relevant=False but relevance_type='{relevance_type}'")
        
        # Check confidence range
        confidence = evaluation.get("confidence", 0.0)
        if not (0.0 <= confidence <= 1.0):
            issues.append(f"Invalid confidence: {confidence}")
        
        # Proposition IDs: drop unknown IDs instead of failing the whole evaluation (the LLM often cites "p6" of 5)
        valid_prop_ids = {p.get("id") for p in candidate.propositions}
        for key in ("supporting_propositions", "contradicting_propositions"):
            ids = evaluation.get(key, []) or []
            kept = [i for i in ids if i in valid_prop_ids]
            if len(kept) != len(ids):
                evaluation[key] = kept
                evaluation.setdefault("_sanitized", []).append(f"{key}: dropped {sorted(set(ids) - set(kept))}")

        # Label inflation: DIRECTLY/STRONGLY_SUPPORTING with LOW fact match is only allowed for cases that entered
        # through the retriever's ISSUE channel (candidate.channel == "principle"), i.e. cases retrieved precisely
        # because their holdings match a legal issue the input raises. Nothing is exempted by name.
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
    
    def evaluate_candidates_for_both_roles(self, candidates: List[PrecedentCandidate],
                                          input_case_summary: str, input_statutes: List[Dict],
                                          stage4_result: Dict) -> Dict[str, List[Dict]]:
        """Evaluate all candidates for both prosecution and defense roles."""
        
        stage4_summary = self._extract_stage4_summary(stage4_result)
        prosecution_precedents = []
        defense_precedents = []
        
        print(f"\n[PrecedentRelevanceBatchEvaluator] Evaluating {len(candidates)} candidates...")
        
        for i, candidate in enumerate(candidates, 1):
            print(f"\n  Candidate {i}/{len(candidates)}: {candidate.case_name}")
            
            # Evaluate for PROSECUTION
            print(f"    -> Evaluating for PROSECUTION...")
            prosecution_eval = self.reasoner.evaluate_precedent_for_role(
                "prosecution", candidate, input_case_summary, input_statutes, stage4_summary)
            
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
            
            # Evaluate for DEFENSE
            print(f"    -> Evaluating for DEFENSE...")
            defense_eval = self.reasoner.evaluate_precedent_for_role(
                "defense", candidate, input_case_summary, input_statutes, stage4_summary)
            
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
    
    def _calculate_calibrated_score(self, candidate: PrecedentCandidate, evaluation: Dict[str, Any], role: str) -> float:
        """
        Calculate calibrated relevance score on 0.0 - 10.0 scale according to:
        - procedural-stage match: 30%
        - factual similarity: 25%
        - legal-section overlap: 20%
        - legal-principle similarity: 15%
        - outcome / role direction: 10%
        """
        breakdown = candidate.score_breakdown or {}
        stage_sim = float(breakdown.get("stage", 0.5))
        fact_sim = float(breakdown.get("fact", 0.3))
        stat_sim = float(breakdown.get("statutory", 0.5))
        
        role_data = (breakdown.get("by_role") or {}).get(role, {})
        principle_sim = float(role_data.get("principle", 0.4))
        direction_sim = float(role_data.get("direction", 0.5))
        
        # Incorporate LLM adjustment
        rel_type = evaluation.get("relevance_type", "BACKGROUND")
        llm_conf = float(evaluation.get("confidence", 0.8))
        fact_level = str(evaluation.get("factual_similarity_level", "")).upper()
        
        is_on_point = (fact_sim >= 0.4 or fact_level in ("HIGH", "MODERATE"))
        
        # Taxonomy multipliers:
        # In legal practice, an on-point precedent that is adverse (must be distinguished)
        # is critical mandatory authority. It must rank alongside supporting precedents, not be suppressed.
        if is_on_point:
            if rel_type in ("DIRECTLY_SUPPORTING", "STRONGLY_SUPPORTING"):
                type_multiplier = 1.25 if rel_type == "DIRECTLY_SUPPORTING" else 1.15
            elif rel_type == "DISTINGUISHABLE":
                type_multiplier = 1.15
                direction_sim = max(direction_sim, 0.5)  # Distinguishing on-point adverse authority is vital advocacy
            elif rel_type in ("DIRECTLY_OPPOSING", "STRONGLY_OPPOSING"):
                type_multiplier = 1.05
                direction_sim = max(direction_sim, 0.5)
            elif rel_type == "BACKGROUND":
                type_multiplier = 1.00
            else:
                type_multiplier = 0.60
            fact_dampener = 1.0
        else:
            # Principle-only precedent (low factual overlap)
            type_multiplier = {
                "DIRECTLY_SUPPORTING": 1.00,
                "STRONGLY_SUPPORTING": 1.15,
                "DISTINGUISHABLE": 0.85,
                "BACKGROUND": 0.85,
                "STRONGLY_OPPOSING": 0.70,
                "DIRECTLY_OPPOSING": 0.60,
                "LOW_RELEVANCE": 0.40,
            }.get(rel_type, 0.80)
            fact_dampener = 1.0 if rel_type == "STRONGLY_SUPPORTING" else 0.85
        
        base_score = (
            0.30 * stage_sim +
            0.25 * fact_sim +
            0.20 * stat_sim +
            0.15 * principle_sim +
            0.10 * direction_sim
        )
        
        # Scale to 0 - 10 and apply LLM confidence, type multiplier, and fact dampener
        calibrated = base_score * 10.0 * (0.8 + 0.2 * llm_conf) * type_multiplier * fact_dampener
        return round(min(10.0, max(0.0, calibrated)), 2)
    
    def build_role_specific_precedent_items(self, role_precedents: List[Dict], role: str) -> List[RoleSpecificPrecedentItem]:
        """Build RoleSpecificPrecedentItem objects and CompactPrecedentSummary from evaluated precedents."""
        items = []
        
        for prec_data in role_precedents:
            candidate: PrecedentCandidate = prec_data["candidate"]
            evaluation: Dict[str, Any] = prec_data["evaluation"]
            
            final_score = self._calculate_calibrated_score(candidate, evaluation, role)
            
            # Convert to schema objects
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
            
            # Construct CompactPrecedentSummary
            stat_matches = [m.get("judgment_section", "") for m in candidate.matched_statutes if m.get("judgment_section")]
            supports_role = evaluation.get("relevance_type") in ("DIRECTLY_SUPPORTING", "STRONGLY_SUPPORTING")
            
            # Procedural match rating
            b_stage = float((candidate.score_breakdown or {}).get("stage", 0.0))
            proc_match = "HIGH" if b_stage >= 0.8 else ("MODERATE" if b_stage >= 0.5 else "LOW")
            
            # Factual match rating
            b_fact = float((candidate.score_breakdown or {}).get("fact", 0.0))
            fact_match = "HIGH" if b_fact >= 0.6 else ("MODERATE" if b_fact >= 0.3 else "LOW")
            
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
                relevance_score=final_score
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
            
            items.append(item)
        
        # Sort items strictly by relevance score in descending order
        items.sort(key=lambda x: x.final_relevance_score, reverse=True)
        return items