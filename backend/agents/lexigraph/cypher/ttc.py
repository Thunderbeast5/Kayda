# import os
# import sys
# from typing import Any, Dict
# from dotenv import load_dotenv, find_dotenv

# # Load environment variables from .env file
# load_dotenv(find_dotenv())

# # ==========================================
# # 0. Environment Setup & Graph Schema Info
# # ==========================================
# # Ensure you have your .env file or environment variables set for:
# # NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, and GROQ_API_KEY
# # 
# # The expected Indian Law Schema (from bns_sections_clean.csv, ipc.csv, ipc2bns.csv):
# # Nodes: Act, Chapter, LawSection, Keyword, Crime, Punishment, LegalRule
# # Relationships: HAS_CHAPTER, HAS_SECTION, DEFINED_BY, HAS_PUNISHMENT, HAS_KEYWORD, 
# #                REPLACED_BY, REPLACES, MORE_SPECIFIC_THAN, APPLIES_FROM, APPLIES_TO

# NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
# NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
# NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
# NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
# GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# print("URI:", NEO4J_URI)
# print("USER:", NEO4J_USER)
# print("PASSWORD:", NEO4J_PASSWORD)

# COMPLEX_QUERY = (
#     "Find the IPC section for 'murder' and show me which BNS section replaced it, "
#     "along with the new punishment details and mapping status."
# )

# SCHEMA_PROMPT = """
# You are a legal AI assistant generating Cypher queries for a Neo4j database of Indian Law.
# The database contains laws from the Indian Penal Code (IPC) and Bharatiya Nyaya Sanhita (BNS).
# Nodes:
# - LawSection (properties: id, act, section, title, description, punishment, mapping_status)
# - Crime (properties: name)
# - Punishment (properties: text)
# Relationships:
# - (Crime)-[:DEFINED_BY]->(LawSection)
# - (LawSection)-[:REPLACED_BY {note, status}]->(LawSection)
# - (LawSection)-[:REPLACES]->(LawSection)
# - (LawSection)-[:HAS_PUNISHMENT]->(Punishment)
# Output strictly valid Cypher.
# """


# # ==========================================
# # Option 1: LangChain (GraphCypherQAChain)
# # ==========================================
# def run_langchain_nlp_to_cypher(query: str):
#     """
#     Standard and highly popular approach. LangChain handles schema fetching, 
#     Cypher generation via LLM, execution, and natural language synthesis.
#     """
#     print("\n--- Running Option 1: LangChain ---")
#     from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
#     from langchain_groq import ChatGroq

#     graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USER, password=NEO4J_PASSWORD, database=NEO4J_DATABASE)
#     llm = ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0)
    
#     chain = GraphCypherQAChain.from_llm(
#         cypher_llm=llm,
#         qa_llm=llm,
#         graph=graph,
#         verbose=True,
#         allow_dangerous_requests=True,
#         return_direct=False # Set to True to just get the Cypher execution JSON
#     )
    
#     response = chain.invoke({"query": query})
#     print("LangChain Response:", response["result"])


# # ==========================================
# # Option 2: LlamaIndex (Neo4jPropertyGraphStore)
# # ==========================================
# def run_llamaindex_nlp_to_cypher(query: str):
#     """
#     LlamaIndex path is not configured for Groq in this environment.
#     Use run_langchain_nlp_to_cypher or run_direct_api_nlp_to_cypher instead.
#     """
#     raise RuntimeError(
#         "LlamaIndex Groq integration is not available. "
#         "Use run_langchain_nlp_to_cypher or run_direct_api_nlp_to_cypher."
#     )


# # ==========================================
# # Option 3: DSPy (Declarative Framework)
# # ==========================================
# def run_dspy_nlp_to_cypher(query: str):
#     """
#     DSPy removes the prompt engineering guesswork by defining a strict Signature.
#     This generates the Cypher, which you then execute via the Neo4j driver.
#     """
#     print("\n--- Running Option 3: DSPy ---")
#     import dspy
#     from neo4j import GraphDatabase

