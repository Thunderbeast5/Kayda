# Agent: Judge (The Decision Maker)
## Role
Evaluates the debate, measures legal validity, checks evidence sufficiency, and issues a verdict.
## Dependencies
- `OpenAI`, `Accused Agent`
## Workflow
1. Receive `prosecutor_arguments`, `defense_arguments`, and `facts_object`.
2. **Score Arguments**: Use LLM to rate both arguments on 3 axes: Legal Validity, Evidence Linkage, Logic Coherence.
3. **Sufficiency Check**: Evaluate if the evidence is sufficient for a ruling.
   - If `No` (requires clarification), trigger `Accused Agent` with a specific question.
   - Loop back to Step 2 after receiving testimony.
4. **Final Verdict**: Issue `Guilty` or `Not Guilty`.
5. **Verdict Explanation**: Generate a detailed explanation citing applied IPC sections and pivotal evidence.
6. **Confidence Score**: Assign a percentage confidence.
7. Return `verdict_object` to Orchestrator.