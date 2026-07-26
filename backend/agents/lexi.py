# """
# Sprint 4: LexiGraph Agent — GraphRAG Legal Retriever
# ======================================================
# Connects Neo4j (graph) + Pinecone (vector) to retrieve real IPC sections
# BEFORE any LLM reasoning call. This is the retrieval backbone for
# Prosecutor, Defense, and Judge agents.

# Pipeline for every query
# ------------------------
# Step A  — spaCy NER: extract crime keywords from query_text
# Step B  — Neo4j graph query: CONTAINS match on Crime.name and IPC.description
# Step C  — Pinecone vector query: 384-dim semantic similarity search
# Step D  — Merge + deduplicate + rank: Neo4j hits first (exact), then Pinecone
# Step E  — Guardrail: if 0 results, LLM rewrites the query and retries once

# Key facts about the database (verified before writing):
#   Neo4j  : IPC nodes have {section, description, punishment}
#            Crime nodes store FULL offense text (e.g. "Theft by clerk…")
#            Relationship: (:Crime)-[:DEFINED_BY]->(:IPC)
#   Pinecone: 448 vectors, dim=384 (all-MiniLM-L6-v2)
#             IDs like "IPC_302", metadata={section, offense, punishment}
# """

# import os
# import json
# import re
# from pathlib import Path
# from typing import Optional

# from dotenv import load_dotenv

# # ── Environment ───────────────────────────────────────────────────────────────
# BASE_DIR = Path(__file__).resolve().parent.parent
# load_dotenv(BASE_DIR / ".env")

# NEO4J_URI      = os.getenv("NEO4J_URI", "")
# NEO4J_USER     = os.getenv("NEO4J_USER", "")
# NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
# NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
# PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
# PINECONE_HOST    = os.getenv(
#     "PINECONE_HOST",
#     "legal-embeddings-ce6891u.svc.aped-4627-b74a.pinecone.io",
# )

# # ── Lazy singletons ───────────────────────────────────────────────────────────
# _spacy_nlp      = None
# _embedder       = None
# _pinecone_index = None
# _neo4j_driver   = None


# def _nlp():
#     global _spacy_nlp
#     if _spacy_nlp is None:
#         import spacy
#         try:
#             _spacy_nlp = spacy.load("en_core_web_sm")
#         except OSError:
#             raise RuntimeError(
#                 "spaCy model not found. Run:\n"
#                 "  venv\\Scripts\\python -m spacy download en_core_web_sm"
#             )
#     return _spacy_nlp


# def _embed(texts: list[str]) -> list[list[float]]:
#     """Embed a list of strings using sentence-transformers (384-dim)."""
#     global _embedder
#     if _embedder is None:
#         from sentence_transformers import SentenceTransformer
#         _embedder = SentenceTransformer("all-MiniLM-L6-v2")
#     return _embedder.encode(texts, convert_to_numpy=True).tolist()


# def _pinecone():
#     global _pinecone_index
#     if _pinecone_index is None:
#         if not PINECONE_API_KEY:
#             raise RuntimeError("PINECONE_API_KEY not set in backend/.env")
#         from pinecone import Pinecone
#         pc = Pinecone(api_key=PINECONE_API_KEY)
#         _pinecone_index = pc.Index(host=PINECONE_HOST)
#     return _pinecone_index


# def _neo4j():
#     global _neo4j_driver
#     if _neo4j_driver is None:
#         if not NEO4J_URI:
#             raise RuntimeError("NEO4J_URI not set in backend/.env")
#         from neo4j import GraphDatabase
#         _neo4j_driver = GraphDatabase.driver(
#             NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
#         )
#     return _neo4j_driver


# # ── Step A: spaCy keyword extraction ─────────────────────────────────────────

# # Legal crime keywords that spaCy may not label as NER entities but are
# # critical for IPC matching.
# _LEGAL_KEYWORDS = {
#     "theft", "robbery", "dacoity", "murder", "homicide", "assault", "rape",
#     "fraud", "cheating", "forgery", "extortion", "kidnap", "abduction",
#     "trespass", "arson", "bribery", "corruption", "defamation", "sedition",
#     "rioting", "hurt", "grievous", "intimidation", "threatening", "stalking",
#     "dowry", "cruelty", "obscenity", "gambling", "smuggling", "trafficking",
#     "poisoning", "accident", "negligence", "embezzlement", "breach",
#     "misappropriation", "impersonation", "counterfeiting", "mischief",
# }


# def extract_crime_keywords(query_text: str) -> list[str]:
#     """
#     Step A — Use spaCy NER + legal keyword matching to extract crime terms.

#     Returns a deduplicated list of keywords in order of confidence:
#       1. spaCy EVENT entities (highest — explicit event labels)
#       2. spaCy ORG/NORP entities that overlap legal terms
#       3. Pattern-matched legal keywords from the text
#       4. Significant nouns/noun-chunks as fallback
#     """
#     nlp  = _nlp()
#     doc  = nlp(query_text)
#     seen = set()
#     keywords: list[str] = []

#     def _add(word: str):
#         w = word.strip().lower()
#         if w and w not in seen and len(w) > 2:
#             seen.add(w)
#             keywords.append(w)

#     # 1. spaCy named entities
#     for ent in doc.ents:
#         if ent.label_ in ("EVENT", "ORG", "NORP", "LAW", "GPE"):
#             _add(ent.text)

#     # 2. Legal keywords present in text (case-insensitive)
#     text_lower = query_text.lower()
#     for kw in _LEGAL_KEYWORDS:
#         if kw in text_lower:
#             _add(kw)

