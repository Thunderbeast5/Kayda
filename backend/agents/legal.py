"""
LexiGraph Retrieval Agent — narrative -> applicable IPC/BNS sections
=====================================================================
Takes a free-text description of an incident (possibly involving several
distinct criminal acts, e.g. "robbed a shop and accidentally killed the
owner") and returns the applicable IPC and BNS sections, retrieved from
your existing Pinecone index (legal-sections-v2) and Neo4j graph.

Why not just embed the whole sentence and do one Pinecone query?
------------------------------------------------------------------
A single embedding of a multi-clause narrative gets dominated by whichever
clause is semantically "loudest" (usually the first / most concrete noun,
e.g. "robbery"). Subordinate clauses like "...and accidentally killed the
owner" rarely surface culpable-homicide or robbery-with-death sections in
the top-k of a single query. So this agent:

  1. Uses an LLM to DECOMPOSE the narrative into distinct criminal acts,
     each rewritten as a clean legal-semantic query (not the raw sentence
     span) -- this is the "understand meaning, not keywords" part.
  2. Retrieves per identified act (Pinecone semantic + Neo4j Crime-name
     fuzzy match as a recall net), AND retrieves on the whole narrative
     once more to catch compound/aggravated sections (e.g. robbery
     resulting in death) that per-act splitting alone could miss.
  3. Expands every candidate through Neo4j to pull full text, punishment,
     and the IPC<->BNS crosswalk (REPLACED_BY / REPLACES), so an IPC hit
     always carries its current BNS equivalent and vice versa.
  4. Reranks + dedupes into one structure per identified act.
  5. Optionally asks the LLM for a short justification per act, GROUNDED
     ONLY in retrieved section text -- it is explicitly told never to cite
     a section number that wasn't actually retrieved, to prevent
     hallucinated sections.

Requires: pinecone, neo4j, sentence-transformers, openai, python-dotenv
(same as your ingest scripts, plus `openai` for the DeepSeek client).

Env vars (same .env your ingest scripts already use), plus:
    DEEPSEEK_API_KEY
    DEEPSEEK_BASE_URL   (default: https://api.deepseek.com)
    DEEPSEEK_MODEL      (default: deepseek-chat)
    PINECONE_INDEX_NAME (default: legal-sections-v2)

Usage
-----
    python legal_agent.py "A person robbed a shop and accidentally killed the owner"
    python legal_agent.py --json "..."          # raw JSON output, no pretty print
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

# ----------------------------------------------------------------------
# Env / config
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))
env_candidates = [BASE_DIR / ".env", BASE_DIR.parent / ".env", Path(".env")]
ENV_PATH = next((c for c in env_candidates if c.exists()), None)
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH) if ENV_PATH else load_dotenv()
except ImportError:
    pass

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-sections-v2")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")  # must match ingest

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Groq uses standard configuration via config.llm_config

TOP_K_PER_ACT = 6          # pinecone candidates pulled per identified criminal act
TOP_K_WHOLE_NARRATIVE = 6  # pinecone candidates pulled for the full narrative (compound offenses)
FINAL_SECTIONS_PER_ACT = 4 # how many ranked sections to keep per act, per side (IPC/BNS)


# ----------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------
@dataclass
class SectionCandidate:
    id: str                    # e.g. "IPC_302"
    act: str                   # "IPC" | "BNS"
    section: str
    title: str
    description: str = ""
    punishment: str = ""
    chapter: str = ""
    category: str = ""
    cognizable: str = ""
    bailable: str = ""
    court: str = ""
    equivalent_act: str | None = None
    equivalent_section: str | None = None
    mapping_status: str | None = None
    semantic_score: float = 0.0
    source: str = "pinecone"   # "pinecone" | "graph_crime_match" | "graph_crosswalk"
    final_score: float = 0.0

    def key(self) -> str:
        return self.id


@dataclass
class CriminalAct:
    label: str                 # e.g. "Robbery of the shop"
    query_text: str            # semantically clean text used for retrieval
    raw_span: str = ""         # the part of the user's narrative this came from
    candidates: list[SectionCandidate] = field(default_factory=list)
    reasoning: str = ""


# ----------------------------------------------------------------------
# LLM: decomposition + grounded reasoning (Groq)
# ----------------------------------------------------------------------
def _get_llm(temperature: float = 0.2):
    from config.llm_config import get_llm
    return get_llm(temperature=temperature)


DECOMPOSE_SYSTEM_PROMPT = """You are a legal-analysis assistant for Indian criminal law (IPC/BNS).
Given a plain-language description of an incident, identify every DISTINCT
criminal act described (there may be one, or several — e.g. a robbery in
which someone is also killed is TWO acts: the robbery, and the killing).

