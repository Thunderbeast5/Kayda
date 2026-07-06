# Agent: Orchestrator (The Manager)
## Role
Acts as the central state machine. It routes data between agents, manages the session using Redis, and handles the LangGraph loop.
## Dependencies
- `langgraph`, `langgraph-checkpoint-redis`, `langchain`
## Step-by-Step Workflow
1. Receives user input (case text or file path).
2. Invokes `Evidence Analyzer Agent` to process the raw files and return structured JSON facts.
3. Receives structured facts and serializes them into the current LangGraph state.
4. Triggers `Prosecutor Agent` and `Defense Agent` concurrently (Parallel execution).
5. Aggregates their arguments and triggers `Judge Agent`.
6. If Judge needs a clarification, it pauses the state and triggers `Accused Agent`, then resumes Judge.
7. Collects Verdict and pushes the results to the frontend via WebSocket.
## State Schema (LangGraph)
{
  "session_id": "uuid",
  "case_facts_raw": "string",
  "evidence_analyzed": { "who": "str", "what": "str", "when": "date", "where": "str" },
  "prosecutor_arguments": "string",
  "defense_arguments": "string",
  "judge_questions": "string",
  "accused_testimonies": "list[str]",
  "final_verdict": { "decision": "Guilty/Not Guilty", "laws_applied": "list", "confidence": "float" }
}