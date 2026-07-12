import os
import json
import re
from typing import Dict, Any, List

from config.llm_config import get_llm
from lexigraph import format_for_prompt

# ── Guardrails-AI setup ───────────────────────────────────────────────────────
try:
    from guardrails import Guard
    from guardrails.validators import Validator, register_validator, ValidationResult, PassResult, FailResult
    
    @register_validator(name="contains_ipc", data_type="string")
    class ContainsIPC(Validator):
        def validate(self, value: Any, metadata: Dict) -> ValidationResult:
            if "IPC " in str(value):
                return PassResult()
            return FailResult(
                error_message="The generated argument does not contain any 'IPC ' citations."
            )
    _HAS_GUARDRAILS = True
except Exception as e:
    print(f"[Prosecutor] guardrails-ai warning: {e}. Falling back to manual checks.")
    _HAS_GUARDRAILS = False


# ── Database Verification Guardrail Helper ────────────────────────────────────

def section_exists_in_db(section: str) -> bool:
    """Verify if a specific section exists in the Neo4j database."""
    clean_sec = re.sub(r"[^0-9A-Za-z]", "", section).strip().upper()
    if not clean_sec:
        return False
        
    from neo4j import GraphDatabase
    
    uri = os.getenv("NEO4J_URI", "")
    user = os.getenv("NEO4J_USER", "")
    pwd = os.getenv("NEO4J_PASSWORD", "")
    db_name = os.getenv("NEO4J_DATABASE", "neo4j")
    
    if not uri or not user or not pwd:
        # Fallback to true if DB is not configured (to avoid silent failures in local test)
        print("[Prosecutor] Neo4j not configured, skipping DB verification.")
        return True
        
    try:
        with GraphDatabase.driver(uri, auth=(user, pwd)) as driver:
            with driver.session(database=db_name) as session:
                result = session.run(
                    "MATCH (l:IPC) WHERE l.section = $sec OR l.section = $sec_lower RETURN l.section LIMIT 1",
                    {"sec": clean_sec, "sec_lower": clean_sec.lower()}
                )
                record = result.single()
                return record is not None
    except Exception as e:
        print(f"[Prosecutor] Neo4j verification error: {e}. Defaulting to True.")
        return True


def extract_cited_sections(text: str) -> List[str]:
    """Extract cited sections matching 'IPC <number>' or 'Section <number>'."""
    pattern = r"(?:ipc\s*|section\s*)(\d+[a-z]?)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    return list(set(m.strip().upper() for m in matches))


def verify_ipc_citations(text: str, relevant_laws: list) -> List[str]:
    """Find cited IPC sections that do not exist in relevant laws or the DB."""
    cited = extract_cited_sections(text)
    
    verified_sections = {
        str(s.get("section", "")).strip().upper() 
        for s in relevant_laws 
        if s.get("section")
    }
    
    invalid_sections = []
    for sec in cited:
        if sec in verified_sections:
            continue
        # If not in the retrieved laws list, check the Neo4j DB directly
        if not section_exists_in_db(sec):
            invalid_sections.append(sec)
            
    return invalid_sections


# ── ProsecutorAgent Class ─────────────────────────────────────────────────────

