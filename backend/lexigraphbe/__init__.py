"""
LexiGraph Backend - Stage 0 (Intake), Stage 1 (Query Understanding), Stage 2 (Sub-Query Mapping), Stage 3 (Chapter Identification), Stage 3b (BSA Evidence Law Retrieval), Stage 4 (Statutory Verification), Stage 5 (Bail Reasoning), Stage 6 (Precedent Retrieval), IPC ↔ BNS Mapper, Local Classifier Pre-filter, and Batched Pipeline Utilities.
"""

from .schemas import (
    AccusedParty,
    CaseMetadata,
    Parties,
    PrimaryParticipants,
    LowConfidenceField,
    CaseProfile,
    CaseContextObject,
    VerificationIssue,
    VerificationResult,
    IntakeInput,
    LegalConceptItem,
    SubQueryItem,
    ImportantFacts,
    LegalQueryObject,
    QueryVerificationIssue,
    QueryVerificationResult,
    Stage2VerificationIssue,
    Stage2VerificationResult,
    ChapterCandidateItem,
    SectionCandidateItem,
    ChapterIdentificationObject,
    ChapterVerificationIssue,
    ChapterVerificationResult,
    StatutoryIngredientItem,
    VerifiedSectionItem,
    StatutoryVerificationObject,
    StatutoryVerificationIssue,
    StatutoryVerificationResult,
    BailFactorEvaluationItem,
    BailEvaluationMap,
    OverallBailRecommendation,
    BailReasoningObject,
    BailVerificationIssue,
    BailVerificationResult,
    PrecedentItem,
    PrecedentRetrievalObject,
    PrecedentVerificationIssue,
    PrecedentVerificationResult,
)
from .batch_utils import (
    SubQueryChapterMapping,
    Stage2BatchedMappingResponse,
    SectionIngredientEvaluation,
    Stage5BatchedIngredientResponse,
)
from .classifier_prefilter import CandidateSectionMatch, StatuteClassifierPrefilter
from .ipc2bns_mapper import IPC2BNSMapper
from .eval_prefilter import run_prefilter_recall_evaluation, BENCHMARK_CORPUS
from .eval_models import evaluate_model_performance, ModelBenchmarkReport
from .eval_auditor import run_auditor_benchmark_evaluation
from .intake_agent import CaseIntakeAgent
from .verifier_agent import CaseIntakeVerifierAgent
from .pipeline import Stage0Pipeline
from .query_understanding_agent import QueryUnderstandingAgent
from .query_verifier_agent import QueryVerificationAgent
from .stage1_pipeline import Stage1Pipeline
from .stage2_mapping_agent import Stage2SubQueryMappingAgent
from .stage2_verifier_agent import Stage2MappingVerifierAgent
from .stage2_pipeline import Stage2Pipeline
from .chapter_identification_agent import ChapterIdentificationAgent
from .chapter_verifier_agent import ChapterVerificationAgent
from .stage3_pipeline import Stage3Pipeline
from .statutory_verification_agent import StatutoryVerificationAgent
from .statutory_verifier_agent import StatutoryVerificationAuditor
from .stage4_pipeline import Stage4Pipeline
from .bail_reasoning_agent import BailReasoningAgent
from .bail_verifier_agent import BailReasoningVerifierAgent
from .stage5_pipeline import Stage5Pipeline
from .precedent_retrieval_agent import PrecedentRetrievalAgent
from .precedent_verifier_agent import PrecedentVerificationAuditor
from .stage6_pipeline import Stage6Pipeline
from .bsa_retrieval_agent import BSARetrievalAgent
from .bsa_verifier_agent import BSAVerifierAgent
from .schemas import BSASectionItem, BSAVerificationIssue, BSARetrievalObject


__all__ = [
    # Stage 0
    "AccusedParty",
    "CaseMetadata",
    "Parties",
    "PrimaryParticipants",
    "LowConfidenceField",
    "CaseProfile",
    "CaseContextObject",
    "VerificationIssue",
    "VerificationResult",
    "IntakeInput",
    "CaseIntakeAgent",
    "CaseIntakeVerifierAgent",
    "Stage0Pipeline",
    # Stage 1
    "LegalConceptItem",
    "SubQueryItem",
    "ImportantFacts",
    "LegalQueryObject",
    "QueryVerificationIssue",
    "QueryVerificationResult",
    "QueryUnderstandingAgent",
    "QueryVerificationAgent",
    "Stage1Pipeline",
    # Stage 2
    "SubQueryChapterMapping",
    "Stage2BatchedMappingResponse",
    "Stage2VerificationIssue",
    "Stage2VerificationResult",
    "Stage2SubQueryMappingAgent",
    "Stage2MappingVerifierAgent",
    "Stage2Pipeline",
    # Stage 3
    "ChapterCandidateItem",
    "SectionCandidateItem",
    "ChapterIdentificationObject",
    "ChapterVerificationIssue",
    "ChapterVerificationResult",
    "ChapterIdentificationAgent",
    "ChapterVerificationAgent",
    "Stage3Pipeline",
    # Stage 4
    "StatutoryIngredientItem",
    "VerifiedSectionItem",
    "StatutoryVerificationObject",
    "StatutoryVerificationIssue",
    "StatutoryVerificationResult",
    "StatutoryVerificationAgent",
    "StatutoryVerificationAuditor",
    "Stage4Pipeline",
    # Stage 5
    "BailFactorEvaluationItem",
    "BailEvaluationMap",
    "OverallBailRecommendation",
    "BailReasoningObject",
    "BailVerificationIssue",
    "BailVerificationResult",
    "BailReasoningAgent",
    "BailReasoningVerifierAgent",
    "Stage5Pipeline",
    # Stage 6
    "PrecedentItem",
    "PrecedentRetrievalObject",
    "PrecedentVerificationIssue",
    "PrecedentVerificationResult",
    "PrecedentRetrievalAgent",
    "PrecedentVerificationAuditor",
    "Stage6Pipeline",
    # Stage 3b — BSA Evidence Law Retrieval
    "BSASectionItem",
    "BSAVerificationIssue",
    "BSARetrievalObject",
    "BSARetrievalAgent",
    "BSAVerifierAgent",

    # Local Classifier Pre-filter & Evaluation
    "CandidateSectionMatch",
    "StatuteClassifierPrefilter",
    "IPC2BNSMapper",
    "run_prefilter_recall_evaluation",
    "BENCHMARK_CORPUS",
    "evaluate_model_performance",
    "ModelBenchmarkReport",
    "run_auditor_benchmark_evaluation",
    # Batching Utilities
    "SectionIngredientEvaluation",
    "Stage5BatchedIngredientResponse",
]
