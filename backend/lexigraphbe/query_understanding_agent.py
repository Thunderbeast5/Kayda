"""
Query Understanding Agent for Stage 1: Query Understanding & Legal Decomposition.
Converts structured CaseContextObject into verified legal sub-queries (LegalQueryObject).
Strictly independent of statutory IPC/BNS section numbers or legal outcome predictions.
Model: gpt-4o-mini (MODEL_STAGE1).
"""

import json
from typing import Any, Dict, List, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE1
from .prompts import STAGE1_QUERY_UNDERSTANDING_SYSTEM_PROMPT, STAGE1_QUERY_UNDERSTANDING_USER_PROMPT_TEMPLATE
from .schemas import CaseContextObject, CaseProfile, LegalQueryObject


# ---------------------------------------------------------------------------
# Disambiguation hints for IPC sections whose headings share surface
# vocabulary but have different legal scope.  Placed on BOTH sides of each
# confused pair so the LLM sees the contrast whichever entry it reads first.
# Keep hints short — they are injected inline beside every occurrence of the
# section in the heading reference and must not bloat the prompt.
# ---------------------------------------------------------------------------
_DISAMBIGUATION_HINTS: Dict[str, Dict[str, str]] = {
    # ── Homicide chain: negligence vs culpable homicide vs murder ──────────
    "299": {
        "use_when": "Death or bodily injury was caused with the knowledge that it is likely to cause death (but not the intention to cause death amounting to murder).",
        "not_when": "Death was caused by a rash or negligent act without any culpable mental state → use 304A instead.",
        "distinguish_from": "300 (murder — requires specific intention or knowledge under Section 300 clauses); 304A (pure negligence/rashness, no culpable homicide).",
    },
    "300": {
        "use_when": "The act causing death satisfies one of the four clauses of Section 300 (intention to cause death, intention to cause bodily injury sufficient to cause death, etc.).",
        "not_when": "Death resulted from negligence or recklessness that does not rise to culpable homicide → use 304/304A instead.",
        "distinguish_from": "299 (culpable homicide — lower threshold); 304A (causing death by negligence — no culpable intent).",
    },
    "304": {
        "use_when": "Death was caused by an act that amounts to culpable homicide NOT amounting to murder (i.e. satisfies Section 299 but not Section 300).",
        "not_when": "Death was caused purely by negligence or rashness without any culpable mental state → use 304A. If Section 300 is satisfied → use 302.",
        "distinguish_from": "302 (murder — Section 300 satisfied); 304A (causing death by negligence — no culpable mental state).",
    },
    "304A": {
        "use_when": "Death was caused by a rash or negligent act that does NOT amount to culpable homicide — e.g. medical negligence, rash driving, industrial accident.",
        "not_when": "The accused had the intention or knowledge required for culpable homicide → use 299/304. If no death occurred → use 336/337/338.",
        "distinguish_from": "304 (culpable homicide not amounting to murder — requires culpable mental state); 269 (negligent act risking COMMUNICABLE DISEASE spread to third parties, not treatment-related death).",
    },
    "269": {
        "use_when": "The accused negligently did an act likely to spread the infection of a disease DANGEROUS TO LIFE — e.g. not observing quarantine, exposing others to a contagious condition.",
        "not_when": "A patient died from negligent medical treatment → use 304A. This section is about communicable disease risk to third parties, not medical negligence causing a patient's death.",
        "distinguish_from": "304A (causing death by negligence — for patient deaths from negligent treatment); 270 (malignant/intentional act spreading disease).",
    },
    # ── Attempt offences ───────────────────────────────────────────────────
    "307": {
        "use_when": "The accused attempted to commit murder — i.e. did an act with intent or knowledge sufficient for murder under Section 300.",
        "not_when": "The attempt was to cause culpable homicide only → use 308.",
        "distinguish_from": "308 (attempt to commit culpable homicide — lower mental state than murder).",
    },
    "308": {
        "use_when": "The accused attempted to commit culpable homicide not amounting to murder.",
        "not_when": "The intent was sufficient for murder → use 307.",
        "distinguish_from": "307 (attempt to murder — higher mental state).",
    },
    # ── Hurt/endangerment chain ────────────────────────────────────────────
    "336": {
        "use_when": "The accused did a rash or negligent act that ENDANGERED the life or personal safety of others — no actual hurt required.",
        "not_when": "Actual hurt resulted → use 337. Actual grievous hurt resulted → use 338. Death resulted → use 304A.",
        "distinguish_from": "337 (hurt caused); 338 (grievous hurt caused); 304A (death caused by negligence).",
    },
    "337": {
        "use_when": "A rash or negligent act caused HURT (not grievous) to another person.",
        "not_when": "Injury is grievous → use 338. No injury, only endangerment → use 336. Death resulted → use 304A.",
        "distinguish_from": "336 (endangerment only, no hurt); 338 (grievous hurt); 304A (death by negligence).",
    },
    "338": {
        "use_when": "A rash or negligent act caused GRIEVOUS HURT to another person.",
        "not_when": "Injury is simple hurt → use 337. No injury → use 336. Death resulted → use 304A.",
        "distinguish_from": "336 (endangerment only); 337 (simple hurt); 304A (death by negligence).",
    },
    # ── Property offences: misappropriation vs breach of trust ─────────────
    "403": {
        "use_when": "The accused dishonestly misappropriated or converted to their own use property that came into their possession — no prior entrustment or dominion required.",
        "not_when": "The property was entrusted to the accused or came into their dominion → use 405/406.",
        "distinguish_from": "405 (criminal breach of trust — requires entrustment or dominion).",
    },
    "405": {
        "use_when": "Property was entrusted to the accused, or came into their dominion, and they dishonestly misappropriated or converted it.",
        "not_when": "There was no entrustment or dominion — property simply came into accused's possession → use 403.",
        "distinguish_from": "403 (dishonest misappropriation — no entrustment element).",
    },
    # ── Cheating chain ─────────────────────────────────────────────────────
    "415": {
        "use_when": "The accused deceived a person and thereby induced them to deliver property, consent to an act, or omit an act they would not otherwise have done — causing wrongful gain/loss.",
        "not_when": "No deception element — use a property offence. For the aggravated form requiring dishonest inducement to deliver property → confirm Section 420 ingredients.",
        "distinguish_from": "420 (aggravated cheating — additionally requires dishonest inducement causing delivery of property or alteration of a valuable security).",
    },
    "420": {
        "use_when": "Cheating AND the deception caused the victim to dishonestly deliver property or alter/destroy a valuable security.",
        "not_when": "Deception present but no delivery of property or alteration of valuable security → use 415 alone.",
        "distinguish_from": "415 (base cheating — does not require delivery of property).",
    },
    # ── Forgery / false document / falsification of accounts ───────────────
    "463": {
        "use_when": "The accused made a false document or false electronic record with intent to cause damage or injury, support a claim, cause a person to part with property, or commit fraud.",
        "not_when": "No intent to cause damage/fraud — document is merely inaccurate. For the punishment provision → cite 465 alongside.",
        "distinguish_from": "464 (definition of 'making a false document' — the actus reus; 463 adds the required intent); 477A (falsification of accounts — limited to books of account/financial records, not all documents).",
    },
    "464": {
        "use_when": "A document or electronic record was made that is false in a material part — e.g. signed without authority, backdated, altered — regardless of document type.",
        "not_when": "The document is not false but merely inaccurate or incomplete.",
        "distinguish_from": "463 (adds fraudulent/dishonest intent to 464's actus reus); 477A (falsification of books of account — narrower scope, financial records only).",
    },
    "465": {
        "use_when": "The punishment provision for forgery under Section 463 — cite alongside 463/464 whenever a false document is alleged.",
        "not_when": "No false document — mere verbal deception → use cheating provisions.",
        "distinguish_from": "468 (forgery specifically FOR THE PURPOSE of cheating — additional purposive element); 477A (falsification of books of account — NOT a general forgery provision).",
    },
    "468": {
        "use_when": "Forgery was committed SPECIFICALLY FOR THE PURPOSE of cheating (i.e. the forged document was the instrument of a cheating offence).",
        "not_when": "Forgery was not for the purpose of cheating — use 465. Cheating occurred but no forged document → use 415/420.",
        "distinguish_from": "465 (general forgery — no purpose requirement); 471 (using a forged document as genuine — distinct from making it).",
    },
    "471": {
        "use_when": "The accused USED a forged document as genuine (presented, submitted, or relied on it) — the making and using may be by different persons.",
        "not_when": "The accused only made the forged document but did not use it → use 463/465.",
        "distinguish_from": "463/465 (making the forged document); 468 (making it for purpose of cheating).",
    },
    "477A": {
        "use_when": "The accused wilfully and with intent to defraud falsified, altered, or destroyed BOOKS OF ACCOUNT or financial/accounting records — ledger, cash book, journal, day book, or any register that is legally required to be maintained.",
        "not_when": "The falsified document is NOT a book of account or legally required financial record — e.g. medical records, clinical notes, property documents, contracts → use 463/464/465 instead.",
        "distinguish_from": "463/464/465 (general forgery / making a false document — covers ALL document types including medical records, property documents, etc.); 477A is NOT a general falsification provision.",
    },
    # ── Evidence concealment: disappearance of evidence vs document destruction
    "201": {
        "use_when": "A person, knowing an offence has been committed, caused the disappearance of evidence OR gave false information to screen the offender — requires the predicate offence to be established.",
        "not_when": "No predicate offence is yet established — Section 201 inherits conditionality from the predicate. If the only act is destroying a document → consider 204 as the base offence.",
        "distinguish_from": "204 (destruction of a document to prevent its production as evidence — does NOT require a predicate offence; any person, any document).",
    },
    "204": {
        "use_when": "Any person secreted, destroyed, or rendered illegible any document or electronic record to prevent its production as evidence — no predicate offence, no official capacity, no special role required.",
        "not_when": "The document was not destroyed to prevent production as evidence — another motive applies.",
        "distinguish_from": "201 (disappearance of evidence — broader screening purpose but requires a predicate offence already committed); 217/218 (public servant specific — require official capacity; 204 does NOT).",
    },
    # ── Abetment ──────────────────────────────────────────────────────────
    "107": {
        "use_when": "The accused instigated another to commit an offence, engaged in conspiracy, or intentionally aided the commission — this is the DEFINITION provision.",
        "not_when": "No instigation, conspiracy, or aid — the accused committed the act themselves.",
        "distinguish_from": "109 (punishment for abetment when the abetted act is committed and no specific punishment exists — cite alongside 107); 120A/120B (criminal conspiracy — two or more persons agreeing to commit an offence).",
    },
    "109": {
        "use_when": "The abetted act WAS committed in consequence of the abetment and no express punishment provision exists — cite alongside Section 107.",
        "not_when": "The abetted act was not committed → use 115/116 instead.",
        "distinguish_from": "107 (defines abetment — always cite 107 first); 115/116 (abetment where abetted act is NOT committed).",
    },
    # ── False evidence ─────────────────────────────────────────────────────
    "191": {
        "use_when": "A person bound by oath or under any express provision of law to state the truth made a false statement knowing it to be false.",
        "not_when": "No oath/legal obligation to state truth — use 177 (false information to public servant) instead. For creating false circumstances rather than making a statement → use 192.",
        "distinguish_from": "192 (fabricating false evidence — creating false circumstances, entries, or marks, not making a false statement).",
    },
    "192": {
        "use_when": "The accused caused any circumstance to exist, made any false entry in a book or record, or made any document containing a false statement — intending it to appear in evidence.",
        "not_when": "The accused made a false verbal statement under oath → use 191.",
        "distinguish_from": "191 (giving false evidence — requires oath/legal obligation; statement-based); 464 (making a false document — broader, not limited to evidence context).",
    },
}


