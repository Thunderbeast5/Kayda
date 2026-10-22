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
    "423": [("Execution of Deed / Instrument purporting to transfer or charge property", True), ("Deed contains false statement relating to consideration or person for whose use/benefit it is intended to operate", True), ("Dishonest or Fraudulent Intent", True)],
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
        
        if p_max and re.search(r"\b(death|life)\b", p_max, re.I):
            return (p_text, 20.0, True)
        
        p_low = (p_max or "").lower()
        matches = re.findall(r"(\d+)\s*(?:years?|yrs?)", p_low)
        if matches:
            max_yrs = max(float(m) for m in matches)
            return (p_text, max_yrs, max_yrs > 7.0)
        month_matches = re.findall(r"(\d+)\s*(?:months?|mths?)", p_low)
        if month_matches:  # e.g. 336 "3 Months or Fine or Both"
            return (p_text, round(max(float(m) for m in month_matches) / 12.0, 2), False)
        if re.search(r"\bfine\b", p_low):  # e.g. 283 "Fine": no imprisonment
            return (p_text, 0.0, False)

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



def _norm_status(status: str) -> str:
    return str(status or "").strip().upper()


def _aggregate_ingredient_status(evaluations, classification: str = "PRIMARY"):
    """
    Deterministic aggregation of per-ingredient statuses (the reasoner's judgements) into the
    section's overall status:
      any mandatory ingredient Missing / Contradicted / Not Satisfied -> Not Attracted (Weak)
      any Unknown (not evaluated)                                       -> Partially Attracted (Weak)
      any Partially Satisfied                                           -> Partially Attracted (Moderate)
      all Satisfied                                                     -> Prima Facie Attracted (Strong)
    A CONDITIONAL section (depends on a fact not yet alleged) is capped at Partially Attracted.
    """
    # Alternatives: ipc.json marks disjunctive ingredients with a trailing "OR" (e.g. 107: instigation; OR
    # conspiracy; OR intentional aid). A run of alternatives is one requirement, met if any member is met.
    rank = {"SATISFIED": 0, "PARTIALLY SATISFIED": 1, "UNKNOWN": 2, "": 2,
            "MISSING": 3, "NOT SATISFIED": 3, "CONTRADICTED": 3}
    statuses, group = [], []
    for e in (evaluations or []):
        group.append(_norm_status(e.status))
        text = re.sub(r"\s*\[per section [^\]]*\]\s*$", "", str(e.ingredient or ""), flags=re.I).rstrip(" ;,.")
        if not re.search(r"(?:^|[\s;,])OR$", text):
            statuses.append(min(group, key=lambda x: rank.get(x, 2)))
            group = []
    if group:
        statuses.append(min(group, key=lambda x: rank.get(x, 2)))
    if not statuses:
        # No ingredients were available to evaluate: nothing supports attraction.
        return "Not Evaluated", "Weak"
    if any(s in ("MISSING", "CONTRADICTED", "NOT SATISFIED") for s in statuses):
        return "Not Attracted", "Weak"
    if any(s in ("UNKNOWN", "") for s in statuses):
        return "Partially Attracted", "Weak"
    if any(s == "PARTIALLY SATISFIED" for s in statuses) or classification == "CONDITIONAL":
        return "Partially Attracted", "Moderate"
    return "Prima Facie Attracted", "Strong"



_RESULT_INGREDIENT_RE = re.compile(
    r"\bcaus\w*\b[^.;]{0,40}\b(hurt|grievous|death|injury|damage|loss|miscarriage)\b", re.IGNORECASE)
CAUSATION_INGREDIENT = ("Causation: the result was caused by the accused's own act or omission "
                        "(not merely followed it, and not by an independent intervening cause)")
_MENTAL_CONDITION_RE = re.compile(r"\b(intention|intent|knowledge)\b", re.IGNORECASE)
_RESIDUAL_RE = re.compile(r"\bnot otherwise (?:punishable|provided)", re.IGNORECASE)


