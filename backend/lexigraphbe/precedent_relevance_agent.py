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
)


class PrecedentRelevanceReasonerAgent:
    """LLM reasoner that evaluates precedent relevance for prosecution or defense."""
    
    def __init__(self, llm: Optional[BaseChatModel] = None):
        self.llm = llm or get_llm(temperature=0.1)
    
    def _build_enriched_case_context(self, candidate: PrecedentCandidate) -> str:
        """Build enriched case context with ALL metadata for LLM evaluation."""
        lines = [
            f"CASE: {candidate.case_name}",
            f"CASE ID: {candidate.case_id}",
            f"COURT: {candidate.court}",
            f"DECIDED ON: {candidate.decided_on}",
            f"PROCEDURAL STAGE: {candidate.procedural_stage}",
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
                "position": "The PROSECUTION seeks to establish guilt and oppose bail/discharge",
                "goals": ["Prove all statutory ingredients", "Establish strong prima facie case",
                         "Show gravity of offence", "Argue against bail"],
                "focus": "Does this precedent strengthen prosecution or weaken defense?"
            },
            "defense": {
                "position": "The DEFENSE seeks acquittal or bail/discharge",
                "goals": ["Challenge statutory ingredients", "Establish weak prima facie case",
                         "Show civil dispute criminalized", "Argue for bail or quashing"],
                "focus": "Does this precedent strengthen defense or weaken prosecution?"
            }
        }
        
        context = role_context[role]
        
        return f"""You are a senior legal expert evaluating precedent relevance for the {role.upper()} in an anticipatory bail / criminal proceedings case.

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
EVALUATION TASK
═══════════════════════════════════════════════════════════════════════════════

Evaluate this precedent STRICTLY from the {role.upper()}'s perspective.

EVALUATION FOCUS:
{context['focus']}

Return ONLY valid JSON with these fields:

{{
  "is_relevant": true/false,
  "relevance_type": "strongly_supporting|supporting|distinguishable|contradictory|not_relevant",
  "confidence": 0.0-1.0,
  "factual_similarity": "detailed assessment",
  "legal_principle_alignment": "how principles align with {role}'s position",
  "statutory_interpretation_value": "value for {role}",
  "procedural_relevance": "relevance of procedural aspects",
  "supporting_propositions": ["p1", "p2"],
  "contradicting_propositions": ["p3"],
  "usage_recommendation": "how {role} should use this",
  "key_quotes": ["quote1"],
  "distinguishing_factors": ["factor1"]
}}

IMPORTANT:
- Be HONEST. Not every precedent helps the {role}.
- Precedents favoring "accused" help DEFENSE, hurt PROSECUTION.
- Analyze INDEPENDENTLY for each role.
- Focus on substantive legal analysis, not just statutory overlap."""
    
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
            
            return evaluation
            
        except json.JSONDecodeError as e:
            print(f"[PrecedentRelevanceReasonerAgent] JSON error for {candidate.case_id}: {e}")
            return {
                "case_id": candidate.case_id,
                "case_name": candidate.case_name,
                "is_relevant": False,
                "relevance_type": "not_relevant",
                "confidence": 0.0,
                "factual_similarity": "Error parsing LLM response",
                "legal_principle_alignment": "Error parsing LLM response",
                "statutory_interpretation_value": "Error parsing LLM response",
                "procedural_relevance": "Error parsing LLM response",
                "supporting_propositions": [],
                "contradicting_propositions": [],
                "usage_recommendation": "Manual review required",
                "key_quotes": [],
                "distinguishing_factors": ["LLM evaluation failed"]
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
        
        if is_relevant and relevance_type == "not_relevant":
            issues.append("Inconsistency: is_relevant=True but relevance_type='not_relevant'")
        elif not is_relevant and relevance_type in ["strongly_supporting", "supporting"]:
            issues.append(f"Inconsistency: is_relevant=False but relevance_type='{relevance_type}'")
        
        # Check confidence range
        confidence = evaluation.get("confidence", 0.0)
        if not (0.0 <= confidence <= 1.0):
            issues.append(f"Invalid confidence: {confidence}")
        
        # Check proposition IDs validity
        valid_prop_ids = {p.get("id") for p in candidate.propositions}
        invalid_supporting = [p for p in evaluation.get("supporting_propositions", [])
                            if p not in valid_prop_ids]
        if invalid_supporting:
            issues.append(f"Invalid supporting proposition IDs: {invalid_supporting}")
        
        # Check required fields
        if not evaluation.get("factual_similarity", "").strip():
            issues.append("factual_similarity field is empty")
        if not evaluation.get("legal_principle_alignment", "").strip():
            issues.append("legal_principle_alignment field is empty")
        
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
            
            if prosecution_eval.get("is_relevant", False):
                prosecution_precedents.append({
                    "candidate": candidate,
                    "evaluation": prosecution_eval,
                    "verification": prosecution_verification
                })
                print(f"       [+] Relevant ({prosecution_eval.get('relevance_type')})")
            else:
                print(f"       [-] Not relevant")
            
            # Evaluate for DEFENSE
            print(f"    -> Evaluating for DEFENSE...")
            defense_eval = self.reasoner.evaluate_precedent_for_role(
                "defense", candidate, input_case_summary, input_statutes, stage4_summary)
            
            defense_verification = self.verifier.verify_evaluation(
                "defense", candidate, defense_eval)
            
            if defense_eval.get("is_relevant", False):
                defense_precedents.append({
                    "candidate": candidate,
                    "evaluation": defense_eval,
                    "verification": defense_verification
                })
                print(f"       [+] Relevant ({defense_eval.get('relevance_type')})")
            else:
                print(f"       [-] Not relevant")
        
        print(f"\n[PrecedentRelevanceBatchEvaluator] Results:")
        print(f"  Prosecution: {len(prosecution_precedents)} relevant precedents")
        print(f"  Defense: {len(defense_precedents)} relevant precedents")
        
        # Rank by relevance
        prosecution_precedents.sort(
            key=lambda x: x["evaluation"].get("confidence", 0.0) * 
            (1 if x["evaluation"].get("relevance_type") == "strongly_supporting" else 0.7),
            reverse=True
        )
        defense_precedents.sort(
            key=lambda x: x["evaluation"].get("confidence", 0.0) *
            (1 if x["evaluation"].get("relevance_type") == "strongly_supporting" else 0.7),
            reverse=True
        )
        
        return {"prosecution": prosecution_precedents, "defense": defense_precedents}
    
    def build_role_specific_precedent_items(self, role_precedents: List[Dict],
                                           statutory_weight: float = 0.3) -> List[RoleSpecificPrecedentItem]:
        """Build RoleSpecificPrecedentItem objects from evaluated precedents."""
        items = []
        
        for prec_data in role_precedents:
            candidate = prec_data["candidate"]
            evaluation = prec_data["evaluation"]
            
            # Calculate final relevance score
            statutory_score = candidate.match_score
            llm_confidence = evaluation.get("confidence", 0.0)
            
            relevance_boost = {
                "strongly_supporting": 1.2,
                "supporting": 1.0,
                "distinguishable": 0.8,
                "contradictory": 0.6
            }.get(evaluation.get("relevance_type"), 1.0)
            
            final_score = (statutory_weight * statutory_score +
                          (1 - statutory_weight) * llm_confidence * relevance_boost)
            
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
            
            relevance_eval = RoleSpecificRelevanceEvaluation(**evaluation)
            
            item = RoleSpecificPrecedentItem(
                case_id=candidate.case_id, case_name=candidate.case_name,
                court=candidate.court, decided_on=candidate.decided_on, citation=None,
                procedural_stage=candidate.procedural_stage, disposition=candidate.disposition,
                matched_statutes=matched_statutes, match_score=candidate.match_score,
                abstract_facts=candidate.abstract_facts, all_statutes=candidate.statutes,
                propositions=propositions, relevance_evaluation=relevance_eval,
                final_relevance_score=final_score
            )
            
            items.append(item)
        
        items.sort(key=lambda x: x.final_relevance_score, reverse=True)
        return items
