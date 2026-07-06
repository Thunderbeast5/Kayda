# Agent: Defense Lawyer (The Defender)
## Role
Analyzes prosecution claims, identifies logical gaps, and builds a counter-narrative.
## Dependencies
- `LexiGraph Agent`, `OpenAI`, `Guardrails AI`
## Workflow
1. Receive `facts_object` and `prosecutor_arguments` from Orchestrator.
2. **Call LexiGraph**: Send a query specifically for "Find counter-precedents, exemptions, or mitigating IPC sections for [Crime]".
3. **Challenge Evidence**: Identify gaps, contradictions, or lack of intent in the prosecution's evidence chain.
4. **Draft Counter-Argument**: Use LLM to write a defense narrative.
5. **Guardrails Check**: Verify all cited precedents actually exist in Neo4j.
6. Return final `defense_arguments` to Orchestrator.