#     # 3. Noun chunks as fallback (take first 4 words max per chunk)
#     if len(keywords) < 2:
#         for chunk in doc.noun_chunks:
#             # Skip very short or stopword-only chunks
#             if any(t.is_alpha and not t.is_stop for t in chunk):
#                 _add(" ".join(t.text for t in chunk if t.is_alpha)[:40])

#     # 4. Individual non-stop nouns as final fallback
#     if len(keywords) < 2:
#         for token in doc:
#             if token.pos_ in ("NOUN", "PROPN") and not token.is_stop:
#                 _add(token.lemma_)

#     return keywords[:8]   # cap: 8 keywords is enough, more causes noise


# # ── Step B: Neo4j graph queries ───────────────────────────────────────────────

# def _neo4j_run(cypher: str, params: dict) -> list[dict]:
#     driver = _neo4j()
#     with driver.session(database=NEO4J_DATABASE) as session:
#         result = session.run(cypher, params)
#         return [dict(record) for record in result]


# def _query_neo4j(keywords: list[str], section_hint: str = None) -> list[dict]:
#     """
#     Step B — Query Neo4j using the extracted keywords.

#     Three strategies (run all, merge results):
#       B1. Exact section fetch if a specific IPC number is known.
#       B2. Crime node CONTAINS match on full offense text.
#       B3. IPC description CONTAINS match (broader fallback).
#     """
#     results   = []
#     seen_secs = set()

#     def _add_rows(rows: list[dict], source: str):
#         for r in rows:
#             sec = str(r.get("section", "")).strip()
#             if sec and sec not in seen_secs:
#                 seen_secs.add(sec)
#                 results.append({
#                     "section":     sec,
#                     "description": r.get("description", ""),
#                     "punishment":  r.get("punishment", ""),
#                     "offense":     r.get("offense", r.get("crime_name", "")),
#                     "source":      source,
#                     "score":       1.0 if source == "neo4j:exact" else 0.85,
#                 })

#     # B1 — exact section
#     if section_hint:
#         clean = re.sub(r"[^0-9A-Za-z]", "", section_hint)
#         rows = _neo4j_run(
#             """
#             MATCH (l:IPC)
#             WHERE l.section = $sec OR l.section = $sec_upper
#             RETURN l.section AS section, l.description AS description,
#                    l.punishment AS punishment, '' AS offense
#             LIMIT 3
#             """,
#             {"sec": clean, "sec_upper": clean.upper()},
#         )
#         _add_rows(rows, "neo4j:exact")

#     if not keywords:
#         return results

#     # B2 — Crime node offense text CONTAINS keyword
#     # Build WHERE clause dynamically for each keyword
#     for kw in keywords[:5]:
#         rows = _neo4j_run(
#             """
#             MATCH (c:Crime)-[:DEFINED_BY]->(l:IPC)
#             WHERE toLower(c.name) CONTAINS toLower($kw)
#             RETURN l.section AS section, l.description AS description,
#                    l.punishment AS punishment, c.name AS offense
#             LIMIT 5
#             """,
#             {"kw": kw},
#         )
#         _add_rows(rows, "neo4j:crime_node")

#     # B3 — IPC description CONTAINS keyword (broader)
#     if len(results) < 3:
#         for kw in keywords[:4]:
#             rows = _neo4j_run(
#                 """
#                 MATCH (l:IPC)
#                 WHERE toLower(l.description) CONTAINS toLower($kw)
#                 RETURN l.section AS section, l.description AS description,
#                        l.punishment AS punishment, '' AS offense
#                 LIMIT 5
#                 """,
#                 {"kw": kw},
#             )
#             _add_rows(rows, "neo4j:description")

#     return results


# # ── Step C: Pinecone vector search ────────────────────────────────────────────

# # IPC law vectors were ingested with IDs like "IPC_379", "IPC_302A" etc.
# # FIR/case-summary vectors stored by evidence_analyzer use "CASE_..." IDs.
# _IPC_ID_RE      = re.compile(r"^IPC_\d+[A-Za-z]*$")
# _IPC_SECTION_RE = re.compile(r"^\d+[A-Za-z]*$")


# def _is_ipc_hit(match_id: str, meta: dict) -> bool:
#     """Return True only for IPC law vectors; skip FIR session embeddings."""
#     if _IPC_ID_RE.match(match_id):
#         return True
#     sec = str(meta.get("section", ""))
#     return bool(sec and _IPC_SECTION_RE.match(sec))


# def _query_pinecone(query_text: str, top_k: int = 5) -> list[dict]:
#     """
#     Step C — Embed query_text and search Pinecone for semantically
#     similar IPC sections. Filters out FIR/case-summary embeddings.
#     """
#     index  = _pinecone()
#     vector = _embed([query_text])[0]

#     # Request extra candidates so we still get top_k after filtering FIR noise
#     response = index.query(
#         vector=vector,
#         top_k=top_k * 3,
#         include_metadata=True,
#     )

#     results = []
#     for match in response.get("matches", []):
#         mid  = match.get("id", "")
#         meta = match.get("metadata", {})

#         # Skip FIR / case-summary embeddings
#         if not _is_ipc_hit(mid, meta):
#             continue

#         section = meta.get("section", mid.replace("IPC_", ""))
#         results.append({
#             "section":     section,
#             "description": meta.get("description", ""),
#             "punishment":  meta.get("punishment", ""),
#             "offense":     meta.get("offense", ""),
#             "source":      "pinecone:vector",
#             "score":       round(float(match.get("score", 0.0)), 4),
#         })

