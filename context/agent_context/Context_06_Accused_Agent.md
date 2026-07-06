# Agent: Accused (The Witness/Defendant)
## Role
Simulates a real defendant, ensuring their testimony is consistent and trustworthy.
## Dependencies
- `Redis` (memory store), `OpenAI`
## Workflow
1. Receive a **Question** from Judge or Defense agents.
2. **Load History**: Load `prior_statements` from the current session in Redis.
3. **Generate Response**: Prompt LLM to generate a testimony response while being mindful of the previous context.
4. **Consistency Guardrail**:
   - Check if the new response contradicts any prior statements.
   - If `Contradicts`, force LLM to regenerate while respecting the factual truth established in the case.
   - If `Consistent`, proceed to step 5.
5. **Submit**: Send testimony to the Judge/Orchestrator.