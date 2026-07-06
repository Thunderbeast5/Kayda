# Sprint 0: The Developer Environment Setup

Before touching any code, set up the infrastructure on your local machines (or on a remote VM).

- Install Python 3.11+ & Node.js 18+.
- **Launch Neo4j (Graph DB):** Run this Docker command on your local machine:

```bash
docker run -p 7474:7474 -p 7687:7687 --name neo4j -e NEO4J_AUTH=neo4j/password neo4j
```

  (You will access Neo4j Browser at http://localhost:7474).

- **Launch Redis (Short-term memory):** Run:

```bash
docker run -p 6379:6379 --name redis redis
```

- **Create a Pinecone Index:** Log in to Pinecone, create an index called `legal-embeddings` with dimension 1536 and metric `cosine`.
- **Install Python libs:**

```bash
pip install langgraph langchain-openai langchain-neo4j pinecone-client redis fastapi uvicorn websockets PyPDF2 pytesseract guardrails-ai
```

---

# Sprint 1: Legal Data Ingest (The Foundation)

Your LexiGraph Agent is useless if it doesn't have Indian Penal Code (IPC) data inside it.

1. **Find a CSV/JSON dataset of IPC Sections** (search for "IPC sections dataset GitHub"). It must contain: `Section_Number`, `Description`, `Punishment`, and `Crime_Type`.
2. **Upload to Neo4j:** Write a Python script called `ingest_neo4j.py`. Use the Neo4j Python driver to loop through the CSV and run this Cypher query:

```cypher
MERGE (c:Crime {name: $crime_type})
MERGE (l:IPC {section: $section, description: $desc, punishment: $punish})
MERGE (c)-[:DEFINED_BY]->(l)
```

3. **Upload to Pinecone:** In the same script, use OpenAI `text-embedding-3-small` to embed the `Description` field and upload it to your Pinecone index.

**Goal for Sprint 1:** Open the Neo4j browser, run `MATCH (n:IPC) RETURN n LIMIT 10`, and confirm you see real Indian laws.

---

# Sprint 2: LangGraph State Machine (The Orchestrator Scaffold)

Now, integrate the Orchestrator Agent logic using LangGraph. Do not code the agents yet — just build the skeleton that holds the state.

**Create `state.py`:**

```python
from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph

class AgentState(TypedDict):
    session_id: str
    user_query: str
    structured_facts: dict
    prosecution_args: str
    defense_args: str
    judge_verdict: dict
    accused_history: List[str]
```

**Create `orchestrator_graph.py`:**

1. Initialize `StateGraph(AgentState)`.
2. Add nodes: `evidence_analyzer`, `prosecutor`, `defense`, `judge`.
3. Add edges:
   - `START -> evidence_analyzer`
   - `evidence_analyzer -> prosecutor` and `evidence_analyzer -> defense`
   - `prosecutor -> judge`
   - `defense -> judge`
   - `judge -> END`

**Run a dummy test:** Use a mock function for `evidence_analyzer` that just prints "Done." Run the graph — if it compiles, you have successfully built the simulation engine.

---

# Sprint 3: The Evidence Analyzer (OCR + NER)

This handles the first real-world input: the PDFs and FIR images.

**Create `evidence_analyzer.py`:**

1. Write a function `extract_text(file_path)`: use `PyPDF2` for PDFs and `pytesseract` for images.
2. Write a function `extract_facts(raw_text)`: prompt GPT-4o with:

   > "Extract the following from this text into JSON: Who is the accused, what is the crime, when did it happen, where did it happen, and what is the monetary amount involved (if any)."

3. Save the JSON to MongoDB (using `pymongo`).
4. **Connect to Orchestrator:** Update your LangGraph `evidence_analyzer` node to call this script and output the JSON into `AgentState['structured_facts']`.

---

# Sprint 4: LexiGraph Agent (The RAG Logic)

This is your most critical agent. It connects Neo4j (Graph) and Pinecone (Vector) together.

**Create `lexigraph.py`:**

- **Input:** `query_text` (e.g., "Theft of a bicycle in a public street").
- **Implementation logic:**
  - **Step A:** Use spaCy to extract the crime name ("Theft").
  - **Step B (Graph):** Run a Neo4j Cypher query:

    ```cypher
    MATCH (c:Crime {name: $crime_name})-[:DEFINED_BY]->(l:IPC)
    RETURN l.section, l.description, l.punishment
    ```

  - **Step C (Vector):** Convert the `query_text` to an embedding, query Pinecone for the top 3 semantically similar sections.
  - **Step D (Rank):** Combine both sets of results, remove duplicates, and return a list of 5 laws and their details.
  - **Step E (Guardrail):** If the query returns 0 results, prompt the LLM to rewrite the query.

---

# Sprint 5: Prosecutor & Defense (The Debate Agents)

Now, plug the LexiGraph into your adversarial agents.

**Create `prosecutor.py`:**

1. Pass `structured_facts` into `lexigraph.py`.
2. Use a prompt template with GPT-4o:

   > "You are a prosecutor. Here are the facts: [facts]. Here are the relevant IPC sections: [LexiGraph results]. Write a structured, formal legal argument mapping the facts to these sections."

3. **Guardrails check:** Use the Python `guardrails-ai` library. Define a custom validator that checks if `"IPC "` is in the output. If the guardrail fails, trigger a retry action in LangGraph.

**Create `defense.py`:**

Similar to the prosecutor, but the prompt says:

> "You are a defense lawyer. Challenge the evidence and find counter-precedents using LexiGraph."

---

# Sprint 6: The Judge & Accused Loop (The Brain)

This is where the "truth becomes clearer through debate" paper comes in.

**Create `judge.py`:**

1. The Judge takes `prosecution_args` and `defense_args`.
2. The Judge prompts GPT-4o to: "Score arguments on Legal Validity (0–10), Evidence Linkage (0–10), and Logic (0–10)."
3. The Judge checks if the total score is high enough. If not (e.g., insufficient evidence), the agent sets `AgentState['judge_question'] = "Did the accused have the intent to steal?"` and routes execution to the Accused node.

**Create `accused.py`:**

1. Receives the question.
2. **Load past context:** Pull previous testimony from Redis.
3. **Generate response:** Use the LLM to generate an answer (e.g., "I did not intend to steal, I just borrowed it").
4. **Consistency guardrail:** Build a constraint — "Does this answer contradict the fact that the accused had the keys to the car?" If yes, force the LLM to regenerate until it aligns with the ground-truth facts.
5. **Close the loop:** After the Accused responds, LangGraph routes back to the Judge to issue the final verdict.

---

# Sprint 7: API & Real-Time Frontend Integration

Now turn the Python brain into a usable web app.

**Create `api.py` (FastAPI):**

- Use FastAPI instead of Flask (better for async).
- Create a `POST /upload` endpoint: accepts files, calls `EvidenceAnalyzer`.
- Create a `WS /ws/{session_id}` WebSocket: this acts as a bridge — when a debate step happens in LangGraph, the API pushes the text log to the React frontend in real time.

**Create `react_frontend` (Vite + React Flow):**

- Build a chat interface (like ChatGPT) where you see the agents speaking sequentially.
- Use React Flow to visualize the Neo4j graph. Whenever a law is cited, a graph node appears linking "Crime → IPC Section → Precedent." This provides the explainability your PPT promises.

---

# Sprint 8: The "AI Code Gen" Phase (Team Task Assignment)

Do not write all this code from scratch — you have the 10 Markdown context files given in the previous step.

Here is how to delegate to your 4 team members:

| Team Member | Context Files | Task for Claude |
|---|---|---|
| **Person A** (Backend/Graph Expert) | Context_07 (LexiGraph), Context_10 (DB Schemas) | "Generate the Python Neo4j and Pinecone hybrid retrieval script." |
| **Person B** (LangGraph Expert) | Context_01 (Orchestrator), Context_03, Context_04 | "Generate the LangGraph state machine with nodes for Prosecutor and Defense." |
| **Person C** (Logic/LLM Expert) | Context_05 (Judge), Context_06 (Accused), Context_02 (Evidence) | "Generate the Python functions for OCR, Judge scoring, and Accused consistency checking." |
| **Person D** (Frontend/API Expert) | Context_08 (API), Context_09 (Frontend) | "Generate the FastAPI WebSocket server and React Dashboard with React Flow." |

---

## Final Recommendation to the Lead

Do not connect the frontend to the backend until Sprint 7. For the first 6 sprints, run your tests purely using the Python command line (print the state to the terminal). Once the Python logic is solid, let the frontend team connect the sockets. This saves you weeks of debugging UI bugs while the logic is broken.

Start with Sprint 0 and 1 today. Get that Neo4j database running and populated with IPC sections. Once you have data, everything else builds on top of it. Good luck, and keep the team focused!