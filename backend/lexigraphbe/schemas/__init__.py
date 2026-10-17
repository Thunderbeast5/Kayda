"""
LexiGraph Backend Pydantic Schemas Package.
Re-exports stage-specific schemas for Stages 0 through 4 (and statutory extensions).
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
    FactualAllegation,
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

from .stage_bsa import (
    BSASectionItem,
    BSAVerificationIssue,
    BSARetrievalObject,
)

from .stage_bnss import (
    BNSSSectionItem,
    BNSSVerificationIssue,
    BNSSRetrievalObject,
)

from .stage_special_act import (
    ActRoutingDecisionItem,
    SpecialActSectionItem,
    SpecialActRetrievalObject,
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
    "FactualAllegation",
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
    "BSASectionItem",
    "BSAVerificationIssue",
    "BSARetrievalObject",
    "BNSSSectionItem",
    "BNSSVerificationIssue",
    "BNSSRetrievalObject",
    "ActRoutingDecisionItem",
    "SpecialActSectionItem",
    "SpecialActRetrievalObject",
]