#         if len(results) >= top_k:
#             break

#     return results


# # ── Step D: Merge, enrich from Neo4j, rank ────────────────────────────────────

# def _enrich_from_neo4j(section: str) -> dict:
#     """
#     For a Pinecone hit that has a section number but no description,
#     fetch the full node from Neo4j.
#     """
#     rows = _neo4j_run(
#         """
#         MATCH (l:IPC)
#         WHERE l.section = $sec
#         RETURN l.section AS section, l.description AS description,
#                l.punishment AS punishment
#         LIMIT 1
#         """,
#         {"sec": section},
#     )
#     if rows:
#         return rows[0]
#     return {}


# def _merge_and_rank(
#     neo4j_hits: list[dict],
#     pinecone_hits: list[dict],
#     top_n: int = 5,
# ) -> list[dict]:
#     """
#     Step D — Deduplicate and rank results.

#     Scoring logic:
#       - Neo4j exact match:       score = 1.0
#       - Neo4j crime/desc match:  score = 0.85
#       - Pinecone only:           score = cosine similarity (0–1)
#       - Both Neo4j + Pinecone:   score = max(neo4j_score, pinecone_score) + 0.1 boost
#     """
#     merged: dict[str, dict] = {}   # section -> best record

#     # Add Neo4j hits first
#     for r in neo4j_hits:
#         sec = r["section"]
#         merged[sec] = dict(r)

#     # Merge Pinecone hits
#     for r in pinecone_hits:
#         sec = r["section"]
#         if sec in merged:
#             # Section already found by Neo4j — boost score
#             existing       = merged[sec]
#             boosted_score  = max(existing["score"], r["score"]) + 0.10
#             existing["score"]  = round(min(boosted_score, 1.0), 4)
#             existing["source"] = existing["source"] + "+pinecone"
#             # Fill in missing description from Pinecone metadata if Neo4j had none
#             if not existing.get("description") and r.get("description"):
#                 existing["description"] = r["description"]
#             if not existing.get("offense") and r.get("offense"):
#                 existing["offense"] = r["offense"]
#         else:
#             # New section from Pinecone — enrich with Neo4j description
#             record = dict(r)
#             if not record.get("description") or not record.get("punishment"):
#                 enriched = _enrich_from_neo4j(sec)
#                 if enriched:
#                     record["description"] = record.get("description") or enriched.get("description", "")
#                     record["punishment"]  = record.get("punishment")  or enriched.get("punishment", "")
#             merged[sec] = record

#     # Sort by score descending, return top_n
#     ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
#     return ranked[:top_n]


# # ── Step E: Guardrail — LLM query rewrite ────────────────────────────────────

# def _rewrite_query(original_query: str) -> str:
#     """
#     Step E — If retrieval returns 0 results, ask the LLM to rephrase
#     the query using Indian Penal Code terminology.
#     """
#     from config.llm_config import get_llm
#     llm    = get_llm(temperature=0.3)
#     prompt = (
#         f"You are an Indian legal expert. The following query returned no results "
#         f"from an IPC (Indian Penal Code) database:\n\n"
#         f"\"{original_query}\"\n\n"
#         f"Rewrite this query using precise Indian Penal Code legal terminology "
#         f"(e.g. 'theft', 'culpable homicide', 'criminal intimidation', 'cheating'). "
#         f"Return ONLY the rewritten query — no explanation, no punctuation."
#     )
#     response  = llm.invoke(prompt)
#     rewritten = response.content.strip().strip('"').strip("'")
#     print(f"[LexiGraph] Query rewritten: '{original_query}' → '{rewritten}'")
#     return rewritten


# # ── Public API ────────────────────────────────────────────────────────────────

# def retrieve(
#     query_text: str,
#     section_hint: str = None,
#     top_n: int = 5,
#     pinecone_top_k: int = 7,
# ) -> dict:
#     """
#     Main retrieval function. Call this BEFORE any LLM prompt.

#     Parameters
#     ----------
#     query_text    : Free-text crime description from structured_facts or user query.
#     section_hint  : Specific IPC section if already known (e.g. "302" or "IPC_381").
#     top_n         : Number of final ranked results to return (default 5).
#     pinecone_top_k: How many Pinecone candidates to fetch before ranking (default 7).

#     Returns
#     -------
#     {
#         "ipc_sections": [
#             {
#                 "section":     "302",
#                 "description": "...",
#                 "punishment":  "Death or Imprisonment for Life + Fine",
#                 "offense":     "Murder",
#                 "source":      "neo4j:crime_node+pinecone",
#                 "score":       0.95
#             },
#             ...
#         ],
#         "keywords":       ["murder", "homicide"],
#         "neo4j_count":    3,
#         "pinecone_count": 5,
#         "query_used":     "murder of a person",   # may differ if rewritten
#         "rewritten":      False,
#     }
#     """
#     print(f"\n[LexiGraph] ── Retrieving for: '{query_text[:80]}'")

#     # ── Step A: extract keywords ──────────────────────────────────────
#     keywords = extract_crime_keywords(query_text)
#     print(f"[LexiGraph] Step A — keywords: {keywords}")

#     # ── Step B: Neo4j ─────────────────────────────────────────────────
#     neo4j_hits = []
#     try:
#         neo4j_hits = _query_neo4j(keywords, section_hint)
#         print(f"[LexiGraph] Step B — Neo4j: {len(neo4j_hits)} hits")
#     except Exception as e:
#         print(f"[LexiGraph] Neo4j error: {e}")