def _build_ipc_heading_reference(statute_db: Optional[Dict] = None) -> str:
    """
    Build a compact IPC heading reference string for injection into the system prompt.

    Pulls headings from StatuteRepository.statute_db when available, otherwise falls back
    to a curated set of the most commonly needed headings so the prompt is never empty.

    Sections listed in _DISAMBIGUATION_HINTS receive inline USE WHEN / NOT WHEN / DISTINGUISH FROM
    notes so the LLM can distinguish commonly confused pairs at the point of selection.
    Only ambiguous sections get hints — the rest remain as plain bullet entries.
    """
    def _annotate(sec_num: str, title: str) -> str:
        """Return the bullet line for one section, with hints if available."""
        hint = _DISAMBIGUATION_HINTS.get(sec_num)
        if not hint:
            return f"  • IPC {sec_num}: {title}"
        parts = [f"  • IPC {sec_num}: {title}"]
        parts.append(f"    [USE WHEN]: {hint['use_when']}")
        parts.append(f"    [NOT WHEN]: {hint['not_when']}")
        if hint.get("distinguish_from"):
            parts.append(f"    [DISTINGUISH FROM]: {hint['distinguish_from']}")
        return "\n".join(parts)

    if statute_db:
        try:
            lines: List[str] = []
            for key, entry in statute_db.items():
                if not key.startswith("IPC_"):
                    continue
                sec_num = key[4:]  # strip "IPC_"
                title = (entry.get("title") or entry.get("heading") or "").strip()
                if title:
                    lines.append(_annotate(sec_num, title))
            if lines:
                lines.sort()
                return "\n".join(lines)
        except Exception:
            pass  # fall through to curated fallback

    # Curated fallback — covers the most common retrieval targets.
    # Sections present in _DISAMBIGUATION_HINTS automatically receive inline guidance.
    _FALLBACK_SECTIONS = [
        ("96-106", "Acts done in private defence (Right of private defence)"),
        ("107",    "Abetment of a thing"),
        ("108",    "Abettor"),
        ("109",    "Punishment of abetment if the act abetted is committed"),
        ("118",    "Concealing design to commit offence punishable with death or imprisonment for life"),
        ("119",    "Public servant concealing design to commit offence"),
        ("120A",   "Definition of criminal conspiracy"),
        ("120B",   "Punishment of criminal conspiracy"),
        ("34",     "Acts done by several persons in furtherance of common intention"),
        ("177",    "Furnishing false information"),
        ("182",    "False information with intent to cause public servant to use lawful power to the injury of another person"),
        ("191",    "Giving false evidence"),
        ("192",    "Fabricating false evidence"),
        ("193",    "Punishment for false evidence"),
        ("196",    "Using evidence known to be false"),
        ("197",    "Issuing or signing false certificate"),
        ("198",    "Using as true a certificate known to be false"),
        ("201",    "Causing disappearance of evidence of offence, or giving false information to screen offender"),
        ("202",    "Intentional omission to give information of offence by person bound to inform"),
        ("203",    "Giving false information respecting an offence committed"),
        ("204",    "Destruction of document to prevent its production as evidence"),
        ("217",    "Public servant disobeying direction of law with intent to save person from punishment"),
        ("218",    "Public servant framing incorrect record or writing with intent to save person from punishment"),
        ("268",    "Public nuisance"),
        ("269",    "Negligent act likely to spread infection of disease dangerous to life"),
        ("270",    "Malignant act likely to spread infection of disease dangerous to life"),
        ("299",    "Culpable homicide"),
        ("300",    "Murder"),
        ("302",    "Punishment for murder"),
        ("304",    "Punishment for culpable homicide not amounting to murder"),
        ("304A",   "Causing death by negligence"),
        ("304B",   "Dowry death"),
        ("306",    "Abetment of suicide"),
        ("307",    "Attempt to murder"),
        ("308",    "Attempt to commit culpable homicide"),
        ("319",    "Hurt"),
        ("320",    "Grievous hurt"),
        ("321",    "Voluntarily causing hurt"),
        ("322",    "Voluntarily causing grievous hurt"),
        ("323",    "Punishment for voluntarily causing hurt"),
        ("324",    "Voluntarily causing hurt by dangerous weapons or means"),
        ("325",    "Punishment for voluntarily causing grievous hurt"),
        ("336",    "Act endangering life or personal safety of others"),
        ("337",    "Causing hurt by act endangering life or personal safety of others"),
        ("338",    "Causing grievous hurt by act endangering life or personal safety of others"),
        ("340",    "Wrongful confinement"),
        ("341",    "Punishment for wrongful restraint"),
        ("342",    "Punishment for wrongful confinement"),
        ("350",    "Criminal force"),
        ("351",    "Assault"),
        ("376",    "Punishment for rape"),
        ("378",    "Theft"),
        ("379",    "Punishment for theft"),
        ("383",    "Extortion"),
        ("384",    "Punishment for extortion"),
        ("390",    "Robbery"),
        ("392",    "Punishment for robbery"),
        ("403",    "Dishonest misappropriation of property"),
        ("405",    "Criminal breach of trust"),
        ("406",    "Punishment for criminal breach of trust"),
        ("415",    "Cheating"),
        ("420",    "Cheating and dishonestly inducing delivery of property"),
        ("425",    "Mischief"),
        ("427",    "Mischief causing damage to the amount of fifty rupees"),
        ("441",    "Criminal trespass"),
        ("447",    "Punishment for criminal trespass"),
        ("463",    "Forgery"),
        ("464",    "Making a false document"),
        ("465",    "Punishment for forgery"),
        ("466",    "Forgery of record of court or of public register"),
        ("467",    "Forgery of valuable security, will, etc."),
        ("468",    "Forgery for purpose of cheating"),
        ("471",    "Using as genuine a forged document"),
        ("477A",   "Falsification of accounts"),
        ("491",    "Breach of contract to attend on and supply wants of helpless person"),
        ("498A",   "Husband or relative of husband of a woman subjecting her to cruelty"),
        ("499",    "Defamation"),
        ("500",    "Punishment for defamation"),
        ("503",    "Criminal intimidation"),
        ("506",    "Punishment for criminal intimidation"),
    ]
    return "\n".join(_annotate(sec, title) for sec, title in _FALLBACK_SECTIONS)