For each act output:
  - "label": a short human-readable name (e.g. "Robbery of the shop")
  - "query_text": a clean, legally-phrased description suitable for a
    semantic search against a database of penal code sections. Use the
    correct legal terminology where obvious (e.g. "culpable homicide not
    amounting to murder" vs "murder" depending on intent described),
    but do NOT invent facts not implied by the narrative, and do NOT
    output a specific section number yourself — that is looked up
    separately.
  - "raw_span": the portion of the original text this act refers to.

Respond with ONLY valid JSON, no markdown fences, no commentary:
{"acts": [{"label": "...", "query_text": "...", "raw_span": "..."}]}
"""


def decompose_incident(narrative: str) -> list[CriminalAct]:
    llm = _get_llm(temperature=0.0)
    from langchain_core.messages import SystemMessage, HumanMessage
    resp = llm.invoke([
        SystemMessage(content=DECOMPOSE_SYSTEM_PROMPT),
        HumanMessage(content=narrative)
    ])
    raw = resp.content.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat the whole narrative as a single act rather than fail outright
        return [CriminalAct(label="Reported incident", query_text=narrative, raw_span=narrative)]

    acts = []
    for a in data.get("acts", []):
        label = (a.get("label") or "").strip()
        query_text = (a.get("query_text") or "").strip() or label
        if not query_text:
            continue
        acts.append(CriminalAct(label=label or query_text, query_text=query_text,
                                 raw_span=(a.get("raw_span") or "").strip()))
    if not acts:
        acts = [CriminalAct(label="Reported incident", query_text=narrative, raw_span=narrative)]
    return acts


REASONING_SYSTEM_PROMPT = """You are a legal-analysis assistant for Indian criminal law.
You will be given a description of one criminal act from an incident, and a
list of candidate law sections that were RETRIEVED from a legal database
(with their real titles, descriptions and punishments).

Write a short (2-4 sentence) explanation of which of the listed sections
apply and why, in plain language.

STRICT RULES:
  - Only ever refer to sections that appear in the provided candidate list.
  - Never state or imply a section number that is not in that list.
  - If none of the candidates clearly fit, say so plainly instead of
    guessing.
  - Do not invent facts beyond what the act description states.
"""


def synthesize_reasoning(act: CriminalAct) -> str:
    if not act.candidates:
        return "No matching sections were retrieved for this act."
    llm = _get_llm(temperature=0.0)
    from langchain_core.messages import SystemMessage, HumanMessage
    candidate_block = "\n\n".join(
        f"[{c.id}] {c.act} Section {c.section} — {c.title}\n"
        f"Description: {c.description[:400]}\n"
        f"Punishment: {c.punishment[:200]}"
        for c in act.candidates
    )
    user_msg = f"Criminal act: {act.label}\n({act.query_text})\n\nCandidate sections:\n{candidate_block}"
    resp = llm.invoke([
        SystemMessage(content=REASONING_SYSTEM_PROMPT),
        HumanMessage(content=user_msg)
    ])
    return resp.content.strip()


# ----------------------------------------------------------------------
# Pinecone retrieval
# ----------------------------------------------------------------------
_embed_model = None
_pinecone_index = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    return _embed_model


def _get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is None:
        from pinecone import Pinecone
        if not PINECONE_API_KEY:
            raise ValueError(f"PINECONE_API_KEY not set (checked {ENV_PATH}).")
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    return _pinecone_index


def semantic_search(query_text: str, top_k: int) -> list[SectionCandidate]:
    model = _get_embed_model()
    index = _get_pinecone_index()
    vector = model.encode(query_text).tolist()
    result = index.query(vector=vector, top_k=top_k, include_metadata=True)

    candidates = []
    for match in result.get("matches", []):
        meta = match.get("metadata", {}) or {}
        candidates.append(SectionCandidate(
            id=match["id"],
            act=meta.get("act", match["id"].split("_")[0]),
            section=meta.get("section", match["id"].split("_", 1)[-1]),
            title=meta.get("title", ""),
            punishment=meta.get("punishment", ""),
            chapter=meta.get("chapter", ""),
            category=meta.get("category", ""),
            cognizable=meta.get("cognizable", ""),
            bailable=meta.get("bailable", ""),
            court=meta.get("court", ""),
            equivalent_act=meta.get("equivalent_act"),
            equivalent_section=meta.get("equivalent_section"),
            mapping_status=meta.get("mapping_status"),
            semantic_score=float(match.get("score", 0.0)),
            source="pinecone",
        ))
    return candidates


# ----------------------------------------------------------------------
# Neo4j graph expansion (ground truth: full text, punishment, crosswalk)
# ----------------------------------------------------------------------
_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        from neo4j import GraphDatabase
        if not (NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
            raise ValueError(f"Neo4j credentials not set (checked {ENV_PATH}).")
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def graph_enrich(candidates: list[SectionCandidate]) -> None:
    """Fill in full description/punishment/crosswalk from Neo4j, in place.
    Pinecone metadata already has most of this, but Neo4j is the source of
    truth and has the full (untruncated) description + punishment, plus the
    live crosswalk relationship rather than a metadata snapshot."""
    if not candidates:
        return
    driver = _get_driver()
    ids = [c.id for c in candidates]
    with driver.session() as session:
        rows = session.run(
            """
            UNWIND $ids AS lid
            MATCH (l:LawSection {id: lid})
            OPTIONAL MATCH (l)-[:REPLACED_BY]->(other:LawSection)
            OPTIONAL MATCH (l)<-[:REPLACES]-(other2:LawSection)
            WITH l, coalesce(other, other2) AS eq
            RETURN l.id AS id, l.description AS description, l.punishment AS punishment,
                   l.title AS title, eq.act AS eq_act, eq.section AS eq_section,
                   l.mapping_status AS mapping_status
            """,
            ids=ids,
        ).data()
    by_id = {r["id"]: r for r in rows}
    for c in candidates:
        r = by_id.get(c.id)
        if not r:
            continue
        if r.get("description"):
            c.description = r["description"]
        if r.get("punishment"):
            c.punishment = r["punishment"]
        if r.get("title"):
            c.title = r["title"]
        if r.get("eq_act") and r.get("eq_section"):
            c.equivalent_act = r["eq_act"]
            c.equivalent_section = r["eq_section"]
        if r.get("mapping_status"):
            c.mapping_status = r["mapping_status"]


def crime_name_recall(query_text: str) -> list[SectionCandidate]:
    """Recall net: fuzzy-match the act's key noun(s) against Crime.name /
    LawSection.title directly in the graph. Catches exact-title offenses
    (e.g. 'Murder', 'Theft') that a single embedding sometimes ranks lower
    than a more verbose but less relevant section."""
    driver = _get_driver()
    # crude but effective: take the most distinctive word(s) from the query
    terms = [w for w in re.findall(r"[A-Za-z]+", query_text) if len(w) > 4]
    if not terms:
        return []
    with driver.session() as session:
        rows = session.run(
            """
            UNWIND $terms AS term
            MATCH (l:LawSection)
            WHERE toLower(l.title) CONTAINS toLower(term)
            RETURN DISTINCT l.id AS id, l.act AS act, l.section AS section,
                   l.title AS title, l.description AS description,
                   l.punishment AS punishment, l.mapping_status AS mapping_status
            LIMIT 10
            """,
            terms=terms,
        ).data()
    return [
        SectionCandidate(
            id=r["id"], act=r["act"], section=r["section"], title=r["title"] or "",
            description=r.get("description") or "", punishment=r.get("punishment") or "",
            mapping_status=r.get("mapping_status"), semantic_score=0.0,
            source="graph_crime_match",
        )
        for r in rows
    ]


# ----------------------------------------------------------------------
# Rerank + merge
# ----------------------------------------------------------------------
def rerank_and_dedupe(candidates: list[SectionCandidate], query_text: str) -> list[SectionCandidate]:
    query_terms = set(w.lower() for w in re.findall(r"[A-Za-z]+", query_text) if len(w) > 3)

    by_id: dict[str, SectionCandidate] = {}
    for c in candidates:
        title_terms = set(w.lower() for w in re.findall(r"[A-Za-z]+", c.title))
        title_overlap_bonus = 0.15 if (query_terms & title_terms) else 0.0
        graph_match_bonus = 0.1 if c.source == "graph_crime_match" else 0.0
        c.final_score = c.semantic_score + title_overlap_bonus + graph_match_bonus

        existing = by_id.get(c.id)
        if existing is None or c.final_score > existing.final_score:
            by_id[c.id] = c

    return sorted(by_id.values(), key=lambda c: c.final_score, reverse=True)


def split_by_act_and_trim(candidates: list[SectionCandidate], n_per_side: int) -> list[SectionCandidate]:
    ipc = [c for c in candidates if c.act == "IPC"][:n_per_side]
    bns = [c for c in candidates if c.act == "BNS"][:n_per_side]
    merged = ipc + bns
    merged.sort(key=lambda c: c.final_score, reverse=True)
    return merged


# ----------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------
def retrieve_for_act(act: CriminalAct) -> None:
    raw_candidates = semantic_search(act.query_text, TOP_K_PER_ACT)
    raw_candidates += crime_name_recall(act.query_text)
    graph_enrich(raw_candidates)
    ranked = rerank_and_dedupe(raw_candidates, act.query_text)
    act.candidates = split_by_act_and_trim(ranked, FINAL_SECTIONS_PER_ACT)


def analyze_incident(narrative: str, explain: bool = True) -> dict[str, Any]:
    acts = decompose_incident(narrative)

    for act in acts:
        retrieve_for_act(act)

    # Whole-narrative pass to catch compound/aggravated offenses that
    # per-act decomposition can miss (e.g. "robbery with murder" as a
    # single named offense distinct from robbery + murder separately).
    compound = CriminalAct(label="Compound/aggravated offense check", query_text=narrative)
    retrieve_for_act(compound)
    # Only keep compound results that aren't already covered by a per-act hit
    already_seen = {c.id for act in acts for c in act.candidates}
    compound.candidates = [c for c in compound.candidates if c.id not in already_seen]

    if explain:
        for act in acts:
            act.reasoning = synthesize_reasoning(act)
        if compound.candidates:
            compound.reasoning = synthesize_reasoning(compound)

    result_acts = acts + ([compound] if compound.candidates else [])

    return {
        "narrative": narrative,
        "identified_acts": [
            {
                "label": act.label,
                "query_used": act.query_text,
                "raw_span": act.raw_span,
                "reasoning": act.reasoning,
                "sections": [
                    {
                        "id": c.id,
                        "act": c.act,
                        "section": c.section,
                        "title": c.title,
                        "description": c.description,
                        "punishment": c.punishment,
                        "cognizable": c.cognizable,
                        "bailable": c.bailable,
                        "court": c.court,
                        "equivalent_act": c.equivalent_act,
                        "equivalent_section": c.equivalent_section,
                        "mapping_status": c.mapping_status,
                        "score": round(c.final_score, 4),
                        "source": c.source,
                    }
                    for c in act.candidates
                ],
            }
            for act in result_acts
        ],
    }


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Narrative -> IPC/BNS section retrieval agent")
    parser.add_argument("narrative", help="Free-text description of the incident")
    parser.add_argument("--json", action="store_true", help="Print raw JSON only")
    parser.add_argument("--no-explain", action="store_true", help="Skip LLM reasoning synthesis (retrieval only)")
    args = parser.parse_args()

    result = analyze_incident(args.narrative, explain=not args.no_explain)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"\nIncident: {result['narrative']}\n" + "=" * 70)
    for act in result["identified_acts"]:
        print(f"\n>> {act['label']}")
        if act["raw_span"]:
            print(f"   (from: \"{act['raw_span']}\")")
        if act["reasoning"]:
            print(f"   {act['reasoning']}")
        for s in act["sections"]:
            eq = f"  [<-> {s['equivalent_act']} {s['equivalent_section']}]" if s["equivalent_section"] else ""
            print(f"     - {s['act']} Section {s['section']}: {s['title']}  (score {s['score']}){eq}")
        if not act["sections"]:
            print("     (no sections retrieved)")


if __name__ == "__main__":
    main()