import json
import re
import sys
import logging
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from langgraph.graph import StateGraph, START, END
from state import AgentState
from evidence_analyzer import analyze_evidence, build_session_id
from defense import DefenseAgent
from prosecutor import ProsecutorAgent
from llm_config import get_llm
import console_fmt as fmt

# Suppress verbose sub-agent loggers to keep terminal output clean
logging.getLogger("prosecutor").setLevel(logging.WARNING)

defense_agent = DefenseAgent()
prosecutor_agent = ProsecutorAgent()

# ── Agent nodes ───────────────────────────────────────────────────────────────

def evidence_analyzer(state: AgentState) -> AgentState:
    with fmt.buffered_output():
        print(fmt.header("EVIDENCE ANALYZER", "OCR & Fact Extraction"))

        facts = analyze_evidence(state["session_id"], state["user_query"])
        state["structured_facts"] = facts

        print(fmt.subheader("EXTRACTED FACT SCHEMA"))

        # Who
        who = facts.get("who", {})
        print(fmt.kv("Complainant", who.get("complainant", "N/A")))
        print(fmt.kv("Accused", ", ".join(who.get("accused", [])) or "N/A"))
        print(fmt.kv("Victims", ", ".join(who.get("victims", [])) or "N/A"))

        # Incident
        inc = facts.get("incident", {})
        print(fmt.kv("Summary", inc.get("summary", "N/A")))
        print(fmt.kv("Date", inc.get("date", "N/A")))
        print(fmt.kv("Time", inc.get("time", "N/A")))
        print(fmt.kv("Place", inc.get("place", "N/A")))

        # Property
        prop = facts.get("property", {})
        vehicles = prop.get("vehicles", [])
        if vehicles:
            for v in vehicles:
                print(fmt.kv("Vehicle", f"{v.get('make_model', '?')} ({v.get('registration_no', '?')})"))
        if prop.get("estimated_loss"):
            print(fmt.kv("Est. Loss", f"Rs.{prop['estimated_loss']}"))

        # Sections
        sections = facts.get("sections", [])
        print(fmt.kv("IPC Sections", ", ".join(sections) if sections else "None found"))

        # Validation
        errors = facts.get("validation_errors", [])
        if errors:
            print(fmt.status("[!]", f"OCR Validation: {len(errors)} warning(s)"))
            for err in errors:
                print(fmt.bullet(err, indent=8))
        else:
            print(fmt.status("[OK]", "OCR Validation: All facts verified against source text"))

        print(fmt.section_complete("Evidence Analyzer"))

    return state


def lexigraph(state: AgentState) -> dict:
    with fmt.buffered_output():
        print(fmt.header("LEXIGRAPH", "Legal Retrieval & IPC Mapping"))

        # Import the original node wrapper and execute it
        from lexigraph import lexigraph_node as original_lexigraph_node
        result_state = original_lexigraph_node(state)

        print(fmt.subheader("RETRIEVED IPC SECTIONS"))
        relevant_laws = result_state.get("relevant_laws") or []
        if not relevant_laws:
            print(fmt.status("[!]", "No relevant IPC sections found."))
        else:
            for idx, law in enumerate(relevant_laws):
                sec = law.get("section", "?")
                offense = law.get("offense", "N/A")
                punishment = law.get("punishment", "Not specified")
                source = law.get("source", "?")
                score = law.get("score", 0.0)
                print(f"\n      {fmt._bold(f'{idx+1}. IPC Section {sec}')}: {offense}")
                print(fmt.kv("Punishment", punishment, indent=9))
                print(fmt.kv("Source", f"{source} (score: {score:.2f})", indent=9))

        print(fmt.section_complete("LexiGraph"))

    return result_state


def prosecutor(state: AgentState) -> dict:
    with fmt.buffered_output():
        print(fmt.header("PROSECUTOR", "Arguments & Retry Guardrails"))

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

        print(fmt.subheader("PROSECUTION SUBMISSIONS"))
        print(fmt.wrap_text(fmt.truncate(output.full_argument, max_lines=40), indent=6))

        print(fmt.section_complete("Prosecutor"))

    return {
        "prosecution_args": output.full_argument
    }


