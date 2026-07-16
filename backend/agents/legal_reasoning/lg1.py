"""
Multi-crime IPC/BNS legal reasoning engine.

Pipeline:
1. Groq extracts structured incident facts and legal events.
2. Each event is normalized to a crime concept.
3. Pinecone retrieves semantic candidates per event.
4. Neo4j enriches candidates with section metadata, mappings, punishments,
   and deterministic rule relationships.
5. A rule engine dedupes, prefers specific sections, keeps legally
   compatible multi-crime sections, ranks, and explains the result.

This module is usable as an import or as a CLI:
    python backend/agents/legal_reasoning/lg1.py "A person robbed a jewellery shop, shot the owner, and the owner later died."
    python backend/agents/legal_reasoning/lg1.py --json "..."
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent.parent
PROJECT_DIR = BACKEND_DIR.parent

for env_path in (
    BACKEND_DIR / ".env",
    PROJECT_DIR / ".env",
    BASE_DIR / ".env",
    Path(".env"),
):
    if env_path.exists():
        load_dotenv(env_path)
        break
else:
    load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-sections-v2")
EMBEDDING_MODEL = os.getenv("LEXIGRAPH_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class LegalEvent:
    event_id: str
    description: str
    normalized_crime: str
    legal_concepts: list[str] = field(default_factory=list)
    supporting_facts: list[str] = field(default_factory=list)


@dataclass
class SectionCandidate:
    law_id: str
    act: str
    section: str
    title: str = ""
    description: str = ""
    punishment: str = ""
    cognizable: str = ""
    bailable: str = ""
    court: str = ""
    chapter: str = ""
    category: str = ""
    mapping_status: str = ""
    equivalent_act: str = ""
    equivalent_section: str = ""
    retrieval_score: float = 0.0
    rule_score: float = 0.0
    graph_score: float = 0.0
    confidence: float = 0.0
    sources: set[str] = field(default_factory=set)
    supporting_events: list[LegalEvent] = field(default_factory=list)
    graph_relationships: list[dict[str, Any]] = field(default_factory=list)
    rule_notes: list[str] = field(default_factory=list)
    removed: bool = False
    removal_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "law_id": self.law_id,
            "act": self.act,
            "section": self.section,
            "title": self.title,
            "description": self.description,
            "punishment": self.punishment,
            "cognizable": self.cognizable,
            "bailable": self.bailable,
            "court": self.court,
            "chapter": self.chapter,
            "category": self.category,
            "mapping_status": self.mapping_status,
            "equivalent_act": self.equivalent_act,
            "equivalent_section": self.equivalent_section,
            "confidence": round(self.confidence, 4),
            "score_breakdown": {
                "retrieval": round(self.retrieval_score, 4),
                "rules": round(self.rule_score, 4),
                "graph": round(self.graph_score, 4),
            },
            "sources": sorted(self.sources),
            "supporting_events": [
                {
                    "event_id": e.event_id,
                    "description": e.description,
                    "normalized_crime": e.normalized_crime,
                }
                for e in self.supporting_events
            ],
            "graph_relationships": self.graph_relationships,
            "rule_notes": self.rule_notes,
            "why_it_applies": build_section_explanation(self),
        }


# ---------------------------------------------------------------------------
# Lazy clients
# ---------------------------------------------------------------------------
_groq_client = None
_embedder = None
_pinecone_index = None
_neo4j_driver = None


def _groq():
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set.")
        from groq import Groq

        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def _embed(texts: list[str]) -> list[list[float]]:
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder.encode(texts, convert_to_numpy=True).tolist()


def _pinecone():
    global _pinecone_index
    if _pinecone_index is None:
        if not PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY is not set.")
        from pinecone import Pinecone

        _pinecone_index = Pinecone(api_key=PINECONE_API_KEY).Index(PINECONE_INDEX_NAME)
    return _pinecone_index


def _neo4j():
    global _neo4j_driver
    if _neo4j_driver is None:
        if not NEO4J_URI or not NEO4J_PASSWORD:
            raise RuntimeError("Neo4j credentials are not set.")
        from neo4j import GraphDatabase

        _neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _neo4j_driver


def _neo4j_run(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with _neo4j().session(database=NEO4J_DATABASE) as session:
        return [dict(record) for record in session.run(cypher, params or {})]


# ---------------------------------------------------------------------------
# Incident understanding
# ---------------------------------------------------------------------------
INCIDENT_SCHEMA = {
    "accused": "",
    "victim": "",
    "actions": [],
    "weapons": [],
    "property": [],
    "intent": "",
    "outcome": "",
    "events": [
        {
            "description": "",
            "normalized_crime": "",
            "legal_concepts": [],
            "supporting_facts": [],
        }
    ],
}


EXTRACTION_PROMPT = f"""
You are an Indian criminal law incident extraction system for IPC and BNS retrieval.
Return only valid JSON. Do not cite section numbers.

