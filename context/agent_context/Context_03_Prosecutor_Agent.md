# Agent: Prosecutor (The Accuser)
## Role
Builds a strong, logical case against the Accused using legal reasoning.
## Dependencies
- `LexiGraph Agent` (for retrieval), `OpenAI` (for drafting), `Guardrails AI`
## Workflow
1. Receive `facts_object` and `session_id` from Orchestrator.
2. **Call LexiGraph**: Send a query formatted as "Find IPC sections and precedents for [Crime] with facts [Who, What, When, Where]".
3. Receive `list[IPC_Sections, Precedents]`.
4. **Map Evidence to Law**: Use the LLM to generate a link between the specific facts and the retrieved legal clauses.
5. **Draft Narrative**: Use LLM to write a cohesive prosecution argument.
6. **Guardrails Check**: Verify all cited IPC sections actually exist in the Neo4j database (to prevent hallucinations). If a section doesn't exist, the LLM must rewrite the argument dropping that section.
7. Return final `prosecutor_arguments` to Orchestrator.