def _is_residual_provision(section: str, statute_db: Dict[str, Any]) -> bool:
    """Residual provisions apply only 'in cases not otherwise punishable / provided for' (e.g. 290)."""
    ings = (statute_db.get(f"IPC_{section}") or {}).get("ingredients") or []
    title = (statute_db.get(f"IPC_{section}") or {}).get("section_title") or ""
    return bool(_RESIDUAL_RE.search(" ".join(map(str, ings)) + " " + title))


_MENTAL_ELEMENT_RE = re.compile(
    r"\b(intent\w*|intend\w*|knowing\w*|knowledge|knows|reason to believe|dishonest\w*|fraudulent\w*|"
    r"wilful\w*|purpose|deliberate\w*|likely to)\b", re.IGNORECASE)


def classify_ingredient_kind(ingredient_text: str) -> str:
    """
    Classifies a statutory ingredient into:
      'factual_circumstance' - extrinsic factual condition (must be specifically alleged)
      'conduct' - overt actus reus action or immediate result
      'legal_characterisation' - legal duty, legal compulsion, or admissibility
      'mental' - mens rea / knowledge / intention / state of mind
    """
    text = str(ingredient_text or "").strip().lower()
    if re.search(r"\b(woman|marriage|husband|relative of husband|within 7 years|seven years|minor|child|below \d+ years|dwelling house|at night|sunset|sunrise)\b", text):
        return "factual_circumstance"
    if re.search(r"\b(insult\w*|assault\w*|destroys?|secretes?|causes? (?:any )?evidence to disappear|gives? false information|causes? death|strikes?|enters?|falsif\w*|takes? property)\b", text):
        return "conduct"
    if re.search(r"\b(lawfully compelled|due course of law|legally bound|as evidence|public servant|valuable security|breach of (?:the )?peace|screen\w* (?:the )?offender|legal punishment)\b", text):
        return "legal_characterisation"
    if re.search(r"\b(intent\w*|intend\w*|knowing\w*|knowledge|knows|reason to believe|dishonest\w*|fraudulent\w*|wilful\w*|purpose|deliberate\w*|likely to|malicious\w*|corrupt\w*|voluntarily)\b", text):
        return "mental"
    return "conduct"


INFERABLE_KINDS = {"mental", "legal_characterisation"}


def _infer_mental_elements(vo) -> List[str]:
    """
    Prima facie standard: at the FIR / bail stage allegations are taken at face value.
    Mental elements and legal characterisations are inferred from alleged overt conduct.
    Factual circumstances (e.g. marriage, woman) must be alleged and are never inferred.
    """
    evals = list(getattr(vo, "ingredient_evaluation", []) or [])
    inferable = [e for e in evals if classify_ingredient_kind(e.ingredient) in INFERABLE_KINDS]
    conduct = [e for e in evals if e not in inferable]
    if not inferable or not conduct:
        return []
    if not all(_norm_status(e.status) in ("SATISFIED", "PARTIALLY SATISFIED") for e in conduct):
        return []
    notes = []
    for e in inferable:
        if _norm_status(e.status) in ("MISSING", "UNKNOWN", "NOT SATISFIED"):
            kind = classify_ingredient_kind(e.ingredient)
            e.status = "Partially Satisfied"
            e.reason = (e.reason or "") + f" [Prima facie: {kind} element not expressly alleged verbatim but inferable from alleged conduct at FIR/bail stage; to be established at trial.]"
            notes.append(f"Section {vo.section_number}: {kind} element '{str(e.ingredient)[:60]}' treated as inferable at the prima facie stage.")
    return notes