Extract:
- accused
- victim
- actions
- weapons
- property
- intent
- outcome
- events

Each event must be a distinct legally relevant act. Normalize each event to a
standard crime concept such as Robbery, Murder, Criminal intimidation,
Kidnapping, Theft, Cheating, Forgery, Hurt, Grievous hurt, Rape, Dacoity,
Extortion, Trespass, Mischief, or Culpable homicide.

JSON shape:
{json.dumps(INCIDENT_SCHEMA, indent=2)}
"""


_CONNECTOR_RE = re.compile(
    r"\b(?:and then|then|thereafter|subsequently|later|after|before|while|during)\b|[.;]",
    flags=re.IGNORECASE,
)

_CRIME_NORMALIZATION = [
    ("robbery", ("robbed", "robbery", "loot", "looted", "snatch", "gunpoint")),
    ("dacoity", ("dacoity", "five persons", "five or more", "gang robbery")),
    ("murder", ("murder", "killed", "shot dead", "stabbed to death", "died", "death")),
    ("culpable homicide", ("homicide", "caused death", "fatal injury")),
    ("criminal intimidation", ("threat", "threatened", "intimidation", "blackmail")),
    ("kidnapping", ("kidnap", "kidnapped", "abduct", "abducted", "hostage")),
    ("theft", ("theft", "stole", "stolen", "steal")),
    ("cheating", ("cheat", "cheated", "fraud", "fraudulent")),
    ("forgery", ("forged", "forgery", "fake document", "false document")),
    ("hurt", ("hurt", "injured", "injury", "beaten", "assault")),
    ("grievous hurt", ("grievous", "fracture", "disfigure", "serious injury")),
    ("extortion", ("extort", "ransom", "forced to pay")),
    ("trespass", ("trespass", "entered", "house breaking", "break in")),
    ("mischief", ("damaged", "destroyed", "burned", "arson", "vandal")),
]


def _safe_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def normalize_crime(text: str) -> str:
    t = text.lower()
    for concept, triggers in _CRIME_NORMALIZATION:
        if any(trigger in t for trigger in triggers):
            return concept.title()
    return "Reported criminal act"


def fallback_understand_incident(user_query: str) -> dict[str, Any]:
    parts = [p.strip(" ,") for p in _CONNECTOR_RE.split(user_query) if p.strip(" ,")]
    if not parts:
        parts = [user_query]
    events = []
    for idx, part in enumerate(parts, 1):
        events.append(
            {
                "event_id": f"E{idx}",
                "description": part,
                "normalized_crime": normalize_crime(part),
                "legal_concepts": [normalize_crime(part)],
                "supporting_facts": [part],
            }
        )
    return {
        "accused": "",
        "victim": "",
        "actions": parts,
        "weapons": [w for w in ("gun", "pistol", "knife", "weapon") if w in user_query.lower()],
        "property": [],
        "intent": "Inferred from incident text",
        "outcome": "death" if re.search(r"\b(died|death|killed|murder)\b", user_query, re.I) else "",
        "events": events,
        "extraction_source": "fallback",
    }


def understand_incident(user_query: str) -> dict[str, Any]:
    try:
        response = _groq().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": user_query},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = _safe_json(response.choices[0].message.content or "{}")
        data["extraction_source"] = "groq"
    except Exception as exc:
        data = fallback_understand_incident(user_query)
        data["extraction_error"] = str(exc)

    normalized_events = []
    for idx, event in enumerate(data.get("events") or [], 1):
        description = str(event.get("description") or "").strip()
        crime = str(event.get("normalized_crime") or "").strip()
        if not description and crime:
            description = crime
        if not description:
            continue
        if not crime:
            crime = normalize_crime(description)
        normalized_events.append(
            {
                "event_id": event.get("event_id") or f"E{idx}",
                "description": description,
                "normalized_crime": crime,
                "legal_concepts": event.get("legal_concepts") or [crime],
                "supporting_facts": event.get("supporting_facts") or [description],
            }
        )

    if not normalized_events:
        return fallback_understand_incident(user_query)

    data["events"] = normalized_events
    return data


def build_events(incident_data: dict[str, Any]) -> list[LegalEvent]:
    return [
        LegalEvent(
            event_id=str(event["event_id"]),
            description=str(event["description"]),
            normalized_crime=str(event["normalized_crime"]),
            legal_concepts=[str(v) for v in event.get("legal_concepts", []) if v],
            supporting_facts=[str(v) for v in event.get("supporting_facts", []) if v],
        )
        for event in incident_data.get("events", [])
    ]


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def event_query(event: LegalEvent) -> str:
    concepts = ", ".join(event.legal_concepts)
    return " ".join(
        part
        for part in (
            event.normalized_crime,
            event.description,
            concepts,
        )
        if part
    )


def retrieve_from_pinecone(event: LegalEvent, top_k: int) -> list[SectionCandidate]:
    vector = _embed([event_query(event)])[0]
    response = _pinecone().query(vector=vector, top_k=top_k, include_metadata=True)
    candidates = []
    for match in response.get("matches", []):
        meta = match.get("metadata") or {}
        act = str(meta.get("act") or match.get("id", "").split("_", 1)[0])
        section = str(meta.get("section") or match.get("id", "").split("_", 1)[-1])
        candidate = SectionCandidate(
            law_id=str(match.get("id") or f"{act}_{section}"),
            act=act,
            section=section,
            title=str(meta.get("title") or ""),
            punishment=str(meta.get("punishment") or ""),
            cognizable=str(meta.get("cognizable") or ""),
            bailable=str(meta.get("bailable") or ""),
            court=str(meta.get("court") or ""),
            chapter=str(meta.get("chapter") or ""),
            category=str(meta.get("category") or ""),
            mapping_status=str(meta.get("mapping_status") or ""),
            equivalent_act=str(meta.get("equivalent_act") or ""),
            equivalent_section=str(meta.get("equivalent_section") or ""),
            retrieval_score=float(match.get("score") or 0.0),
            supporting_events=[event],
        )
        candidate.sources.add("pinecone")
        candidates.append(candidate)
    return candidates


def _keywords_for_graph(event: LegalEvent) -> list[str]:
    raw = " ".join([event.normalized_crime, event.description, *event.legal_concepts]).lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z]+", raw)
    stop = {
        "a",
        "an",
        "the",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "and",
        "or",
        "with",
        "from",
        "into",
        "later",
        "after",
        "before",
        "while",
        "during",
        "person",
        "owner",
        "victim",
        "accused",
        "reported",
        "criminal",
        "act",
        "shop",
        "jewellery",
    }
    legal_terms = {
        "robbery",
        "robbed",
        "dacoity",
        "murder",
        "homicide",
        "death",
        "died",
        "killed",
        "shot",
        "shooting",
        "firearm",
        "gun",
        "weapon",
        "hurt",
        "injury",
        "grievous",
        "threat",
        "intimidation",
        "kidnapping",
        "abduction",
        "ransom",
        "theft",
        "stolen",
        "cheating",
        "fraud",
        "forgery",
        "extortion",
        "trespass",
        "mischief",
    }
    seen = set()
    keywords = []
    for word in words:
        if word in stop or word in seen:
            continue
        if len(word) < 4 and word not in legal_terms:
            continue
        if word not in legal_terms and word != event.normalized_crime.lower():
            continue
        seen.add(word)
        keywords.append(word)
    return keywords[:8]


def retrieve_from_neo4j(event: LegalEvent, top_k: int) -> list[SectionCandidate]:
    keywords = _keywords_for_graph(event)
    if not keywords:
        return []
    rows = _neo4j_run(
        """
        MATCH (l:LawSection)
        OPTIONAL MATCH (c:Crime)-[:DEFINED_BY]->(l)
        WITH l, collect(DISTINCT c.name) AS crimes
        WITH l, crimes,
             [kw IN $keywords WHERE
            toLower(coalesce(l.title, '')) CONTAINS kw OR
            toLower(coalesce(l.description, '')) CONTAINS kw OR
            any(name IN crimes WHERE toLower(coalesce(name, '')) CONTAINS kw)] AS matched_keywords
        WHERE size(matched_keywords) > 0
        RETURN l.id AS law_id, l.act AS act, l.section AS section,
               l.title AS title, l.description AS description,
               l.punishment AS punishment, l.cognizable AS cognizable,
               l.bailable AS bailable, l.court AS court,
               l.category AS category, l.mapping_status AS mapping_status,
               crimes, matched_keywords
        ORDER BY size(matched_keywords) DESC, l.act, l.section
        LIMIT $limit
        """,
        {"keywords": keywords, "limit": top_k},
    )
    candidates = []
    for row in rows:
        title = str(row.get("title") or "")
        description = str(row.get("description") or "")
        haystack = " ".join([title, description, " ".join(row.get("crimes") or [])]).lower()
        overlap = sum(1 for kw in keywords if kw in haystack)
        title_or_crime = " ".join([title, " ".join(row.get("crimes") or [])]).lower()
        strong_title_match = any(kw in title_or_crime for kw in keywords)
        score = min(0.72 if strong_title_match else 0.58, 0.36 + (0.08 * overlap))
        candidate = SectionCandidate(
            law_id=str(row["law_id"]),
            act=str(row["act"]),
            section=str(row["section"]),
            title=title,
            description=description,
            punishment=str(row.get("punishment") or ""),
            cognizable=str(row.get("cognizable") or ""),
            bailable=str(row.get("bailable") or ""),
            court=str(row.get("court") or ""),
            category=str(row.get("category") or ""),
            mapping_status=str(row.get("mapping_status") or ""),
            retrieval_score=score,
            supporting_events=[event],
        )
        candidate.sources.add("neo4j_keyword")
        candidates.append(candidate)
    return candidates


def collect_candidates(events: list[LegalEvent], top_k: int) -> tuple[dict[str, SectionCandidate], list[dict[str, Any]]]:
    merged: dict[str, SectionCandidate] = {}
    retrieval_debug = []

    for event in events:
        pinecone_hits: list[SectionCandidate] = []
        graph_hits: list[SectionCandidate] = []

        try:
            pinecone_hits = retrieve_from_pinecone(event, top_k)
        except Exception as exc:
            retrieval_debug.append({"event_id": event.event_id, "source": "pinecone", "error": str(exc)})

        try:
            graph_hits = retrieve_from_neo4j(event, top_k)
        except Exception as exc:
            retrieval_debug.append({"event_id": event.event_id, "source": "neo4j", "error": str(exc)})

        retrieval_debug.append(
            {
                "event_id": event.event_id,
                "query": event_query(event),
                "pinecone_hits": len(pinecone_hits),
                "neo4j_hits": len(graph_hits),
            }
        )

        for candidate in [*pinecone_hits, *graph_hits]:
            existing = merged.get(candidate.law_id)
            if not existing:
                merged[candidate.law_id] = candidate
                continue

            existing.retrieval_score = max(existing.retrieval_score, candidate.retrieval_score)
            existing.sources.update(candidate.sources)
            for event_item in candidate.supporting_events:
                if event_item.event_id not in {e.event_id for e in existing.supporting_events}:
                    existing.supporting_events.append(event_item)
            for field_name in (
                "title",
                "description",
                "punishment",
                "cognizable",
                "bailable",
                "court",
                "chapter",
                "category",
                "mapping_status",
                "equivalent_act",
                "equivalent_section",
            ):
                if not getattr(existing, field_name) and getattr(candidate, field_name):
                    setattr(existing, field_name, getattr(candidate, field_name))

    return merged, retrieval_debug


# ---------------------------------------------------------------------------
# Graph enrichment and rules
# ---------------------------------------------------------------------------
def enrich_candidates(candidates: dict[str, SectionCandidate]) -> None:
    if not candidates:
        return
    rows = _neo4j_run(
        """
        MATCH (l:LawSection)
        WHERE l.id IN $ids
        OPTIONAL MATCH (l)-[:REPLACED_BY|REPLACES]->(mapped:LawSection)
        OPTIONAL MATCH (chapter:Chapter)-[:HAS_SECTION]->(l)
        RETURN l.id AS law_id, l.act AS act, l.section AS section,
               l.title AS title, l.description AS description,
               l.punishment AS punishment, l.cognizable AS cognizable,
               l.bailable AS bailable, l.court AS court,
               l.category AS category, l.mapping_status AS mapping_status,
               chapter.title AS chapter,
               collect(DISTINCT {
                   act: mapped.act,
                   section: mapped.section,
                   id: mapped.id
               }) AS mappings
        """,
        {"ids": list(candidates)},
    )
    for row in rows:
        candidate = candidates[str(row["law_id"])]
        for field_name in (
            "act",
            "section",
            "title",
            "description",
            "punishment",
            "cognizable",
            "bailable",
            "court",
            "category",
            "mapping_status",
            "chapter",
        ):
            value = row.get(field_name)
            if value and not getattr(candidate, field_name):
                setattr(candidate, field_name, str(value))

        mappings = [m for m in row.get("mappings", []) if m.get("id")]
        if mappings and not candidate.equivalent_section:
            mapped = mappings[0]
            candidate.equivalent_act = str(mapped.get("act") or "")
            candidate.equivalent_section = str(mapped.get("section") or "")
        if mappings:
            candidate.graph_score = max(candidate.graph_score, 0.06)
            candidate.graph_relationships.append(
                {
                    "type": "IPC_BNS_MAPPING",
                    "targets": mappings,
                }
            )


def fetch_rule_relationships(candidate_ids: list[str]) -> list[dict[str, Any]]:
    if not candidate_ids:
        return []
    return _neo4j_run(
        """
        MATCH (source:LawSection)-[rel]->(target:LawSection)
        WHERE source.id IN $ids
          AND target.id IN $ids
          AND type(rel) IN [
              'OVERRIDES',
              'MORE_SPECIFIC_THAN',
              'INCLUDES_ELEMENTS_OF',
              'CANNOT_COEXIST_WITH',
              'ENHANCES'
          ]
        RETURN source.id AS source_id, target.id AS target_id,
               type(rel) AS relationship,
               rel.rule_id AS rule_id,
               rel.condition AS condition,
               rel.confidence AS confidence
        """,
        {"ids": candidate_ids},
    )


def _incident_text(events: list[LegalEvent]) -> str:
    return " ".join(
        [
            *[event.description for event in events],
            *[event.normalized_crime for event in events],
            *[concept for event in events for concept in event.legal_concepts],
        ]
    ).lower()


def condition_supported(rule: dict[str, Any], events: list[LegalEvent]) -> bool:
    text = _incident_text(events)
    source_id = str(rule.get("source_id") or "")
    target_id = str(rule.get("target_id") or "")
    condition = str(rule.get("condition") or "").lower()

    if source_id.endswith("_364A") or "ransom" in condition:
        return any(word in text for word in ("ransom", "hostage", "death threat", "hurt threat"))
    if source_id.endswith("_396"):
        return any(word in text for word in ("dacoity", "five", "gang")) and any(
            word in text for word in ("murder", "death", "died", "killed")
        )
    if source_id.endswith("_397"):
        return any(word in text for word in ("weapon", "gun", "pistol", "knife", "firearm", "grievous", "shot"))
    if source_id.endswith("_394"):
        return any(word in text for word in ("hurt", "injury", "injured", "assault", "beaten", "shot"))
    if source_id.endswith("_302") and target_id.endswith("_304"):
        return any(word in text for word in ("intention", "intentionally", "murder", "shot", "stabbed", "killed"))
    return True


def apply_rule_engine(candidates: dict[str, SectionCandidate], events: list[LegalEvent]) -> list[SectionCandidate]:
    try:
        relationships = fetch_rule_relationships(list(candidates))
    except Exception:
        relationships = []

    for rel in relationships:
        source = candidates.get(str(rel["source_id"]))
        target = candidates.get(str(rel["target_id"]))
        if not source or not target:
            continue
        if not condition_supported(rel, events):
            continue

        note = {
            "type": str(rel["relationship"]),
            "source_id": str(rel["source_id"]),
            "target_id": str(rel["target_id"]),
            "rule_id": str(rel.get("rule_id") or ""),
            "condition": str(rel.get("condition") or ""),
            "confidence": float(rel.get("confidence") or 0.75),
        }
        source.graph_relationships.append(note)
        target.graph_relationships.append(note)

        relationship = str(rel["relationship"])
        if relationship in {"OVERRIDES", "MORE_SPECIFIC_THAN"}:
            target.removed = True
            target.removal_reason = f"{source.law_id} {relationship} {target.law_id}"
            source.rule_score = max(source.rule_score, 0.12 * note["confidence"])
            source.rule_notes.append(target.removal_reason)
        elif relationship == "CANNOT_COEXIST_WITH":
            loser = target if source.retrieval_score >= target.retrieval_score else source
            winner = source if loser is target else target
            loser.removed = True
            loser.removal_reason = f"Conflicts with higher-ranked {winner.law_id}"
            winner.rule_score = max(winner.rule_score, 0.10 * note["confidence"])
        elif relationship in {"ENHANCES", "INCLUDES_ELEMENTS_OF"}:
            source.rule_score = max(source.rule_score, 0.10 * note["confidence"])
            source.rule_notes.append(f"{source.law_id} {relationship} {target.law_id}")

    # Penalize definitional sections when the corresponding punishment section survived.
    definition_pairs = [
        ("IPC_390", "IPC_392"),
        ("IPC_300", "IPC_302"),
        ("IPC_378", "IPC_379"),
        ("IPC_415", "IPC_420"),
        ("IPC_503", "IPC_506"),
    ]
    for definition_id, punishment_id in definition_pairs:
        definition = candidates.get(definition_id)
        punishment = candidates.get(punishment_id)
        if definition and punishment and not punishment.removed:
            definition.removed = True
            definition.removal_reason = f"{punishment_id} is the punishable/specific section for {definition_id}"
            punishment.rule_score = max(punishment.rule_score, 0.08)
            punishment.rule_notes.append(definition.removal_reason)

    min_confidence = 0.52
    survivors = []
    for candidate in candidates.values():
        if candidate.removed:
            continue
        source_boost = 0.04 if len(candidate.sources) > 1 else 0.0
        event_boost = min(0.08, 0.03 * max(0, len(candidate.supporting_events) - 1))
        candidate.graph_score = max(candidate.graph_score, source_boost + event_boost)
        candidate.confidence = min(
            1.0,
            (0.78 * candidate.retrieval_score)
            + candidate.rule_score
            + candidate.graph_score
        )
        if candidate.confidence >= min_confidence:
            survivors.append(candidate)

    survivors.sort(key=lambda item: item.confidence, reverse=True)
    return survivors


# ---------------------------------------------------------------------------
# Crosswalk materialization
# ---------------------------------------------------------------------------
def fetch_sections_by_ids(ids: list[str]) -> dict[str, SectionCandidate]:
    if not ids:
        return {}
    rows = _neo4j_run(
        """
        MATCH (l:LawSection)
        WHERE l.id IN $ids
        OPTIONAL MATCH (l)-[:REPLACED_BY|REPLACES]->(mapped:LawSection)
        OPTIONAL MATCH (chapter:Chapter)-[:HAS_SECTION]->(l)
        RETURN l.id AS law_id, l.act AS act, l.section AS section,
               l.title AS title, l.description AS description,
               l.punishment AS punishment, l.cognizable AS cognizable,
               l.bailable AS bailable, l.court AS court,
               l.category AS category, l.mapping_status AS mapping_status,
               chapter.title AS chapter,
               collect(DISTINCT {
                   act: mapped.act,
                   section: mapped.section,
                   id: mapped.id
               }) AS mappings
        """,
        {"ids": ids},
    )
    sections = {}
    for row in rows:
        candidate = SectionCandidate(
            law_id=str(row["law_id"]),
            act=str(row["act"]),
            section=str(row["section"]),
            title=str(row.get("title") or ""),
            description=str(row.get("description") or ""),
            punishment=str(row.get("punishment") or ""),
            cognizable=str(row.get("cognizable") or ""),
            bailable=str(row.get("bailable") or ""),
            court=str(row.get("court") or ""),
            category=str(row.get("category") or ""),
            mapping_status=str(row.get("mapping_status") or ""),
            chapter=str(row.get("chapter") or ""),
            retrieval_score=0.0,
            graph_score=0.08,
            confidence=0.0,
        )
        mappings = [m for m in row.get("mappings", []) if m.get("id")]
        if mappings:
            mapped = mappings[0]
            candidate.equivalent_act = str(mapped.get("act") or "")
            candidate.equivalent_section = str(mapped.get("section") or "")
        sections[candidate.law_id] = candidate
    return sections


def materialize_crosswalk_sections(sections: list[SectionCandidate]) -> list[SectionCandidate]:
    existing_ids = {section.law_id for section in sections}
    wanted_ids = []
    source_by_mapped_id: dict[str, SectionCandidate] = {}

    for section in sections:
        if not section.equivalent_act or not section.equivalent_section:
            continue
        mapped_id = f"{section.equivalent_act}_{section.equivalent_section}"
        if mapped_id in existing_ids:
            continue
        wanted_ids.append(mapped_id)
        source_by_mapped_id[mapped_id] = section

    try:
        mapped_sections = fetch_sections_by_ids(wanted_ids)
    except Exception:
        mapped_sections = {}

    for mapped_id, mapped in mapped_sections.items():
        source = source_by_mapped_id[mapped_id]
        mapped.sources.add("neo4j_crosswalk")
        mapped.supporting_events = list(source.supporting_events)
        mapped.retrieval_score = max(0.0, source.retrieval_score - 0.04)
        mapped.graph_score = max(mapped.graph_score, source.graph_score)
        mapped.rule_score = source.rule_score
        mapped.confidence = max(0.0, source.confidence - 0.03)
        mapped.graph_relationships.append(
            {
                "type": "IPC_BNS_MAPPING",
                "source_id": source.law_id,
                "target_id": mapped.law_id,
            }
        )
        mapped.rule_notes.append(f"Included through IPC/BNS mapping from {source.law_id}")
        sections.append(mapped)
        existing_ids.add(mapped_id)

    sections.sort(key=lambda item: item.confidence, reverse=True)
    return sections


# ---------------------------------------------------------------------------
# Output and explanation
# ---------------------------------------------------------------------------
def build_section_explanation(candidate: SectionCandidate) -> str:
    event_text = "; ".join(event.description for event in candidate.supporting_events[:3])
    crime_text = ", ".join(sorted({event.normalized_crime for event in candidate.supporting_events if event.normalized_crime}))
    base = f"{candidate.act} {candidate.section} applies to {crime_text or candidate.title}."
    if event_text:
        base += f" Supporting event(s): {event_text}."
    if candidate.rule_notes:
        base += f" Rule evidence: {'; '.join(candidate.rule_notes[:2])}."
    if candidate.equivalent_act and candidate.equivalent_section:
        base += f" It maps to {candidate.equivalent_act} {candidate.equivalent_section}."
    return base


def split_by_act(candidates: list[SectionCandidate], act: str) -> list[dict[str, Any]]:
    return [candidate.as_dict() for candidate in candidates if candidate.act == act]


def summarize_with_groq(user_query: str, sections: list[SectionCandidate]) -> str:
    if not sections:
        return "No applicable sections survived retrieval and rule filtering."
    compact = [
        {
            "id": section.law_id,
            "title": section.title,
            "punishment": section.punishment,
            "events": [event.description for event in section.supporting_events],
            "confidence": round(section.confidence, 3),
        }
        for section in sections[:12]
    ]
    prompt = """
