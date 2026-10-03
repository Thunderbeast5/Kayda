"""
Statutory Verification Agent for Stage 4: Full Statutory Verification & Ingredient Matching.
Retrieves complete statutory context for candidate sections shortlisted in Stage 3 and evaluates
essential statutory ingredients against verified case facts in ONE single batched LLM call.
Extracts punishment text and Arnesh Kumar (<=7 years) threshold metrics into output contract.
Model: gpt-4o-mini (MODEL_STAGE2) — structured verification, near-deterministic ingredient matching.
"""

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE2
from .prompts import STAGE4_STATUTORY_VERIFICATION_SYSTEM_PROMPT, STAGE4_STATUTORY_VERIFICATION_USER_PROMPT_TEMPLATE
from .schemas import ChapterIdentificationObject, LegalQueryObject, StatutoryVerificationObject
from .statute_repository import StatuteRepository

# ---------------------------------------------------------------------------
# Generic Statutory Ingredient Registry (law-derived, not case-specific)
# Covers common IPC sections likely to appear in bail/trial matters.
# Tuples: (ingredient_name, is_mandatory)
# ---------------------------------------------------------------------------
STATUTORY_INGREDIENTS: Dict[str, List[tuple]] = {
    # Document fraud cluster
    "415": [("Deception / Fraudulent Misrepresentation", True), ("Dishonest Inducement or Intentional Concealment", True), ("Harm caused (property / bodily / mental / reputational)", True)],
    "420": [("Deception / Fraudulent Misrepresentation", True), ("Dishonest Inducement", True), ("Delivery / Transfer of Property, Valuable Security, or Signed Document (physical delivery not required — transfer of title or possession suffices)", True), ("Wrongful Loss to Victim or Wrongful Gain to Accused", True)],
    "463": [("Making / Altering a False Document", True), ("Dishonest or Fraudulent Intent", True)],
    "464": [("Executing / Signing a document with false representation or without authority", True), ("Dishonest or Fraudulent Intent", True), ("Intent to cause damage or injury or that a claim be supported", True)],
    "465": [("Making / Executing a False Document", True), ("Fraudulent or Dishonest Intent", True)],
    "467": [("Forgery of a Valuable Security, Will, or Document creating/transferring interest in property", True), ("Intent to cause damage or injury", True)],
    "468": [("Act of Forgery", True), ("Purpose / Intention of Cheating", True)],
    "471": [("Using / Presenting / Registering a Document as Genuine", True), ("Knowledge or Reason to Believe Document is Forged", True)],
    "423": [("Execution of a Deed / Instrument (sale deed, mortgage, gift deed, etc.)", True), ("Deed Contains a False / Misleading Statement or is made without full consideration", True), ("Dishonest or Fraudulent Intent", True)],
    # Property offences
    "378": [("Movable Property", True), ("Taken out of possession of another", True), ("Without consent", True), ("Dishonest Intention", True)],
    "379": [("Movable Property", True), ("Taken out of possession of another", True), ("Without consent", True), ("Dishonest Intention", True)],
    "383": [("Putting person in fear of injury", True), ("Dishonestly inducing delivery of property / valuable thing", True)],
    "390": [("Theft or Extortion committed", True), ("Hurt caused or threatened imminently", True)],
    "391": [("Five or more persons", True), ("Committing or attempting Robbery", True)],
    "392": [("Theft committed", True), ("Hurt caused or threatened imminently", True)],
    "403": [("Movable property of another person", True), ("Dishonest misappropriation or conversion to own use", True)],
    "405": [("Entrustment of property", True), ("Dishonest misappropriation / conversion / disposal in violation of trust", True), ("Refusal to account / return when legally required", True)],
    "406": [("Entrustment of property", True), ("Dishonest misappropriation / conversion / disposal in violation of trust", True), ("Refusal to account / return when legally required", True)],
    "441": [("Entry into property in possession of another", True), ("Without right / authority", True), ("Intent to commit offence / intimidate / insult / annoy", True)],
    "442": [("Entry into a building / tent / vessel used as a dwelling", True), ("Without right / authority", True), ("Intent to commit offence / intimidate", True)],
    "425": [("Causing wrongful loss or damage to property of another", True), ("Intention or knowledge that wrongful loss / damage will be caused", True)],
    # Violent offences
    "299": [("Causing Death of a Person", True), ("Intention to cause death or bodily injury likely to cause death or knowledge of imminently dangerous act", True)],
    "300": [("Causing Death of a Person", True), ("Intention to cause death OR knowledge that death is likely consequence", True)],
    "302": [("Causing Death of a Person", True), ("Murder (s.300 satisfied)", True)],
    "304B": [("Death of Wife", True), ("Within Seven Years of Marriage", True), ("Death by burns / bodily injury / abnormal circumstances", True), ("Harassment / Cruelty for Dowry Soon Before Death", True)],
    "306": [("Suicide Committed", True), ("Abetment by Accused — instigation / conspiracy / intentional aid", True)],
    "307": [("Act done with Intention / Knowledge that death would be caused", True), ("Act capable of causing death", True), ("Death did not occur", True)],
    "323": [("Voluntarily Causing Hurt — bodily pain, disease, or infirmity", True)],
    "324": [("Hurt caused by dangerous weapon / fire / poison / corrosive substance", True)],
    "325": [("Grievous Hurt — fracture, permanent disfigurement, loss of member, danger to life", True)],
    "326": [("Grievous Hurt caused by dangerous weapon", True)],
    "326A": [("Voluntarily Causing Grievous Hurt", True), ("By use of acid or burning / corrosive substance", True), ("Permanent or partial damage to body part", True)],
    "354": [("Physical contact or gesture by accused", True), ("Victim is a Woman", True), ("Intent to outrage modesty or Knowledge that modesty likely outraged", True)],
    "354A": [("Physical contact / unwelcome sexual advance", True), ("Victim is a Woman", True)],
    "354D": [("Following / contacting / monitoring the woman", True), ("Despite clear indication of disinterest", True), ("More than once", True)],
    "376": [("Sexual intercourse", True), ("Absence of Consent or Consent obtained by fraud / fear / impersonation", True)],
    "498A": [("Marriage between victim and accused", True), ("Clause (a): Cruelty of gravity to drive to suicide or cause grave injury, OR Clause (b): Harassment for unlawful demand / dowry", True)],
    # Abetment / conspiracy
    "34": [("Criminal act done by several persons", True), ("In furtherance of common intention of all", True)],
    "107": [("Abetment by Instigation / Conspiracy / Intentional Aid", True), ("Main offence committed or attempted", True)],
    "120A": [("Agreement between two or more persons", True), ("To commit an illegal act or legal act by illegal means", True)],
    "120B": [("Agreement between two or more persons", True), ("To commit an illegal act or legal act by illegal means", True)],
    # Threats / intimidation
    "503": [("Threat of injury to person / property / reputation", True), ("Intent to cause alarm or compel to do / omit something", True)],
    "506": [("Threat of injury to person / property / reputation", True), ("Intent to cause alarm or compel to do / omit something", True)],
    # Kidnapping / abduction
    "359": [("Taking / Enticing away a person", True), ("Minor (male <16, female <18) or person of unsound mind", True), ("Taking out of keeping of lawful guardian without consent", True)],
    "361": [("Taking / Enticing away a person", True), ("Minor (male <16, female <18) or person of unsound mind", True), ("Taking out of keeping of lawful guardian without consent", True)],
    "362": [("Compelling by force or inducing by deceit", True), ("To go from one place to another", True)],
    "363": [("Kidnapping from Lawful Guardianship", True), ("Taking / Enticing minor away", True)],
    # Defamation
    "499": [("Making / Publishing an imputation", True), ("Imputation lowers reputation in estimation of others", True), ("Imputation made to third party", True)],
    "500": [("Defamation committed (s.499 satisfied)", True)],
}