def defense(state: AgentState) -> dict:
    with fmt.buffered_output():
        print(fmt.header("DEFENSE LAWYER", "Contradictions & Reasonable Doubt"))

        arguments = defense_agent.generate(
            structured_facts=state["structured_facts"],
            lexigraph_result=state["lexigraph_result"],
            prosecution_arguments=state["prosecution_args"],
        )

        print(fmt.subheader("DEFENSE SUBMISSIONS"))
        print(fmt.wrap_text(fmt.truncate(arguments, max_lines=40), indent=6))

        print(fmt.section_complete("Defense Lawyer"))

    return {
        "defense_args": arguments
    }


def judge(state: AgentState) -> dict:
    with fmt.buffered_output():
        print(fmt.header("JUDGE", "Verdict & Legal Reasoning"))

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
            defense_args = state.get("defense_args") or "No defense arguments provided."
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
{defense_args}

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
                print(fmt.status("[!]", f"Judge LLM call failed: {e}"))
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

        print(fmt.subheader("RENDERED JUDGMENT"))
        print(fmt.verdict_box(
            verdict_data.get("verdict", "unknown"),
            verdict_data.get("reasoning", ""),
            verdict_data.get("detailed_order", ""),
        ))

        print(fmt.section_complete("Judge"))

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


# ── Interactive runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Enable ANSI colors on Windows
    import os
    import glob
    import time
    os.system("")

    app = build_graph()

    # Discover all PDFs in data/fir/
    fir_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fir")
    fir_dir = os.path.normpath(fir_dir)
    pdf_files = sorted(glob.glob(os.path.join(fir_dir, "*.pdf")))

    if not pdf_files:
        print(f"\n  [!]  No PDF files found in {fir_dir}\n")
        exit(1)

    # ── Display available PDFs ────────────────────────────────────────────────
    print()
    print(fmt._color(fmt.THICK * fmt.WIDTH, fmt.C.B_YELLOW))
    print(fmt._color("  [MOOT COURT SIMULATION]  --  Select a case file", fmt.C.B_YELLOW))
    print(fmt._color(fmt.THICK * fmt.WIDTH, fmt.C.B_YELLOW))
    print(fmt.kv("Source Dir", fir_dir))
    print()
    print(fmt._bold("    Available FIR documents:"))
    print()
    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"      {fmt._color(f'[{i}]', fmt.C.B_CYAN)}  {os.path.basename(pdf_path)}")
    print()
    print(fmt._color(fmt.THIN * fmt.WIDTH, fmt.C.DIM))

    # ── Prompt for selection ──────────────────────────────────────────────────
    while True:
        try:
            choice = input(f"\n  Enter file number (1-{len(pdf_files)}): ").strip()
            idx = int(choice)
            if 1 <= idx <= len(pdf_files):
                break
            print(f"  [!]  Please enter a number between 1 and {len(pdf_files)}.")
        except ValueError:
            print(f"  [!]  Invalid input. Please enter a number between 1 and {len(pdf_files)}.")
        except (KeyboardInterrupt, EOFError):
            print("\n\n  Cancelled.\n")
            exit(0)

    # ── Process the selected PDF ──────────────────────────────────────────────
    selected_path = pdf_files[idx - 1]
    file_name = os.path.basename(selected_path)
    rel_path  = os.path.relpath(selected_path, os.path.join(os.path.dirname(__file__), ".."))

    session_id = build_session_id(selected_path)
    print(fmt.session_banner(session_id, rel_path))

    start_time = time.time()

    init_state: AgentState = {
        "session_id":       session_id,
        "user_query":       selected_path,
        "structured_facts": {},
        "relevant_laws":    [],
        "lexigraph_result": {},
        "prosecution_args": "",
        "defense_args":     "",
        "judge_verdict":    {},
        "accused_history":  [],
    }

    result = app.invoke(init_state)

    elapsed = time.time() - start_time
    print(fmt.final_banner())
    print(fmt.summary_table(result))
    print(fmt._dim(f"    Completed in {elapsed:.1f}s\n"))