#     # ── Step C: Pinecone ──────────────────────────────────────────────
#     pinecone_hits = []
#     try:
#         pinecone_hits = _query_pinecone(query_text, top_k=pinecone_top_k)
#         print(f"[LexiGraph] Step C — Pinecone: {len(pinecone_hits)} hits")
#     except Exception as e:
#         print(f"[LexiGraph] Pinecone error: {e}")

#     # ── Step D: merge & rank ──────────────────────────────────────────
#     ranked = _merge_and_rank(neo4j_hits, pinecone_hits, top_n=top_n)
#     print(f"[LexiGraph] Step D — merged: {len(ranked)} unique sections")

#     rewritten = False

#     # ── Step E: guardrail — retry with rewritten query ────────────────
#     if len(ranked) == 0:
#         print("[LexiGraph] Step E — 0 results, rewriting query...")
#         rewritten_query = _rewrite_query(query_text)
#         rewritten       = True

#         # Retry with rewritten query
#         keywords_2      = extract_crime_keywords(rewritten_query)
#         neo4j_hits_2    = []
#         pinecone_hits_2 = []
#         try:
#             neo4j_hits_2 = _query_neo4j(keywords_2, section_hint)
#         except Exception as e:
#             print(f"[LexiGraph] Neo4j retry error: {e}")
#         try:
#             pinecone_hits_2 = _query_pinecone(rewritten_query, top_k=pinecone_top_k)
#         except Exception as e:
#             print(f"[LexiGraph] Pinecone retry error: {e}")

#         ranked     = _merge_and_rank(neo4j_hits_2, pinecone_hits_2, top_n=top_n)
#         keywords   = keywords_2
#         print(f"[LexiGraph] Step E retry — {len(ranked)} sections after rewrite")
#         query_text = rewritten_query

#     return {
#         "ipc_sections":   ranked,
#         "keywords":       keywords,
#         "neo4j_count":    len(neo4j_hits),
#         "pinecone_count": len(pinecone_hits),
#         "query_used":     query_text,
#         "rewritten":      rewritten,
#     }


# def format_for_prompt(result: dict) -> str:
#     """
#     Formats the retrieval result into a clean, numbered string
#     ready to be injected into any LLM system/user prompt.
#     """
#     sections = result.get("ipc_sections", [])
#     if not sections:
#         return (
#             "DATABASE RETRIEVAL: No relevant IPC sections found.\n"
#             f"Keywords tried: {result.get('keywords', [])}\n"
#             "The LLM must reason from general knowledge only."
#         )

#     lines = [
#         f"RETRIEVED IPC SECTIONS  "
#         f"[Neo4j:{result['neo4j_count']}  Pinecone:{result['pinecone_count']}  "
#         f"Final:{len(sections)}]",
#         "=" * 65,
#     ]
#     for i, s in enumerate(sections, 1):
#         sec    = s.get("section", "?")
#         off    = s.get("offense", "").strip()
#         punish = s.get("punishment", "N/A").strip()
#         src    = s.get("source", "")
#         score  = s.get("score", 0)
#         desc   = s.get("description", "").strip()

#         # Show first 200 chars of description only — keeps prompt lean
#         desc_short = (desc[:200] + "…") if len(desc) > 200 else desc

#         lines.append(
#             f"\n{i}. IPC {sec}  [score={score:.2f} | {src}]\n"
#             f"   Offense   : {off or 'See description'}\n"
#             f"   Punishment: {punish}\n"
#             f"   Summary   : {desc_short}"
#         )

#     if result.get("rewritten"):
#         lines.append(f"\n[Note: query was rewritten for better matching]")

#     return "\n".join(lines)


# # ── LangGraph node wrapper ────────────────────────────────────────────────────

# def lexigraph_node(state: dict) -> dict:
#     """
#     LangGraph-compatible node. Reads structured_facts (or user_query as fallback)
#     and stores retrieved laws into state['relevant_laws'].

#     Wire into orchestrator_graph.py:
#         graph.add_node("lexigraph", lexigraph_node)
#         graph.add_edge("evidence_analyzer", "lexigraph")
#     """
#     facts   = state.get("structured_facts") or {}
#     incident = facts.get("incident", {})
#     sections = facts.get("sections", [])

#     query_parts: list[str] = []
#     if incident.get("summary"):
#         query_parts.append(incident["summary"])
#     if sections:
#         # Use the first known section as a hint
#         section_hint = sections[0].replace("IPC ", "").replace("IPC_", "").strip()
#     else:
#         section_hint = None

#     if not query_parts:
#         query_parts.append(state.get("user_query", ""))

#     query_text = ". ".join(filter(None, query_parts))
#     result     = retrieve(query_text, section_hint=section_hint)

#     state["relevant_laws"]      = result["ipc_sections"]
#     state["lexigraph_result"]   = result          # full result for downstream agents
#     print(f"[LexiGraph] Retrieved {len(result['ipc_sections'])} law(s).")
#     return state


# # ── CLI / standalone runner ───────────────────────────────────────────────────

# def _print_results(query: str, result: dict) -> None:
#     """Pretty-print retrieve() output in a readable bordered format."""
#     import textwrap
#     sections = result["ipc_sections"]
#     W = 70   # display width

#     print(f"\n🔍 Query: {query}\n")
#     print("─" * W)

#     if not sections:
#         print("❌  No results found even after guardrail rewrite.")
#         print("─" * W)
#         return

#     print(f"✅  Found {len(sections)} relevant law(s):\n")

