"""
Static schema definition for the Indian Law Neo4j graph.

This module is the **single source of truth** for:
  • Node labels and their properties
  • Relationship types and their properties
  • Full-text index names
  • Validation allow-lists

The CypherBuilder and CypherValidator import from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Set


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Node Definitions                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@dataclass(frozen=True)
class NodeDef:
    label: str
    properties: FrozenSet[str]
    id_property: str = "id"


NODES: Dict[str, NodeDef] = {
    "Act": NodeDef(
        label="Act",
        properties=frozenset({"code", "name"}),
        id_property="code",
    ),
    "Chapter": NodeDef(
        label="Chapter",
        properties=frozenset({"id", "act", "raw", "number", "title"}),
    ),
    "LawSection": NodeDef(
        label="LawSection",
        properties=frozenset({
            "id", "act", "section", "node_type", "title", "description", "punishment",
            "mapping_status", "cognizable", "bailable", "court",
            "category", "keywords", "aliases", "chapter_raw", "data_complete",
            "source_url",
        }),
    ),
    "Crime": NodeDef(
        label="Crime",
        properties=frozenset({"id", "name"}),
    ),
    "Punishment": NodeDef(
        label="Punishment",
        properties=frozenset({"id", "text"}),
    ),
    "Keyword": NodeDef(
        label="Keyword",
        properties=frozenset({"id", "name"}),
    ),
    "LegalRule": NodeDef(
        label="LegalRule",
        properties=frozenset({"id", "relationship", "condition", "confidence"}),
    ),
}

VALID_LABELS: FrozenSet[str] = frozenset(NODES.keys())


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Relationship Definitions                                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@dataclass(frozen=True)
class RelDef:
    rel_type: str
    source_label: str
    target_label: str
    properties: FrozenSet[str] = frozenset()


RELATIONSHIPS: Dict[str, RelDef] = {
    "HAS_CHAPTER": RelDef("HAS_CHAPTER", "Act", "Chapter"),
    "HAS_SECTION": RelDef("HAS_SECTION", "Act", "LawSection"),  # also Chapter->LawSection
    "HAS_SUBSECTION": RelDef("HAS_SUBSECTION", "LawSection", "LawSection", frozenset({"level"})),
    "HAS_CLAUSE": RelDef("HAS_CLAUSE", "LawSection", "LawSection", frozenset({"level"})),
    "HAS_EXPLANATION": RelDef("HAS_EXPLANATION", "LawSection", "LawSection", frozenset({"type"})),
    "HAS_ILLUSTRATION": RelDef("HAS_ILLUSTRATION", "LawSection", "LawSection", frozenset({"type"})),
    "HAS_EXCEPTION": RelDef("HAS_EXCEPTION", "LawSection", "LawSection", frozenset({"type"})),
    "HAS_PROVISO": RelDef("HAS_PROVISO", "LawSection", "LawSection", frozenset({"type"})),
    "DEFINED_BY": RelDef("DEFINED_BY", "Crime", "LawSection"),
    "HAS_PUNISHMENT": RelDef("HAS_PUNISHMENT", "LawSection", "Punishment"),
    "HAS_KEYWORD": RelDef("HAS_KEYWORD", "LawSection", "Keyword"),
    "REPLACED_BY": RelDef(
        "REPLACED_BY", "LawSection", "LawSection",
        frozenset({"note", "status", "mapping_type", "official_mapping", "effective_date", "mapping_status", "amendment_type", "provenance"}),
    ),
    "REPLACES": RelDef(
        "REPLACES", "LawSection", "LawSection",
        frozenset({"note", "status", "mapping_type", "official_mapping", "effective_date", "mapping_status", "amendment_type", "provenance"}),
    ),
    "MORE_SPECIFIC_THAN": RelDef("MORE_SPECIFIC_THAN", "LawSection", "LawSection"),
    "OVERRIDES": RelDef("OVERRIDES", "LawSection", "LawSection"),
    "ENHANCES": RelDef("ENHANCES", "LawSection", "LawSection"),
    "INCLUDES_ELEMENTS_OF": RelDef("INCLUDES_ELEMENTS_OF", "LawSection", "LawSection"),
    "CANNOT_COEXIST_WITH": RelDef("CANNOT_COEXIST_WITH", "LawSection", "LawSection"),
    "APPLIES_FROM": RelDef("APPLIES_FROM", "LegalRule", "LawSection"),
    "APPLIES_TO": RelDef("APPLIES_TO", "LegalRule", "LawSection"),
}

VALID_RELATIONSHIPS: FrozenSet[str] = frozenset(RELATIONSHIPS.keys())

# Subset used for graph expansion
EXPANSION_RELATIONSHIPS: List[str] = [
    "HAS_SUBSECTION",
    "HAS_CLAUSE",
    "HAS_EXPLANATION",
    "HAS_ILLUSTRATION",
    "HAS_EXCEPTION",
    "HAS_PROVISO",
    "MORE_SPECIFIC_THAN",
    "OVERRIDES",
    "ENHANCES",
    "INCLUDES_ELEMENTS_OF",
    "REPLACED_BY",
    "REPLACES",
    "CANNOT_COEXIST_WITH",
    "DEFINED_BY",
]


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Full-text Indexes                                                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@dataclass(frozen=True)
class FulltextIndex:
    name: str
    label: str
    properties: List[str]


FULLTEXT_INDEXES: Dict[str, FulltextIndex] = {
    "crimeName": FulltextIndex(
        name="crimeName",
        label="Crime",
        properties=["name"],
    ),
    "lawSectionText": FulltextIndex(
        name="lawSectionText",
        label="LawSection",
        properties=["title", "description", "keywords", "aliases", "punishment"],
    ),
}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Forbidden / Guard Lists                                               ║
# ╚══════════════════════════════════════════════════════════════════════════╝

FORBIDDEN_LABELS: FrozenSet[str] = frozenset({
    "User", "Admin", "Session", "Token",  # not in our graph
})

FORBIDDEN_OPERATIONS: FrozenSet[str] = frozenset({
    "DELETE", "DETACH DELETE", "REMOVE", "DROP", "CREATE", "SET", "MERGE",
})


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Schema Summary (for LLM prompts)                                      ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def get_schema_summary() -> str:
    """Return a concise text summary of the graph schema for use in LLM prompts."""
    lines: List[str] = ["Graph Schema:", ""]

    lines.append("Nodes:")
    for nd in NODES.values():
        props = ", ".join(sorted(nd.properties))
        lines.append(f"  {nd.label} {{{props}}}")

    lines.append("")
    lines.append("Relationships:")
    for rd in RELATIONSHIPS.values():
        props = ""
        if rd.properties:
            props = " {" + ", ".join(sorted(rd.properties)) + "}"
        lines.append(f"  ({rd.source_label})-[:{rd.rel_type}{props}]->({rd.target_label})")

    lines.append("")
    lines.append("Full-text Indexes:")
    for fi in FULLTEXT_INDEXES.values():
        lines.append(f"  {fi.name} → {fi.label}({', '.join(fi.properties)})")

    return "\n".join(lines)