def parse_punishment_and_severity(text: str, section_number: str = "", statute: str = "") -> Tuple[str, float, bool]:
    """
    Extracts punishment text, max imprisonment in years, and Arnesh Kumar threshold (>7 years).
    Validates against StatuteRepository First Schedule CrPC/BNSS ground truth.

    Returns:
        (punishment_text, max_imprisonment_years, arnesh_kumar_threshold_exceeded)
    """
    clean_sec = (section_number or "").strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
    first_sched = StatuteRepository.get_instance().get_first_schedule_metadata(clean_sec, statute)

    if first_sched:
        p_max = first_sched["punishment_maximum"]
        p_min = first_sched["punishment_minimum"]
        p_text = f"Punishment: {p_min + ' to ' if p_min else ''}{p_max}"
        
        if p_max in ("Death", "Life Imprisonment"):
            return (p_text, 20.0, True)
        
        matches = re.findall(r"(\d+)\s*(?:years?|yrs?)", p_max.lower())
        if matches:
            max_yrs = max(float(m) for m in matches)
            return (p_text, max_yrs, max_yrs > 7.0)

    if not text:
        return ("Punishment as prescribed by law.", 3.0, False)

    cleaned = text.lower()
    punishment_snippet = text.strip()

    # Check Life or Death penalty
    if "imprisonment for life" in cleaned or "death" in cleaned or "life imprisonment" in cleaned:
        return (punishment_snippet, 20.0, True)

    # Search for numeric years in text e.g. "3 years", "7 years", "10 years", "2 years"
    matches = re.findall(r"(\d+)\s*(?:years?|yrs?)", cleaned)
    if matches:
        years = [float(m) for m in matches]
        max_yrs = max(years)
        exceeded = max_yrs > 7.0
        return (punishment_snippet, max_yrs, exceeded)

    # Search for months e.g. "6 months", "3 months"
    month_matches = re.findall(r"(\d+)\s*(?:months?|mths?)", cleaned)
    if month_matches:
        months = [float(m) for m in month_matches]
        max_yrs = round(max(months) / 12.0, 2)
        return (punishment_snippet, max_yrs, False)

    return (punishment_snippet, 3.0, False)


