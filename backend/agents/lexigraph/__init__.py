import json
from typing import Any, Dict, List, Optional
from .holding_retrieval import retrieve_holdings, format_holdings_for_prompt

def retrieve(query_text: str, section_hint=None, case_facts: Optional[List[Any]] = None) -> dict:
    """Backwards-compatible retrieve function calling LexiGraphAgent statutory pipeline and dynamic holding retrieval."""
    from .lexigraph_agent import LexiGraphAgent
    agent = LexiGraphAgent()
    output = agent.process_query(query_text, debug=True)
    ranked_candidates = output.get("debug", {}).get("ranked_candidates") or output.get("recommended_sections") or []
    
    mapped_sections = []
    for s in ranked_candidates:
        mapped_sections.append({
            "section": s.get("section", ""),
            "description": s.get("description", ""),
            "punishment": s.get("punishment", ""),
            "offense": s.get("title", ""),
            "source": "+".join(s.get("sources", [])) if s.get("sources") else "pinecone",
            "score": s.get("confidence", 0.0)
        })

    # Dynamically retrieve operative precedent holdings
    holdings = retrieve_holdings(query_text, case_facts=case_facts, top_k=5)
        
    return {
        "ipc_sections": mapped_sections,
        "holdings": holdings,
        "keywords": [],
        "neo4j_count": len([s for s in ranked_candidates if s.get("graph_verified")]),
        "pinecone_count": len(ranked_candidates),
        "query_used": query_text,
        "rewritten": False,
        "raw_agent_output": output
    }

def format_for_prompt(result: dict) -> str:
    """Formats the retrieval result into a clean, numbered string for prompts, including statutory sections and precedent holdings."""
    sections = result.get("ipc_sections", [])
    holdings = result.get("holdings", [])

    lines = []
    if sections:
        lines.extend([
            f"RETRIEVED IPC/BNS SECTIONS  "
            f"[Neo4j:{result.get('neo4j_count', 0)}  Pinecone:{result.get('pinecone_count', 0)}  "
            f"Final:{len(sections)}]",
            "=" * 65,
        ])
        for i, s in enumerate(sections, 1):
            sec    = s.get("section", "?")
            off    = s.get("offense", "").strip()
            punish = s.get("punishment", "N/A").strip()
            src    = s.get("source", "")
            score  = s.get("score", 0)
            desc   = s.get("description", "").strip()

            desc_short = (desc[:200] + "…") if len(desc) > 200 else desc

            lines.append(
                f"\n{i}. {sec}  [score={score:.2f} | {src}]\n"
                f"   Offense   : {off or 'See description'}\n"
                f"   Punishment: {punish}\n"
                f"   Summary   : {desc_short}"
            )
    else:
        lines.append(
            "DATABASE RETRIEVAL: No relevant IPC/BNS sections found.\n"
            "The LLM must reason from general knowledge only."
        )

    if holdings:
        lines.append("\n" + format_holdings_for_prompt(holdings))

    return "\n".join(lines)

def lexigraph_node(state: dict) -> dict:
    """LangGraph node wrapper for orchestrator_graph.py."""
    facts   = state.get("structured_facts") or {}
    incident = facts.get("incident", {})
    sections = facts.get("sections", [])
    case_facts = state.get("case_facts", [])

    query_parts: list[str] = []
    if incident.get("summary"):
        query_parts.append(incident["summary"])

    if not query_parts:
        query_parts.append(state.get("user_query", ""))

    query_text = ". ".join(filter(None, query_parts))
    result     = retrieve(query_text, case_facts=case_facts)

    state["relevant_laws"]      = result["ipc_sections"]
    state["holdings"]           = result.get("holdings", [])
    state["lexigraph_result"]   = result
    print(f"[LexiGraph] Retrieved {len(result['ipc_sections'])} law(s) and {len(result.get('holdings', []))} holding(s).")
    return state