def _structure_disputed_reasons(vo, facts: List[Any], important_facts: Any) -> None:
    """
    Rewrites the reason of every "Partially Satisfied" ingredient as Prosecution / Defence / To resolve, from the
    structured facts: the allegation it rests on, the specific defence statement that answers it (an alternative
    cause for causation, compliance or denial for fault), and the evidence that would decide it.
    """
    def g(o, k):
        return o.get(k) if isinstance(o, dict) else getattr(o, k, None)

    stmts = [f for f in facts if str(g(f, "conduct_type") or "").upper() == "STATEMENT"]
    if not stmts:
        return
    acts = [f for f in facts if str(g(f, "conduct_type") or "").upper() in ("ACT", "OMISSION")]
    imp = important_facts if isinstance(important_facts, dict) else (important_facts.model_dump() if hasattr(important_facts, "model_dump") else {})
    evidence = [str(x) for x in (imp.get("documents") or []) + (imp.get("witnesses") or []) if x]

    def quote(f):
        return f"{g(f, 'fact_id')} \"{g(f, 'verbatim_quote') or g(f, 'description') or ''}\""

    for e in getattr(vo, "ingredient_evaluation", []) or []:
        if _norm_status(e.status) != "PARTIALLY SATISFIED" or str(e.reason or "").startswith("Prosecution:"):
            continue
        ing = str(e.ingredient or "").lower()
        if ing.startswith("causation"):
            wanted = ("alternative causal",)
        elif re.search(r"rash|negligen|intent|knowledge", ing):  # fault element: answered by compliance / denial
            wanted = ("compliance", "denial")
        elif "endanger" in ing:
            wanted = ("alternative causal",)
        else:
            wanted = ()
        defence = [f for f in stmts if any(w in str(g(f, "description") or "").lower() for w in wanted)] or stmts
        prosecution = e.matched_fact or (quote(acts[0]) if acts else "the FIR allegation")
        e.reason = (
            f"Prosecution: {prosecution}"
            + (f"; evidence: {', '.join(evidence)}" if evidence else "")
            + f" | Defence: {'; '.join(quote(f) for f in defence)}"
            + f" | To resolve: {', '.join(evidence) if evidence else 'evidence on this element'}"
            + (f" | Assessment: {e.reason}" if e.reason else "")
        )


def _fact_coverage_recheck(vo, facts: List[Any], llm=None) -> List[str]:
    """
    Deterministic fact-coverage re-check (§10.1 Item 3 & §4.4).
    Flags conduct ingredients marked Missing where an alleged ACT fact describes related conduct.
    Sends only the specific missing ingredient and candidate fact for targeted verification.
    """
    evals = list(getattr(vo, "ingredient_evaluation", []) or [])
    notes = []
    for e in evals:
        if classify_ingredient_kind(e.ingredient) == "conduct" and _norm_status(e.status) in ("MISSING", "NOT SATISFIED"):
            ing_text = str(e.ingredient).lower()
            for f in facts:
                c_type = str(getattr(f, "conduct_type", "") if hasattr(f, "conduct_type") else (f.get("conduct_type", "") if isinstance(f, dict) else "")).upper()
                if c_type and c_type not in ("ACT", "OMISSION"):
                    continue
                quote = str(getattr(f, "verbatim_quote", "") if hasattr(f, "verbatim_quote") else (f.get("verbatim_quote", "") if isinstance(f, dict) else "")).strip()
                if not quote:
                    quote = str(getattr(f, "description", "") if hasattr(f, "description") else (f.get("description", "") if isinstance(f, dict) else "")).strip()
                if not quote:
                    continue
                q_lower = quote.lower()
                has_overlap = False
                if any(w in q_lower for w in ("destroy", "record", "tamper", "falsif", "delet", "wipe", "hide", "disclos")) and \
                   any(w in ing_text for w in ("disappear", "evidence", "document", "record", "false information")):
                    has_overlap = True
                elif any(w in q_lower for w in ("assault", "beat", "hit", "strike", "wound", "knife", "weapon")) and \
                     any(w in ing_text for w in ("hurt", "force", "assault", "weapon", "injury")):
                    has_overlap = True

                if has_overlap and llm:
                    try:
                        from langchain_core.messages import HumanMessage
                        from .config import extract_json_from_text
                        msg = HumanMessage(
                            content=f"Does the allegation '{quote}' prima facie satisfy the conduct ingredient '{e.ingredient}' of Section {vo.section_number} ({vo.title})? Return JSON: {{\"status\": \"Satisfied\" or \"Not Satisfied\", \"reason\": \"...\"}}"
                        )
                        resp = llm.invoke([msg])
                        parsed = extract_json_from_text(resp)
                        if str(parsed.get("status", "")).strip().lower() == "satisfied":
                            e.status = "Satisfied"
                            e.matched_fact = quote
                            e.reason = str(parsed.get("reason", "Targeted fact grounding verified."))
                            notes.append(f"Section {vo.section_number}: grounded ingredient '{e.ingredient[:40]}' in fact '{quote[:40]}'.")
                            break
                    except Exception as err:
                        pass
    return notes