#     # Configure DSPy LM
#     raise RuntimeError(
#         "DSPy Groq integration is not configured in this script. "
#         "Use run_langchain_nlp_to_cypher or run_direct_api_nlp_to_cypher."
#     )

#     # Define strict input/output signature
#     class TextToCypher(dspy.Signature):
#         """Generate a Neo4j Cypher query based on the Indian Law graph schema."""
#         schema_context: str = dspy.InputField(description="The Neo4j graph schema context")
#         user_query: str = dspy.InputField(description="The natural language query regarding crimes or laws")
#         cypher_query: dspy.Code["cypher"] = dspy.OutputField(description="The executable Cypher query without markdown blocks")

#     predictor = dspy.Predict(TextToCypher)
#     result = predictor(schema_context=SCHEMA_PROMPT, user_query=query)
    
#     generated_cypher = result.cypher_query.strip("`").replace("cypher\n", "")
#     print(f"DSPy Generated Cypher:\n{generated_cypher}\n")

#     # Execute with official driver
#     driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
#     with driver.session() as session:
#         try:
#             records = session.run(generated_cypher)
#             print("DSPy Execution Results:", [dict(r) for r in records])
#         except Exception as e:
#             print("DSPy Cypher Execution Failed:", e)
#     driver.close()


# # ==========================================
# # Option 4: Direct LLM + Official Neo4j Driver
# # ==========================================
# def run_direct_api_nlp_to_cypher(query: str):
#     """
#     The leanest, most controllable production method. No heavy frameworks.
#     Direct call to Groq APIs for code generation, followed by driver execution.
#     """
#     print("\n--- Running Option 4: Direct Groq API & Neo4j Driver ---")
#     from groq import Groq
#     from neo4j import GraphDatabase
#     import json

#     client = Groq(api_key=GROQ_API_KEY)

#     system_message = (
#         f"{SCHEMA_PROMPT}\n"
#         "Return ONLY a raw JSON object with a single key 'cypher'. "
#         "Do not include markdown formatting or explanations."
#     )

#     response = client.chat.completions.create(
#         model=GROQ_MODEL,
#         messages=[
#             {"role": "system", "content": system_message},
#             {"role": "user", "content": query}
#         ],
#         temperature=0,
#         response_format={"type": "json_object"}
#     )

#     try:
#         content = response.choices[0].message.content
#         cypher_query = json.loads(content).get("cypher", "")
#         print(f"Direct API Generated Cypher:\n{cypher_query}\n")

#         driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
#         with driver.session() as session:
#             records = session.run(cypher_query)
#             print("Direct API Execution Results:", [dict(r) for r in records])
#         driver.close()
#     except Exception as e:
#         print("Direct API Failed parsing or execution:", e)


# # ==========================================
# # Option 5: Haystack (Custom Pipeline)
# # ==========================================
# def run_haystack_nlp_to_cypher(query: str):
#     """
#     Haystack v2 pipeline utilizing deepset's generator and custom components.
#     Excellent for modular enterprise RAG pipelines.
#     """
#     print("\n--- Running Option 5: Haystack (v2) ---")
#     from haystack import Pipeline
#     from haystack.components.generators import OpenAIGenerator
#     from haystack.components.builders.prompt_builder import PromptBuilder
#     from neo4j import GraphDatabase
#     from haystack import component
    
#     # Custom Haystack Component to execute the generated Cypher
#     @component
#     class Neo4jCypherExecutor:
#         def __init__(self, uri, user, password):
#             self.driver = GraphDatabase.driver(uri, auth=(user, password))
            
#         @component.output_types(db_results=list)
#         def run(self, cypher: str):
#             clean_cypher = cypher.strip("`").replace("cypher\n", "")
#             with self.driver.session() as session:
#                 try:
#                     records = session.run(clean_cypher)
#                     return {"db_results": [dict(r) for r in records]}
#                 except Exception as e:
#                     return {"db_results": [f"Error: {e}"]}
                    
#     prompt_template = """
#     {{schema_prompt}}
#     Based on the schema, write ONLY a valid Cypher query for this request: {{query}}
#     Do not use markdown backticks.
#     """

