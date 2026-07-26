"""
Deterministic Cypher Builder — Stage 6 of the Text-to-Cypher pipeline.

PURE PYTHON.  NO LLM.

Reads the QueryPlan JSON and generates parameterised, case-insensitive
Cypher queries using templates.  Every query uses parameterised variables
($param) to prevent injection and improve plan-cache hit rate.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..schemas.models import CypherQuery, LegalIntent, QueryPlan

logger = logging.getLogger(__name__)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Template Helpers                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _section_return_fields(alias: str = "l", prefix: str = "") -> str:
    """Standard RETURN clause fields for a LawSection node."""
    p = f"{prefix}_" if prefix else ""
    return (
        f"{alias}.id AS {p}id, "
        f"{alias}.act AS {p}act, "
        f"{alias}.section AS {p}section, "
        f"{alias}.title AS {p}title, "
        f"{alias}.description AS {p}description, "
        f"{alias}.punishment AS {p}punishment, "
        f"{alias}.cognizable AS {p}cognizable, "
        f"{alias}.bailable AS {p}bailable, "
        f"{alias}.court AS {p}court, "
        f"{alias}.keywords AS {p}keywords, "
        f"{alias}.mapping_status AS {p}mapping_status"
    )


def _punishment_return(alias: str = "p", prefix: str = "punishment") -> str:
    return f"{alias}.id AS {prefix}_id, {alias}.text AS {prefix}_text"


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Template Builders — one per intent pattern                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _build_section_lookup(plan: QueryPlan) -> List[CypherQuery]:
    """Look up section(s) by node ID with optional punishment, keywords, chapter."""
    if not plan.linked_node_ids:
        return []

    queries: List[CypherQuery] = []

    # Main section data
    parts = [
        "UNWIND $node_ids AS nid",
        "MATCH (l:LawSection {id: nid})",
    ]

    optional_parts: List[str] = []
    return_fields = [_section_return_fields("l")]

    if plan.need_punishment:
        optional_parts.append("OPTIONAL MATCH (l)-[:HAS_PUNISHMENT]->(p:Punishment)")
        return_fields.append(_punishment_return("p"))

    if plan.need_keywords:
        optional_parts.append("OPTIONAL MATCH (l)-[:HAS_KEYWORD]->(k:Keyword)")
        return_fields.append("collect(DISTINCT k.name) AS keyword_list")

    if plan.need_chapter:
        optional_parts.append("OPTIONAL MATCH (ch:Chapter)-[:HAS_SECTION]->(l)")
        return_fields.append("ch.number AS chapter_number, ch.title AS chapter_title")

    cypher = "\n".join(parts + optional_parts + [f"RETURN {', '.join(return_fields)}"])

    queries.append(CypherQuery(
        cypher=cypher,
        parameters={"node_ids": plan.linked_node_ids},
        description=f"Section lookup for {plan.linked_node_ids}",
    ))

    return queries


def _build_crime_lookup(plan: QueryPlan) -> List[CypherQuery]:
    """Look up crimes with their defining sections and punishments."""
    queries: List[CypherQuery] = []

    if plan.linked_node_ids:
        # We have resolved section IDs — look up crimes defined by these sections
        cypher = (
            "UNWIND $node_ids AS nid\n"
            "MATCH (l:LawSection {id: nid})\n"
            "OPTIONAL MATCH (c:Crime)-[:DEFINED_BY]->(l)\n"
        )
        return_parts = [
            _section_return_fields("l"),
            "c.id AS crime_id, c.name AS crime_name",
        ]

        if plan.need_punishment:
            cypher += "OPTIONAL MATCH (l)-[:HAS_PUNISHMENT]->(p:Punishment)\n"
            return_parts.append(_punishment_return("p"))

        if plan.need_replacement:
            cypher += (
                "OPTIONAL MATCH (l)-[:REPLACED_BY]->(bns:LawSection)\n"
                "OPTIONAL MATCH (bns)-[:HAS_PUNISHMENT]->(bp:Punishment)\n"
            )
            return_parts.append(
                "bns.id AS bns_id, bns.section AS bns_section, "
                "bns.title AS bns_title, bns.punishment AS bns_punishment_text, "
                "bp.text AS bns_punishment_detail"
            )

        cypher += f"RETURN {', '.join(return_parts)}"
        queries.append(CypherQuery(
            cypher=cypher,
            parameters={"node_ids": plan.linked_node_ids},
            description=f"Crime lookup for section IDs: {plan.linked_node_ids}",
        ))

    elif plan.entities:
        # Fulltext search for each crime entity
        for entity in plan.entities:
            cypher = (
                "CALL db.index.fulltext.queryNodes('crimeName', $term) YIELD node AS c, score\n"
                "WHERE score >= 0.3\n"
                "MATCH (c)-[:DEFINED_BY]->(l:LawSection)\n"
            )
            return_parts = [
                "c.id AS crime_id, c.name AS crime_name, score",
                _section_return_fields("l"),
            ]

            if plan.need_punishment:
                cypher += "OPTIONAL MATCH (l)-[:HAS_PUNISHMENT]->(p:Punishment)\n"
                return_parts.append(_punishment_return("p"))

            if plan.need_replacement:
                cypher += "OPTIONAL MATCH (l)-[:REPLACED_BY]->(bns:LawSection)\n"
                return_parts.append(
                    "bns.id AS bns_id, bns.section AS bns_section, "
                    "bns.title AS bns_title, bns.punishment AS bns_punishment_text"
                )

            cypher += f"RETURN {', '.join(return_parts)}\nORDER BY score DESC\nLIMIT 10"
            queries.append(CypherQuery(
                cypher=cypher,
                parameters={"term": entity},
                description=f"Fulltext crime lookup for '{entity}'",
            ))

    return queries


def _build_punishment_lookup(plan: QueryPlan) -> List[CypherQuery]:
    """Get punishment details for linked sections or crime entities."""
    if plan.linked_node_ids:
        cypher = (
            "UNWIND $node_ids AS nid\n"
            "MATCH (l:LawSection {id: nid})\n"
            "OPTIONAL MATCH (l)-[:HAS_PUNISHMENT]->(p:Punishment)\n"
            "OPTIONAL MATCH (c:Crime)-[:DEFINED_BY]->(l)\n"
            f"RETURN {_section_return_fields('l')}, "
            f"{_punishment_return('p')}, "
            "c.name AS crime_name"
        )
        return [CypherQuery(
            cypher=cypher,
            parameters={"node_ids": plan.linked_node_ids},
            description=f"Punishment lookup for {plan.linked_node_ids}",
        )]

    if plan.entities:
        cypher = (
            "CALL db.index.fulltext.queryNodes('crimeName', $term) YIELD node AS c, score\n"
            "WHERE score >= 0.3\n"
            "MATCH (c)-[:DEFINED_BY]->(l:LawSection)\n"
            "OPTIONAL MATCH (l)-[:HAS_PUNISHMENT]->(p:Punishment)\n"
            f"RETURN c.name AS crime_name, score, "
            f"{_section_return_fields('l')}, "
            f"{_punishment_return('p')}\n"
            "ORDER BY score DESC\nLIMIT 10"
        )
        queries = []
        for entity in plan.entities:
            queries.append(CypherQuery(
                cypher=cypher,
                parameters={"term": entity},
                description=f"Punishment lookup for crime '{entity}'",
            ))
        return queries

    return []


def _build_ipc_to_bns(plan: QueryPlan) -> List[CypherQuery]:
    """Map IPC section(s) to their BNS replacement(s)."""
    queries: List[CypherQuery] = []

    if plan.linked_node_ids:
        # Filter to IPC sections only
        ipc_ids = [nid for nid in plan.linked_node_ids if nid.startswith("IPC_")]
        if not ipc_ids:
            ipc_ids = plan.linked_node_ids  # try all

        cypher = (
            "UNWIND $node_ids AS nid\n"
            "MATCH (ipc:LawSection {id: nid, act: 'IPC'})\n"
            "OPTIONAL MATCH (ipc)-[r:REPLACED_BY]->(bns:LawSection {act: 'BNS'})\n"
        )
        return_parts = [
            _section_return_fields("ipc", "ipc"),
            "bns.id AS bns_id, bns.section AS bns_section, "
            "bns.title AS bns_title, bns.description AS bns_description, "
            "bns.punishment AS bns_punishment",
            "r.note AS mapping_note, r.status AS mapping_status, "
            "r.bns_subsection AS bns_subsection",
        ]

        if plan.need_punishment:
            cypher += (
                "OPTIONAL MATCH (ipc)-[:HAS_PUNISHMENT]->(ip:Punishment)\n"
                "OPTIONAL MATCH (bns)-[:HAS_PUNISHMENT]->(bp:Punishment)\n"
            )
            return_parts.append("ip.text AS ipc_punishment_detail, bp.text AS bns_punishment_detail")

        cypher += f"RETURN {', '.join(return_parts)}"
        queries.append(CypherQuery(
            cypher=cypher,
            parameters={"node_ids": ipc_ids},
            description=f"IPC→BNS mapping for {ipc_ids}",
        ))

    elif plan.entities:
        for entity in plan.entities:
            cypher = (
                "CALL db.index.fulltext.queryNodes('crimeName', $term) YIELD node AS c, score\n"
                "WHERE score >= 0.3\n"
                "MATCH (c)-[:DEFINED_BY]->(ipc:LawSection {act: 'IPC'})\n"
                "OPTIONAL MATCH (ipc)-[r:REPLACED_BY]->(bns:LawSection {act: 'BNS'})\n"
                "OPTIONAL MATCH (ipc)-[:HAS_PUNISHMENT]->(ip:Punishment)\n"
                "OPTIONAL MATCH (bns)-[:HAS_PUNISHMENT]->(bp:Punishment)\n"
                f"RETURN c.name AS crime_name, score, "
                f"{_section_return_fields('ipc', 'ipc')}, "
                "bns.id AS bns_id, bns.section AS bns_section, "
                "bns.title AS bns_title, bns.description AS bns_description, "
                "bns.punishment AS bns_punishment, "
                "r.note AS mapping_note, r.status AS mapping_status, "
                "r.bns_subsection AS bns_subsection, "
                "ip.text AS ipc_punishment_detail, bp.text AS bns_punishment_detail\n"
                "ORDER BY score DESC\nLIMIT 10"
            )
            queries.append(CypherQuery(
                cypher=cypher,
                parameters={"term": entity},
                description=f"IPC→BNS mapping for crime '{entity}'",
            ))

    return queries


def _build_bns_to_ipc(plan: QueryPlan) -> List[CypherQuery]:
    """Map BNS section(s) back to their IPC predecessor(s)."""
    queries: List[CypherQuery] = []

    if plan.linked_node_ids:
        bns_ids = [nid for nid in plan.linked_node_ids if nid.startswith("BNS_")]
        if not bns_ids:
            bns_ids = plan.linked_node_ids

        cypher = (
            "UNWIND $node_ids AS nid\n"
            "MATCH (bns:LawSection {id: nid, act: 'BNS'})\n"
            "OPTIONAL MATCH (bns)-[r:REPLACES]->(ipc:LawSection {act: 'IPC'})\n"
        )
        return_parts = [
            _section_return_fields("bns", "bns"),
            "ipc.id AS ipc_id, ipc.section AS ipc_section, "
            "ipc.title AS ipc_title, ipc.description AS ipc_description, "
            "ipc.punishment AS ipc_punishment",
            "r.note AS mapping_note, r.status AS mapping_status",
        ]

        if plan.need_punishment:
            cypher += (
                "OPTIONAL MATCH (bns)-[:HAS_PUNISHMENT]->(bp:Punishment)\n"
                "OPTIONAL MATCH (ipc)-[:HAS_PUNISHMENT]->(ip:Punishment)\n"
            )
            return_parts.append("bp.text AS bns_punishment_detail, ip.text AS ipc_punishment_detail")

        cypher += f"RETURN {', '.join(return_parts)}"
        queries.append(CypherQuery(
            cypher=cypher,
            parameters={"node_ids": bns_ids},
            description=f"BNS→IPC mapping for {bns_ids}",
        ))

    return queries


def _build_keyword_lookup(plan: QueryPlan) -> List[CypherQuery]:
    """Look up sections by keyword."""
    queries: List[CypherQuery] = []

    for entity in plan.entities:
        cypher = (
            "CALL db.index.fulltext.queryNodes('lawSectionText', $term) YIELD node AS l, score\n"
            "WHERE score >= 0.3\n"
            "OPTIONAL MATCH (l)-[:HAS_KEYWORD]->(k:Keyword)\n"
            f"RETURN {_section_return_fields('l')}, "
            "score, collect(DISTINCT k.name) AS keyword_list\n"
            "ORDER BY score DESC\nLIMIT 10"
        )
        queries.append(CypherQuery(
            cypher=cypher,
            parameters={"term": entity},
            description=f"Keyword lookup for '{entity}'",
        ))

    return queries


def _build_related_offences(plan: QueryPlan) -> List[CypherQuery]:
    """Find offences related through legal relationships."""
    if not plan.linked_node_ids:
        return []

    cypher = (
        "UNWIND $node_ids AS nid\n"
        "MATCH (l:LawSection {id: nid})\n"
        "OPTIONAL MATCH (l)-[r1:MORE_SPECIFIC_THAN|OVERRIDES|ENHANCES|"
        "INCLUDES_ELEMENTS_OF|CANNOT_COEXIST_WITH]->(related:LawSection)\n"
        "OPTIONAL MATCH (related)-[:HAS_PUNISHMENT]->(rp:Punishment)\n"
        "OPTIONAL MATCH (rc:Crime)-[:DEFINED_BY]->(related)\n"
        f"RETURN {_section_return_fields('l', 'source')}, "
        "type(r1) AS relationship, "
        f"{_section_return_fields('related', 'related')}, "
        "rp.text AS related_punishment_text, "
        "rc.name AS related_crime_name"
    )
    return [CypherQuery(
        cypher=cypher,
        parameters={"node_ids": plan.linked_node_ids},
        description=f"Related offences for {plan.linked_node_ids}",
    )]


def _build_hierarchy(plan: QueryPlan) -> List[CypherQuery]:
    """Show hierarchy / specificity relationships."""
    if not plan.linked_node_ids:
        return []

    cypher = (
        "UNWIND $node_ids AS nid\n"
        "MATCH (l:LawSection {id: nid})\n"
        "OPTIONAL MATCH (l)-[r:MORE_SPECIFIC_THAN]->(general:LawSection)\n"
        "OPTIONAL MATCH (specific:LawSection)-[r2:MORE_SPECIFIC_THAN]->(l)\n"
        "OPTIONAL MATCH (l)-[r3:OVERRIDES]->(overridden:LawSection)\n"
        f"RETURN {_section_return_fields('l', 'source')}, "
        "general.id AS more_general_id, general.title AS more_general_title, "
        "specific.id AS more_specific_id, specific.title AS more_specific_title, "
        "overridden.id AS overridden_id, overridden.title AS overridden_title"
    )
    return [CypherQuery(
        cypher=cypher,
        parameters={"node_ids": plan.linked_node_ids},
        description=f"Hierarchy lookup for {plan.linked_node_ids}",
    )]


def _build_comparison(plan: QueryPlan) -> List[CypherQuery]:
    """Compare two or more sections side by side."""
    if not plan.linked_node_ids or len(plan.linked_node_ids) < 2:
        return _build_section_lookup(plan)

    cypher = (
        "UNWIND $node_ids AS nid\n"
        "MATCH (l:LawSection {id: nid})\n"
        "OPTIONAL MATCH (l)-[:HAS_PUNISHMENT]->(p:Punishment)\n"
        "OPTIONAL MATCH (l)-[:HAS_KEYWORD]->(k:Keyword)\n"
        "OPTIONAL MATCH (c:Crime)-[:DEFINED_BY]->(l)\n"
        f"RETURN {_section_return_fields('l')}, "
        f"{_punishment_return('p')}, "
        "collect(DISTINCT k.name) AS keyword_list, "
        "c.name AS crime_name\n"
        "ORDER BY l.act, l.section"
    )
    return [CypherQuery(
        cypher=cypher,
        parameters={"node_ids": plan.linked_node_ids},
        description=f"Comparison of {plan.linked_node_ids}",
    )]


def _build_multiple_crimes(plan: QueryPlan) -> List[CypherQuery]:
    """
    Handle multi-crime queries with a single optimised query
    instead of multiple independent queries.
    """
    queries: List[CypherQuery] = []

    if plan.linked_node_ids:
        cypher = (
            "UNWIND $node_ids AS nid\n"
            "MATCH (l:LawSection {id: nid})\n"
            "OPTIONAL MATCH (c:Crime)-[:DEFINED_BY]->(l)\n"
            "OPTIONAL MATCH (l)-[:HAS_PUNISHMENT]->(p:Punishment)\n"
            "OPTIONAL MATCH (l)-[:REPLACED_BY]->(bns:LawSection {act: 'BNS'})\n"
            "OPTIONAL MATCH (bns)-[:HAS_PUNISHMENT]->(bp:Punishment)\n"
            "OPTIONAL MATCH (l)-[rel:MORE_SPECIFIC_THAN|OVERRIDES|ENHANCES|"
            "INCLUDES_ELEMENTS_OF|CANNOT_COEXIST_WITH]->(related:LawSection)\n"
            f"RETURN {_section_return_fields('l')}, "
            "c.name AS crime_name, "
            f"{_punishment_return('p')}, "
            "bns.id AS bns_id, bns.section AS bns_section, "
            "bns.title AS bns_title, bp.text AS bns_punishment_text, "
            "type(rel) AS rel_to_related, related.id AS related_id, "
            "related.title AS related_title"
        )
        queries.append(CypherQuery(
            cypher=cypher,
            parameters={"node_ids": plan.linked_node_ids},
            description=f"Multi-crime lookup for {plan.linked_node_ids}",
        ))

    elif plan.entities:
        # Single optimised fulltext query for all crime entities
        for entity in plan.entities:
            cypher = (
                "CALL db.index.fulltext.queryNodes('crimeName', $term) YIELD node AS c, score\n"
                "WHERE score >= 0.3\n"
                "MATCH (c)-[:DEFINED_BY]->(l:LawSection)\n"
                "OPTIONAL MATCH (l)-[:HAS_PUNISHMENT]->(p:Punishment)\n"
                "OPTIONAL MATCH (l)-[:REPLACED_BY]->(bns:LawSection {act: 'BNS'})\n"
                "OPTIONAL MATCH (bns)-[:HAS_PUNISHMENT]->(bp:Punishment)\n"
                f"RETURN c.name AS crime_name, score, "
                f"{_section_return_fields('l')}, "
                f"{_punishment_return('p')}, "
                "bns.id AS bns_id, bns.section AS bns_section, "
                "bns.title AS bns_title, bp.text AS bns_punishment_text\n"
                "ORDER BY score DESC\nLIMIT 15"
            )
            queries.append(CypherQuery(
                cypher=cypher,
                parameters={"term": entity},
                description=f"Multi-crime fulltext for '{entity}'",
            ))

    return queries


def _build_graph_reasoning(plan: QueryPlan) -> List[CypherQuery]:
    """General graph reasoning — traverse all relationship types."""
    if not plan.linked_node_ids:
        return []

    cypher = (
        "UNWIND $node_ids AS nid\n"
        "MATCH (l:LawSection {id: nid})\n"
        "OPTIONAL MATCH (l)-[r]->(target)\n"
        "OPTIONAL MATCH (source)-[r2]->(l)\n"
        f"RETURN {_section_return_fields('l', 'center')}, "
        "type(r) AS outgoing_rel, labels(target)[0] AS outgoing_label, "
        "CASE WHEN target IS NOT NULL THEN coalesce(target.id, target.name, target.code) END AS outgoing_id, "
        "type(r2) AS incoming_rel, labels(source)[0] AS incoming_label, "
        "CASE WHEN source IS NOT NULL THEN coalesce(source.id, source.name, source.code) END AS incoming_id"
    )
    return [CypherQuery(
        cypher=cypher,
        parameters={"node_ids": plan.linked_node_ids},
        description=f"Graph reasoning for {plan.linked_node_ids}",
    )]


def _build_punishment_comparison(plan: QueryPlan) -> List[CypherQuery]:
    """Compare punishments across multiple sections."""
    return _build_comparison(plan)


def _build_legal_explanation(plan: QueryPlan) -> List[CypherQuery]:
    """Get full details for legal explanation."""
    queries: List[CypherQuery] = []

    if plan.linked_node_ids:
        # Full section detail
        cypher = (
            "UNWIND $node_ids AS nid\n"
            "MATCH (l:LawSection {id: nid})\n"
            "OPTIONAL MATCH (c:Crime)-[:DEFINED_BY]->(l)\n"
            "OPTIONAL MATCH (l)-[:HAS_PUNISHMENT]->(p:Punishment)\n"
            "OPTIONAL MATCH (l)-[:HAS_KEYWORD]->(k:Keyword)\n"
            "OPTIONAL MATCH (ch:Chapter)-[:HAS_SECTION]->(l)\n"
            "OPTIONAL MATCH (l)-[:REPLACED_BY]->(bns:LawSection)\n"
            "OPTIONAL MATCH (l)-[:REPLACES]->(ipc:LawSection)\n"
            f"RETURN {_section_return_fields('l')}, "
            "c.name AS crime_name, "
            f"{_punishment_return('p')}, "
            "collect(DISTINCT k.name) AS keyword_list, "
            "ch.number AS chapter_number, ch.title AS chapter_title, "
            "bns.id AS replaced_by_id, bns.title AS replaced_by_title, "
            "ipc.id AS replaces_id, ipc.title AS replaces_title"
        )
        queries.append(CypherQuery(
            cypher=cypher,
            parameters={"node_ids": plan.linked_node_ids},
            description=f"Legal explanation for {plan.linked_node_ids}",
        ))

    elif plan.entities:
        for entity in plan.entities:
            cypher = (
                "CALL db.index.fulltext.queryNodes('lawSectionText', $term) YIELD node AS l, score\n"
                "WHERE score >= 0.3\n"
                "OPTIONAL MATCH (c:Crime)-[:DEFINED_BY]->(l)\n"
                "OPTIONAL MATCH (l)-[:HAS_PUNISHMENT]->(p:Punishment)\n"
                "OPTIONAL MATCH (l)-[:HAS_KEYWORD]->(k:Keyword)\n"
                f"RETURN {_section_return_fields('l')}, "
                "score, c.name AS crime_name, "
                f"{_punishment_return('p')}, "
                "collect(DISTINCT k.name) AS keyword_list\n"
                "ORDER BY score DESC\nLIMIT 10"
            )
            queries.append(CypherQuery(
                cypher=cypher,
                parameters={"term": entity},
                description=f"Legal explanation fulltext for '{entity}'",
            ))

    return queries


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Intent → Builder Dispatch                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝

_INTENT_BUILDERS = {
    LegalIntent.PUNISHMENT: _build_punishment_lookup,
    LegalIntent.IPC_TO_BNS: _build_ipc_to_bns,
    LegalIntent.BNS_TO_IPC: _build_bns_to_ipc,
    LegalIntent.SECTION_LOOKUP: _build_section_lookup,
    LegalIntent.CRIME_LOOKUP: _build_crime_lookup,
    LegalIntent.KEYWORD_LOOKUP: _build_keyword_lookup,
    LegalIntent.LEGAL_EXPLANATION: _build_legal_explanation,
    LegalIntent.GRAPH_REASONING: _build_graph_reasoning,
    LegalIntent.RELATED_OFFENCES: _build_related_offences,
    LegalIntent.MULTIPLE_CRIMES: _build_multiple_crimes,
    LegalIntent.COMPARISON: _build_comparison,
    LegalIntent.HIERARCHY: _build_hierarchy,
    LegalIntent.PUNISHMENT_COMPARISON: _build_punishment_comparison,
}


def build_cypher(plan: QueryPlan) -> List[CypherQuery]:
    """
    Build deterministic parameterised Cypher queries from a QueryPlan.

    This function is PURE PYTHON — no LLM is used.

    Parameters
    ----------
    plan : QueryPlan
        The JSON query specification from the planner.

    Returns
    -------
    List[CypherQuery]
        One or more ready-to-execute Cypher queries.
    """
    logger.info("Building Cypher for intent=%s", plan.intent.value)

    builder = _INTENT_BUILDERS.get(plan.intent)
    if builder is None:
        logger.warning("No builder for intent=%s, falling back to section lookup", plan.intent.value)
        builder = _build_section_lookup

    queries = builder(plan)

    if not queries:
        logger.warning("Builder produced no queries, attempting general lookup")
        queries = _build_legal_explanation(plan)

    for i, q in enumerate(queries):
        logger.info("Cypher query %d: %s", i, q.cypher[:200])
        logger.debug("Parameters: %s", q.parameters)

    return queries