class ProsecutorAgent:
    """
    Prosecutor Agent (The Accuser)
    
    Builds a strong, logical case against the Accused using legal reasoning.
    """
    def __init__(self):
        self.llm = get_llm(temperature=0.2)

    def generate(
        self,
        structured_facts: dict,
        lexigraph_result: dict,
    ) -> str:
        retrieved_laws = format_for_prompt(lexigraph_result)
        relevant_laws_list = lexigraph_result.get("ipc_sections", [])

        # 1. Base Prompt Template
        prompt = f"""
You are a formal prosecutor in an Indian criminal court. Your objective is to build a strong, logical case against the Accused using precise legal reasoning.

Here are the case facts:
------------------------
CASE FACTS:
{json.dumps(structured_facts, indent=2)}

------------------------
LEXIGRAPH RETRIEVAL (VERIFIED IPC SECTIONS):
{retrieved_laws}

Write a structured, formal legal argument mapping the facts to these sections. 

Rules:
1. You must only cite verified IPC sections from the retrieval list above.
2. Formally cite sections using the format "IPC <section_number>", e.g., "IPC 379".
3. Map specific facts and evidence to each cited IPC section.
4. Establish the intention (mens rea) and action (actus reus) of the accused.

Prepare the response in this format:

1. Prosecution Theory

2. Accused Details & Context

3. Mapping of Facts to IPC Sections

4. Action (Actus Reus) & Intention (Mens Rea)

5. Critical Evidence & Witnesses

6. Final Prosecution Submission

Keep the arguments professional, authoritative, and courtroom ready.
"""

        # 2. Rewrite Prompt Template
        rewrite_prompt = """
You are a formal prosecutor in an Indian criminal court. 

Here is your previous draft of the prosecution arguments:
------------------------
PREVIOUS DRAFT:
{previous_draft}

------------------------
CRITICAL ERROR:
You cited the following IPC sections which do not exist in the verified legal database:
{invalid_sections}

You are only allowed to cite sections from this verified database retrieval:
{retrieved_laws}

Rewrite the prosecution argument. You must:
1. Drop the invalid sections completely.
2. Remove any arguments or claims based on the invalid sections.
3. Keep the formal, courtroom-ready structure.

Prepare the updated argument in the same structured format.
"""

        # 3. Generation & Guardrail Retry Loop
        max_retries = 3
        
        # Initial run
        response = self.llm.invoke(prompt)
        current_draft = response.content
        
        for attempt in range(max_retries):
            # Guardrail 1: Check if "IPC " is in the output (uses guardrails-ai)
            guard_passed = True
            validation_error_msg = ""
            if _HAS_GUARDRAILS:
                try:
                    guard = Guard.for_string(
                        validators=[ContainsIPC(on_fail="exception")]
                    )
                    guard.parse(current_draft)
                except Exception as exc:
                    print(f"[Prosecutor] Guardrails validation failed (attempt {attempt + 1}): {exc}")
                    guard_passed = False
                    validation_error_msg = str(exc)
            else:
                if "IPC " not in current_draft:
                    print(f"[Prosecutor] Manual guardrail check failed (attempt {attempt + 1}): 'IPC ' not found")
                    guard_passed = False
                    validation_error_msg = "The generated argument does not contain any 'IPC ' citations."
            
            # Guardrail 2: Verify all cited IPC sections exist in Neo4j database
            invalid_sections = verify_ipc_citations(current_draft, relevant_laws_list)
            
            # Action if Guardrail 1 fails: Trigger retry/rewrite
            if not guard_passed:
                retry_prompt = f"""
You are a formal prosecutor in an Indian criminal court. 

Here is your previous draft:
{current_draft}

CRITICAL ERROR: Your draft did not cite any IPC sections correctly. You must cite relevant IPC sections from the database using the format "IPC <section_number>" (e.g., "IPC 379").

Here are the verified IPC sections:
{retrieved_laws}

Rewrite the argument ensuring you explicitly cite the relevant IPC sections.
"""
                response = self.llm.invoke(retry_prompt)
                current_draft = response.content
                continue
                
            # Action if Guardrail 2 fails: Trigger retry/rewrite dropping invalid sections
            if invalid_sections:
                print(f"[Prosecutor] Database verification guardrail failed (attempt {attempt + 1}): Invalid sections cited: {invalid_sections}")
                response = self.llm.invoke(
                    rewrite_prompt.format(
                        previous_draft=current_draft,
                        invalid_sections=", ".join(invalid_sections),
                        retrieved_laws=retrieved_laws
                    )
                )
                current_draft = response.content
                continue
                
            # If all checks passed successfully
            print("[Prosecutor] All guardrail checks passed successfully!")
            return current_draft
            
        # If we exhausted retries and still fail, raise exception to trigger retry action in LangGraph
        error_msg = "Guardrail verification failed after maximum retries."
        if not guard_passed:
            raise ValueError(f"LangGraph Retry: {validation_error_msg}")
        elif invalid_sections:
            raise ValueError(f"LangGraph Retry: Invalid IPC sections cited: {invalid_sections}")
            
        return current_draft


# ── LangGraph node wrapper ────────────────────────────────────────────────────

def prosecutor_node(state: dict) -> dict:
    """
    LangGraph-compatible node for orchestrator.py
    """
    print("\n[Orchestrator] Running Prosecutor Agent...")
    agent = ProsecutorAgent()
    
    # Retrieve inputs from state
    facts = state.get("structured_facts") or {}
    lexigraph_res = state.get("lexigraph_result") or {}
    
    # Generate arguments
    args = agent.generate(facts, lexigraph_res)
    
    # Update and return state
    state["prosecution_args"] = args
    return {"prosecution_args": args}


# ── Standalone Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    agent = ProsecutorAgent()

    test_facts = {
        "who": {
            "complainant": "Amit",
            "accused": ["Rahul"],
            "victims": ["Amit"]
        },
        "incident": {
            "summary": "Rahul allegedly stole a motorcycle from the parking lot.",
            "date": "05/07/2026",
            "time": "14:30",
            "place": "Pune"
        },
        "sections": ["IPC 379"]
    }

    test_lexigraph = {
        "ipc_sections": [
            {
                "section": "379",
                "description": "Punishment for theft.",
                "punishment": "Imprisonment of either description for a term which may extend to 3 years, or with fine, or with both.",
                "offense": "Theft",
                "source": "neo4j",
                "score": 1.0
            }
        ],
        "keywords": ["theft"],
        "neo4j_count": 1,
        "pinecone_count": 0,
        "query_used": "Motorcycle theft",
        "rewritten": False,
    }

    result = agent.generate(test_facts, test_lexigraph)

    print("\n" + "=" * 80)
    print("PROSECUTION ARGUMENTS")
    print("=" * 80)
    print(result)
