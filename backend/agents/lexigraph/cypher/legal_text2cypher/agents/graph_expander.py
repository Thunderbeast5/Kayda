"""
Graph Expander — Stage 4 of the Text-to-Cypher pipeline.

Expands linked entities using legal relationships:
  MORE_SPECIFIC_THAN, OVERRIDES, ENHANCES, INCLUDES_ELEMENTS_OF,
  REPLACED_BY, REPLACES, CANNOT_COEXIST_WITH, DEFINED_BY

Returns enriched context for the planner.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Set

from ..schemas.models import (
    ExpandedContext,
    ExpandedRelation,
    LinkedEntities,
    LinkedNode,
)
from ..utils.neo4j_utils import run_cypher
from ..utils.schema_loader import EXPANSION_RELATIONSHIPS

logger = logging.getLogger(__name__)


def _expand_section(
    section_id: str,
    rel_types: List[str],
    visited: Set[str],
    depth: int = 1,
    max_depth: int = 2,
) -> tuple[List[ExpandedRelation], List[LinkedNode]]:
    """
    Expand a single section node outward through specified relationship types.

    Returns (relations, discovered_nodes).
    """
    if depth > max_depth or section_id in visited:
        return [], []

    visited.add(section_id)

    # Build a multi-relationship Cypher pattern
    rel_filter = "|".join(rel_types)

    cypher = f"""
    MATCH (source:LawSection {{id: $sid}})-[r:{rel_filter}]->(target:LawSection)
    RETURN source.id     AS source_id,
           target.id     AS target_id,
           type(r)       AS rel_type,
           properties(r) AS rel_props,
           target.title  AS target_title,
           target.act    AS target_act,
           target.section AS target_section,
           target.description AS target_description,
           target.punishment  AS target_punishment
    """
    rows = run_cypher(cypher, {"sid": section_id})

    relations: List[ExpandedRelation] = []
    discovered: List[LinkedNode] = []

    for row in rows:
        tid = row["target_id"]

        relations.append(ExpandedRelation(
            source_id=row["source_id"],
            target_id=tid,
            relationship=row["rel_type"],
            properties=row.get("rel_props", {}),
        ))

        discovered.append(LinkedNode(
            node_id=tid,
            label="LawSection",
            name=row.get("target_title", ""),
            score=0.8,
            properties={
                k: row.get(k)
                for k in ("target_act", "target_section", "target_description", "target_punishment")
                if row.get(k) is not None
            },
        ))

        # Recurse
        if depth < max_depth and tid not in visited:
            sub_rels, sub_nodes = _expand_section(tid, rel_types, visited, depth + 1, max_depth)
            relations.extend(sub_rels)
            discovered.extend(sub_nodes)

    # Also expand incoming relationships
    cypher_in = f"""
    MATCH (source:LawSection)-[r:{rel_filter}]->(target:LawSection {{id: $sid}})
    RETURN source.id     AS source_id,
           target.id     AS target_id,
           type(r)       AS rel_type,
           properties(r) AS rel_props,
           source.title  AS source_title,
           source.act    AS source_act,
           source.section AS source_section
    """
    rows_in = run_cypher(cypher_in, {"sid": section_id})

    for row in rows_in:
        sid_found = row["source_id"]

        relations.append(ExpandedRelation(
            source_id=sid_found,
            target_id=row["target_id"],
            relationship=row["rel_type"],
            properties=row.get("rel_props", {}),
        ))

        discovered.append(LinkedNode(
            node_id=sid_found,
            label="LawSection",
            name=row.get("source_title", ""),
            score=0.7,
            properties={
                k: row.get(k)
                for k in ("source_act", "source_section")
                if row.get(k) is not None
            },
        ))

    return relations, discovered


def _get_punishments(section_ids: List[str]) -> List[LinkedNode]:
    """Fetch Punishment nodes linked to the given sections."""
    if not section_ids:
        return []

    cypher = """
    UNWIND $sids AS sid
    MATCH (l:LawSection {id: sid})-[:HAS_PUNISHMENT]->(p:Punishment)
    RETURN p.id   AS node_id,
           p.text AS name,
           'Punishment' AS label,
           l.id   AS source_section
    """
    rows = run_cypher(cypher, {"sids": section_ids})
    return [
        LinkedNode(
            node_id=r.get("node_id") or f"PUN_{r.get('source_section', 'UNKNOWN')}",
            label="Punishment",
            name=r.get("name") or r.get("source_section") or "Punishment",
            score=1.0,
            properties={"source_section": r.get("source_section", "")},
        )
        for r in rows
    ]


def _get_replacements(section_ids: List[str]) -> tuple[List[ExpandedRelation], List[LinkedNode]]:
    """Fetch IPC↔BNS replacement mappings for the given sections."""
    if not section_ids:
        return [], []

    cypher = """
    UNWIND $sids AS sid
    MATCH (l:LawSection {id: sid})-[r:REPLACED_BY]->(b:LawSection)
    RETURN l.id AS source_id,
           b.id AS target_id,
           'REPLACED_BY' AS rel_type,
           properties(r) AS rel_props,
           b.title AS target_title,
           b.act AS target_act,
           b.section AS target_section,
           b.description AS target_description,
           b.punishment AS target_punishment
    UNION
    UNWIND $sids AS sid
    MATCH (l:LawSection {id: sid})-[r:REPLACES]->(i:LawSection)
    RETURN l.id AS source_id,
           i.id AS target_id,
           'REPLACES' AS rel_type,
           properties(r) AS rel_props,
           i.title AS target_title,
           i.act AS target_act,
           i.section AS target_section,
           i.description AS target_description,
           i.punishment AS target_punishment
    """
    rows = run_cypher(cypher, {"sids": section_ids})

    relations: List[ExpandedRelation] = []
    nodes: List[LinkedNode] = []

    for row in rows:
        relations.append(ExpandedRelation(
            source_id=row["source_id"],
            target_id=row["target_id"],
            relationship=row["rel_type"],
            properties=row.get("rel_props", {}),
        ))
        nodes.append(LinkedNode(
            node_id=row["target_id"],
            label="LawSection",
            name=row.get("target_title", ""),
            score=0.9,
            properties={
                k: row.get(k)
                for k in ("target_act", "target_section", "target_description", "target_punishment")
                if row.get(k) is not None
            },
        ))

    return relations, nodes


def expand_graph(linked: LinkedEntities, max_depth: int = 2) -> ExpandedContext:
    """
    Expand linked entities through legal relationships.

    Parameters
    ----------
    linked : LinkedEntities
        Output of the entity linker.
    max_depth : int
        Maximum traversal depth.

    Returns
    -------
    ExpandedContext
        Enriched context with relationships and discovered nodes.
    """
    logger.info("Expanding graph context (max_depth=%d)...", max_depth)

    all_relations: List[ExpandedRelation] = []
    all_related_sections: List[LinkedNode] = []
    visited: Set[str] = set()

    section_ids = [n.node_id for n in linked.section_nodes]

    # 1. Expand through legal relationships
    for section_id in section_ids:
        rels, nodes = _expand_section(
            section_id,
            EXPANSION_RELATIONSHIPS,
            visited,
            depth=1,
            max_depth=max_depth,
        )
        all_relations.extend(rels)
        all_related_sections.extend(nodes)

    # 2. Get replacement mappings
    replacement_rels, replacement_nodes = _get_replacements(section_ids)
    all_relations.extend(replacement_rels)

    # 3. Get punishment nodes
    all_section_ids = section_ids + [n.node_id for n in replacement_nodes]
    punishment_nodes = _get_punishments(list(set(all_section_ids)))

    # Deduplicate
    seen_rels: Dict[str, ExpandedRelation] = {}
    for r in all_relations:
        key = f"{r.source_id}|{r.relationship}|{r.target_id}"
        seen_rels[key] = r

    seen_nodes: Dict[str, LinkedNode] = {}
    for n in all_related_sections + replacement_nodes:
        if n.node_id not in seen_nodes or n.score > seen_nodes[n.node_id].score:
            seen_nodes[n.node_id] = n

    result = ExpandedContext(
        linked=linked,
        relations=list(seen_rels.values()),
        replacement_sections=replacement_nodes,
        punishment_nodes=punishment_nodes,
        related_sections=list(seen_nodes.values()),
    )

    logger.info(
        "Expanded: %d relations, %d replacement sections, %d punishments, %d related sections",
        len(result.relations),
        len(result.replacement_sections),
        len(result.punishment_nodes),
        len(result.related_sections),
    )
    return result