def _linked_definition_ingredients(section: str, statute_db) -> List[str]:
    """Ingredients of the definition section(s) linked to a punishment section, tagged with their source."""
    try:
        from .family_retrieval import get_family_retriever
        links = get_family_retriever().punishment_links.get(section, set())
    except Exception:
        return []
    out: List[str] = []
    for d in sorted(links):
        for ing in (statute_db.get(f"IPC_{d}") or {}).get("ingredients") or []:
            item = f"{ing} [per Section {d}]"
            if item not in out:
                out.append(item)
    return out

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
        """Loads complete statutory text database from data/new/ CSV and JSON datasets."""
        ipc_paths = [
            Path("data/new/ipc_sections.csv"),
            Path("../data/new/ipc_sections.csv"),
            Path("c:/MootCourt/data/new/ipc_sections.csv"),
        ]

        # Load IPC DB
        for p in ipc_paths:
            if p.exists():
                try:
                    with open(p, mode="r", encoding="utf-8", errors="ignore") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            sec_num = (row.get("Section") or "").replace("IPC_", "").strip()
                            offense = (row.get("Offense") or "").strip()
                            desc = (row.get("Description") or "").strip()
                            punishment = (row.get("Punishment") or "").strip()
                            if sec_num:
                                self.statute_db[f"IPC_{sec_num}"] = {
                                    "statute": "IPC",
                                    "section_number": sec_num,
                                    "section_title": offense,
                                    "full_text": desc,
                                    "punishment": punishment or desc,
                                    "explanations": "See statutory description.",
                                    "illustrations": "N/A",
                                    "exceptions": "N/A",
                                    "provisos": "N/A",
                                }
                    break
                except Exception:
                    pass

    def retrieve_statutory_context_for_candidates(
        self,
        chapter_obj: ChapterIdentificationObject,
    ) -> List[Dict[str, Any]]:
        """Retrieves full statutory context records for all section candidates shortlisted in Stage 3."""
        statute_prefix = "IPC"

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
                ings = list(record.get("ingredients") or []) or _linked_definition_ingredients(clean_sec, self.statute_db)
                # Compact context: only what ingredient evaluation needs (keeps the prompt small).
                rec_copy = {
                    "statute": record.get("statute", statute_prefix),
                    "section_number": clean_sec,
                    "section_title": record.get("section_title", ""),
                    "statutory_text": str(record.get("full_text") or ""),
                    "ingredients": ings,
                }
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
            raw_ings = list(rec.get("ingredients") or [])
            if not raw_ings:
                # Punishment sections (e.g. 323, 465, 109, 120B) carry no ingredients in ipc.json;
                # use the definition section linked by their "Punishment for/of ..." heading.
                raw_ings = _linked_definition_ingredients(clean_sec, statute_db)
            
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

            if expanded_ings and _RESULT_INGREDIENT_RE.search(" ".join(expanded_ings)) and not any(
                    "caus" in i.lower() and "accused" in i.lower() for i in expanded_ings):
                # A result offence needs the result to be caused by the accused's act, not merely to follow it.
                expanded_ings.append(CAUSATION_INGREDIENT)
            if expanded_ings:
                ings_formatted = "\n".join([f"      * Statutory Ingredient: {ing}" for ing in expanded_ings])
            elif clean_sec in STATUTORY_INGREDIENTS:
                ings_formatted = "\n".join([f"      * Statutory Ingredient: {name}" for name, _ in STATUTORY_INGREDIENTS[clean_sec]])
            else:
                ings_formatted = f"      * Statutory definition elements of Section {clean_sec} {vo.title}"

            condition = next((n[len("CONDITION:"):].strip() for n in (getattr(vo, "verification_notes", None) or [])
                              if str(n).startswith("CONDITION:")), "")
            condition_line = (
                f"    CONDITIONAL - this section was retrieved only on the condition: {condition}. Mark the ingredient "
                f"that needs it 'Satisfied' only if a fact expressly alleges it (a general word such as 'injured' "
                f"alleges hurt, not grievous hurt); otherwise mark it 'Missing'.\n"
                if str(getattr(vo, "classification", "")).upper() == "CONDITIONAL" else ""
            )
            stage3_sections.append(
                f"  - Section {vo.section_number} IPC ({vo.title}):\n"
                f"{condition_line}"
                f"    Statutory Ingredients (evaluate EACH; copy its text verbatim into 'ingredient', including a "
                f"trailing 'OR' that marks alternatives - only one alternative in such a run needs to be met; "
                f"cite the supporting fact in 'matched_fact' or null if none):\n"
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
                # No keyword guessing: an ingredient the reasoner did not evaluate is unknown.
                return "Unknown", "Not evaluated by the Stage 4 reasoner - manual review required.", 0.0

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

        # Preserve Stage 3 classification; CONDITIONAL sections are not established offences,
        # so they are split out of verified_offences instead of being promoted.
        def _norm(s: str) -> str:
            return s.strip().upper().replace("SECTION ", "").replace("IPC_", "").replace("BNS_", "")

        tier_by_sec = {_norm(vo.section_number): (vo.classification or "PRIMARY").upper() for vo in chap_obj.verified_offences}
        condition_by_sec = {
            _norm(vo.section_number): next((str(n)[len("CONDITION:"):].strip() for n in (vo.verification_notes or [])
                                            if str(n).startswith("CONDITION:")), "")
            for vo in chap_obj.verified_offences
        }
        attracted_offences = []
        conditional_offences = []
        rejected_offences = []

        facts_list = list(getattr(query_obj, "factual_allegations", []) or [])
        for vo in statutory_obj.verified_offences:
            vo.classification = tier_by_sec.get(_norm(vo.section_number), "PRIMARY")
            for note in _fact_coverage_recheck(vo, facts_list, llm=self.llm):
                if note not in statutory_obj.manual_review:
                    statutory_obj.manual_review.append(note)
            mental_condition = bool(_MENTAL_CONDITION_RE.search(condition_by_sec.get(_norm(vo.section_number), "")))
            if not mental_condition:
                for note in _infer_mental_elements(vo):
                    if note not in statutory_obj.manual_review:
                        statutory_obj.manual_review.append(note)
            _structure_disputed_reasons(vo, facts_list, getattr(query_obj, "important_facts", None))
            status, strength = _aggregate_ingredient_status(vo.ingredient_evaluation, vo.classification)
            if status != vo.overall_status:
                note = f"Section {vo.section_number}: overall status set to '{status}' from ingredient statuses (LLM said '{vo.overall_status}')."
                if note not in statutory_obj.manual_review:
                    statutory_obj.manual_review.append(note)
            vo.overall_status, vo.overall_prima_facie_strength = status, strength
            if isinstance(vo.irac_reasoning, dict) and status == "Not Attracted":
                gaps = [e.ingredient for e in vo.ingredient_evaluation
                        if _norm_status(e.status) in ("MISSING", "CONTRADICTED", "NOT SATISFIED")]
                vo.irac_reasoning["conclusion"] = (
                    f"Section {vo.section_number} not attracted on current facts - missing: " + "; ".join(gaps or vo.missing_mandatory_facts or ["mandatory element"])
                )

            if status == "Not Evaluated":
                note = f"Section {vo.section_number}: no statutory ingredients available to evaluate; held for manual review."
                if note not in statutory_obj.manual_review:
                    statutory_obj.manual_review.append(note)
                conditional_offences.append(vo)
            elif (vo.classification == "CONDITIONAL" and status in ("Prima Facie Attracted", "Partially Attracted")
                  and not _MENTAL_CONDITION_RE.search(condition_by_sec.get(_norm(vo.section_number), ""))):
                # A condition on intention / knowledge was set because Stage 1 found only rash or negligent conduct;
                # no Stage 4 inference or "disputed" rating can meet it, so such sections never reach this branch.
                # Every ingredient, including the one the condition was about, is met on the alleged facts.
                note = f"Section {vo.section_number}: retrieved as CONDITIONAL; the facts meet the condition, so it is attracted."
                if note not in statutory_obj.manual_review:
                    statutory_obj.manual_review.append(note)
                attracted_offences.append(vo)
            elif vo.classification == "CONDITIONAL":
                conditional_offences.append(vo)
            elif status in ("Prima Facie Attracted", "Partially Attracted"):
                attracted_offences.append(vo)
            else:
                rejected_offences.append(vo)

        # A residual provision ("not otherwise punishable") cannot be attracted alongside a specific provision
        # that already punishes the same conduct; it is held as conditional on that being shown otherwise.
        statute_db_all = StatuteRepository.get_instance().get_statute_db() or {}
        specific = [vo.section_number for vo in attracted_offences if not _is_residual_provision(_norm(vo.section_number), statute_db_all)]
        for vo in list(attracted_offences):
            if specific and _is_residual_provision(_norm(vo.section_number), statute_db_all):
                attracted_offences.remove(vo)
                vo.overall_status = "Conditional (residual provision)"
                vo.missing_mandatory_facts = list(vo.missing_mandatory_facts or []) + [
                    f"Residual provision: applies only if no other provision punishes the conduct; "
                    f"specific provisions already attracted: {', '.join(specific)}"]
                note = f"Section {vo.section_number}: residual provision held CONDITIONAL because {', '.join(specific)} already attracted."
                if note not in statutory_obj.manual_review:
                    statutory_obj.manual_review.append(note)
                conditional_offences.append(vo)

        statutory_obj.attracted_offences = attracted_offences
        statutory_obj.conditional_offences = conditional_offences
        statutory_obj.rejected_offences = rejected_offences
        # Downstream consumers (bail, precedent, etc.) receive only attracted offences
        statutory_obj.verified_offences = attracted_offences

        # Pass only attracted sections forward to Stage 5
        stage4_accepted_secs = [vo.section_number for vo in attracted_offences]
        stage4_dropped = [vo.section_number for vo in rejected_offences]

        # Synchronize backward-compatible verified_sections from verified_offences
        if statutory_obj.verified_offences:
            from .schemas import VerifiedSectionItem
            synced = []
            for vo in statutory_obj.verified_offences:
                # Punishment from the First Schedule metadata, not a fixed "3 years" placeholder.
                p_text, p_years, p_arnesh = parse_punishment_and_severity("", vo.section_number, "IPC")
                synced.append(VerifiedSectionItem(
                    section_number=vo.section_number,
                    section_title=vo.title,
                    punishment_text=p_text,
                    max_imprisonment_years=p_years,
                    arnesh_kumar_threshold_exceeded=p_arnesh,
                    ingredients=vo.ingredients,
                    overall_confidence=vo.overall_confidence,
                ))
            statutory_obj.verified_sections = synced

        for v_sec in statutory_obj.verified_sections:
            if v_sec.overall_confidence < self.min_confidence_threshold:
                note = f"Verified section {v_sec.section_number} ('{v_sec.section_title}') confidence {v_sec.overall_confidence:.2f} < cutoff {self.min_confidence_threshold}."
                if note not in statutory_obj.manual_review:
                    statutory_obj.manual_review.append(note)

        statutory_obj.verified_sections.sort(key=lambda x: x.overall_confidence, reverse=True)

        # Attach pipeline_transition audit
        def _gaps(vo) -> str:
            g = [str(e.ingredient) for e in (vo.ingredient_evaluation or [])
                 if _norm_status(e.status) in ("MISSING", "NOT SATISFIED", "CONTRADICTED", "UNKNOWN")]
            return "; ".join(g) or (vo.overall_status or "")

        statutory_obj.pipeline_transition = {
            "stage": "STAGE_3_TO_STAGE_4",
            "source": "Stage 3 Chapter Identification",
            "stage3_input_sections": stage3_input_sections,
            "stage4_accepted_sections": stage4_accepted_secs,
            "stage4_conditional_sections": [
                {"section_number": vo.section_number, "reason": f"Depends on: {_gaps(vo)}"} for vo in conditional_offences
            ],
            "stage4_rejected_sections": stage4_dropped + [
                {"section_number": vo.section_number, "reason": f"Not attracted - missing: {_gaps(vo)}",
                 "rejection_type": "NOT_ATTRACTED"} for vo in rejected_offences
            ],
            "passing_to_stage5": stage4_accepted_secs,
        }

        return statutory_obj

