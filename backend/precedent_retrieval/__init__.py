"""
Precedent Retrieval Package.

Provides complete precedent retrieval pipeline for Indian Criminal Law:
- Deterministic statutory and stage-aware candidate retrieval
- Batch LLM screening and verification
- Role-specific relevance evaluation for prosecution and defense
- Compact summaries and structured precedent packages
"""

from .schemas import (
    MatchedStatuteItem,
    PropositionItem,
    CaseRetrievalProfile,
    CompactPrecedentSummary,
    RoleSpecificRelevanceEvaluation,
    RoleSpecificPrecedentItem,
    RoleSpecificPrecedentRetrievalObject,
    PrecedentRetrievalIssue,
    PrecedentRetrievalResult,
    PrecedentItem,
    PrecedentRetrievalObject,
    PrecedentVerificationIssue,
    PrecedentVerificationResult,
)
from .precedent_statute_matcher import PrecedentStatuteMatcher, detect_stage_mode
from .precedent_index import PrecedentIndex
from .case_packet import build_packet, packet_ids, packet_text
from .precedent_retrieval import (
    PrecedentRetriever,
    PrecedentCandidate,
    RetrievalProfile,
    build_profile,
    build_case_retrieval_profile,
)
from .precedent_batch_screen import BatchPrecedentScreen
from .precedent_relevance_agent import (
    PrecedentRelevanceBatchEvaluator,
    PrecedentRelevanceReasonerAgent,
    PrecedentRelevanceVerifierAgent,
)
from .precedent_selection import select_sections
from .pipeline import PrecedentPipeline, Stage5PrecedentPipeline
from .runner import run_precedent_pipeline, extract_legal_issues

__all__ = [
    # Main Pipeline & Runner
    "PrecedentPipeline",
    "Stage5PrecedentPipeline",
    "run_precedent_pipeline",
    "extract_legal_issues",
    # Retrieval Engine
    "PrecedentRetriever",
    "PrecedentCandidate",
    "RetrievalProfile",
    "build_profile",
    "build_case_retrieval_profile",
    "PrecedentStatuteMatcher",
    "detect_stage_mode",
    "PrecedentIndex",
    # Screening & Evaluation
    "BatchPrecedentScreen",
    "PrecedentRelevanceBatchEvaluator",
    "PrecedentRelevanceReasonerAgent",
    "PrecedentRelevanceVerifierAgent",
    "select_sections",
    "build_packet",
    "packet_ids",
    "packet_text",
    # Schemas
    "MatchedStatuteItem",
    "PropositionItem",
    "CaseRetrievalProfile",
    "CompactPrecedentSummary",
    "RoleSpecificRelevanceEvaluation",
    "RoleSpecificPrecedentItem",
    "RoleSpecificPrecedentRetrievalObject",
    "PrecedentRetrievalIssue",
    "PrecedentRetrievalResult",
    "PrecedentItem",
    "PrecedentRetrievalObject",
    "PrecedentVerificationIssue",
    "PrecedentVerificationResult",
    # Legacy agents
    "PrecedentRetrievalAgent",
    "PrecedentVerificationAuditor",
]
