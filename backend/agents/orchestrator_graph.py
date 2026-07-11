import json
import re
from langgraph.graph import StateGraph, START, END
from state import AgentState
from evidence_analyzer import analyze_evidence, build_session_id
from defense import DefenseAgent
from prosecutor import ProsecutorAgent
from llm_config import get_llm

defense_agent = DefenseAgent()
prosecutor_agent = ProsecutorAgent()

# ── Agent nodes ───────────────────────────────────────────────────────────────

def evidence_analyzer(state: AgentState) -> AgentState:
    print("\n" + "="*80)
    print(" [AGENT] EVIDENCE ANALYZER (OCR & FACT EXTRACTION)")
    print("="*80)
    facts = analyze_evidence(state["session_id"], state["user_query"])
    state["structured_facts"] = facts
    
    print("\n--- EXTRACTED FACT SCHEMA ---")
    print(json.dumps(facts, indent=2))
    print("\n[Evidence Analyzer] Execution Completed successfully.")
    print("="*80 + "\n")
    return state


def lexigraph(state: AgentState) -> dict:
    print("\n" + "="*80)
    print(" [AGENT] LEXIGRAPH (LEGAL RETRIEVAL & MAPPING)")
    print("="*80)
    
    # Import the original node wrapper and execute it
    from lexigraph import lexigraph_node as original_lexigraph_node
    result_state = original_lexigraph_node(state)
    
    print("\n--- RETRIEVED IPC SECTIONS ---")
    relevant_laws = result_state.get("relevant_laws") or []
    if not relevant_laws:
        print("  No relevant IPC sections found.")
    else:
        for idx, law in enumerate(relevant_laws):
            print(f"  {idx+1}. IPC Section {law['section']}: {law['offense']}")
            desc = law.get('description', '')
            desc_first = desc.splitlines()[0] if desc else 'No description available.'
            print(f"     Description: {desc_first}")
            print(f"     Punishment: {law.get('punishment') or 'Not specified.'}")
            print(f"     Source: {law.get('source')} (Score: {law.get('score', 1.0)})")
            
    print("\n[LexiGraph] Legal retrieval completed successfully.")
    print("="*80 + "\n")
    return result_state


def prosecutor(state: AgentState) -> dict:
    print("\n" + "="*80)
    print(" [AGENT] PROSECUTOR (ARGUMENTS & RETRY GUARDRAILS)")
    print("="*80)
    session_id = state["session_id"]
    structured_facts = state["structured_facts"]
    
    # 1. Accept and build context
    ctx = prosecutor_agent.accept(session_id, structured_facts)
    
    # 2. Populate LexiGraph result if the orchestrator already ran it
    if state.get("lexigraph_result"):
        raw_result = state["lexigraph_result"]
        from agents.prosecutor import validate_retrieval, check_retrieval_quality
        typed_result = validate_retrieval(raw_result)
        has_results = check_retrieval_quality(typed_result)
        
        ctx.retrieved_laws = typed_result
        ctx.retrieved_sections = list(typed_result.ipc_sections)
        ctx.valid_section_numbers = [sec.section for sec in typed_result.ipc_sections]
        ctx.retrieval_empty = not has_results
        
        try:
            from agents.lexigraph import format_for_prompt
            if has_results:
                ctx.formatted_laws_for_prompt = format_for_prompt(raw_result)
            else:
                ctx.formatted_laws_for_prompt = (
                    "DATABASE RETRIEVAL: No applicable IPC sections found.\n"
                    "Do not invent or fabricate legal sections."
                )
        except Exception:
            ctx.formatted_laws_for_prompt = (
                "DATABASE RETRIEVAL: No applicable IPC sections found.\n"
                "Do not invent or fabricate legal sections."
            )
    else:
        ctx = prosecutor_agent.retrieve_laws(ctx)
        
    # 3. Generate and validate argument
    ctx = prosecutor_agent.generate_argument(ctx)
    
    # 4. Get structured output
    output = prosecutor_agent.get_output(ctx)
    
    print("\n--- GENERATED PROSECUTION SUBMISSIONS ---")
    print(output.full_argument)
    print("\n[Prosecutor] Arguments formulated and validated successfully.")
    print("="*80 + "\n")
    return {
        "prosecution_args": output.full_argument
    }


def defense(state: AgentState) -> dict:
    print("\n" + "="*80)
    print(" [AGENT] DEFENSE LAWYER (CONTRADICTIONS & REASONABLE DOUBT)")
    print("="*80)
    
    arguments = defense_agent.generate(
        structured_facts=state["structured_facts"],
        lexigraph_result=state["lexigraph_result"],
        prosecution_arguments=state["prosecution_args"],
    )
    
    print("\n--- GENERATED DEFENSE SUBMISSIONS ---")
    print(arguments)
    print("\n[Defense] Arguments formulated successfully.")
    print("="*80 + "\n")
    return {
        "defense_args": arguments
    }