#     prompt_builder = PromptBuilder(template=prompt_template)
#     llm = OpenAIGenerator(model="gpt-4o", generation_kwargs={"temperature": 0})
#     executor = Neo4jCypherExecutor(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

#     pipeline = Pipeline()
#     pipeline.add_component("prompt_builder", prompt_builder)
#     pipeline.add_component("llm", llm)
#     pipeline.add_component("executor", executor)

#     pipeline.connect("prompt_builder.prompt", "llm.prompt")
#     # In Haystack, the generator outputs a list of strings called 'replies'
#     pipeline.connect("llm.replies[0]", "executor.cypher") 

#     results = pipeline.run({
#         "prompt_builder": {
#             "query": query,
#             "schema_prompt": SCHEMA_PROMPT
#         }
#     })
    
#     print("Haystack Results:", results["executor"]["db_results"])


# # ==========================================
# # Main Execution Block
# # ==========================================
# if __name__ == "__main__":
#     user_query = sys.argv[1] if len(sys.argv) > 1 else COMPLEX_QUERY
#     print(f"Query Submitted: {user_query}")
    
#     # Uncomment the specific option you wish to evaluate for your Indian Law Graph:
    
#     # run_langchain_nlp_to_cypher(user_query)
#     # run_llamaindex_nlp_to_cypher(user_query)
#     # run_dspy_nlp_to_cypher(user_query)
#     # run_direct_api_nlp_to_cypher(user_query)
#     run_haystack_nlp_to_cypher(user_query)


import os
import sys
from typing import Any, Dict
from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env file
load_dotenv(find_dotenv())

# ==========================================
# 0. Environment Setup & Graph Schema Info
# ==========================================
# Ensure you have your .env file or environment variables set for:
# NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, and GROQ_API_KEY
#
# The ACTUAL Indian Law Schema, as built by neo4j_v5.py from
# bns_sections_clean.csv, ipc.csv, ipc2bns.csv:
#
# Nodes:
#   Act        {code, name}
#   Chapter    {id, act, raw, number, title}
#   LawSection {id, act, section, title, description, punishment,
#               mapping_status, cognizable, bailable, court,      (IPC only)
#               category, keywords, chapter_raw, ...}             (BNS only)
#   Crime      {id, name}
#   Punishment {id, text}
#   Keyword    {id, name}
#   LegalRule  {id, relationship, condition, confidence}
#
# Relationships:
#   (Act)-[:HAS_CHAPTER]->(Chapter)
#   (Act)-[:HAS_SECTION]->(LawSection)
#   (Chapter)-[:HAS_SECTION]->(LawSection)
#   (Crime)-[:DEFINED_BY]->(LawSection)
#   (LawSection)-[:HAS_PUNISHMENT]->(Punishment)
#   (LawSection)-[:HAS_KEYWORD]->(Keyword)
#   (LawSection[IPC])-[:REPLACED_BY {note, status, bns_subsection}]->(LawSection[BNS])
#   (LawSection[BNS])-[:REPLACES {note, status, ipc_subsection}]->(LawSection[IPC])
#   (LawSection)-[:MORE_SPECIFIC_THAN|OVERRIDES|ENHANCES|INCLUDES_ELEMENTS_OF|CANNOT_COEXIST_WITH]->(LawSection)
#   (LegalRule)-[:APPLIES_FROM]->(LawSection)
#   (LegalRule)-[:APPLIES_TO]->(LawSection)
#
# Full-text indexes that already exist (created by create_fulltext_indexes):
#   lawSectionText  -> LawSection(title, description, punishment, keywords)
#   crimeName       -> Crime(name)
#
# IMPORTANT: Crime.name and LawSection.title are stored with the EXACT
# capitalization from the source CSVs (e.g. "Dowry death", not "Dowry Death").
# Never rely on exact case-sensitive equality against these — use
# toLower(x) CONTAINS toLower('...') or the fulltext indexes above.

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"  # OpenAI-compatible endpoint, used by Haystack

print("URI:", NEO4J_URI)
print("USER:", NEO4J_USER)
print("PASSWORD: ***redacted***")  # never print secrets to stdout/logs

COMPLEX_QUERY = (
    "Find the IPC section for 'murder' and show me which BNS section replaced it, "
    "along with the new punishment details and mapping status."
)

