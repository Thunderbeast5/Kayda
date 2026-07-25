"""
Entity Linker — Stage 3 of the Text-to-Cypher pipeline.

Resolves extracted entities against the Neo4j graph using full-text
indexes (crimeName, lawSectionText) and direct ID lookups.

Never relies on exact string equality.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from ..schemas.models import (
    ExtractedEntities,
    LinkedEntities,
    LinkedNode,
)
from ..utils.neo4j_utils import (
    fulltext_search_crimes,
    fulltext_search_sections,
    find_section_by_number,
    run_cypher,
)
from ..utils.query_cache import (
    cache_entity_linking,
    get_cached_entity_linking,
)

logger = logging.getLogger(__name__)


def _section_number_to_id(act: str, section: str) -> str:
    """Build a canonical Neo4j node id like 'IPC_302'."""
    # Strip non-alphanumeric except trailing letters (e.g. '120A')
    cleaned = re.sub(r"[^0-9A-Za-z]", "", section.strip())
    return f"{act.upper()}_{cleaned}"


def _link_crime(crime_name: str) -> List[LinkedNode]:
    """Resolve a crime name via fulltext search."""
    cached = get_cached_entity_linking(f"crime:{crime_name}")
    if cached is not None:
        return cached

    results = fulltext_search_crimes(crime_name, limit=5, min_score=0.3)
    nodes = [
        LinkedNode(
            node_id=r["node_id"],
            label="Crime",
            name=r.get("name", ""),
            score=r.get("score", 0.0),
        )
        for r in results
    ]

    cache_entity_linking(f"crime:{crime_name}", nodes)
    return nodes


def _link_section_by_number(act: str, section: str) -> Optional[LinkedNode]:
    """Resolve a section by its act + number via direct lookup."""
    cache_key = f"section:{act}:{section}"
    cached = get_cached_entity_linking(cache_key)
    if cached is not None:
        return cached

    result = find_section_by_number(act, section)
    if result is None:
        return None

    node = LinkedNode(
        node_id=result["node_id"],
        label="LawSection",
        name=result.get("title", ""),
        score=1.0,
        properties={
            k: v for k, v in result.items()
            if k not in {"node_id", "label"} and v is not None
        },
    )
    cache_entity_linking(cache_key, node)
    return node


def _link_section_by_text(search_term: str) -> List[LinkedNode]:
    """Resolve a section via fulltext search on lawSectionText."""
    cached = get_cached_entity_linking(f"section_text:{search_term}")
    if cached is not None:
        return cached

    results = fulltext_search_sections(search_term, limit=5, min_score=0.3)
    nodes = [
        LinkedNode(
            node_id=r["node_id"],
            label="LawSection",
            name=r.get("title", ""),
            score=r.get("score", 0.0),
            properties={
                k: v for k, v in r.items()
                if k not in {"node_id", "label", "score"} and v is not None
            },
        )
        for r in results
    ]

    cache_entity_linking(f"section_text:{search_term}", nodes)
    return nodes


def _link_keyword(keyword: str) -> List[LinkedNode]:
    """Resolve a keyword against Keyword nodes."""
    cypher = """
    MATCH (k:Keyword)
    WHERE toLower(k.name) CONTAINS toLower($kw)
    RETURN k.id AS node_id, k.name AS name, 'Keyword' AS label
    LIMIT 5
    """
    results = run_cypher(cypher, {"kw": keyword})
    return [
        LinkedNode(
            node_id=r["node_id"],
            label="Keyword",
            name=r.get("name", ""),
            score=1.0,
        )
        for r in results
    ]


def link_entities(entities: ExtractedEntities) -> LinkedEntities:
    """
    Resolve all extracted entities against the Neo4j graph.

    Uses fulltext indexes for fuzzy matching and direct ID lookups
    for explicit section references.

    Parameters
    ----------
    entities : ExtractedEntities
        Output of the entity extractor.

    Returns
    -------
    LinkedEntities
        Canonical graph nodes for each entity.
    """
    logger.info("Linking entities to graph nodes...")

    crime_nodes: List[LinkedNode] = []
    section_nodes: List[LinkedNode] = []
    keyword_nodes: List[LinkedNode] = []
    raw_matches: Dict[str, List[LinkedNode]] = {}

    # 1. Link crimes via fulltext
    for crime in entities.crimes:
        nodes = _link_crime(crime)
        crime_nodes.extend(nodes)
        raw_matches[f"crime:{crime}"] = nodes
        logger.debug("Crime '%s' → %d matches", crime, len(nodes))

    # 2. Link IPC sections by number
    for sec in entities.ipc_sections:
        node = _link_section_by_number("IPC", sec)
        if node:
            section_nodes.append(node)
            raw_matches[f"ipc:{sec}"] = [node]
            logger.debug("IPC section %s → %s", sec, node.node_id)
        else:
            # Fallback: try fulltext
            fallback = _link_section_by_text(f"Section {sec} IPC")
            section_nodes.extend(fallback)
            raw_matches[f"ipc:{sec}"] = fallback
            logger.debug("IPC section %s (fulltext fallback) → %d matches", sec, len(fallback))

    # 3. Link BNS sections by number
    for sec in entities.bns_sections:
        node = _link_section_by_number("BNS", sec)
        if node:
            section_nodes.append(node)
            raw_matches[f"bns:{sec}"] = [node]
            logger.debug("BNS section %s → %s", sec, node.node_id)
        else:
            fallback = _link_section_by_text(f"Section {sec} BNS")
            section_nodes.extend(fallback)
            raw_matches[f"bns:{sec}"] = fallback
            logger.debug("BNS section %s (fulltext fallback) → %d matches", sec, len(fallback))

    # 4. Link keywords
    for kw in entities.keywords:
        nodes = _link_keyword(kw)
        keyword_nodes.extend(nodes)
        raw_matches[f"keyword:{kw}"] = nodes

    # 5. Link legal concepts via section text search
    for concept in entities.legal_concepts:
        nodes = _link_section_by_text(concept)
        section_nodes.extend(nodes)
        raw_matches[f"concept:{concept}"] = nodes

    # 6. If we have crimes linked but no sections yet, resolve Crime → LawSection via DEFINED_BY
    if crime_nodes and not section_nodes:
        crime_ids = list({n.node_id for n in crime_nodes})
        cypher = """
        UNWIND $crime_ids AS cid
        MATCH (c:Crime {id: cid})-[:DEFINED_BY]->(l:LawSection)
        RETURN l.id AS node_id, l.act AS act, l.section AS section,
               l.title AS title, l.description AS description,
               l.punishment AS punishment, 'LawSection' AS label
        """
        results = run_cypher(cypher, {"crime_ids": crime_ids})
        for r in results:
            section_nodes.append(LinkedNode(
                node_id=r["node_id"],
                label="LawSection",
                name=r.get("title", ""),
                score=0.9,
                properties={k: v for k, v in r.items() if k not in {"node_id", "label"} and v is not None},
            ))

    # Deduplicate
    crime_nodes = _deduplicate(crime_nodes)
    section_nodes = _deduplicate(section_nodes)
    keyword_nodes = _deduplicate(keyword_nodes)

    result = LinkedEntities(
        crime_nodes=crime_nodes,
        section_nodes=section_nodes,
        keyword_nodes=keyword_nodes,
        raw_matches=raw_matches,
    )

    logger.info(
        "Linked: %d crimes, %d sections, %d keywords",
        len(result.crime_nodes), len(result.section_nodes), len(result.keyword_nodes),
    )
    return result


def _deduplicate(nodes: List[LinkedNode]) -> List[LinkedNode]:
    """Remove duplicate nodes, keeping the highest score for each node_id."""
    seen: Dict[str, LinkedNode] = {}
    for n in nodes:
        if n.node_id not in seen or n.score > seen[n.node_id].score:
            seen[n.node_id] = n
    return list(seen.values())
