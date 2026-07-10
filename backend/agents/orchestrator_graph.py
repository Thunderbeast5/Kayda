from langgraph.graph import StateGraph, START, END
from state import AgentState
from evidence_analyzer import analyze_evidence, build_session_id
<<<<<<< Updated upstream
from lexigraph import retrieve, format_for_prompt
from llm_config import get_llm
=======
from lexigraph import lexigraph_node
>>>>>>> Stashed changes


def evidence_analyzer(state: AgentState) -> dict:
    """
    Extracts structured facts from user_query.
    Accepts a file path (PDF/image) or raw case text.
    """
    query = state.get("user_query", "")
    file_extensions = (".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".bmp")

    if query.lower().endswith(file_extensions):
        facts = analyze_evidence(state["session_id"], query)
    else:
        from evidence_analyzer import extract_facts
        facts = extract_facts(query)

    print(f"evidence_analyzer: Done. Fields: {list(facts.keys())}")
    return {"structured_facts": facts}


def prosecutor(state: AgentState) -> dict:
    """
    Builds a formal prosecution argument grounded in real IPC sections
    retrieved from Neo4j + Pinecone via LexiGraph.
    """
    facts = state.get("structured_facts", {})
    incident = facts.get("incident", {})

    # Build a rich query from structured facts
    query_parts = []
    if incident.get("summary"):
        query_parts.append(incident["summary"])
    if facts.get("sections"):
        query_parts.append("IPC sections: " + ", ".join(facts["sections"]))

    query_text = " ".join(query_parts) if query_parts else state.get("user_query", "")

    # Extract section hint from facts (first cited section)
    section_hint = None
    if facts.get("sections"):
        raw = facts["sections"][0]
        import re
        m = re.search(r"\d+[A-Za-z]*", raw)
        if m:
            section_hint = m.group(0)

    # Retrieve from databases
    retrieval     = retrieve(query_text, section_hint=section_hint)
    retrieved_law = format_for_prompt(retrieval)

    llm    = get_llm(temperature=0.3)
    prompt = (
        f"You are a senior Public Prosecutor in an Indian High Court.\n\n"
        f"CASE FACTS:\n{query_text}\n\n"
        f"{retrieved_law}\n\n"
        f"Using ONLY the IPC sections retrieved above, write a formal, structured "
        f"prosecution argument. Map each fact to a specific IPC section. "
        f"State charges, establish mens rea and actus reus, cite punishments. "
        f"End with: 'The prosecution submits the accused is GUILTY of [charges].'"
    )

    response = llm.invoke(prompt)
    print("prosecutor: Done.")
    return {"prosecution_args": response.content}


def defense(state: AgentState) -> dict:
    """
    Builds a formal defense argument using LexiGraph to find mitigating
    IPC sections and counter the prosecution.
    """
    facts          = state.get("structured_facts", {})
    prosecution    = state.get("prosecution_args", "")
    incident       = facts.get("incident", {})

    query_text = "defense exception mitigation " + (
        incident.get("summary") or state.get("user_query", "")
    )

    retrieval     = retrieve(query_text)
    retrieved_law = format_for_prompt(retrieval)

    llm    = get_llm(temperature=0.4)
    prompt = (
        f"You are a senior Defense Lawyer in an Indian High Court.\n\n"
        f"CASE FACTS:\n{incident.get('summary') or state.get('user_query','')}\n\n"
        f"{retrieved_law}\n\n"
        f"PROSECUTION ARGUMENT:\n{prosecution}\n\n"
        f"Using the retrieved IPC sections, challenge the prosecution. "
        f"Identify gaps in evidence, question intent, cite exceptions or mitigating "
        f"provisions. End with: 'The defense submits the accused is NOT GUILTY because [reason].'"
    )

    response = llm.invoke(prompt)
    print("defense: Done.")
    return {"defense_args": response.content}


def judge(state: AgentState) -> dict:
    """
    Evaluates prosecution and defense arguments, returns structured verdict.
    """
    facts       = state.get("structured_facts", {})
    prosecution = state.get("prosecution_args", "")
    defense_arg = state.get("defense_args", "")

    llm    = get_llm(temperature=0.2)
    prompt = (
        f"You are a strict, impartial Judge of the Indian High Court.\n\n"
        f"CASE FACTS:\n{facts}\n\n"
        f"PROSECUTION:\n{prosecution}\n\n"
        f"DEFENSE:\n{defense_arg}\n\n"
        f"Score both arguments on:\n"
        f"  - Legal Validity (0-10)\n"
        f"  - Evidence Linkage (0-10)\n"
        f"  - Logic Coherence (0-10)\n\n"
        f"Return ONLY valid JSON:\n"
        f'{{"prosecution_score":{{"legal_validity":0,"evidence_linkage":0,"logic":0}},'
        f'"defense_score":{{"legal_validity":0,"evidence_linkage":0,"logic":0}},'
        f'"decision":"Guilty | Not Guilty | Inconclusive",'
        f'"confidence_percent":0,'
        f'"ipc_sections_applied":[],'
        f'"reasoning":""}}'
    )

    import json
    response = llm.invoke(prompt)
    try:
        import re
        clean = re.sub(r"^```(?:json)?|```$", "", response.content.strip(), flags=re.MULTILINE).strip()
        verdict = json.loads(clean)
    except Exception:
        verdict = {"decision": "Inconclusive", "reasoning": response.content}

    print("judge: Done.")
    return {"judge_verdict": verdict}


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("evidence_analyzer", evidence_analyzer)
    graph.add_node("lexigraph", lexigraph_node)
    graph.add_node("prosecutor", prosecutor)
    graph.add_node("defense", defense)
    graph.add_node("judge", judge)

    graph.add_edge(START, "evidence_analyzer")
    graph.add_edge("evidence_analyzer", "lexigraph")       # ← law retrieval after facts
    graph.add_edge("lexigraph", "prosecutor")
    graph.add_edge("lexigraph", "defense")
    graph.add_edge("prosecutor", "judge")
    graph.add_edge("defense", "judge")
    graph.add_edge("judge", END)

    return graph.compile()


if __name__ == "__main__":
    app = build_graph()

    file_path = "../test_fir.pdf"
    session_id = build_session_id(file_path)
    print(f"Creating new session: {session_id}")

    dummy_state: AgentState = {
        "session_id": session_id,
        "user_query": file_path,
        "structured_facts": {},
        "relevant_laws": [],
        "prosecution_args": "",
        "defense_args": "",
        "judge_verdict": {},
        "accused_history": [],
    }

    result = app.invoke(dummy_state)
    print("\nFinal state:")
    print(result)