from .subquery_expander import expand_sub_queries


class QueryUnderstandingAgent:
    """
    Query Understanding Agent responsible for legal decomposition of CaseContextObject into
    independent legal concepts and single-issue sub-queries without statute section numbers.
    Passes through Stage 0 legal regime flags unchanged without re-deriving.
    Injects IPC statutory heading reference into system prompt so concept labels are anchored
    to actual heading vocabulary, enabling accurate BM25 retrieval in the prefilter.
    Model: gpt-4o-mini (MODEL_STAGE1).
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        min_confidence_threshold: float = 0.70,
        statute_db: Optional[Dict] = None,
    ):
        self._llm = llm
        self.min_confidence_threshold = min_confidence_threshold
        # Pre-build heading reference once; updated if statute_db provided later.
        self._ipc_heading_reference: str = _build_ipc_heading_reference(statute_db)
        # Build the system prompt with the heading reference injected.
        self._system_prompt: str = STAGE1_QUERY_UNDERSTANDING_SYSTEM_PROMPT.format(
            ipc_heading_reference=self._ipc_heading_reference
        )

    @property
    def llm(self):
        if self._llm is None:
            # Use config's get_llm which now defaults to Groq
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE1)
        return self._llm

    def run(
        self,
        case_context: Union[CaseContextObject, CaseProfile, Dict[str, Any], str],
        correction_feedback: Optional[str] = None,
    ) -> LegalQueryObject:
        """
        Decomposes CaseContextObject into a LegalQueryObject.

        Args:
            case_context: CaseContextObject, CaseProfile, dict, or JSON string from Stage 0.
            correction_feedback: Feedback from QueryVerificationAgent if retrying.

        Returns:
            Validated LegalQueryObject instance.
        """
        # Extract Stage 0 legal regime passthrough fields directly without re-deriving
        stage0_regime = "UNKNOWN"
        stage0_flag = False
        stage0_notes = None

        if isinstance(case_context, CaseContextObject):
            stage0_regime = case_context.case_profile.legal_regime
            stage0_flag = case_context.case_profile.flag_for_confirmation
            stage0_notes = case_context.case_profile.regime_notes
        elif isinstance(case_context, CaseProfile):
            stage0_regime = case_context.legal_regime
            stage0_flag = case_context.flag_for_confirmation
            stage0_notes = case_context.regime_notes
        elif isinstance(case_context, dict):
            profile_dict = case_context.get("case_profile", case_context)
            stage0_regime = profile_dict.get("legal_regime", "UNKNOWN")
            stage0_flag = profile_dict.get("flag_for_confirmation", False)
            stage0_notes = profile_dict.get("regime_notes")
        elif isinstance(case_context, str):
            try:
                parsed_ctx = json.loads(case_context)
                if isinstance(parsed_ctx, dict):
                    profile_dict = parsed_ctx.get("case_profile", parsed_ctx)
                    stage0_regime = profile_dict.get("legal_regime", "UNKNOWN")
                    stage0_flag = profile_dict.get("flag_for_confirmation", False)
                    stage0_notes = profile_dict.get("regime_notes")
            except Exception:
                pass

        # Standardize input to JSON string
        if isinstance(case_context, CaseContextObject):
            case_context_str = case_context.to_downstream_json()
        elif isinstance(case_context, CaseProfile):
            case_context_str = json.dumps(case_context.model_dump(), indent=2)
        elif isinstance(case_context, dict):
            case_context_str = json.dumps(case_context, indent=2)
        elif isinstance(case_context, str):
            case_context_str = case_context
        else:
            raise ValueError(f"Invalid case_context type: {type(case_context)}")

        feedback_section = ""
        if correction_feedback:
            feedback_section = f"\nATTENTION - PREVIOUS QUERY VERIFICATION FEEDBACK FOR CORRECTION:\n{correction_feedback}\n"

        user_prompt = STAGE1_QUERY_UNDERSTANDING_USER_PROMPT_TEMPLATE.format(
            case_context_json=case_context_str,
            correction_feedback_section=feedback_section,
        )

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        extracted_dict = extract_json_from_text(response_text)

        # Validate with LegalQueryObject Pydantic schema
        query_obj = LegalQueryObject.model_validate(extracted_dict)

        query_obj = expand_sub_queries(query_obj)

        # Explicit passthrough of Stage 0 legal regime fields (never re-derived)
        query_obj.legal_regime = stage0_regime
        query_obj.flag_for_confirmation = stage0_flag
        query_obj.regime_notes = stage0_notes

        # Structural safeguards before verification. These checks do not decide legal merits.
        fact_ids = [fact.fact_id for fact in query_obj.factual_allegations]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("Stage 1 produced duplicate factual allegation IDs")
        if query_obj.sub_queries and not query_obj.factual_allegations:
            query_obj.manual_review.append(
                "Stage 1 generated retrieval queries without a factual allegation inventory."
            )
        concept_ids = {item.concept_id for item in query_obj.legal_concepts}
        for sq in query_obj.sub_queries:
            if not sq.concept_id or sq.concept_id not in concept_ids:
                query_obj.manual_review.append(
                    f"Sub-query {sq.id} has no valid concept_id reference."
                )
            if query_obj.factual_allegations and not sq.fact_ids:
                query_obj.manual_review.append(
                    f"Sub-query {sq.id} has no supporting fact_ids."
                )

        # Evaluate confidence cutoffs on legal concepts; confidence is a review signal, not proof.
        for item in query_obj.legal_concepts:
            if item.confidence < self.min_confidence_threshold:
                warning = f"Legal concept '{item.concept}' (confidence: {item.confidence:.2f} < cutoff {self.min_confidence_threshold}) requires manual review."
                if warning not in query_obj.manual_review:
                    query_obj.manual_review.append(warning)

        return query_obj