def judge(state: AgentState) -> dict:
    print("\n" + "="*80)
    print(" [AGENT] JUDGE (VERDICT & LEGAL REASONING)")
    print("="*80)
    
    relevant_laws = state.get("relevant_laws") or []
    if not relevant_laws:
        verdict_data = {
            "reasoning": "No applicable IPC sections were retrieved from LexiGraph.",
            "verdict": "deferred",
            "detailed_order": "The case is deferred indefinitely due to the absence of valid legal sections to map the alleged offenses."
        }
    else:
        facts = state["structured_facts"]
        prosecution = state.get("prosecution_args") or "No prosecution arguments provided."
        defense = state.get("defense_args") or "No defense arguments provided."
        facts_str = json.dumps(facts, indent=2)

        system_prompt = """You are an honorable Judge presiding over a Moot Court simulating Indian Criminal Law.

Your task is to analyze the CASE FACTS, PROSECUTION ARGUMENTS, and DEFENSE ARGUMENTS, and deliver a structured judgment in JSON format.

CRITICAL RULES:
1. FIR & Investigation Stage Check: An FIR (First Information Report) is merely an initiation of investigation. It is not substantive evidence of guilt. If the case is only based on an FIR and the investigation has not concluded (e.g. no chargesheet filed, no trial evidence presented), you must NOT convict.
2. Unidentified Accused Check: If the accused is listed as "Unknown", "Unknown Person", or "अज्ञात इसम", a conviction CANNOT be pronounced. You must state that judgment is deferred or the case cannot proceed to conviction because the perpetrator is unidentified.
3. Standard of Proof: A conviction requires proof "beyond a reasonable doubt". If there is no concrete physical, forensic, or eyewitness evidence linking a specific accused to the crime, you must either acquit (if a specific accused is charged but the evidence is insufficient) or defer/dismiss the case (if the accused is unknown).

Return ONLY a valid JSON object matching this schema:
{
  "reasoning": "A concise paragraph explaining your legal reasoning, specifically analyzing whether the accused is identified, the stage of the case (FIR vs. trial), and the sufficiency of the evidence.",
  "verdict": "deferred" | "acquitted" | "guilty" | "insufficient_evidence",
  "detailed_order": "Your formal judicial order detailing the final decision, directions to the police/prosecution, or details of the sentence/acquittal."
}"""

        user_prompt = f"""CASE FACTS:
{facts_str}

PROSECUTION ARGUMENTS:
{prosecution}

DEFENSE ARGUMENTS:
{defense}

Deliver your structured judgment JSON now."""

        llm = get_llm(temperature=0.1)
        
        try:
            response = llm.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ])
            content = response.content.strip()
            
            if content.startswith("```"):
                content = re.sub(r"^```json\s*|^```\s*", "", content, flags=re.MULTILINE)
                content = re.sub(r"\s*```$", "", content, flags=re.MULTILINE).strip()
                
            verdict_data = json.loads(content)
        except Exception as e:
            print(f"[Warning] Judge LLM call failed or output was invalid JSON: {e}")
            accused_list = facts.get("who", {}).get("accused", [])
            is_unknown = not accused_list or any("unknown" in str(a).lower() for a in accused_list)
            
            if is_unknown:
                verdict_data = {
                    "reasoning": "The accused is unknown, and the case is at the FIR investigation stage.",
                    "verdict": "deferred",
                    "detailed_order": "The court defers the judgment because the accused is unidentified. The police are directed to investigate the theft and trace the perpetrator."
                }
            else:
                verdict_data = {
                    "reasoning": "Insufficient evidence presented during the initial stage.",
                    "verdict": "insufficient_evidence",
                    "detailed_order": "The court rules that the current evidence is insufficient to sustain a conviction."
                }
                
    print("\n--- RENDERED JUDGMENT ---")
    print(f"VERDICT: {verdict_data.get('verdict', 'unknown').upper()}")
    print(f"\nReasoning:\n{verdict_data.get('reasoning', '')}")
    print(f"\nDetailed Order:\n{verdict_data.get('detailed_order', '')}")
    print("\n[Judge] Verdict and detailed order pronounced successfully.")
    print("="*80 + "\n")
    return {"judge_verdict": verdict_data}


# ── Graph definition ──────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("evidence_analyzer", evidence_analyzer)
    graph.add_node("lexigraph",         lexigraph)
    graph.add_node("prosecutor",        prosecutor)
    graph.add_node("defense",           defense)
    graph.add_node("judge",             judge)

    graph.add_edge(START,              "evidence_analyzer")
    graph.add_edge("evidence_analyzer", "lexigraph")
    graph.add_edge("lexigraph",         "prosecutor")
    graph.add_edge("lexigraph",         "defense")
    graph.add_edge("prosecutor",        "judge")
    graph.add_edge("defense",           "judge")
    graph.add_edge("judge",             END)

    return graph.compile()


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = build_graph()

    file_path  = "../data/fir/0083 Publish FIR.pdf"
    session_id = build_session_id(file_path)
    print(f"Creating new session: {session_id}")

    dummy_state: AgentState = {
        "session_id":       session_id,
        "user_query":       file_path,
        "structured_facts": {},
        "relevant_laws":    [],
        "lexigraph_result": {},
        "prosecution_args": "",
        "defense_args":     "",
        "judge_verdict":    {},
        "accused_history":  [],
    }

    result = app.invoke(dummy_state)
    
    print("\n" + "="*80)
    print(" MOOT COURT SIMULATION RUN COMPLETE")
    print("="*80)
    print(f"Session ID  : {result['session_id']}")
    print(f"Complainant : {result['structured_facts']['who']['complainant']}")
    print(f"Accused     : {', '.join(result['structured_facts']['who']['accused'])}")
    print(f"IPC Sections: {', '.join(result['structured_facts']['sections'])}")
    print(f"Verdict     : {result['judge_verdict'].get('verdict', '').upper()}")
    print("="*80 + "\n")