# ==========================================
# Shared schema/instruction prompt for every backend
# ==========================================
SCHEMA_PROMPT = """
You are a legal AI assistant generating Cypher queries for a Neo4j database of Indian Law
(Indian Penal Code [IPC] and Bharatiya Nyaya Sanhita [BNS]).

Nodes:
- Act        {code, name}
- Chapter    {id, act, raw, number, title}
- LawSection {id, act, section, title, description, punishment, mapping_status,
              cognizable, bailable, court, category, keywords}
- Crime      {id, name}
- Punishment {id, text}
- Keyword    {id, name}
- LegalRule  {id, relationship, condition, confidence}

Relationships:
- (Act)-[:HAS_CHAPTER]->(Chapter)
- (Act)-[:HAS_SECTION]->(LawSection)
- (Chapter)-[:HAS_SECTION]->(LawSection)
- (Crime)-[:DEFINED_BY]->(LawSection)
- (LawSection)-[:HAS_PUNISHMENT]->(Punishment)
- (LawSection)-[:HAS_KEYWORD]->(Keyword)
- (LawSection {act:'IPC'})-[:REPLACED_BY {note, status, bns_subsection}]->(LawSection {act:'BNS'})
- (LawSection {act:'BNS'})-[:REPLACES {note, status, ipc_subsection}]->(LawSection {act:'IPC'})
- (LawSection)-[:MORE_SPECIFIC_THAN]->(LawSection)

Full-text indexes available (use these for any name/keyword lookup):
- crimeName      over Crime(name)
- lawSectionText over LawSection(title, description, punishment, keywords)

CRITICAL RULES:
1. Crime.name and LawSection.title use the exact capitalization from source data
   (e.g. "Dowry death"). NEVER use exact case-sensitive equality (=) to match a
   name or title supplied in natural language.
2. Instead, either:
   a) use `toLower(n.property) CONTAINS toLower('search term')`, or
   b) use the full-text indexes, e.g.
      CALL db.index.fulltext.queryNodes('crimeName', 'dowry death') YIELD node, score
3. Output strictly valid Cypher only — no markdown fences, no explanation.
"""


# ==========================================
# Option 1: LangChain (GraphCypherQAChain)
# ==========================================
def run_langchain_nlp_to_cypher(query: str):
    """
    Standard and highly popular approach. LangChain handles schema fetching,
    Cypher generation via LLM, execution, and natural language synthesis.
    """
    print("\n--- Running Option 1: LangChain ---")
    from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
    from langchain_groq import ChatGroq

    graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USER, password=NEO4J_PASSWORD, database=NEO4J_DATABASE)
    llm = ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0)

    chain = GraphCypherQAChain.from_llm(
        cypher_llm=llm,
        qa_llm=llm,
        graph=graph,
        verbose=True,
        allow_dangerous_requests=True,
        return_direct=False,  # Set to True to just get the Cypher execution JSON
        # GraphCypherQAChain builds its own schema string from the DB by default;
        # cypher_prompt lets us inject our stricter case-insensitive-matching rules
        # on top of that. We do it via the chain's cypher_generation_chain prompt.
    )

    # Inject our stricter instructions into the generated cypher prompt so the
    # LLM stops doing case-sensitive exact matches against Crime.name / title.
    try:
        chain.cypher_generation_chain.prompt.template = (
            SCHEMA_PROMPT + "\n\n" + chain.cypher_generation_chain.prompt.template
        )
    except AttributeError:
        pass  # older/newer langchain_neo4j versions may not expose this; safe to skip

    response = chain.invoke({"query": query})
    print("LangChain Response:", response["result"])
    return response["result"]


