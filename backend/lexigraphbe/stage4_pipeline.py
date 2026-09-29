"""
Stage 4 Pipeline orchestrating StatutoryVerificationAgent and StatutoryVerificationAuditor.
Transforms Stage 1 LegalQueryObject + Stage 3 ChapterIdentificationObject into verified StatutoryVerificationObject.
Caps retries at 1 max for genuine judgment failures, falling back to manual_review flags.
"""

from typing import Any, Dict, Optional, Union
from .statutory_verification_agent import StatutoryVerificationAgent
from .statutory_verifier_agent import StatutoryVerificationAuditor
from .statute_repository import StatuteRepository
from .schemas import ChapterIdentificationObject, LegalQueryObject, StatutoryVerificationObject, StatutoryVerificationResult


class Stage4Pipeline:
    """
    Complete Stage 4 pipeline for Full Statutory Verification & Ingredient Matching.
    Executes LegalQueryObject + ChapterIdentificationObject -> StatutoryVerificationAgent -> StatutoryVerificationAuditor -> Reflection Retry Loop -> Verified StatutoryVerificationObject.
    Caps retries at 1 max for genuine judgment failures, falling back to manual_review flags.
    """

    def __init__(
        self,
        statutory_agent: Optional[StatutoryVerificationAgent] = None,
        verifier_agent: Optional[StatutoryVerificationAuditor] = None,
        max_retries: int = 1,
    ):
        self.statutory_agent = statutory_agent or StatutoryVerificationAgent()
        self.verifier_agent = verifier_agent or StatutoryVerificationAuditor()
        self.max_retries = max_retries

    def run(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        chapter_object: Union[ChapterIdentificationObject, Dict[str, Any], str],
    ) -> StatutoryVerificationResult:
        """
        Runs full Stage 4 pipeline on LegalQueryObject and ChapterIdentificationObject.

        Args:
            legal_query: LegalQueryObject instance or equivalent JSON/dict from Stage 1.
            chapter_object: ChapterIdentificationObject instance or equivalent JSON/dict from Stage 3.

        Returns:
            StatutoryVerificationResult containing final verified StatutoryVerificationObject and audit details.
        """
        correction_feedback = None
        current_attempt = 0

        last_statutory_obj: Optional[StatutoryVerificationObject] = None
        verification_result: Optional[StatutoryVerificationResult] = None

        while current_attempt <= self.max_retries:
            current_attempt += 1

            # Step 1: Statutory Verification & Ingredient Matching
            last_statutory_obj = self.statutory_agent.run(
                legal_query=legal_query,
                chapter_object=chapter_object,
                correction_feedback=correction_feedback,
            )

            # Step 2: Auditor Verification Check
            verification_result = self.verifier_agent.verify(
                legal_query=legal_query,
                chapter_object=chapter_object,
                statutory_object=last_statutory_obj,
            )

            if verification_result.status == "VERIFIED":
                verification_result.verified_statutory_object = last_statutory_obj
                
                # Dynamic KB Learning: Promote verified sections to KB for future queries
                self._learn_from_verification(legal_query, last_statutory_obj)
                
                return verification_result

            # Step 3: Prepare feedback for single reflection retry
            if current_attempt <= self.max_retries:
                feedback_parts = [f"Attempt {current_attempt} verification failed with audit issues:"]
                for issue in verification_result.issues:
                    feedback_parts.append(f"- Target '{issue.target}': {issue.issue} | Action: {issue.feedback}")
                if verification_result.feedback:
                    feedback_parts.append(f"Summary: {verification_result.feedback}")
                correction_feedback = "\n".join(feedback_parts)

        # Fallback Policy: If retries are exhausted, attach issues to manual_review
        if last_statutory_obj:
            if verification_result and verification_result.issues:
                for issue in verification_result.issues:
                    flag_note = f"Unresolved statutory verification audit issue ({issue.target}): {issue.issue}"
                    if flag_note not in last_statutory_obj.manual_review:
                        last_statutory_obj.manual_review.append(flag_note)

            if verification_result:
                verification_result.verified_statutory_object = last_statutory_obj
                verification_result.feedback += " (Exhausted retries -> Flagged for human review)."
                return verification_result

        return StatutoryVerificationResult(
            status="RETRY",
            issues=[],
            feedback="Pipeline execution completed without verification (Flagged for human review).",
            verified_statutory_object=last_statutory_obj,
        )
    
    def _learn_from_verification(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        statutory_obj: StatutoryVerificationObject,
    ) -> None:
        """
        Learns from verified sections by promoting them to Dynamic KB.
        Each verified section becomes a KB rule with concept → section mapping.
        
        Args:
            legal_query: The original legal query with concepts
            statutory_obj: Verified statutory object with matched sections
        """
        try:
            from .classifier_prefilter import promote_from_llm_result
            
            # Extract query object
            if isinstance(legal_query, LegalQueryObject):
                query_obj = legal_query
            elif isinstance(legal_query, dict):
                query_obj = LegalQueryObject.model_validate(legal_query)
            else:
                return  # Can't learn without proper query object
            
            # Build concept → section mapping
            concept_map = {}
            for concept_item in query_obj.legal_concepts:
                concept_map[concept_item.concept.lower()] = concept_item
            
            # For each verified offence, promote to Dynamic KB using its authoritative ipc.json definition
            statute_db = StatuteRepository.get_instance().get_statute_db()
            for offence in statutory_obj.verified_offences:
                section_num = offence.section_number
                statute = offence.statute or "IPC"

                # Fetch authoritative metadata from ipc.json
                rec = statute_db.get(f"IPC_{section_num}") or {}
                # section_title is the section's own heading — always correct and authoritative.
                # We do NOT use chapter_title or sub_heading: ipc.json chapter nesting is structurally
                # incorrect for many sections (e.g. 378-382 Theft sections are nested under
                # the Kidnapping sub_heading in the JSON tree).
                title = rec.get("section_title") or offence.title or f"{statute} Section {section_num}"
                chapter = rec.get("chapter_title") or "General Offences"
                
                # Canonical concept = section's own heading (e.g. "Theft in dwelling house, etc.")
                # This is always derived from ipc.json data, never from a hardcoded mapping.
                matched_concept = title

                # If the query has a concept whose text appears in the section title, prefer that wording
                title_lower = title.lower()
                for concept_text, concept_item in concept_map.items():
                    if concept_text in title_lower or title_lower in concept_text:
                        matched_concept = concept_item.concept
                        break

                ingredients = offence.ingredient_evaluation or []

                if section_num and matched_concept:
                    promote_from_llm_result(
                        section_number=section_num,
                        statute=statute,
                        title=title,
                        chapter=chapter,
                        ingredients=[ing.ingredient for ing in ingredients],
                        matched_concept=matched_concept,
                        bns_equivalent=section_num,
                        cognizable=True,
                        bailable=False,
                        punishment_maximum=rec.get("punishment"),
                    )
                    print(f"[Stage4 Learning] Promoted {statute} {section_num} '{title}' with concept '{matched_concept}'")

        
        except Exception as e:
            # Don't fail the pipeline if learning fails
            print(f"[Stage4 Learning] Warning: Could not promote to KB - {e}")