#     for i, law in enumerate(sections, 1):
#         src   = law.get("source", "").upper()
#         score = law.get("score", 0.0)
#         sec   = law.get("section", "?")
#         desc  = law.get("description", "") or "(no description stored)"
#         pun   = law.get("punishment", "") or "(no punishment stored)"

#         # Normalise "nan" that comes from the CSV
#         if str(pun).strip().lower() == "nan":
#             pun = "(not specified)"

#         print("─" * W)
#         print(f"  #{i}  IPC Section {sec}   [{src} | score {score:.3f}]")
#         print()
#         print("  DESCRIPTION:")
#         for line in textwrap.wrap(desc, width=W - 4):
#             print(f"    {line}")
#         print()
#         print(f"  PUNISHMENT:  {pun}")
#         print()

#     print("─" * W)
#     if result.get("rewritten"):
#         print("  ℹ️  Query was rewritten by the guardrail LLM for better matching.")
#         print("─" * W)


# if __name__ == "__main__":
#     import sys

#     # Single-query mode: python lexigraph.py "Theft of a bicycle …"
#     if len(sys.argv) > 1:
#         q = " ".join(sys.argv[1:])
#         r = retrieve(q)
#         _print_results(q, r)

#     # Smoke-test mode: python lexigraph.py
#     else:
#         test_cases = [
#             ("Theft of electronics from employer's store caught on CCTV", "381"),
#             ("Sending threatening WhatsApp messages to a person",          None),
#             ("Murder of a person with premeditation",                      "302"),
#             ("Cheating someone of money through fraudulent documents",     None),
#             ("xyzabc completely unknown crime type",                       None),
#         ]
#         for q, hint in test_cases:
#             r = retrieve(q, section_hint=hint)
#             _print_results(q, r)

"""
Sprint 4: LexiGraph Agent — GraphRAG Legal Retriever
======================================================
Connects Neo4j (graph) + Pinecone (vector) to retrieve real IPC/BNS sections
BEFORE any LLM reasoning call. This is the retrieval backbone for
Prosecutor, Defense, and Judge agents.

Pipeline for every query
------------------------
Step A  — spaCy NER: extract crime keywords from query_text
Step B  — Neo4j graph query: CONTAINS match on LawSection.title and LawSection.description
Step C  — Pinecone vector query: 384-dim semantic similarity search
Step D  — Merge + deduplicate + rank: Neo4j hits first (exact), then Pinecone
Step E  — Guardrail: if 0 results, LLM rewrites the query and retries once

Key facts about the database schema (aligned with ingestion):
  Neo4j   : LawSection nodes have {section, title, description, punishment, act, chapter}
            Act nodes store legislation name {name}
            Relationship: (:Act)-[:HAS_SECTION]->(:LawSection)
  Pinecone: 448 vectors, dim=384 (all-MiniLM-L6-v2)
            IDs like "IPC_302", metadata={section, offense, punishment}
"""

import os
import json
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ── Environment ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