# ==========================================
# Option 2: LlamaIndex (Groq LLM + direct Cypher execution)
# ==========================================
def run_llamaindex_nlp_to_cypher(query: str):
    """
    Uses LlamaIndex's LLM abstraction (llama-index-llms-groq) to generate Cypher,
    then executes it with the official Neo4j driver.

    Requires: pip install llama-index-core llama-index-llms-groq neo4j
    """
    print("\n--- Running Option 2: LlamaIndex ---")
    from llama_index.llms.groq import Groq as LlamaIndexGroq
    from neo4j import GraphDatabase

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set.")

    llm = LlamaIndexGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0)

    prompt = (
        f"{SCHEMA_PROMPT}\n\n"
        f"User request: {query}\n\n"
        "Return ONLY the raw Cypher query. No markdown, no backticks, no commentary."
    )
    response = llm.complete(prompt)
    cypher_query = str(response).strip().strip("`")
    if cypher_query.lower().startswith("cypher"):
        cypher_query = cypher_query[len("cypher"):].strip()

    print(f"LlamaIndex Generated Cypher:\n{cypher_query}\n")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            try:
                records = session.run(cypher_query)
                results = [dict(r) for r in records]
                print("LlamaIndex Execution Results:", results)
                return results
            except Exception as e:
                print("LlamaIndex Cypher Execution Failed:", e)
                return None
    finally:
        driver.close()


# ==========================================
# Option 3: DSPy (Declarative Framework)
# ==========================================
def run_dspy_nlp_to_cypher(query: str):
    """
    DSPy removes the prompt engineering guesswork by defining a strict Signature.
    This generates the Cypher, which you then execute via the Neo4j driver.

    Requires: pip install dspy neo4j
    DSPy talks to Groq through LiteLLM, so the model string needs the
    "groq/" provider prefix, e.g. "groq/llama-3.3-70b-versatile".
    """
    print("\n--- Running Option 3: DSPy ---")
    import dspy
    from neo4j import GraphDatabase

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set.")

    # Configure DSPy's LM to route through Groq via LiteLLM
    lm = dspy.LM(f"groq/{GROQ_MODEL}", api_key=GROQ_API_KEY, temperature=0)
    dspy.configure(lm=lm)

    # Define strict input/output signature
    class TextToCypher(dspy.Signature):
        """Generate a single valid Neo4j Cypher query based on the Indian Law graph schema."""

        schema_context: str = dspy.InputField(description="The Neo4j graph schema context")
        user_query: str = dspy.InputField(description="The natural language query regarding crimes or laws")
        cypher_query: str = dspy.OutputField(
            description="The executable Cypher query only, no markdown fences, no commentary"
        )

    predictor = dspy.Predict(TextToCypher)
    result = predictor(schema_context=SCHEMA_PROMPT, user_query=query)

    generated_cypher = result.cypher_query.strip().strip("`")
    if generated_cypher.lower().startswith("cypher"):
        generated_cypher = generated_cypher[len("cypher"):].strip()
    print(f"DSPy Generated Cypher:\n{generated_cypher}\n")

    # Execute with official driver
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            try:
                records = session.run(generated_cypher)
                results = [dict(r) for r in records]
                print("DSPy Execution Results:", results)
                return results
            except Exception as e:
                print("DSPy Cypher Execution Failed:", e)
                return None
    finally:
        driver.close()


# ==========================================
# Option 4: Direct LLM + Official Neo4j Driver
# ==========================================
def run_direct_api_nlp_to_cypher(query: str):
    """
    The leanest, most controllable production method. No heavy frameworks.
    Direct call to Groq APIs for code generation, followed by driver execution.
    """
    print("\n--- Running Option 4: Direct Groq API & Neo4j Driver ---")
    from groq import Groq
    from neo4j import GraphDatabase
    import json

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set.")

    client = Groq(api_key=GROQ_API_KEY)

    system_message = (
        f"{SCHEMA_PROMPT}\n"
        "Return ONLY a raw JSON object with a single key 'cypher'. "
        "Do not include markdown formatting or explanations."
    )

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": query},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    try:
        content = response.choices[0].message.content
        cypher_query = json.loads(content).get("cypher", "")
        print(f"Direct API Generated Cypher:\n{cypher_query}\n")

        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        try:
            with driver.session(database=NEO4J_DATABASE) as session:
                records = session.run(cypher_query)
                results = [dict(r) for r in records]
                print("Direct API Execution Results:", results)
                return results
        finally:
            driver.close()
    except Exception as e:
        print("Direct API Failed parsing or execution:", e)
        return None


