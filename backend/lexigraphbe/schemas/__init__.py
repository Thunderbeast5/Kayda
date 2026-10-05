"""
LexiGraph Backend Pydantic Schemas Package.
Re-exports all stage-specific schemas and common models for 100% backward compatibility.
"""

from .common import (
    ManualReviewMixin,
    _sanitize_manual_review,
    STAGE1_MANDATORY_FIELDS,
    UNIVERSAL_PROCEDURAL_DOCUMENTS,
    VerificationIssue,
    VerificationResult,
)

from .stage0 import (
    AccusedParty,
    CaseContextObject,
    CaseMetadata,
    CaseProfile,
    IntakeInput,
    IntakeVerificationIssue,
    IntakeVerificationResult,
    LowConfidenceField,
    Parties,
    PrimaryParticipants,
)

from .stage1 import (
    EntityItem,
    ImportantFacts,
    LegalConceptItem,
    LegalQueryObject,
    QueryVerificationIssue,
    QueryVerificationResult,
    SubQueryItem,
)

from .stage2 import (
    Stage2VerificationIssue,
    Stage2VerificationResult,
)

from .stage3 import (
    ChapterCandidateItem,
    ChapterIdentificationObject,
    ChapterVerificationIssue,
    ChapterVerificationResult,
    PunishmentSpec,
    SectionCandidateItem,
    VerifiedOffenceItem,
)

from .stage4 import (
    IngredientEvaluationItem,
    StatutoryIngredientItem,
    StatutoryVerificationIssue,
    StatutoryVerificationObject,
    StatutoryVerificationResult,
    VerifiedOffenceItemStage4,
    VerifiedSectionItem,
)

from .stage5 import (
    BailEvaluationMap,
    BailFactorEvaluationItem,
    BailReasoningObject,
    BailVerificationIssue,
    BailVerificationResult,
    OverallBailRecommendation,
    SideArgumentPackage,
)

from .stage6 import (
    PrecedentItem,
    PrecedentRetrievalObject,
    PrecedentVerificationIssue,
    PrecedentVerificationResult,
)

from .stage_bsa import (
    BSASectionItem,
    BSAVerificationIssue,
    BSARetrievalObject,
)


__all__ = [
    "ManualReviewMixin",
    "_sanitize_manual_review",
    "STAGE1_MANDATORY_FIELDS",
    "UNIVERSAL_PROCEDURAL_DOCUMENTS",
    "VerificationIssue",
    "VerificationResult",
    "AccusedParty",
    "CaseContextObject",
    "CaseMetadata",
    "CaseProfile",
    "IntakeInput",
    "IntakeVerificationIssue",
    "IntakeVerificationResult",
    "LowConfidenceField",
    "Parties",
    "PrimaryParticipants",
    "EntityItem",
    "ImportantFacts",
    "LegalConceptItem",
    "LegalQueryObject",
    "QueryVerificationIssue",
    "QueryVerificationResult",
    "SubQueryItem",
    "Stage2VerificationIssue",
    "Stage2VerificationResult",
    "ChapterCandidateItem",
    "ChapterIdentificationObject",
    "ChapterVerificationIssue",
    "ChapterVerificationResult",
    "PunishmentSpec",
    "SectionCandidateItem",
    "VerifiedOffenceItem",
    "IngredientEvaluationItem",
    "StatutoryIngredientItem",
    "StatutoryVerificationIssue",
    "StatutoryVerificationObject",
    "StatutoryVerificationResult",
    "VerifiedOffenceItemStage4",
    "VerifiedSectionItem",
    "BailEvaluationMap",
    "BailFactorEvaluationItem",
    "BailReasoningObject",
    "BailVerificationIssue",
    "BailVerificationResult",
    "OverallBailRecommendation",
    "PrecedentItem",
    "PrecedentRetrievalObject",
    "PrecedentVerificationIssue",
    "PrecedentVerificationResult",
    "BSASectionItem",
    "BSAVerificationIssue",
    "BSARetrievalObject",
]