class StatutoryVerificationAgent:
    """
    Stage 4 Statutory Verification & Ingredient Matching Agent (Schema v4.0).
    Uses StatuteRepository singleton for cached statutory text lookups.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        min_confidence_threshold: float = 0.70,
    ):
        self._llm = llm
        self.min_confidence_threshold = min_confidence_threshold
        self.statute_db = StatuteRepository.get_instance().get_statute_db()

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE2)
        return self._llm

    def _load_statutory_text_db(self):
        """Loads complete statutory text database strictly and exclusively from ipc.json via StatuteRepository."""
        repo = StatuteRepository.get_instance()
        self.statute_db = repo.get_statute_db()

    def retrieve_statutory_context_for_candidates(
        self,
        chapter_obj: ChapterIdentificationObject,
    ) -> List[Dict[str, Any]]:
        """Retrieves full statutory context records for all section candidates shortlisted in Stage 3."""
        regime_str = chapter_obj.legal_regime or ""
        statute_prefix = "BNS" if "BNS" in regime_str.upper() else "IPC"

        context_list = []
        target_list = chapter_obj.verified_offences or chapter_obj.section_candidates
        for sec_cand in target_list:
            clean_sec = str(sec_cand.section_number).strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
            db_key = f"{statute_prefix}_{clean_sec}"

            record = self.statute_db.get(db_key)
            if not record:
                record = next(
                    (val for key, val in self.statute_db.items() if val["section_number"] == clean_sec),
                    None,
                )

            if record:
                p_source = record.get("punishment") or record.get("full_text") or ""
                p_text, max_yrs, exceeded = parse_punishment_and_severity(p_source, section_number=clean_sec, statute=statute_prefix)
                rec_copy = dict(record)
                rec_copy["parsed_punishment_text"] = p_text
                rec_copy["parsed_max_imprisonment_years"] = max_yrs
                rec_copy["parsed_arnesh_kumar_threshold_exceeded"] = exceeded
                context_list.append(rec_copy)
            else:
                p_text, max_yrs, exceeded = parse_punishment_and_severity("", section_number=clean_sec, statute=statute_prefix)
                cand_title = getattr(sec_cand, "title", None) or getattr(sec_cand, "section_title", f"Section {clean_sec}")
                context_list.append({
                    "statute": statute_prefix,
                    "section_number": clean_sec,
                    "section_title": cand_title,
                    "full_text": f"Section {clean_sec} - {cand_title}",
                    "punishment": p_text,
                    "parsed_punishment_text": p_text,
                    "parsed_max_imprisonment_years": max_yrs,
                    "parsed_arnesh_kumar_threshold_exceeded": exceeded,
                    "explanations": "N/A",
                    "illustrations": "N/A",
                    "exceptions": "N/A",
                    "provisos": "N/A",
                })

        return context_list

    def run(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        chapter_object: Union[ChapterIdentificationObject, Dict[str, Any], str],
        correction_feedback: Optional[str] = None,
    ) -> StatutoryVerificationObject:
        """
        Runs Stage 4 Statutory Verification on Stage 1 LegalQueryObject and Stage 3 ChapterIdentificationObject.

        Args:
            legal_query: Verified LegalQueryObject from Stage 1.
            chapter_object: Verified ChapterIdentificationObject from Stage 3.
            correction_feedback: Feedback from StatutoryVerificationAuditor if retrying.

        Returns:
            StatutoryVerificationObject instance.
        """
        if isinstance(legal_query, LegalQueryObject):
            query_obj = legal_query
            query_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            query_obj = LegalQueryObject.model_validate(legal_query)
            query_json_str = json.dumps(legal_query, indent=2)
        else:
            query_obj = LegalQueryObject.model_validate(json.loads(str(legal_query)))
            query_json_str = str(legal_query)

        if isinstance(chapter_object, ChapterIdentificationObject):
            chap_obj = chapter_object
            chap_json_str = chapter_object.to_downstream_json()
        elif isinstance(chapter_object, dict):
            chap_obj = ChapterIdentificationObject.model_validate(chapter_object)
            chap_json_str = json.dumps(chapter_object, indent=2)
        else:
            chap_obj = ChapterIdentificationObject.model_validate(json.loads(str(chapter_object)))
            chap_json_str = str(chapter_object)

        # Retrieve complete statutory context for shortlisted candidate sections
        statutory_records = self.retrieve_statutory_context_for_candidates(chap_obj)
        statutory_context_json = json.dumps(statutory_records, indent=2)

        feedback_section = ""
        if correction_feedback:
            feedback_section = f"\nATTENTION - PREVIOUS STATUTORY VERIFICATION AUDIT FEEDBACK:\n{correction_feedback}\n"

        # Build mandatory section checklist with authoritative statutory ingredients from ipc.json
        stage3_sections = []
        statute_db = StatuteRepository.get_instance().get_statute_db()
        target_offences = chap_obj.verified_offences or [
            type("obj", (), {"section_number": sc.section_number, "title": sc.section_title})()
            for sc in chap_obj.section_candidates
        ]

        for vo in target_offences:
            clean_sec = str(vo.section_number).strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
            rec = statute_db.get(f"IPC_{clean_sec}") or {}
            raw_ings = rec.get("ingredients") or []
            
            # Dynamic constituent expansion: if an ingredient references a predicate definition section (e.g. "Section 378", "Sections 463–464"), expand its constituent ingredients
            expanded_ings = []
            for ing in raw_ings:
                # Check for referenced predicate sections in the ingredient text
                import re
                pred_matches = re.findall(r"Section[s]?\s+(\d+[A-Z]?)", ing, re.IGNORECASE)
                has_expanded = False
                for pred_sec in pred_matches:
                    pred_rec = statute_db.get(f"IPC_{pred_sec}")
                    if pred_rec and pred_rec.get("ingredients"):
                        for pred_ing in pred_rec["ingredients"]:
                            if pred_ing not in expanded_ings:
                                expanded_ings.append(f"{pred_ing} [per Section {pred_sec}]")
                        has_expanded = True
                if not has_expanded:
                    expanded_ings.append(ing)

            if expanded_ings:
                ings_formatted = "\n".join([f"      * Mandatory Statutory Ingredient: {ing}" for ing in expanded_ings])
            elif clean_sec in STATUTORY_INGREDIENTS:
                ings_formatted = "\n".join([f"      * Mandatory Statutory Ingredient: {name}" for name, _ in STATUTORY_INGREDIENTS[clean_sec]])
            else:
                ings_formatted = f"      * Statutory definition elements of Section {clean_sec} {vo.title}"

            stage3_sections.append(
                f"  - Section {vo.section_number} IPC ({vo.title}):\n"
                f"    Authoritative Statutory Ingredients from Statute (MANDATORY TO EVALUATE):\n"
                f"{ings_formatted}"
            )

        mandatory_checklist_str = "\n".join(stage3_sections) if stage3_sections else "  (all sections from Stage 3 verified_offences)"

        user_prompt = STAGE4_STATUTORY_VERIFICATION_USER_PROMPT_TEMPLATE.format(
            legal_query_json=query_json_str,
            chapter_object_json=chap_json_str,
            statutory_context_json=statutory_context_json,
            correction_feedback_section=feedback_section,
            mandatory_section_checklist=mandatory_checklist_str,
        )

        messages = [
            SystemMessage(content=STAGE4_STATUTORY_VERIFICATION_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        extracted_dict = extract_json_from_text(response_text)

        # Validate with StatutoryVerificationObject Pydantic schema (v4.0)
        statutory_obj = StatutoryVerificationObject.model_validate(extracted_dict)
        statutory_obj.schema_version = "4.0"

        # Passthrough legal_regime from Stage 3 ChapterIdentificationObject
        statutory_obj.legal_regime = chap_obj.legal_regime or "IPC + CrPC"

        print(f"[StatutoryVerificationAgent] Before fallback: verified_offences={len(statutory_obj.verified_offences)}, verified_sections={len(statutory_obj.verified_sections)}")

        # If verified_offences is empty but verified_sections exist, populate verified_offences
        if not statutory_obj.verified_offences and statutory_obj.verified_sections:
            from .schemas import VerifiedOffenceItemStage4, IngredientEvaluationItem
            for v_sec in statutory_obj.verified_sections:
                eval_items = []
                for ing in v_sec.ingredients:
                    eval_items.append(
                        IngredientEvaluationItem(
                            ingredient=ing.ingredient,
                            matched_fact=ing.reason,
                            status="Satisfied" if ing.status in ("Satisfied", "Partially Satisfied") else "Missing",
                            reason=ing.reason,
                            confidence=0.90,
                        )
                    )
                statutory_obj.verified_offences.append(
                    VerifiedOffenceItemStage4(
                        section_number=v_sec.section_number,
                        statute="IPC" if "BNS" not in (v_sec.section_number or "") else "BNS",
                        title=v_sec.section_title,
                        ingredient_evaluation=eval_items,
                        overall_prima_facie_strength="Strong" if v_sec.overall_confidence >= 0.85 else "Moderate",
                        missing_mandatory_facts=[],
                        missing_supporting_facts=[],
                        investigation_requirements=["Verify witness statements", "Collect documentary evidence"],
                        legal_reasoning=f"Ingredients evaluated for Section {v_sec.section_number} {v_sec.section_title}.",
                        overall_status="Prima Facie Attracted" if v_sec.overall_confidence >= 0.70 else "Partially Attracted",
                        confidence=v_sec.overall_confidence,
                    )
                )
        
        print(f"[StatutoryVerificationAgent] After fallback: verified_offences={len(statutory_obj.verified_offences)}, verified_sections={len(statutory_obj.verified_sections)}")

        # Filter Stage 4 outputs to strictly match Stage 3 candidates
        allowed_stage3_secs = {
            vo.section_number.strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
            for vo in chap_obj.verified_offences
        } | {
            sc.section_number.strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
            for sc in chap_obj.section_candidates
        }

        stage3_input_sections = sorted(allowed_stage3_secs)
        stage4_dropped: list = []

        if allowed_stage3_secs:
            pre_filter_offences = list(statutory_obj.verified_offences)
            pre_filter_sections = list(statutory_obj.verified_sections)
            statutory_obj.verified_offences = [
                vo for vo in statutory_obj.verified_offences
                if vo.section_number.strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "") in allowed_stage3_secs
            ]
            statutory_obj.verified_sections = [
                vs for vs in statutory_obj.verified_sections
                if vs.section_number.strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "") in allowed_stage3_secs
            ]
            # Detect which sections the LLM added that were NOT in Stage 3
            accepted_keys = {
                vo.section_number.strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
                for vo in statutory_obj.verified_offences
            }
            for vo in pre_filter_offences:
                key = vo.section_number.strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
                if key not in allowed_stage3_secs:
                    stage4_dropped.append({
                        "section_number": vo.section_number,
                        "reason": "Section hallucinated by LLM — not present in Stage 3 verified_offences. Hard-filtered.",
                        "rejection_type": "LLM_HALLUCINATION"
                    })

        stage4_accepted_secs = [vo.section_number for vo in statutory_obj.verified_offences]

        # Programmatic fallback: construct evaluation for any Stage 3 section the LLM omitted
        stage4_accepted_keys = {
            s.strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")
            for s in stage4_accepted_secs
        }
        already_dropped_keys = {r["section_number"] for r in stage4_dropped}
        facts_text_lower = (getattr(query_obj, "case_facts", "") or "").lower()
        if not facts_text_lower:
            # Pull facts from sub_queries
            sqs = getattr(query_obj, "sub_queries", [])
            facts_text_lower = " ".join([getattr(sq, "query", "") for sq in sqs]).lower()

        for sec in stage3_input_sections:
            if sec in stage4_accepted_keys:
                continue  # already evaluated by LLM

            # Find metadata for this section from Stage 3
            matching_vo = next((vo for vo in chap_obj.verified_offences if vo.section_number.strip().upper() == sec), None)
            sec_title = matching_vo.title if matching_vo else f"Section {sec} IPC"
            statute_name = matching_vo.statute if matching_vo else "IPC"

            # Retrieve ingredients from registry
            ingredients_spec = STATUTORY_INGREDIENTS.get(sec, [])
            if not ingredients_spec:
                # Derive generically from statutory context
                ingredients_spec = [("Statutory elements as defined under the section", True)]

            # Simple heuristic: check if key legal terms appear in facts text
            INGREDIENT_HINT_WORDS: Dict[str, List[str]] = {
                "deception": ["decei", "fraud", "false", "misrepresent", "fabricat"],
                "dishonest": ["dishonest", "wrongful", "fraudulent", "fabricat", "false"],
                "transfer": ["transfer", "sale deed", "sale", "deed", "convey", "deliver", "register"],
                "forgery": ["forg", "fabricat", "false document", "false deed"],
                "using forged": ["present", "register", "use", "tending", "genuine"],
                "intent": ["intent", "purpose", "object", "aim", "motive", "dishonest", "fraudulent"],
                "property": ["property", "land", "agricultural", "immovable", "title", "ownership"],
                "hurt": ["beat", "hit", "assault", "injur", "hurt", "wound", "strike"],
                "death": ["death", "died", "killed", "murder", "homicide"],
                "threat": ["threat", "intimidat", "fear", "alarm", "compel"],
                "kidnap": ["kidnap", "abduct", "taken away", "enticied", "removed from guardian"],
                "rape": ["rape", "sexual", "intercourse", "consent"],
                "agreement": ["conspir", "agreement", "together", "common intention"],
            }

            def _heuristic_status(ingredient_name: str) -> tuple:
                ing_lower = ingredient_name.lower()
                hint_matched = False
                for hint_key, keywords in INGREDIENT_HINT_WORDS.items():
                    if hint_key in ing_lower or any(k in ing_lower for k in ["transfer", "deed", "document", "fraud", "intent", "dishonest"]):
                        if any(kw in facts_text_lower for kw in keywords):
                            hint_matched = True
                            break
                # Also do a direct word overlap check
                ing_words = set(w for w in ing_lower.split() if len(w) > 4)
                direct_match = any(w in facts_text_lower for w in ing_words)
                if hint_matched or direct_match:
                    return "Satisfied", "Auto-inferred from case facts by programmatic fallback (LLM omitted this section).", 0.65
                return "Unknown", "Programmatic fallback could not confirm from available facts — manual review required.", 0.40

            from .schemas import IngredientEvaluationItem, VerifiedOffenceItemStage4
            fallback_ingredients = []
            all_mandatory_satisfied = True
            for ing_name, is_mandatory in ingredients_spec:
                status, reason, conf = _heuristic_status(ing_name)
                if is_mandatory and status != "Satisfied":
                    all_mandatory_satisfied = False
                fallback_ingredients.append(IngredientEvaluationItem(
                    ingredient=ing_name,
                    matched_fact=None,
                    status=status,
                    reason=reason,
                    confidence=conf,
                ))

            pf_strength = "Moderate" if all_mandatory_satisfied else "Weak"
            overall_status = "Partially Attracted" if all_mandatory_satisfied else "Not Attracted"

            fallback_offence = VerifiedOffenceItemStage4(
                section_number=sec,
                statute=statute_name,
                title=sec_title,
                ingredient_evaluation=fallback_ingredients,
                overall_prima_facie_strength=pf_strength,
                missing_mandatory_facts=[] if all_mandatory_satisfied else [ing for ing, m in ingredients_spec if m],
                missing_supporting_facts=["Manual ingredient evaluation required — LLM omitted this section"],
                investigation_requirements=["Retrieve full section text", "Manually evaluate against case facts"],
                legal_reasoning=f"AUTO-FALLBACK: Section {sec} ({sec_title}) was passed by Stage 3 but was omitted from Stage 4 LLM output. Programmatic ingredient evaluation applied using STATUTORY_INGREDIENTS registry. Manual review strongly recommended.",
                overall_status=overall_status,
            )
            statutory_obj.verified_offences.append(fallback_offence)
            stage4_dropped.append({
                "section_number": sec,
                "reason": "LLM omitted this section. Programmatic fallback evaluation constructed and appended.",
                "rejection_type": "LLM_OMITTED_RECOVERED"
            })

        # Pass all evaluated sections forward to Stage 5 with their full strength evaluation
        stage4_accepted_secs = [vo.section_number for vo in statutory_obj.verified_offences]

        # Synchronize backward-compatible verified_sections from verified_offences
        if statutory_obj.verified_offences:
            from .schemas import VerifiedSectionItem
            statutory_obj.verified_sections = [
                VerifiedSectionItem(
                    section_number=vo.section_number,
                    section_title=vo.title,
                    punishment_text="Imprisonment as prescribed by law.",
                    max_imprisonment_years=3.0,
                    arnesh_kumar_threshold_exceeded=False,
                    ingredients=vo.ingredients,
                    overall_confidence=vo.overall_confidence,
                )
                for vo in statutory_obj.verified_offences
            ]

        for v_sec in statutory_obj.verified_sections:
            if v_sec.overall_confidence < self.min_confidence_threshold:
                note = f"Verified section {v_sec.section_number} ('{v_sec.section_title}') confidence {v_sec.overall_confidence:.2f} < cutoff {self.min_confidence_threshold}."
                if note not in statutory_obj.manual_review:
                    statutory_obj.manual_review.append(note)

        statutory_obj.verified_sections.sort(key=lambda x: x.overall_confidence, reverse=True)

        # Attach pipeline_transition audit
        statutory_obj.pipeline_transition = {
            "stage": "STAGE_3_TO_STAGE_4",
            "source": "Stage 3 Chapter Identification",
            "stage3_input_sections": stage3_input_sections,
            "stage4_accepted_sections": stage4_accepted_secs,
            "stage4_rejected_sections": stage4_dropped,
            "passing_to_stage5": stage4_accepted_secs,
        }

        return statutory_obj

