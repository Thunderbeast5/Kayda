"""
Prosecutor Agent — Step 1 + Step 2
====================================
Step 1: Accept, Validate, Normalize, Log  (done)
Step 2: Build legal query, Call LexiGraph, Validate response, Store in context

The Prosecutor does NOT care whether LexiGraph uses Neo4j, Pinecone,
or any other backend.  It calls a single function and gets typed results.
"""

import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.prosecutor_models import (
    LexiGraphResult,
    ProsecutionContext,
    ProsecutorInput,
)

# ── Logger ────────────────────────────────────────────────────────────────────

logger = logging.getLogger("prosecutor")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter(
            "[%(name)s] %(asctime)s | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(_handler)


# ══════════════════════════════════════════════════════════════════════════════
# Task 2.1 — LexiGraph interface definition
# ══════════════════════════════════════════════════════════════════════════════
#
# The Prosecutor interacts with LexiGraph through ONE function:
#
#   lexigraph.retrieve(query_text, section_hint, top_n) -> dict
#
# We import it lazily so prosecutor.py has zero import-time dependency on
# Neo4j / Pinecone / spaCy / sentence-transformers drivers.  If LexiGraph
# is unavailable (e.g. unit-test mode), retrieve_laws() catches the error
# and marks the context as retrieval_empty = True.
# ══════════════════════════════════════════════════════════════════════════════


def _import_lexigraph():
    """Lazy import so tests can run without Neo4j / Pinecone up."""
    try:
        from agents.lexigraph import retrieve, format_for_prompt
        return retrieve, format_for_prompt
    except Exception as exc:
        logger.warning("LexiGraph import failed: %s", exc)
        return None, None


# ══════════════════════════════════════════════════════════════════════════════
# Task 2.2 — Build a legal query from ProsecutionContext
# ══════════════════════════════════════════════════════════════════════════════


def build_legal_query(ctx: ProsecutionContext) -> str:
    """
    Convert a ProsecutionContext into a single natural-language retrieval
    query that works for ANY case type (theft, murder, fraud, assault, etc.).

    Strategy — combine multiple signals for maximum recall:
      1. Incident summary      → primary signal (most descriptive)
      2. Known IPC sections    → exact section hints
      3. Accused action        → infer crime type from who + what
      4. Property / loss       → property crimes often match on keywords
      5. Victim context        → helps in assault / bodily harm cases

    The resulting string is what LexiGraph's spaCy NER + Pinecone semantic
    search will consume.  More context = better retrieval.
    """
    parts: List[str] = []

    # 1. Incident summary — always the primary signal
    parts.append(ctx.incident_summary)

    # 2. Accused names + action — helps NER link persons to crimes
    accused_str = ", ".join(ctx.accused)
    parts.append(f"Accused: {accused_str}")

    # 3. Victims — relevant for assault / murder / hurt cases
    if ctx.victims:
        parts.append(f"Victims: {', '.join(ctx.victims)}")

    # 4. Place — jurisdiction context (e.g. "public place" matters for
    #    trespass, obscenity, rioting sections)
    if ctx.incident_place:
        parts.append(f"Location: {ctx.incident_place}")

    # 5. Property / monetary loss — triggers property-crime sections
    prop = ctx.property_details
    loss_parts: List[str] = []
    if prop.estimated_loss:
        loss_parts.append(f"estimated loss {prop.estimated_loss}")
    if prop.cash:
        loss_parts.append(f"cash: {prop.cash}")
    if prop.gold:
        loss_parts.append(f"gold: {prop.gold}")
    if prop.vehicles:
        for v in prop.vehicles:
            desc = " ".join(filter(None, [v.type, v.make_model, v.registration_no]))
            if desc.strip():
                loss_parts.append(f"vehicle: {desc.strip()}")
    if loss_parts:
        parts.append("Property involved: " + "; ".join(loss_parts))

    query = ". ".join(parts)
    logger.debug("Built legal query (%d chars)", len(query))
    return query


def extract_section_hint(ctx: ProsecutionContext) -> Optional[str]:
    """
    If the Evidence Analyzer already identified IPC/BNS sections,
    pass the first one as a hint to LexiGraph for an exact-match boost.
    """
    for sec in ctx.known_sections:
        # Strip prefixes: "IPC 379" → "379", "BNS 303" → "303"
        cleaned = re.sub(r"^(?:IPC|BNS|Section)\s*", "", sec, flags=re.IGNORECASE).strip()
        if cleaned:
            return cleaned
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Task 2.4 — Validate LexiGraph response
# ══════════════════════════════════════════════════════════════════════════════


def validate_retrieval(raw_result: dict) -> LexiGraphResult:
    """
    Parse the raw dict from lexigraph.retrieve() into a typed
    LexiGraphResult.  This catches schema drift and missing fields
    without crashing the pipeline.
    """
    try:
        return LexiGraphResult(**raw_result)
    except Exception as exc:
        logger.error("LexiGraph response validation failed: %s", exc)
        return LexiGraphResult()


def check_retrieval_quality(result: LexiGraphResult) -> bool:
    """
    Returns True if the retrieval has at least one usable section.
    If False, the prosecutor should NOT ask the LLM to invent laws —
    it should report 'No applicable IPC sections found.'
    """
    return len(result.ipc_sections) > 0


# ══════════════════════════════════════════════════════════════════════════════
# ProsecutorAgent
# ══════════════════════════════════════════════════════════════════════════════


class ProsecutorAgent:
    """
    Prosecutor Agent (Step 1 + Step 2).

    Pipeline:
      Step 1: accept()         → validate + normalize → ProsecutionContext
      Step 2: retrieve_laws()  → query LexiGraph → validate → store in context
    """

    # ══════════════════════════════════════════════════════════════════
    # STEP 1 — Accept, Validate, Normalize, Log
    # ══════════════════════════════════════════════════════════════════

    def accept(
        self,
        session_id: str,
        structured_facts: Dict[str, Any],
    ) -> ProsecutionContext:
        """
        Entry point. Call this from the orchestrator node.

        Parameters
        ----------
        session_id : str
            Unique session / case identifier.
        structured_facts : dict
            Raw output of evidence_analyzer.

        Returns
        -------
        ProsecutionContext
            Validated, normalized internal context object.
        """
        logger.info("-" * 60)
        logger.info("PROSECUTOR -- new request received")
        logger.info("  session_id : %s", session_id)

        validated_input = self._validate(session_id, structured_facts)
        context = self._build_context(validated_input)
        self._log_context(context)

        logger.info("PROSECUTOR -- context ready, awaiting Step 2 (LexiGraph)")
        return context

    @staticmethod
    def _validate(
        session_id: str,
        structured_facts: Dict[str, Any],
    ) -> ProsecutorInput:
        logger.debug("Validating input ...")
        try:
            validated = ProsecutorInput(
                session_id=session_id,
                structured_facts=structured_facts,
            )
        except Exception as exc:
            logger.error("Validation FAILED: %s", exc)
            raise
        logger.debug("Validation OK")
        return validated

    @staticmethod
    def _build_context(validated: ProsecutorInput) -> ProsecutionContext:
        facts = validated.structured_facts
        return ProsecutionContext(
            session_id=validated.session_id,
            accused=facts.who.accused,
            complainant=facts.who.complainant,
            victims=facts.who.victims,
            incident_summary=facts.incident.summary,
            incident_date=facts.incident.date,
            incident_time=facts.incident.time,
            incident_place=facts.incident.place,
            property_details=facts.property,
            known_sections=facts.sections,
        )

    @staticmethod
    def _log_context(ctx: ProsecutionContext) -> None:
        logger.info("  accused      : %s", ctx.accused)
        logger.info("  complainant  : %s", ctx.complainant)
        logger.info("  victims      : %s", ctx.victims)
        summary_display = (ctx.incident_summary[:120] + "..."
                           if len(ctx.incident_summary) > 120
                           else ctx.incident_summary)
        logger.info("  summary      : %s", summary_display)
        logger.info("  date/time    : %s / %s", ctx.incident_date, ctx.incident_time)
        logger.info("  place        : %s", ctx.incident_place)
        logger.info("  known IPC    : %s", ctx.known_sections)
        logger.info("  property loss: %s", ctx.property_details.estimated_loss)

    # ══════════════════════════════════════════════════════════════════
    # STEP 2 — LexiGraph Integration
    # ══════════════════════════════════════════════════════════════════

    def retrieve_laws(self, ctx: ProsecutionContext) -> ProsecutionContext:
        """
        Task 2.2 → 2.3 → 2.4 → 2.5 in one call.

        1. Build a legal query from ProsecutionContext (not raw JSON).
        2. Call LexiGraph (the Prosecutor doesn't care what's behind it).
        3. Validate the response (typed, not raw dict).
        4. If zero results → mark retrieval_empty, DON'T invent laws.
        5. Store everything back into ProsecutionContext.

        Parameters
        ----------
        ctx : ProsecutionContext
            Context from Step 1 (accept).

        Returns
        -------
        ProsecutionContext
            Same object, now enriched with retrieval results.
        """
        logger.info("-" * 60)
        logger.info("PROSECUTOR STEP 2 -- LexiGraph retrieval")

        # ── 2.2 Build the legal query ─────────────────────────────────
        query_text = build_legal_query(ctx)
        section_hint = extract_section_hint(ctx)

        logger.info("  query     : %s", query_text[:150] + "..."
                     if len(query_text) > 150 else query_text)
        if section_hint:
            logger.info("  hint      : %s", section_hint)

        ctx.retrieval_query = query_text

        # ── 2.3 Call LexiGraph ────────────────────────────────────────
        retrieve_fn, format_fn = _import_lexigraph()

        if retrieve_fn is None:
            logger.error("LexiGraph unavailable -- marking retrieval as empty")
            ctx.retrieval_empty = True
            ctx.formatted_laws_for_prompt = (
                "DATABASE RETRIEVAL: LexiGraph service unavailable.\n"
                "No applicable IPC sections found. "
                "Do not invent or fabricate legal sections."
            )
            return ctx

        try:
            raw_result = retrieve_fn(
                query_text=query_text,
                section_hint=section_hint,
                top_n=7,          # request more for prosecution (covers aggravating sections)
                pinecone_top_k=10,
            )
        except Exception as exc:
            logger.error("LexiGraph call failed: %s", exc)
            ctx.retrieval_empty = True
            ctx.formatted_laws_for_prompt = (
                "DATABASE RETRIEVAL: LexiGraph query failed.\n"
                "No applicable IPC sections found. "
                "Do not invent or fabricate legal sections."
            )
            return ctx

        # ── 2.4 Validate the response ────────────────────────────────
        typed_result = validate_retrieval(raw_result)
        has_results = check_retrieval_quality(typed_result)

        logger.info("  sections  : %d retrieved", len(typed_result.ipc_sections))
        logger.info("  neo4j     : %d hits", typed_result.neo4j_count)
        logger.info("  pinecone  : %d hits", typed_result.pinecone_count)
        logger.info("  rewritten : %s", typed_result.rewritten)

        if not has_results:
            logger.warning("  RETRIEVAL EMPTY -- no applicable IPC sections found")

        # ── 2.5 Store in context ─────────────────────────────────────
        #
        # Keep BOTH structured data and formatted string:
        #   - retrieved_laws          → full LexiGraphResult (metadata, counts)
        #   - retrieved_sections      → List[RetrievedSection]  (guardrails iterate this)
        #   - valid_section_numbers   → ['379', '411', ...]     (guardrails check membership)
        #   - formatted_laws_for_prompt → string for LLM prompt (human-readable)
        #
        ctx.retrieved_laws = typed_result
        ctx.retrieval_empty = not has_results
        ctx.retrieved_sections = list(typed_result.ipc_sections)
        ctx.valid_section_numbers = [sec.section for sec in typed_result.ipc_sections]

        # Pre-format laws for the LLM prompt (format_fn = lexigraph.format_for_prompt)
        if format_fn and has_results:
            ctx.formatted_laws_for_prompt = format_fn(raw_result)
        elif has_results:
            # Fallback formatting if format_for_prompt is unavailable
            ctx.formatted_laws_for_prompt = self._fallback_format(typed_result)
        else:
            ctx.formatted_laws_for_prompt = (
                "DATABASE RETRIEVAL: No applicable IPC sections found.\n"
                f"Keywords attempted: {typed_result.keywords}\n"
                "Do not invent or fabricate legal sections. "
                "State that insufficient legal grounds were found."
            )

        # Log each retrieved section for traceability
        for i, sec in enumerate(typed_result.ipc_sections, 1):
            logger.info(
                "    [%d] IPC %s | %s | score=%.2f | %s",
                i, sec.section, sec.offense or "(no title)",
                sec.score, sec.source,
            )

        logger.info("PROSECUTOR STEP 2 -- complete (retrieval_empty=%s)", ctx.retrieval_empty)
        return ctx

    @staticmethod
    def _fallback_format(result: LexiGraphResult) -> str:
        """Simple text formatting when lexigraph.format_for_prompt is unavailable."""
        lines = [
            f"RETRIEVED IPC SECTIONS [{len(result.ipc_sections)} total]",
            "=" * 50,
        ]
        for i, s in enumerate(result.ipc_sections, 1):
            lines.append(
                f"\n{i}. IPC {s.section}  [score={s.score:.2f}]\n"
                f"   Offense   : {s.offense or 'See description'}\n"
                f"   Punishment: {s.punishment or 'N/A'}\n"
                f"   Summary   : {s.description[:200]}"
            )
        return "\n".join(lines)

    # ══════════════════════════════════════════════════════════════════
    # STEP 3 — LLM Generation
    # ══════════════════════════════════════════════════════════════════

    def generate_argument(self, ctx: ProsecutionContext) -> ProsecutionContext:
        """
        Step 3: Generate a structured prosecution argument using GPT-Llama.
        No validation or retry logic here (belongs to Step 4).
        """
        logger.info("-" * 60)
        logger.info("PROSECUTOR STEP 3 -- LLM Generation")

        if ctx.retrieval_empty:
            msg = "No applicable IPC sections were retrieved from LexiGraph. Therefore, legal mapping cannot be performed."
            logger.info("Retrieval is empty. Setting message: %s", msg)
            ctx.draft_argument = msg
            ctx.final_argument = msg
            ctx.guardrail_passed = True
            ctx.retry_count = 0
            ctx.validation_errors = []
            ctx.generation_status = "success"
            return ctx

        # 3.1 & 3.5 — Lazy imports from prompts and llm_client to avoid direct hardcoding
        from prompts.prosecutor_prompt import PROSECUTOR_SYSTEM_PROMPT, build_prosecutor_user_prompt
        from services.llm_client import generate

        # 3.3 — Construct user prompt sections
        # Formatting facts
        facts_str = f"Incident Summary: {ctx.incident_summary}\n"
        facts_str += f"Accused: {', '.join(ctx.accused)}\n"
        if ctx.complainant:
            facts_str += f"Complainant: {ctx.complainant}\n"
        if ctx.victims:
            facts_str += f"Victims: {', '.join(ctx.victims)}\n"
        if ctx.incident_date:
            facts_str += f"Date: {ctx.incident_date}\n"
        if ctx.incident_time:
            facts_str += f"Time: {ctx.incident_time}\n"
        if ctx.incident_place:
            facts_str += f"Place: {ctx.incident_place}\n"
        if ctx.property_details:
            prop = ctx.property_details
            if prop.vehicles:
                for v in prop.vehicles:
                    facts_str += f"Vehicle involved: {v.make_model} (Reg No: {v.registration_no})\n"
            if prop.estimated_loss:
                facts_str += f"Property loss value: {prop.estimated_loss}\n"
        
        # Formatting retrieved IPC sections
        ipc_str = ctx.formatted_laws_for_prompt or "No applicable IPC sections found."

        # Precedents: extract precedents if they actually exist in the database source
        precedents_list = []
        if ctx.retrieved_laws and ctx.retrieved_laws.ipc_sections:
            for s in ctx.retrieved_laws.ipc_sections:
                if "precedent" in s.source.lower():
                    precedents_list.append(f"Precedent for IPC {s.section}: {s.description}")
        
        if precedents_list:
            precedents_str = "\n".join(precedents_list)
        else:
            sections_str = ", ".join(f"IPC {s.section}" for s in ctx.retrieved_laws.ipc_sections) if ctx.retrieved_laws and ctx.retrieved_laws.ipc_sections else "the applicable law"
            precedents_str = f"No judicial precedent was retrieved. The prosecution relies on the statutory language of {sections_str}."

        user_prompt = build_prosecutor_user_prompt(
            facts=facts_str,
            ipc=ipc_str,
            precedents=precedents_str
        )

        # 3.6 — Build messages for generate call
        messages = [
            {"role": "system", "content": PROSECUTOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        # Store prompts in context so Guardrails can retry without rebuilding
        ctx.system_prompt = PROSECUTOR_SYSTEM_PROMPT
        ctx.user_prompt = user_prompt
        ctx.prompt_messages = list(messages)

        # ── Step 4 — Guardrails & Retry Loop ─────────────────────────
        from validators.prosecutor_guardrails import validate_draft_argument

        max_attempts = 3
        final_response_text = None
        success = False
        
        ctx.retry_count = 0
        ctx.validation_errors = []
        ctx.final_argument = None

        for attempt in range(1, max_attempts + 1):
            logger.info("  Attempt %d of %d...", attempt, max_attempts)
            logger.debug("Invoking GPT-Llama client generate method ...")
            
            try:
                response_text = generate(messages, temperature=0.2)
                final_response_text = response_text
                
                # Store the first attempt as the initial draft_argument
                if attempt == 1:
                    ctx.draft_argument = response_text
                
                # Run the structured validation
                val_result = validate_draft_argument(
                    text=response_text,
                    valid_section_numbers=ctx.valid_section_numbers,
                    retrieved_precedents_text=precedents_str,
                )

                if val_result.is_valid:
                    logger.info("  Attempt %d: Validation PASSED", attempt)
                    ctx.final_argument = response_text
                    ctx.llm_response = response_text
                    ctx.generation_status = "success"
                    ctx.guardrail_passed = True
                    success = True
                    break
                else:
                    logger.warning("  Attempt %d: Validation FAILED", attempt)
                    for err in val_result.errors:
                        logger.warning("    Error: %s", err)
                        ctx.validation_errors.append(f"Attempt {attempt}: {err}")
                    
                    # Increment retry count
                    ctx.retry_count += 1
                    
                    # Append feedback for the next retry attempt
                    messages.append({"role": "assistant", "content": response_text})
                    messages.append({"role": "user", "content": val_result.feedback})
                    ctx.prompt_messages = list(messages)
            except Exception as exc:
                logger.error("  Attempt %d: LLM generation error: %s", attempt, exc)
                ctx.validation_errors.append(f"Attempt {attempt} Error: {str(exc)}")
                if attempt == max_attempts:
                    ctx.llm_response = str(exc)
                    ctx.generation_status = "failed"
                    ctx.guardrail_passed = False
                ctx.retry_count += 1

        if not success:
            logger.error("All %d validation attempts FAILED", max_attempts)
            ctx.llm_response = final_response_text if final_response_text else "Failed to generate response"
            ctx.generation_status = "failed"
            ctx.guardrail_passed = False
            ctx.final_argument = None

        # Return updated context containing draft_argument, retry_count, validation_errors, guardrail_passed, final_argument
        return ctx

    # ══════════════════════════════════════════════════════════════════
    # Full pipeline convenience method
    # ══════════════════════════════════════════════════════════════════

    def run(
        self,
        session_id: str,
        structured_facts: Dict[str, Any],
    ) -> ProsecutionContext:
        """
        Run the full pipeline: accept + retrieve_laws + generate_argument.
        """
        ctx = self.accept(session_id, structured_facts)
        ctx = self.retrieve_laws(ctx)
        ctx = self.generate_argument(ctx)
        return ctx

    def get_output(self, ctx: ProsecutionContext):
        """
        Step 5: Check guardrails and return structured ProsecutorOutput.
        Always returns a structured response, never crashes the workflow with exceptions.
        """
        from models.prosecutor_models import ProsecutorOutput, ChargeItem

        if ctx.guardrail_passed:
            sections = list(set(ctx.valid_section_numbers))
            charges_list = []

            # Populate ChargeItem list from retrieved law metadata
            if ctx.retrieved_laws and ctx.retrieved_laws.ipc_sections:
                for s in ctx.retrieved_laws.ipc_sections:
                    if s.section in sections:
                        charges_list.append(
                            ChargeItem(
                                section=f"IPC {s.section}",
                                offence=s.offense or "Criminal Liability",
                                factual_basis=s.description[:200] + "..." if s.description else "Satisfied by facts.",
                                punishment_sought=s.punishment
                            )
                        )

            return ProsecutorOutput(
                charges=charges_list,
                full_argument=ctx.final_argument,
                sections_cited=[f"IPC {s}" for s in sections],
                guardrail_passed=True
            )
        else:
            errors_str = "; ".join(ctx.validation_errors)
            failure_text = f"PROSECUTION GENERATION FAILED after {ctx.retry_count} attempts. Reason: {errors_str}"
            return ProsecutorOutput(
                charges=[],
                full_argument=failure_text,
                sections_cited=[],
                guardrail_passed=False
            )

    def run_pipeline(self, session_id: str, structured_facts: Dict[str, Any]):
        """
        Run the complete workflow and return the final structured ProsecutorOutput.
        This is the direct entry point for the orchestrator.
        """
        ctx = self.run(session_id, structured_facts)
        return self.get_output(ctx)


# ══════════════════════════════════════════════════════════════════════════════
# Smoke tests
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    agent = ProsecutorAgent()

    # ── Test cases covering different crime types ─────────────────────

    CASES = {
        "theft": {
            "who": {
                "complainant": "Amit Kumar",
                "accused": ["Rahul Sharma"],
                "victims": ["Amit Kumar"],
            },
            "incident": {
                "summary": "The accused stole a motorcycle from a parking lot.",
                "date": "05/07/2026",
                "time": "14:30",
                "place": "Pune, Maharashtra",
            },
            "property": {
                "vehicles": [{"type": "Motorcycle", "make_model": "Honda Activa"}],
                "estimated_loss": "Rs. 65,000",
            },
            "sections": ["IPC 379"],
        },
        "assault": {
            "who": {
                "complainant": "Priya Desai",
                "accused": ["Suresh Yadav"],
                "victims": ["Priya Desai"],
            },
            "incident": {
                "summary": "The accused physically assaulted the victim causing grievous injuries to her head and arms.",
                "date": "01/07/2026",
                "time": "22:00",
                "place": "Mumbai, Maharashtra",
            },
            "property": {},
            "sections": ["IPC 325", "IPC 326"],
        },
        "fraud": {
            "who": {
                "complainant": "State Bank of India",
                "accused": ["Vikram Mehta", "Anita Gupta"],
                "victims": ["State Bank of India", "12 account holders"],
            },
            "incident": {
                "summary": "The accused used forged documents and impersonation to fraudulently obtain loans worth Rs. 1.2 crore from the bank.",
                "date": "15/03/2026",
                "place": "Delhi",
            },
            "property": {
                "documents": "Forged Aadhaar cards, PAN cards, salary slips",
                "cash": "Rs. 1,20,00,000",
                "estimated_loss": "Rs. 1.2 crore",
            },
            "sections": ["IPC 420", "IPC 467", "IPC 468", "IPC 471"],
        },
        "no_sections": {
            "who": {
                "complainant": "Anonymous",
                "accused": ["Unknown Person"],
                "victims": ["Shopkeeper"],
            },
            "incident": {
                "summary": "Someone threatened the shopkeeper with a knife and demanded money.",
                "place": "Lucknow",
            },
            "property": {},
            "sections": [],
        },
    }

    # ── Run Step 1 + Step 2 + Step 3 + Step 5 for each case ─────────────────────
    for case_name, facts in CASES.items():
        print(f"\n{'='*70}")
        print(f"  RUNNING PIPELINE FOR CASE: {case_name.upper()}")
        print(f"{'='*70}")

        try:
            # Execute full pipeline and get the final validated structured output
            output = agent.run_pipeline(
                session_id=f"test_{case_name}_001",
                structured_facts=facts,
            )

            print(f"\n  [Orchestrator Output] ProsecutorOutput received:")
            print(f"    guardrail_passed  = {output.guardrail_passed}")
            print(f"    sections_cited    = {output.sections_cited}")
            print(f"    number of charges = {len(output.charges)}")
            
            if output.charges:
                print(f"    charges list      = {[c.section for c in output.charges]}")
            
            if output.full_argument:
                print(f"\n  [Final Argument Snippet]:")
                snippet = output.full_argument[:300].replace("\n", "\n    ")
                print(f"    {snippet}...")

            print(f"\n  [PASS] {case_name}")

        except Exception as e:
            print(f"\n  [FAIL] {case_name}: {type(e).__name__}: {e}")

