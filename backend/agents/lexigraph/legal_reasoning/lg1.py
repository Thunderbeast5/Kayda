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
import math
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
    outcome: str = ""
    crime_family: str = ""
    legal_concepts: list[str] = field(default_factory=list)
    supporting_facts: list[str] = field(default_factory=list)


def score_graph_context(candidate: "SectionCandidate") -> float:
    """Score graph richness from the available relationship context."""
    weights = {
        "IPC_BNS_MAPPING": 0.12,
        "DEFINED_BY": 0.16,
        "CO_CHARGED_WITH": 0.08,
        "ESCALATES_TO": 0.08,
        "AGGRAVATED_BY": 0.08,
        "ABETS": 0.07,
        "PROCEDURAL_FOR": 0.06,
        "LANDMARK_CASE": 0.07,
        "CONSTITUTION_ARTICLE": 0.08,
        "RELATED_OFFENCE": 0.05,
        "RELATED_TO": 0.04,
        "OVERRIDES": 0.05,
        "MORE_SPECIFIC_THAN": 0.05,
        "ENHANCES": 0.05,
        "INCLUDES_ELEMENTS_OF": 0.05,
        "CANNOT_COEXIST_WITH": 0.04,
    }

    score = 0.0
    for relation in candidate.graph_relationships:
        rel_type = str(relation.get("type") or "").upper()
        score += weights.get(rel_type, 0.0)

    if candidate.equivalent_act and candidate.equivalent_section:
        score += 0.04

    if candidate.graph_relationships:
        score += 0.01

    return round(min(0.8, max(0.0, score)), 4)


def build_case_analysis_payload(user_query: str, sections: list["SectionCandidate"]) -> dict[str, Any]:
    return {
        "user_query": user_query,
        "sections": [section.as_dict() for section in sections],
    }


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
                    "outcome": e.outcome,
                    "crime_family": e.crime_family,
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
    outcome = detect_outcome(text)
    if outcome == "death" and any(word in t for word in ("shot", "shoot", "stabbed", "killed", "intentionally")):
        return "Murder"
    if outcome == "death" and any(word in t for word in ("accident", "negligent", "rash")):
        return "Causing death by negligence"
    for concept, triggers in _CRIME_NORMALIZATION:
        if any(trigger in t for trigger in triggers):
            return concept.title()
    return "Reported criminal act"