You are an Indian criminal law assistant. Explain the recommended IPC/BNS
sections using only the supplied section list. Do not add section numbers not
present in the list. Keep the explanation concise.
"""
    try:
        response = _groq().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"incident": user_query, "recommended_sections": compact},
                        ensure_ascii=True,
                    ),
                },
            ],
            temperature=0.1,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        return f"Groq explanation unavailable: {exc}"


def process_incident(user_query: str, top_k_per_event: int = 8, final_top_n: int = 12) -> dict[str, Any]:
    incident_data = understand_incident(user_query)
    events = build_events(incident_data)

    candidates, retrieval_debug = collect_candidates(events, top_k=top_k_per_event)
    try:
        enrich_candidates(candidates)
    except Exception as exc:
        retrieval_debug.append({"source": "neo4j_enrichment", "error": str(exc)})

    ranked = apply_rule_engine(candidates, events)
    final_sections = materialize_crosswalk_sections(ranked[:final_top_n])

    return {
        "incident": {
            "query": user_query,
            "accused": incident_data.get("accused", ""),
            "victim": incident_data.get("victim", ""),
            "actions": incident_data.get("actions", []),
            "weapons": incident_data.get("weapons", []),
            "property": incident_data.get("property", []),
            "intent": incident_data.get("intent", ""),
            "outcome": incident_data.get("outcome", ""),
            "extraction_source": incident_data.get("extraction_source", ""),
            "extraction_error": incident_data.get("extraction_error", ""),
        },
        "events": [
            {
                "event_id": event.event_id,
                "description": event.description,
                "normalized_crime": event.normalized_crime,
                "legal_concepts": event.legal_concepts,
                "supporting_facts": event.supporting_facts,
            }
            for event in events
        ],
        "applicable_ipc_sections": split_by_act(final_sections, "IPC"),
        "applicable_bns_sections": split_by_act(final_sections, "BNS"),
        "all_recommended_sections": [section.as_dict() for section in final_sections],
        "discarded_sections": [
            {
                "law_id": candidate.law_id,
                "title": candidate.title,
                "reason": candidate.removal_reason,
            }
            for candidate in candidates.values()
            if candidate.removed
        ],
        "retrieval_debug": retrieval_debug,
        "explanation": summarize_with_groq(user_query, final_sections),
    }


def format_result(result: dict[str, Any]) -> str:
    lines = []
    incident = result["incident"]
    lines.append(f"Incident: {incident['query']}")
    lines.append("")
    lines.append("Events:")
    for event in result["events"]:
        lines.append(f"- {event['event_id']}: {event['normalized_crime']} - {event['description']}")
    lines.append("")
    lines.append("Recommended Sections:")
    for section in result["all_recommended_sections"]:
        lines.append(
            f"- {section['act']} {section['section']} ({section['title']}) "
            f"confidence={section['confidence']}"
        )
        if section.get("equivalent_act") and section.get("equivalent_section"):
            lines.append(f"  Mapping: {section['equivalent_act']} {section['equivalent_section']}")
        if section.get("punishment"):
            lines.append(f"  Punishment: {section['punishment']}")
        lines.append(f"  Why: {section['why_it_applies']}")
    if result["discarded_sections"]:
        lines.append("")
        lines.append("Discarded By Rules:")
        for item in result["discarded_sections"]:
            lines.append(f"- {item['law_id']}: {item['reason']}")
    lines.append("")
    lines.append("Explanation:")
    lines.append(result["explanation"])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-crime IPC/BNS legal reasoning engine")
    parser.add_argument("query", nargs="*", help="Natural-language incident description")
    parser.add_argument("--json", action="store_true", help="Print raw JSON result")
    parser.add_argument("--top-k", type=int, default=8, help="Retrieval candidates per event")
    parser.add_argument("--final-top-n", type=int, default=12, help="Final sections to return")
    args = parser.parse_args()

    query = " ".join(args.query).strip()
    if not query:
        query = "A person robbed a jewellery shop, shot the owner, and the owner later died."

    result = process_incident(query, top_k_per_event=args.top_k, final_top_n=args.final_top_n)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        print(format_result(result))


if __name__ == "__main__":
    main()