# ==========================================
# Option 5: Haystack (Custom Pipeline)
# ==========================================
def run_haystack_nlp_to_cypher(query: str):
    """
    Haystack v2 (the deepset framework) pipeline using an OpenAI-compatible
    generator pointed at Groq's endpoint, plus a custom component to execute
    the generated Cypher.

    IMPORTANT: the PyPI package is `haystack-ai`, NOT `haystack`.
    `pip install haystack` installs an unrelated process-injection/binary
    analysis tool and does not provide `haystack.Pipeline` at all, which is
    why the previous run failed with an ImportError.

        pip uninstall haystack construct pefile python-ptrace -y
        pip install haystack-ai
    """
    print("\n--- Running Option 5: Haystack (v2 / haystack-ai) ---")
    try:
        from haystack import Pipeline, component
        from haystack.components.generators import OpenAIGenerator
        from haystack.components.builders.prompt_builder import PromptBuilder
        from haystack.utils import Secret
    except ImportError as e:
        raise ImportError(
            "Could not import from 'haystack'. You likely have the wrong package "
            "installed (PyPI has an unrelated package literally named 'haystack'). "
            "Fix with:\n"
            "  pip uninstall haystack construct pefile python-ptrace -y\n"
            "  pip install haystack-ai"
        ) from e

    from neo4j import GraphDatabase

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set.")

    # Custom Haystack Component to execute the generated Cypher
    @component
    class Neo4jCypherExecutor:
        def __init__(self, uri, user, password, database):
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            self.database = database

        @component.output_types(db_results=list)
        def run(self, replies: list):
            cypher = replies[0] if replies else ""
            clean_cypher = cypher.strip().strip("`")
            if clean_cypher.lower().startswith("cypher"):
                clean_cypher = clean_cypher[len("cypher"):].strip()
            with self.driver.session(database=self.database) as session:
                try:
                    records = session.run(clean_cypher)
                    return {"db_results": [dict(r) for r in records]}
                except Exception as e:
                    return {"db_results": [f"Error: {e}"]}

    prompt_template = """
{{schema_prompt}}

Based on the schema above, write ONLY a valid Cypher query for this request: {{query}}
Do not use markdown backticks. Do not add commentary.
"""

    prompt_builder = PromptBuilder(template=prompt_template)
    # Groq exposes an OpenAI-compatible /v1 endpoint, so OpenAIGenerator works
    # as long as we point api_base_url at Groq and pass a Groq key.
    llm = OpenAIGenerator(
        api_key=Secret.from_token(GROQ_API_KEY),
        api_base_url=GROQ_BASE_URL,
        model=GROQ_MODEL,
        generation_kwargs={"temperature": 0},
    )
    executor = Neo4jCypherExecutor(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE)

    pipeline = Pipeline()
    pipeline.add_component("prompt_builder", prompt_builder)
    pipeline.add_component("llm", llm)
    pipeline.add_component("executor", executor)

    pipeline.connect("prompt_builder.prompt", "llm.prompt")
    # llm.replies is a List[str]; the executor component takes the whole list
    # and picks index [0] itself (Haystack sockets can't be subscripted like
    # "llm.replies[0]" — that syntax was never valid and is a common mistake).
    pipeline.connect("llm.replies", "executor.replies")

    results = pipeline.run({
        "prompt_builder": {
            "query": query,
            "schema_prompt": SCHEMA_PROMPT,
        }
    })

    print("Haystack Results:", results["executor"]["db_results"])
    return results["executor"]["db_results"]


# ==========================================
# Main Execution Block
# ==========================================
if __name__ == "__main__":
    user_query = sys.argv[1] if len(sys.argv) > 1 else COMPLEX_QUERY
    print(f"Query Submitted: {user_query}")

    # Uncomment the specific option you wish to evaluate for your Indian Law Graph:

    # run_langchain_nlp_to_cypher(user_query)
    # run_llamaindex_nlp_to_cypher(user_query)
    # run_dspy_nlp_to_cypher(user_query)
    # run_direct_api_nlp_to_cypher(user_query)
    run_haystack_nlp_to_cypher(user_query)