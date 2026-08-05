"""
Pydantic data models for every stage of the Text-to-Cypher pipeline.

All inter-stage communication uses these typed models to enforce
correctness and enable serialisation / logging.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Intent Enum                                                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class LegalIntent(str, Enum):
    """Supported legal query intents."""
    PUNISHMENT = "punishment"
    IPC_TO_BNS = "ipc_to_bns"
    BNS_TO_IPC = "bns_to_ipc"
    SECTION_LOOKUP = "section_lookup"
    CRIME_LOOKUP = "crime_lookup"
    KEYWORD_LOOKUP = "keyword_lookup"
    LEGAL_EXPLANATION = "legal_explanation"
    GRAPH_REASONING = "graph_reasoning"
    RELATED_OFFENCES = "related_offences"
    MULTIPLE_CRIMES = "multiple_crimes"
    COMPARISON = "comparison"
    HIERARCHY = "hierarchy"
    PUNISHMENT_COMPARISON = "punishment_comparison"
    UNKNOWN = "unknown"


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Stage 1 — Intent Classification                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class IntentResult(BaseModel):
    """Output of the intent classifier."""
    intent: LegalIntent = Field(..., description="Primary detected intent")
    secondary_intents: List[LegalIntent] = Field(
        default_factory=list,
        description="Additional intents detected in compound queries",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score")
    reasoning: str = Field(default="", description="Brief explanation of classification")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Stage 2 — Entity Extraction                                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class ExtractedEntities(BaseModel):
    """Structured entities extracted from a natural-language legal query."""
    crimes: List[str] = Field(default_factory=list, description="Crime names, e.g. ['murder', 'kidnapping']")
    ipc_sections: List[str] = Field(default_factory=list, description="IPC section numbers, e.g. ['302', '120A']")
    bns_sections: List[str] = Field(default_factory=list, description="BNS section numbers, e.g. ['103', '61']")
    acts: List[str] = Field(default_factory=list, description="Act codes, e.g. ['IPC', 'BNS']")
    chapters: List[str] = Field(default_factory=list, description="Chapter references")
    punishments: List[str] = Field(default_factory=list, description="Punishment terms mentioned")
    keywords: List[str] = Field(default_factory=list, description="Legal keywords / concepts")
    legal_concepts: List[str] = Field(default_factory=list, description="Abstract legal concepts, e.g. 'mens rea'")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Stage 3 — Entity Linking                                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class LinkedNode(BaseModel):
    """A canonical graph node resolved via fulltext search."""
    node_id: str = Field(..., description="Neo4j node id property, e.g. 'IPC_302'")
    label: str = Field(..., description="Node label, e.g. 'LawSection' or 'Crime'")
    name: str = Field(default="", description="Display name / title")
    score: float = Field(default=0.0, description="Fulltext relevance score")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional node properties")


class LinkedEntities(BaseModel):
    """All entities after resolution against the graph."""
    crime_nodes: List[LinkedNode] = Field(default_factory=list)
    section_nodes: List[LinkedNode] = Field(default_factory=list)
    keyword_nodes: List[LinkedNode] = Field(default_factory=list)
    raw_matches: Dict[str, List[LinkedNode]] = Field(
        default_factory=dict,
        description="Original query term → matched nodes",
    )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Stage 4 — Graph Expansion                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class ExpandedRelation(BaseModel):
    """A single relationship discovered during graph expansion."""
    source_id: str
    target_id: str
    relationship: str = Field(..., description="Relationship type, e.g. 'REPLACED_BY'")
    properties: Dict[str, Any] = Field(default_factory=dict)


class ExpandedContext(BaseModel):
    """All information gathered during graph expansion."""
    linked: LinkedEntities
    relations: List[ExpandedRelation] = Field(default_factory=list)
    replacement_sections: List[LinkedNode] = Field(default_factory=list)
    punishment_nodes: List[LinkedNode] = Field(default_factory=list)
    related_sections: List[LinkedNode] = Field(default_factory=list)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Stage 5 — Query Plan                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class QueryPlan(BaseModel):
    """
    JSON query plan produced by the Planner.

    This is a *specification* — never raw Cypher.
    The CypherBuilder reads this to generate deterministic Cypher.
    """
    intent: LegalIntent
    entities: List[str] = Field(default_factory=list, description="Primary entity names")
    linked_node_ids: List[str] = Field(default_factory=list, description="Resolved Neo4j node IDs")
    need_punishment: bool = Field(default=False)
    need_replacement: bool = Field(default=False)
    need_keywords: bool = Field(default=False)
    need_description: bool = Field(default=False)
    need_chapter: bool = Field(default=False)
    need_related: bool = Field(default=False)
    need_hierarchy: bool = Field(default=False)
    target_act: Optional[str] = Field(default=None, description="'IPC' or 'BNS' filter")
    multi_crime: bool = Field(default=False, description="Whether multiple crimes are involved")
    comparison_pairs: List[List[str]] = Field(
        default_factory=list,
        description="Pairs of node IDs to compare, e.g. [['IPC_302','BNS_103']]",
    )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Stage 6 — Cypher Output                                               ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class CypherQuery(BaseModel):
    """A fully constructed, parameterised Cypher query."""
    cypher: str = Field(..., description="The Cypher query string with $param placeholders")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameter bindings")
    description: str = Field(default="", description="Human-readable description of what this query does")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Stage 7 — Execution Result                                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class ExecutionResult(BaseModel):
    """Structured result from Neo4j query execution."""
    success: bool = Field(default=True)
    records: List[Dict[str, Any]] = Field(default_factory=list)
    cypher: str = Field(default="")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: float = Field(default=0.0)
    error: Optional[str] = Field(default=None)
    retries: int = Field(default=0)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Stage 8 — Final Answer                                                ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class FinalAnswer(BaseModel):
    """The complete pipeline response."""
    query: str = Field(..., description="Original user query")
    intent: LegalIntent
    extracted_entities: ExtractedEntities
    linked_entities: LinkedEntities
    query_plan: QueryPlan
    cypher_queries: List[CypherQuery] = Field(default_factory=list)
    execution_results: List[ExecutionResult] = Field(default_factory=list)
    answer: str = Field(default="", description="Natural language answer")
    total_time_ms: float = Field(default=0.0)
    stages_log: Dict[str, float] = Field(
        default_factory=dict,
        description="Stage name → time in ms",
    )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Pipeline State (mutable, passed through stages)                        ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class PipelineState(BaseModel):
    """Mutable state object flowing through the pipeline stages."""
    query: str
    intent_result: Optional[IntentResult] = None
    extracted_entities: Optional[ExtractedEntities] = None
    linked_entities: Optional[LinkedEntities] = None
    expanded_context: Optional[ExpandedContext] = None
    query_plan: Optional[QueryPlan] = None
    cypher_queries: List[CypherQuery] = Field(default_factory=list)
    execution_results: List[ExecutionResult] = Field(default_factory=list)
    answer: str = ""
    stages_log: Dict[str, float] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