NEO4J_URI      = os.getenv("NEO4J_URI", "")
NEO4J_USER     = os.getenv("NEO4J_USER", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_HOST    = os.getenv(
    "PINECONE_HOST",
    "legal-embeddings-7xh2ksk.svc.aped-4627-b74a.pinecone.io",
)

# ── Lazy singletons ───────────────────────────────────────────────────────────
_spacy_nlp      = None
_embedder       = None
_pinecone_index = None
_neo4j_driver   = None


def _nlp():
    global _spacy_nlp
    if _spacy_nlp is None:
        import spacy
        try:
            _spacy_nlp = spacy.load("en_core_web_sm")
        except OSError:
            raise RuntimeError(
                "spaCy model not found. Run:\n"
                "  venv\\Scripts\\python -m spacy download en_core_web_sm"
            )
    return _spacy_nlp


def _embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings using sentence-transformers (384-dim)."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder.encode(texts, convert_to_numpy=True).tolist()


def _pinecone():
    global _pinecone_index
    if _pinecone_index is None:
        if not PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY not set in backend/.env")
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index = pc.Index(host=PINECONE_HOST)
    return _pinecone_index


def _neo4j():
    global _neo4j_driver
    if _neo4j_driver is None:
        if not NEO4J_URI:
            raise RuntimeError("NEO4J_URI not set in backend/.env")
        from neo4j import GraphDatabase
        _neo4j_driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    return _neo4j_driver


# ── Step A: spaCy keyword extraction ─────────────────────────────────────────

_LEGAL_KEYWORDS = {
    "theft", "robb", "dacoit", "murder", "homicide", "assault", "rape",
    "fraud", "cheat", "forg", "extort", "kidnap", "abduct",
    "trespass", "arson", "brib", "corrupt", "defam", "sedit",
    "riot", "hurt", "grievous", "intimidat", "threat", "stalk",
    "dowry", "cruel", "obscen", "gambl", "smuggl", "traffick",
    "poison", "accident", "neglig", "embezzl", "breach",
    "misappropriat", "imperson", "counterfeit", "mischief",
}

_CONCEPT_EXPANSION = {
    "document": ["forg"],
    "signature": ["forg"],
    "seal": ["forg"],
    "whatsapp": ["threat", "intimidat"],
    "sms": ["threat", "intimidat"],
    "text message": ["threat", "intimidat"],
    "online": ["cyber"],
    "email": ["cyber"],
}


def extract_crime_keywords(query_text: str) -> list[str]:
    """
    Step A — Use spaCy NER + legal keyword matching to extract crime terms.
    """
    nlp  = _nlp()
    doc  = nlp(query_text)
    seen = set()
    keywords: list[str] = []

    def _add(word: str):
        w = word.strip().lower()
        if w and w not in seen and len(w) > 2:
            seen.add(w)
            keywords.append(w)

    for ent in doc.ents:
        if ent.label_ in ("EVENT", "ORG", "NORP", "LAW", "GPE"):
            _add(ent.text)

    text_lower = query_text.lower()
    for kw in _LEGAL_KEYWORDS:
        if kw in text_lower:
            _add(kw)

    for trigger, extra_kws in _CONCEPT_EXPANSION.items():
        if trigger in text_lower:
            for ekw in extra_kws:
                _add(ekw)

    if len(keywords) < 2:
        for chunk in doc.noun_chunks:
            if any(t.is_alpha and not t.is_stop for t in chunk):
                _add(" ".join(t.text for t in chunk if t.is_alpha)[:40])

    if len(keywords) < 2:
        for token in doc:
            if token.pos_ in ("NOUN", "PROPN") and not token.is_stop:
                _add(token.lemma_)

    return keywords[:8]


# ── Step B: Neo4j graph queries ───────────────────────────────────────────────

def _neo4j_run(cypher: str, params: dict) -> list[dict]:
    driver = _neo4j()
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(cypher, params)
        return [dict(record) for record in result]


def _query_neo4j(keywords: list[str], section_hint: str = None) -> list[dict]:
    """
    Step B — Query Neo4j using the extracted keywords. Matches the true schema:
      B1. Exact section fetch targeting the correct (:LawSection) node labels.
      B2. Title CONTAINS match targeting the dynamic section title (Offense representation).
      B3. Description CONTAINS match broad fallback.
    """
    results   = []
    seen_secs = set()

    def _add_rows(rows: list[dict], source: str):
        for r in rows:
            sec = str(r.get("section", "")).strip()
            if sec and sec not in seen_secs:
                seen_secs.add(sec)
                results.append({
                    "section":     sec,
                    "description": r.get("description", ""),
                    "punishment":  r.get("punishment", ""),
                    "offense":     r.get("offense", ""),
                    "source":      source,
                    "score":       1.0 if source == "neo4j:exact" else 0.85,
                })

    # B1 — exact section lookup on the correct LawSection nodes
    if section_hint:
        clean = re.sub(r"[^0-9A-Za-z]", "", section_hint)
        rows = _neo4j_run(
            """
            MATCH (l:LawSection)
            WHERE l.section = $sec OR toLower(l.section) = toLower($sec)
            RETURN l.section AS section, l.description AS description,
                   l.punishment AS punishment, l.title AS offense
            LIMIT 3
            """,
            {"sec": clean},
        )
        _add_rows(rows, "neo4j:exact")

    if not keywords:
        return results

    # B2 — Title (Offense) text CONTAINS keyword mapping
    for kw in keywords[:5]:
        rows = _neo4j_run(
            """
            MATCH (l:LawSection)
            WHERE toLower(l.title) CONTAINS toLower($kw)
            RETURN l.section AS section, l.description AS description,
                   l.punishment AS punishment, l.title AS offense
            LIMIT 5
            """,
            {"kw": kw},
        )
        _add_rows(rows, "neo4j:crime_node")

    # B3 — LawSection description CONTAINS keyword (broader fallback)
    if len(results) < 3:
        for kw in keywords[:4]:
            rows = _neo4j_run(
                """
                MATCH (l:LawSection)
                WHERE toLower(l.description) CONTAINS toLower($kw)
                RETURN l.section AS section, l.description AS description,
                       l.punishment AS punishment, l.title AS offense
                LIMIT 5
                """,
                {"kw": kw},
            )
            _add_rows(rows, "neo4j:description")

    return results


# ── Step C: Pinecone vector search ────────────────────────────────────────────

_IPC_ID_RE      = re.compile(r"^IPC_\d+[A-Za-z]*$")
_IPC_SECTION_RE = re.compile(r"^\d+[A-Za-z]*$")


def _is_ipc_hit(match_id: str, meta: dict) -> bool:
    if _IPC_ID_RE.match(match_id):
        return True
    sec = str(meta.get("section", ""))
    return bool(sec and _IPC_SECTION_RE.match(sec))


def _query_pinecone(query_text: str, top_k: int = 5) -> list[dict]:
    index  = _pinecone()
    vector = _embed([query_text])[0]

    response = index.query(
        vector=vector,
        top_k=top_k * 3,
        include_metadata=True,
    )

    results = []
    for match in response.get("matches", []):
        mid  = match.get("id", "")
        meta = match.get("metadata", {})

        if not _is_ipc_hit(mid, meta):
            continue

        section = meta.get("section", mid.replace("IPC_", ""))
        results.append({
            "section":     section,
            "description": meta.get("description", ""),
            "punishment":  meta.get("punishment", ""),
            "offense":     meta.get("offense", ""),
            "source":      "pinecone:vector",
            "score":       round(float(match.get("score", 0.0)), 4),
        })

        if len(results) >= top_k:
            break

    return results


# ── Step D: Merge, enrich from Neo4j, rank ────────────────────────────────────

def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot     = sum(x * y for x, y in zip(a, b))
    norm_a  = sum(x * x for x in a) ** 0.5
    norm_b  = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _enrich_from_neo4j(section: str) -> dict:
    """Fetch the full properties from the actual LawSection label."""
    rows = _neo4j_run(
        """
        MATCH (l:LawSection)
        WHERE l.section = $sec
        RETURN l.section AS section, l.description AS description,
               l.punishment AS punishment, l.title AS title
        LIMIT 1
        """,
        {"sec": section},
    )
    if rows:
        return rows[0]
    return {}


MIN_CONFIDENCE = 0.32
_EXACT_HINT_SCORE = 0.97
_SOURCE_AGREEMENT_BOOST = 0.04


def _merge_and_rank(
    neo4j_hits: list[dict],
    pinecone_hits: list[dict],
    query_text: str,
    top_n: int = 5,
) -> list[dict]:
    """
    Step D — Deduplicate and cross-rank results natively.
    Protects semantic search capability when textual elements are initially thin.
    """
    merged: dict[str, dict] = {}

    def _upsert(r: dict) -> None:
        sec = r["section"]
        if sec not in merged:
            rec = dict(r)
            rec["_sources"] = {r["source"]}
            merged[sec] = rec
        else:
            existing = merged[sec]
            existing["_sources"].add(r["source"])
            for field in ("description", "offense", "punishment"):
                if not existing.get(field) and r.get(field):
                    existing[field] = r[field]
            existing["score"] = max(existing.get("score", 0.0), r.get("score", 0.0))

    for r in neo4j_hits:
        _upsert(r)
    for r in pinecone_hits:
        _upsert(r)

    if not merged:
        return []

    # Backfill missing properties from our structural graph database
    for sec, rec in merged.items():
        if not rec.get("description") or not rec.get("punishment"):
            enriched = _enrich_from_neo4j(sec)
            if enriched:
                rec["description"] = rec.get("description") or enriched.get("description", "")
                rec["punishment"]  = rec.get("punishment")  or enriched.get("punishment", "")
                if enriched.get("title") and not rec.get("offense"):
                    rec["offense"] = enriched["title"]

    # Unified semantic re-scoring matrix
    secs = list(merged.keys())
    cand_texts = [
        f"{merged[s].get('offense', '')} {merged[s].get('description', '')}".strip()
        for s in secs
    ]
    
    try:
        valid_indices = [i for i, text in enumerate(cand_texts) if len(text) > 5]
        
        if valid_indices:
            texts_to_embed = [query_text] + [cand_texts[i] for i in valid_indices]
            vectors = _embed(texts_to_embed)
            query_vec = vectors[0]
            cand_vecs = vectors[1:]
            
            sem_scores = {}
            vec_map_idx = 0
            for i, s in enumerate(secs):
                if i in valid_indices:
                    sem_scores[s] = _cosine_sim(query_vec, cand_vecs[vec_map_idx])
                    vec_map_idx += 1
                else:
                    sem_scores[s] = merged[s].get("score", 0.5)
        else:
            sem_scores = {s: merged[s].get("score", 0.5) for s in secs}
            
    except Exception as e:
        print(f"[LexiGraph] Semantic re-rank unavailable ({e}); using source scores")
        sem_scores = {s: merged[s].get("score", 0.5) for s in secs}

    for sec, rec in merged.items():
        score = sem_scores.get(sec, 0.0)
        if "neo4j:exact" in rec["_sources"]:
            score = max(score, _EXACT_HINT_SCORE)
        elif len(rec["_sources"]) > 1:
            score = min(1.0, score + _SOURCE_AGREEMENT_BOOST)
        rec["score"]  = round(score, 4)
        rec["source"] = "+".join(sorted(rec["_sources"]))
        del rec["_sources"]

    ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    ranked = [r for r in ranked if r["score"] >= MIN_CONFIDENCE or "pinecone:vector" in r["source"]]
    return ranked[:top_n]


# ── Step E: Guardrail — LLM query rewrite ────────────────────────────────────

def _rewrite_query(original_query: str) -> str:
    from config.llm_config import get_llm
    llm    = get_llm(temperature=0.3)
    prompt = (
        f"You are an Indian legal expert. The following query returned no results "
        f"from an IPC (Indian Penal Code) database:\n\n"
        f"\"{original_query}\"\n\n"
        f"Rewrite this query using precise Indian Penal Code legal terminology "
        f"(e.g. 'theft', 'culpable homicide', 'criminal intimidation', 'cheating'). "
        f"Return ONLY the rewritten query — no explanation, no punctuation."
    )
    response  = llm.invoke(prompt)
    rewritten = response.content.strip().strip('"').strip("'")
    print(f"[LexiGraph] Query rewritten: '{original_query}' → '{rewritten}'")
    return rewritten


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve(
    query_text: str,
    section_hint: str = None,
    top_n: int = 5,
    pinecone_top_k: int = 7,
) -> dict:
    print(f"\n[LexiGraph] ── Retrieving for: '{query_text[:80]}'")

    keywords = extract_crime_keywords(query_text)
    print(f"[LexiGraph] Step A — keywords: {keywords}")

    neo4j_hits = []
    try:
        neo4j_hits = _query_neo4j(keywords, section_hint)
        print(f"[LexiGraph] Step B — Neo4j: {len(neo4j_hits)} hits")
    except Exception as e:
        print(f"[LexiGraph] Neo4j error: {e}")

    pinecone_hits = []
    try:
        pinecone_hits = _query_pinecone(query_text, top_k=pinecone_top_k)
        print(f"[LexiGraph] Step C — Pinecone: {len(pinecone_hits)} hits")
    except Exception as e:
        print(f"[LexiGraph] Pinecone error: {e}")

    ranked = _merge_and_rank(neo4j_hits, pinecone_hits, query_text, top_n=top_n)
    print(f"[LexiGraph] Step D — merged: {len(ranked)} unique sections above confidence floor")

    rewritten = False

    if len(ranked) == 0:
        print("[LexiGraph] Step E — 0 results, rewriting query...")
        rewritten_query = _rewrite_query(query_text)
        rewritten       = True

        keywords_2      = extract_crime_keywords(rewritten_query)
        neo4j_hits_2    = []
        pinecone_hits_2 = []
        try:
            neo4j_hits_2 = _query_neo4j(keywords_2, section_hint)
        except Exception as e:
            print(f"[LexiGraph] Neo4j retry error: {e}")
        try:
            pinecone_hits_2 = _query_pinecone(rewritten_query, top_k=pinecone_top_k)
        except Exception as e:
            print(f"[LexiGraph] Pinecone retry error: {e}")

        ranked     = _merge_and_rank(neo4j_hits_2, pinecone_hits_2, rewritten_query, top_n=top_n)
        keywords   = keywords_2
        print(f"[LexiGraph] Step E retry — {len(ranked)} sections after rewrite")
        query_text = rewritten_query

    return {
        "ipc_sections":   ranked,
        "keywords":       keywords,
        "neo4j_count":    len(neo4j_hits),
        "pinecone_count": len(pinecone_hits),
        "query_used":     query_text,
        "rewritten":      rewritten,
    }


def format_for_prompt(result: dict) -> str:
    sections = result.get("ipc_sections", [])
    if not sections:
        return (
            "DATABASE RETRIEVAL: No relevant IPC sections found.\n"
            f"Keywords tried: {result.get('keywords', [])}\n"
            "The LLM must reason from general knowledge only."
        )

    lines = [
        f"RETRIEVED IPC SECTIONS  "
        f"[Neo4j:{result['neo4j_count']}  Pinecone:{result['pinecone_count']}  "
        f"Final:{len(sections)}]",
        "=" * 65,
    ]
    for i, s in enumerate(sections, 1):
        sec    = s.get("section", "?")
        off    = s.get("offense", "").strip()
        punish = s.get("punishment", "N/A").strip()
        src    = s.get("source", "")
        score  = s.get("score", 0)
        desc   = s.get("description", "").strip()

        desc_short = (desc[:200] + "…") if len(desc) > 200 else desc

        lines.append(
            f"\n{i}. IPC {sec}  [score={score:.2f} | {src}]\n"
            f"   Offense   : {off or 'See description'}\n"
            f"   Punishment: {punish}\n"
            f"   Summary   : {desc_short}"
        )

    if result.get("rewritten"):
        lines.append(f"\n[Note: query was rewritten for better matching]")

    return "\n".join(lines)


# ── LangGraph node wrapper ────────────────────────────────────────────────────

def lexigraph_node(state: dict) -> dict:
    facts    = state.get("structured_facts") or {}
    incident = facts.get("incident", {})
    sections = facts.get("sections", [])

    query_parts: list[str] = []
    if incident.get("summary"):
        query_parts.append(incident["summary"])
    if sections:
        section_hint = sections[0].replace("IPC ", "").replace("IPC_", "").strip()
    else:
        section_hint = None

    if not query_parts:
        query_parts.append(state.get("user_query", ""))

    query_text = ". ".join(filter(None, query_parts))
    result     = retrieve(query_text, section_hint=section_hint)

    state["relevant_laws"]      = result["ipc_sections"]
    state["lexigraph_result"]   = result
    print(f"[LexiGraph] Retrieved {len(result['ipc_sections'])} law(s).")
    return state


# ── CLI / standalone runner ───────────────────────────────────────────────────

def _print_results(query: str, result: dict) -> None:
    import textwrap
    sections = result["ipc_sections"]
    W = 70

    print(f"\n🔍 Query: {query}\n")
    print("─" * W)

    if not sections:
        print("❌  No results found even after guardrail rewrite.")
        print("─" * W)
        return

    print(f"✅  Found {len(sections)} relevant law(s):\n")

    for i, law in enumerate(sections, 1):
        src   = law.get("source", "").upper()
        score = law.get("score", 0.0)
        sec   = law.get("section", "?")
        desc  = law.get("description", "") or "(no description stored)"
        pun   = law.get("punishment", "") or "(no punishment stored)"

        if str(pun).strip().lower() == "nan":
            pun = "(not specified)"

        print("─" * W)
        print(f"  #{i}  IPC Section {sec}   [{src} | score {score:.3f}]")
        print()
        print("  DESCRIPTION:")
        for line in textwrap.wrap(desc, width=W - 4):
            print(f"    {line}")
        print()
        print(f"  PUNISHMENT:  {pun}")
        print()

    print("─" * W)
    if result.get("rewritten"):
        print("  ℹ️  Query was rewritten by the guardrail LLM for better matching.")
        print("─" * W)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        r = retrieve(q)
        _print_results(q, r)
    else:
        test_cases = [
            ("A 22-year-old woman was returning home from work when her former neighbour forcibly took her into his car. He drove her to an isolated farmhouse, locked her inside a room, threatened to kill her if she resisted, and forcibly had sexual intercourse with her without her consent. The victim sustained minor injuries while resisting. The accused later warned her not to report the incident to the police.",None),
            ("Sending threatening WhatsApp messages to a person",          None),
            ("Murder of a person with premeditation",                      "302"),
            ("Cheating someone of money through fraudulent documents",     None),
            ("xyzabc completely unknown crime type",                       None),
        ]
        for q, hint in test_cases:
            r = retrieve(q, section_hint=hint)
            _print_results(q, r)