def detect_outcome(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(died|death|dead|killed|murder|homicide|fatal)\b", t):
        return "death"
    if re.search(r"\b(fracture|grievous|permanent|disfigure|loss of sight|serious injury)\b", t):
        return "grievous_injury"
    if re.search(r"\b(hurt|injury|injured|assault|beaten|shot|stabbed)\b", t):
        return "hurt"
    if re.search(r"\b(robbed|robbery|stole|stolen|theft|loot|property|jewellery|cash)\b", t):
        return "property_loss"
    if re.search(r"\b(kidnap|abduct|hostage|ransom)\b", t):
        return "kidnapping"
    if re.search(r"\b(rape|sexual)\b", t):
        return "sexual_assault"
    if re.search(r"\b(extort|blackmail|threatened to pay)\b", t):
        return "extortion"
    return ""


def classify_crime_family(crime: str, description: str, outcome: str) -> str:
    text = f"{crime} {description} {outcome}".lower()
    if outcome == "death" or any(word in text for word in ("murder", "homicide", "causing death")):
        return "Homicide"
    if any(word in text for word in ("robbery", "robbed", "dacoity", "theft", "stolen", "property", "extortion")):
        return "Property Offences"
    if any(word in text for word in ("rape", "sexual")):
        return "Sexual Offences"
    if any(word in text for word in ("forgery", "cheating", "fraud")):
        return "Forgery/Fraud"
    if any(word in text for word in ("hurt", "injury", "grievous", "assault")):
        return "Hurt"
    if any(word in text for word in ("threat", "intimidation")):
        return "Criminal Intimidation"
    return "General Criminal Offence"


def normalize_event_crime(description: str, crime: str, global_outcome: str = "") -> tuple[str, str, str]:
    local_text = " ".join(part for part in (description, crime) if part)
    local_outcome = detect_outcome(local_text)
    inherits_death = (
        global_outcome == "death"
        and local_outcome in {"", "hurt"}
        and re.search(r"\b(shot|shoot|stabbed|killed|homicide|murder|culpable)\b", local_text, re.I)
    )
    outcome = "death" if inherits_death else local_outcome
    combined = " ".join(part for part in (description, crime, outcome) if part)
    normalized = normalize_crime(combined)
    if outcome == "death" and normalized in {"Hurt", "Grievous Hurt"}:
        normalized = "Murder" if re.search(r"\b(shot|shoot|stabbed|killed)\b", combined, re.I) else "Culpable Homicide"
    family = classify_crime_family(normalized, description, outcome)
    return normalized, outcome, family


def fallback_understand_incident(user_query: str) -> dict[str, Any]:
    parts = [p.strip(" ,") for p in _CONNECTOR_RE.split(user_query) if p.strip(" ,")]
    if not parts:
        parts = [user_query]
    events = []
    for idx, part in enumerate(parts, 1):
        crime, outcome, family = normalize_event_crime(part, "")
        events.append(
            {
                "event_id": f"E{idx}",
                "description": part,
                "normalized_crime": crime,
                "outcome": outcome,
                "crime_family": family,
                "legal_concepts": [crime, family],
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
    global_outcome = str(data.get("outcome") or "")
    for idx, event in enumerate(data.get("events") or [], 1):
        description = str(event.get("description") or "").strip()
        crime = str(event.get("normalized_crime") or "").strip()
        if not description and crime:
            description = crime
        if not description:
            continue
        crime, outcome, family = normalize_event_crime(
            description=description,
            crime=crime,
            global_outcome=global_outcome,
        )
        normalized_events.append(
            {
                "event_id": event.get("event_id") or f"E{idx}",
                "description": description,
                "normalized_crime": crime,
                "outcome": outcome,
                "crime_family": family,
                "legal_concepts": list(dict.fromkeys([*(event.get("legal_concepts") or []), crime, family, outcome])),
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
            outcome=str(event.get("outcome") or ""),
            crime_family=str(event.get("crime_family") or ""),
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
            f"Crime family: {event.crime_family}" if event.crime_family else "",
            event.normalized_crime,
            f"Outcome: {event.outcome}" if event.outcome else "",
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


HOMICIDE_PRIMARY_IDS = {
    "IPC_299",
    "IPC_300",
    "IPC_302",
    "IPC_304",
    "IPC_304A",
    "BNS_100",
    "BNS_101",
    "BNS_102",
    "BNS_103",
    "BNS_105",
    "BNS_106",
}

ROBBERY_PRIMARY_IDS = {
    "IPC_390",
    "IPC_392",
    "IPC_394",
    "IPC_397",
    "IPC_398",
    "BNS_309",
    "BNS_310",
    "BNS_311",
    "BNS_312",
}

HURT_PRIMARY_IDS = {
    "IPC_319",
    "IPC_320",
    "IPC_321",
    "IPC_322",
    "IPC_323",
    "IPC_324",
    "IPC_325",
    "IPC_326",
    "BNS_114",
    "BNS_115",
    "BNS_116",
    "BNS_117",
    "BNS_118",
}


def candidate_matches_event(candidate: SectionCandidate, event: LegalEvent) -> tuple[bool, str]:
    text = " ".join(
        [
            candidate.law_id,
            candidate.title,
            candidate.description,
            candidate.category,
            candidate.chapter,
        ]
    ).lower()

    if event.crime_family == "Homicide":
        if candidate.law_id in HOMICIDE_PRIMARY_IDS:
            return True, ""
        if any(term in text for term in ("murder", "homicide", "causing death", "death by negligence")):
            return True, ""
        if candidate.law_id in HURT_PRIMARY_IDS or any(term in text for term in ("hurt", "grievous hurt")):
            return False, "Rejected ordinary hurt section because the event outcome is death."
        return False, "Rejected non-homicide section for homicide/death event."

    if event.crime_family == "Property Offences":
        if candidate.law_id in ROBBERY_PRIMARY_IDS:
            return True, ""
        if any(term in text for term in ("robbery", "dacoity", "theft", "extortion")):
            return True, ""
        return False, "Rejected non-property section for robbery/property event."

    if event.crime_family == "Hurt" and event.outcome != "death":
        if candidate.law_id in HURT_PRIMARY_IDS or any(term in text for term in ("hurt", "injury", "grievous")):
            return True, ""
        return False, "Rejected non-hurt section for hurt event."

    return True, ""


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
            allowed, reject_reason = candidate_matches_event(candidate, event)
            if not allowed:
                retrieval_debug.append(
                    {
                        "event_id": event.event_id,
                        "law_id": candidate.law_id,
                        "source": sorted(candidate.sources),
                        "rejected": reject_reason,
                    }
                )
                continue

            if event.crime_family == "Homicide" and candidate.law_id in HOMICIDE_PRIMARY_IDS:
                candidate.rule_score = max(candidate.rule_score, 0.10)
                candidate.rule_notes.append("Outcome death: prioritized homicide section.")
            if event.crime_family == "Property Offences" and candidate.law_id in ROBBERY_PRIMARY_IDS:
                candidate.rule_score = max(candidate.rule_score, 0.08)
                candidate.rule_notes.append("Robbery/property event: prioritized robbery section.")

            existing = merged.get(candidate.law_id)
            if not existing:
                merged[candidate.law_id] = candidate
                continue

            existing.retrieval_score = max(existing.retrieval_score, candidate.retrieval_score)
            existing.rule_score = max(existing.rule_score, candidate.rule_score)
            existing.sources.update(candidate.sources)
            for note in candidate.rule_notes:
                if note not in existing.rule_notes:
                    existing.rule_notes.append(note)
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
        graph_context_boost = score_graph_context(candidate)
        candidate.graph_score = max(
            candidate.graph_score,
            source_boost + event_boost,
            graph_context_boost,
        )
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
def _summarize_graph_context(candidate: SectionCandidate) -> list[str]:
    notes: list[str] = []
    for relation in candidate.graph_relationships[:3]:
        rel_type = str(relation.get("type") or "").upper()
        if rel_type == "IPC_BNS_MAPPING":
            targets = [
                f"{item.get('act', '').strip()} {item.get('section', item.get('id', ''))}".strip()
                for item in relation.get("targets", [])
                if item.get("act") or item.get("section") or item.get("id")
            ]
            if targets:
                notes.append(f"it corresponds to {', '.join(targets[:2])} in the legal graph")
            else:
                notes.append("it is linked to a mapped counterpart in the legal graph")
        elif rel_type == "DEFINED_BY":
            notes.append("it is defined by a crime concept in the graph")
        elif rel_type in {"CO_CHARGED_WITH", "AGGRAVATED_BY", "ESCALATES_TO", "ABETS", "PROCEDURAL_FOR"}:
            notes.append("it connects to related or enhanced offences in the graph")
        elif rel_type == "LANDMARK_CASE":
            notes.append("it is supported by landmark-case context")
        elif rel_type == "CONSTITUTION_ARTICLE":
            notes.append("it is connected to constitutional context")
        elif rel_type:
            notes.append("it has additional graph context that strengthens the fit")
    return notes


def build_section_explanation(candidate: SectionCandidate) -> str:
    event_text = "; ".join(event.description for event in candidate.supporting_events[:3])
    crime_text = ", ".join(sorted({event.normalized_crime for event in candidate.supporting_events if event.normalized_crime}))
    base = f"{candidate.act} {candidate.section} applies to {crime_text or candidate.title}."
    if event_text:
        base += f" Supporting event(s): {event_text}."
    if candidate.rule_notes:
        base += f" Rule evidence: {'; '.join(candidate.rule_notes[:2])}."
    graph_notes = _summarize_graph_context(candidate)
    if graph_notes:
        base += f" Graph context: {'; '.join(graph_notes[:2])}."
    if candidate.equivalent_act and candidate.equivalent_section:
        base += f" It maps to {candidate.equivalent_act} {candidate.equivalent_section}."
    return base


def split_by_act(candidates: list[SectionCandidate], act: str) -> list[dict[str, Any]]:
    return [candidate.as_dict() for candidate in candidates if candidate.act == act]


def preserve_event_chains(
    ranked: list[SectionCandidate],
    events: list[LegalEvent],
    final_top_n: int,
    per_event_limit: int = 4,
) -> list[SectionCandidate]:
    selected: list[SectionCandidate] = []
    selected_ids = set()

    for event in events:
        event_ranked = [
            candidate
            for candidate in ranked
            if any(support.event_id == event.event_id for support in candidate.supporting_events)
        ]
        for candidate in event_ranked[:per_event_limit]:
            if candidate.law_id in selected_ids:
                continue
            selected.append(candidate)
            selected_ids.add(candidate.law_id)

    for candidate in ranked:
        if len(selected) >= final_top_n:
            break
        if candidate.law_id in selected_ids:
            continue
        selected.append(candidate)
        selected_ids.add(candidate.law_id)

    selected.sort(key=lambda item: item.confidence, reverse=True)
    return selected[:final_top_n]


def build_event_recommendations(
    sections: list[SectionCandidate],
    events: list[LegalEvent],
) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        event_sections = [
            section.as_dict()
            for section in sections
            if any(support.event_id == event.event_id for support in section.supporting_events)
        ]
        rows.append(
            {
                "event_id": event.event_id,
                "description": event.description,
                "normalized_crime": event.normalized_crime,
                "outcome": event.outcome,
                "crime_family": event.crime_family,
                "recommended_sections": event_sections,
            }
        )
    return rows


def _normalise_expected_sections(expected_sections: list[Any]) -> list[dict[str, Any]]:
    normalised: list[dict[str, Any]] = []
    for entry in expected_sections:
        if isinstance(entry, dict):
            section = str(entry.get("section") or entry.get("id") or "")
            relevance = entry.get("relevance", 1)
        else:
            section = str(entry)
            relevance = 1
        if section:
            normalised.append({"section": section, "relevance": int(relevance) if str(relevance).isdigit() else 1})
    return normalised


def _graded_ndcg(retrieved: list[Any], expected_sections: list[dict[str, Any]]) -> float:
    expected_map = {str(item["section"]).upper(): item["relevance"] for item in expected_sections}
    if not expected_map:
        return 0.0

    dcg = 0.0
    for rank, entry in enumerate(retrieved[:10], start=1):
        relevance = expected_map.get(str(entry).upper(), 0)
        if relevance:
            dcg += (2 ** relevance - 1) / math.log2(rank + 1)

    ideal_relevances = sorted(expected_map.values(), reverse=True)[:10]
    ideal_dcg = 0.0
    for rank, relevance in enumerate(ideal_relevances, start=1):
        if relevance:
            ideal_dcg += (2 ** relevance - 1) / math.log2(rank + 1)

    return round(dcg / ideal_dcg, 4) if ideal_dcg else 0.0


def _reasoning_structure_score(reasoning_items: list[dict[str, Any]]) -> float:
    if not reasoning_items:
        return 0.0

    required_fields = ["reason", "supporting_facts", "missing_evidence", "ambiguities"]
    score = 0.0
    for item in reasoning_items:
        if item.get("reason") and isinstance(item.get("supporting_facts"), list) and isinstance(item.get("missing_evidence"), list) and isinstance(item.get("ambiguities"), list):
            score += 1.0
    return round(score / len(reasoning_items), 4)


def _reasoning_grounding_score(reasoning_items: list[dict[str, Any]], query: str) -> float:
    if not reasoning_items:
        return 0.0
    query_tokens = {token.lower() for token in re.findall(r"[a-zA-Z]+", query) if token}
    if not query_tokens:
        return 0.0

    grounded = 0
    for item in reasoning_items:
        text = " ".join(
            [
                str(item.get("reason") or ""),
                " ".join(item.get("supporting_facts") or []),
                " ".join(item.get("ambiguities") or []),
            ]
        ).lower()
        if query_tokens & set(re.findall(r"[a-zA-Z]+", text)):
            grounded += 1
    return round(grounded / len(reasoning_items), 4)


def evaluate_benchmark(queries: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute ranking metrics for a realistic legal benchmark suite."""
    metrics = {
        "recall_at_5": 0.0,
        "recall_at_10": 0.0,
        "precision_at_5": 0.0,
        "mrr": 0.0,
        "ndcg": 0.0,
        "graph_coverage": 0.0,
        "average_reasoning_confidence": 0.0,
        "graph_improvement": {"ndcg": 0.0, "recall_at_5": 0.0},
        "by_category": {},
        "reasoning_quality": {"structure_score": 0.0, "grounding_score": 0.0},
    }
    if not queries:
        return {**metrics, "total_queries": 0}

    recall_at_5_total = 0.0
    recall_at_10_total = 0.0
    precision_at_5_total = 0.0
    mrr_total = 0.0
    ndcg_total = 0.0
    graph_coverage_total = 0.0
    reasoning_confidence_total = 0.0
    graph_improvement_ndcg_total = 0.0
    graph_improvement_recall_total = 0.0
    structure_score_total = 0.0
    grounding_score_total = 0.0
    by_category: dict[str, dict[str, Any]] = {}

    for item in queries:
        category = str(item.get("category") or "General")
        retrieved = item.get("retrieved", []) or []
        vector_only_retrieved = item.get("vector_only_retrieved", []) or []
        graph_rag_retrieved = item.get("graph_rag_retrieved", []) or []
        expected_sections = _normalise_expected_sections(item.get("expected_sections", []) or [])
        expected_priority = _normalise_expected_sections(item.get("expected_priority", []) or [])
        graph_enriched = item.get("graph_enriched", []) or []
        reasoning_confidence = item.get("reasoning_confidence", []) or []
        reasoning = item.get("reasoning", []) or []

        expected_map = {str(item["section"]).upper(): item["relevance"] for item in [*expected_sections, *expected_priority]}
        expected_set = set(expected_map.keys())
        relevant_hits = [rank for rank, entry in enumerate(retrieved[:10], start=1) if str(entry).upper() in expected_set]

        if relevant_hits:
            mrr_total += 1.0 / relevant_hits[0]

        if expected_sections:
            recall_at_5_total += sum(1 for rank in relevant_hits if rank <= 5) / float(len(expected_sections))
            recall_at_10_total += sum(1 for rank in relevant_hits if rank <= 10) / float(len(expected_sections))
            precision_at_5_total += sum(1 for rank, entry in enumerate(retrieved[:5], start=1) if str(entry).upper() in expected_set) / 5.0
            ndcg_total += _graded_ndcg(retrieved, expected_sections)

        if graph_enriched:
            graph_coverage_total += sum(1 for value in graph_enriched[: len(retrieved)] if value) / float(len(graph_enriched[: len(retrieved)]))

        if reasoning_confidence:
            reasoning_confidence_total += sum(reasoning_confidence[: len(retrieved)]) / float(len(reasoning_confidence[: len(retrieved)]))

        if vector_only_retrieved and graph_rag_retrieved:
            vector_ndcg = _graded_ndcg(vector_only_retrieved, expected_sections)
            graph_ndcg = _graded_ndcg(graph_rag_retrieved, expected_sections)
            graph_improvement_ndcg_total += max(0.0, graph_ndcg - vector_ndcg)
            vector_recall = sum(1 for rank, entry in enumerate(vector_only_retrieved[:5], start=1) if str(entry).upper() in expected_set) / float(len(expected_sections)) if expected_sections else 0.0
            graph_recall = sum(1 for rank, entry in enumerate(graph_rag_retrieved[:5], start=1) if str(entry).upper() in expected_set) / float(len(expected_sections)) if expected_sections else 0.0
            graph_improvement_recall_total += max(0.0, graph_recall - vector_recall)

        structure_score_total += _reasoning_structure_score(reasoning)
        grounding_score_total += _reasoning_grounding_score(reasoning, str(item.get("query") or ""))

        bucket = by_category.setdefault(
            category,
            {
                "total_cases": 0,
                "recall_at_5": 0.0,
                "recall_at_10": 0.0,
                "precision_at_5": 0.0,
                "mrr": 0.0,
                "ndcg": 0.0,
            },
        )
        bucket["total_cases"] += 1
        bucket["recall_at_5"] += sum(1 for rank in relevant_hits if rank <= 5) / float(len(expected_sections)) if expected_sections else 0.0
        bucket["recall_at_10"] += sum(1 for rank in relevant_hits if rank <= 10) / float(len(expected_sections)) if expected_sections else 0.0
        bucket["precision_at_5"] += sum(1 for rank, entry in enumerate(retrieved[:5], start=1) if str(entry).upper() in expected_set) / 5.0 if expected_sections else 0.0
        bucket["mrr"] += 1.0 / relevant_hits[0] if relevant_hits else 0.0
        bucket["ndcg"] += _graded_ndcg(retrieved, expected_sections) if expected_sections else 0.0

    for bucket in by_category.values():
        bucket["recall_at_5"] = round(bucket["recall_at_5"] / bucket["total_cases"], 4)
        bucket["recall_at_10"] = round(bucket["recall_at_10"] / bucket["total_cases"], 4)
        bucket["precision_at_5"] = round(bucket["precision_at_5"] / bucket["total_cases"], 4)
        bucket["mrr"] = round(bucket["mrr"] / bucket["total_cases"], 4)
        bucket["ndcg"] = round(bucket["ndcg"] / bucket["total_cases"], 4)

    metrics.update(
        {
            "total_queries": len(queries),
            "recall_at_5": round(recall_at_5_total / len(queries), 4),
            "recall_at_10": round(recall_at_10_total / len(queries), 4),
            "precision_at_5": round(precision_at_5_total / len(queries), 4),
            "mrr": round(mrr_total / len(queries), 4),
            "ndcg": round(ndcg_total / len(queries), 4),
            "graph_coverage": round(graph_coverage_total / len(queries), 4),
            "average_reasoning_confidence": round(reasoning_confidence_total / len(queries), 4),
            "graph_improvement": {
                "ndcg": round(graph_improvement_ndcg_total / len(queries), 4),
                "recall_at_5": round(graph_improvement_recall_total / len(queries), 4),
            },
            "by_category": by_category,
            "reasoning_quality": {
                "structure_score": round(structure_score_total / len(queries), 4),
                "grounding_score": round(grounding_score_total / len(queries), 4),
            },
        }
    )
    return metrics


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
    final_sections = preserve_event_chains(ranked, events, final_top_n)
    final_sections = materialize_crosswalk_sections(final_sections)

    return {
        "case_analysis": build_case_analysis_payload(user_query, final_sections),
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
                "outcome": event.outcome,
                "crime_family": event.crime_family,
                "legal_concepts": event.legal_concepts,
                "supporting_facts": event.supporting_facts,
            }
            for event in events
        ],
        "event_recommendations": build_event_recommendations(final_sections, events),
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
        lines.append(
            f"- {event['event_id']}: {event['normalized_crime']} "
            f"[{event['crime_family']}, outcome={event['outcome'] or 'none'}] - {event['description']}"
        )
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
    parser.add_argument("--benchmark", action="store_true", help="Run the built-in benchmark evaluation")
    args = parser.parse_args()

    if args.benchmark:
        benchmark_queries = [
            {
                "id": "theft_001",
                "query": "house theft",
                "expected_sections": ["BNS 305", "BNS 331"],
                "expected_priority": ["BNS 305"],
                "retrieved": ["BNS 305", "BNS 331", "BNS 304", "IPC 380"],
                "graph_enriched": [True, True, False, False],
                "reasoning_confidence": [0.91, 0.86, 0.56, 0.41],
            },
            {
                "id": "murder_001",
                "query": "murder",
                "expected_sections": ["BNS 103", "IPC 302"],
                "expected_priority": ["BNS 103"],
                "retrieved": ["BNS 103", "IPC 302", "BNS 109", "IPC 307"],
                "graph_enriched": [True, True, False, False],
                "reasoning_confidence": [0.95, 0.9, 0.62, 0.53],
            },
            {
                "id": "dowry_001",
                "query": "dowry cruelty",
                "expected_sections": ["IPC 498A"],
                "expected_priority": ["IPC 498A"],
                "retrieved": ["IPC 498A", "IPC 304B", "IPC 306"],
                "graph_enriched": [True, False, False],
                "reasoning_confidence": [0.92, 0.71, 0.58],
            },
            {
                "id": "rape_001",
                "query": "rape",
                "expected_sections": ["IPC 376"],
                "expected_priority": ["IPC 376"],
                "retrieved": ["IPC 376", "IPC 354", "IPC 375"],
                "graph_enriched": [True, True, False],
                "reasoning_confidence": [0.94, 0.74, 0.63],
            },
            {
                "id": "acid_attack_001",
                "query": "acid attack",
                "expected_sections": ["IPC 326A"],
                "expected_priority": ["IPC 326A"],
                "retrieved": ["IPC 326A", "IPC 326", "IPC 307"],
                "graph_enriched": [True, False, False],
                "reasoning_confidence": [0.93, 0.67, 0.61],
            },
            {
                "id": "cyber_fraud_001",
                "query": "cyber fraud",
                "expected_sections": ["IPC 420"],
                "expected_priority": ["IPC 420"],
                "retrieved": ["IPC 420", "IPC 468", "IPC 467"],
                "graph_enriched": [True, True, False],
                "reasoning_confidence": [0.9, 0.85, 0.7],
            },
        ]
        print(json.dumps(evaluate_benchmark(benchmark_queries), indent=2, ensure_ascii=True))
        return

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
