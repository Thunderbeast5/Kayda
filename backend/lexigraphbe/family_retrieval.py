"""
Family-constrained statutory retrieval (replaces heading-anchored concept labels and the
deterministic sub-query expander).

Division of labour
------------------
* Stage 1 (LLM) only does two constrained things:
    1. extracts factual allegations as VERBATIM quotes from the narrative, and
    2. tags them with offence FAMILIES chosen from a closed list (OFFENCE_FAMILIES), plus a
       short conduct phrase used only to rank sections inside that family.
  It never names sections or section headings.
* This module (Python, 0 LLM calls):
    - validates the Stage 1 output (quotes really occur in the narrative, family codes are in
      the closed list, fact ids exist, ACT facts are covered by some family);
    - ranks IPC sections inside each chosen family against the quoted facts (BM25);
    - runs a family-independent safety-net search on every charge-bearing fact, so an offence
      the LLM overlooked can still surface;
    - links definition sections to their punishment sections using ipc.json's own
      "Punishment for/of ..." headings (e.g. 107 -> 109, 120A -> 120B, 503 -> 506).

Families come from lexigraphbe.offence_taxonomy, which is derived from the IPC's chapter
structure; nothing here is specific to a case.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .classifier_prefilter import (
    CandidateSectionMatch,
    StatuteClassifierPrefilter,
    _QUERY_ONLY_STOP_STEMS,
    _tokenize,
)
from .offence_taxonomy import ipc_categories
from .statute_repository import StatuteRepository

# ---------------------------------------------------------------------------
# Closed list of offence families shown to the Stage 1 LLM.
# Import registry from offence_taxonomy, which has the canonical list with
# describes, use_when, not_for fields. Build backward-compatible dict for validation.
# ---------------------------------------------------------------------------
from .offence_taxonomy import IPC_FAMILY_REGISTRY

# Build validation set of valid family codes from the registry
OFFENCE_FAMILIES: Dict[str, str] = {
    code: entry.get("describes", "") 
    for code, entry in IPC_FAMILY_REGISTRY.items()
}

_TIERS = {"PRIMARY", "SECONDARY", "CONDITIONAL"}
_CHARGE_BEARING = {"ACT", "OMISSION", "RESULT", "CONDITION"}
_GENERIC_PUNISHMENT_SECTIONS = {"2", "3", "72", "511"}


def family_prompt_block() -> str:
    """
    Format IPC_FAMILY_REGISTRY for Stage 1 family proposal prompt.
    Shows: family code, describes (conduct language), use_when (guidance).
    Excludes: not_for fields (definitional chapters discouraged).
    """
    lines = []
    for code, entry in IPC_FAMILY_REGISTRY.items():
        sections = entry.get("sections", "")
        describes = entry.get("describes", "")
        use_when = entry.get("use_when", "")
        
        # Format: CODE (sections): describes. Use when: use_when
        parts = [f"- {code}"]
        if sections:
            parts.append(f" ({sections})")
        parts.append(f": {describes}")
        if use_when:
            parts.append(f" | Use when: {use_when}")
        
        lines.append("".join(parts))
    
    return "\n".join(lines)


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _obj(o: Any, name: str, default: Any = None) -> Any:
    if isinstance(o, dict):
        return o.get(name, default)
    return getattr(o, name, default)


# ---------------------------------------------------------------------------
# Validation of Stage 1 output (deterministic)
# ---------------------------------------------------------------------------
@dataclass
class DecompositionCheck:
    ok: bool
    issues: List[str] = field(default_factory=list)
    ungrounded_fact_ids: List[str] = field(default_factory=list)
    invalid_families: List[str] = field(default_factory=list)
    uncovered_fact_ids: List[str] = field(default_factory=list)


def validate_decomposition(narrative: str, facts: Iterable[Any], families: Iterable[Any]) -> DecompositionCheck:
    facts = list(facts or [])
    families = list(families or [])
    issues: List[str] = []
    norm_narr = _norm_ws(narrative)
    fact_ids = {str(_obj(f, "fact_id", "")) for f in facts}

    ungrounded = []
    if norm_narr:
        for f in facts:
            quote = _norm_ws(_obj(f, "verbatim_quote") or "")
            if not quote or quote not in norm_narr:
                ungrounded.append(str(_obj(f, "fact_id", "?")))
    if ungrounded:
        issues.append(f"Facts without a verbatim quote found in the narrative: {ungrounded}")

    invalid, covered = [], set()
    for fam in families:
        code = str(_obj(fam, "family", "")).strip().upper()
        if code not in OFFENCE_FAMILIES:
            invalid.append(code)
            continue
        refs = [str(x) for x in (_obj(fam, "fact_ids", []) or [])]
        missing = [x for x in refs if x not in fact_ids]
        if not refs or missing:
            issues.append(f"Family {code} cites unknown or no fact ids: {missing or 'none'}")
        covered.update(refs)
    if invalid:
        issues.append(f"Families outside the closed list were rejected: {invalid}")

    uncovered = [str(_obj(f, "fact_id", "")) for f in facts
                 if str(_obj(f, "conduct_type", "")).upper() in {"ACT", "OMISSION"}
                 and str(_obj(f, "fact_id", "")) not in covered]
    if uncovered:
        issues.append(f"Alleged acts not covered by any offence family (safety-net retrieval still runs): {uncovered}")

    return DecompositionCheck(ok=not (ungrounded or invalid), issues=issues,
                              ungrounded_fact_ids=ungrounded, invalid_families=invalid,
                              uncovered_fact_ids=uncovered)


# ---------------------------------------------------------------------------
# Evidence-backed offence-family gate
# ---------------------------------------------------------------------------
# Each entry maps a family code to a list of trigger-rule dicts.
# A family is SUPPORTED if ANY of its rules match (OR logic across rules;
# AND logic within a rule when multiple "keywords" are supplied).
# Keyword matching is case-insensitive, whole-word aware.
#
# trigger_rule keys:
#   keywords   – all must appear in the combined verbatim quotes of the family's
#                cited facts (AND within a rule; OR across multiple rules).
#   description – human-readable explanation used in the "reason" field.
#
# Families that are naturally derivable from any factual allegation (e.g.
# ATTEMPT, ABETMENT, CONSPIRACY, COMMON_INTENTION) and families whose trigger
# is already enforced structurally (e.g. two actors for COMMON_INTENTION) are
# given a single pass-through rule so they are never incorrectly blocked.
# ---------------------------------------------------------------------------
FAMILY_TRIGGER_RULES: Dict[str, List[Dict[str, Any]]] = {
    # ── Offences against the body ──────────────────────────────────────────
    "HOMICIDE": [
        {"keywords": ["death"], "description": "allegation of death"},
        {"keywords": ["died"], "description": "allegation that a person died"},
        {"keywords": ["kill"], "description": "allegation of killing"},
        {"keywords": ["murder"], "description": "allegation of murder"},
        {"keywords": ["dead"], "description": "allegation that a person is dead"},
        {"keywords": ["cause death"], "description": "allegation of causing death"},
    ],
    "HURT": [
        {"keywords": ["hurt"], "description": "allegation of hurt"},
        {"keywords": ["injur"], "description": "allegation of injury"},
        {"keywords": ["wound"], "description": "allegation of wounding"},
        {"keywords": ["beat"], "description": "allegation of beating"},
        {"keywords": ["struck"], "description": "allegation of striking"},
        {"keywords": ["pain"], "description": "allegation of causing pain"},
        {"keywords": ["fracture"], "description": "allegation of fracture"},
        {"keywords": ["bleed"], "description": "allegation of bleeding"},
        {"keywords": ["hit"], "description": "allegation of hitting"},
    ],
    "RESTRAINT_ASSAULT": [
        {"keywords": ["restrain"], "description": "allegation of physical restraint"},
        {"keywords": ["confin"], "description": "allegation of wrongful confinement"},
        {"keywords": ["assault"], "description": "allegation of assault"},
        {"keywords": ["criminal force"], "description": "allegation of criminal force"},
        {"keywords": ["outraging modesty"], "description": "allegation of outraging modesty"},
        {"keywords": ["grabbed"], "description": "allegation of grabbing"},
        {"keywords": ["detain"], "description": "allegation of wrongful detention"},
        {"keywords": ["held"], "description": "allegation of physical detention"},
        {"keywords": ["push"], "description": "allegation of pushing"},
    ],
    "SEXUAL_OFFENCE": [
        # Rape / sexual assault
        {"keywords": ["rape"], "description": "allegation of rape"},
        {"keywords": ["sexual"], "description": "allegation of a sexual act or sexually coloured conduct"},
        {"keywords": ["molest"], "description": "allegation of molestation"},
        {"keywords": ["intercourse"], "description": "allegation of sexual intercourse"},
        {"keywords": ["penetrat"], "description": "allegation of penetrative assault"},
        # Harassment / outraging modesty (s. 354, 354A, 509)
        {"keywords": ["sexual harass"], "description": "allegation of sexual harassment"},
        {"keywords": ["inappropriate message"], "description": "allegation of inappropriate messages or communication"},
        {"keywords": ["inappropriate remark"], "description": "allegation of inappropriate remarks"},
        {"keywords": ["inappropriate", "contact"], "description": "allegation of inappropriate contact"},
        {"keywords": ["inappropriate", "message"], "description": "allegation of inappropriate messaging"},
        {"keywords": ["unwelcome", "message"], "description": "allegation of unwelcome messages"},
        {"keywords": ["unwelcome", "contact"], "description": "allegation of unwelcome contact"},
        {"keywords": ["unwelcome", "advance"], "description": "allegation of unwelcome advances"},
        {"keywords": ["modesty"], "description": "allegation relating to modesty of a woman"},
        {"keywords": ["obscene"], "description": "allegation of obscene communication or acts"},
        {"keywords": ["vulgar"], "description": "allegation of vulgar communication or gestures"},
        {"keywords": ["lewd"], "description": "allegation of lewd behavior"},
        {"keywords": ["indecent"], "description": "allegation of indecent communication or acts"},
        {"keywords": ["gesture", "woman"], "description": "allegation of offensive gesture to a woman"},
        # Stalking / electronic contact (s. 354D)
        {"keywords": ["stalk"], "description": "allegation of stalking"},
        {"keywords": ["repeatedly contact"], "description": "allegation of repeatedly contacting a person"},
        {"keywords": ["repeatedly", "contact"], "description": "allegation of repeated contact"},
        {"keywords": ["contact", "social media"], "description": "allegation of contact through social media"},
        {"keywords": ["contact", "personal relationship"], "description": "allegation of attempting contact to foster personal relationship"},
        {"keywords": ["contact", "personal interaction"], "description": "allegation of contact to foster personal interaction"},
        {"keywords": ["follow", "woman"], "description": "allegation of following a woman"},
        {"keywords": ["monitor", "internet"], "description": "allegation of monitoring internet or electronic communication"},
        {"keywords": ["monitor", "social media"], "description": "allegation of monitoring social media"},
        {"keywords": ["electronic communication", "woman"], "description": "allegation of monitoring electronic communication of a woman"},
        # Voyeurism (s. 354C)
        {"keywords": ["voyeur"], "description": "allegation of voyeurism"},
        {"keywords": ["private act"], "description": "allegation of capturing or viewing private acts"},
        {"keywords": ["photograph", "private"], "description": "allegation of capturing private photographs"},
        {"keywords": ["filming", "private"], "description": "allegation of recording or filming private acts"},
    ],
    "KIDNAPPING_TRAFFICKING": [
        {"keywords": ["kidnap"], "description": "allegation of kidnapping"},
        {"keywords": ["abduct"], "description": "allegation of abduction"},
        {"keywords": ["trafficking"], "description": "allegation of trafficking"},
        {"keywords": ["taken away"], "description": "allegation of taking a person away"},
        {"keywords": ["lured"], "description": "allegation of luring a person"},
        {"keywords": ["enticed"], "description": "allegation of enticing a person"},
        {"keywords": ["induced"], "description": "allegation of inducing a person to go"},
        {"keywords": ["took away"], "description": "allegation of taking a person away"},
        {"keywords": ["taken from"], "description": "allegation of taking from lawful custody"},
    ],
    "MISCARRIAGE_CHILD": [
        {"keywords": ["miscarriage"], "description": "allegation of causing miscarriage"},
        {"keywords": ["unborn"], "description": "allegation of injury to unborn child"},
        {"keywords": ["foetus"], "description": "allegation relating to a foetus"},
        {"keywords": ["fetus"], "description": "allegation relating to a fetus"},
        {"keywords": ["abandon"], "description": "allegation of child abandonment"},
        {"keywords": ["infant"], "description": "allegation relating to an infant"},
    ],
    # ── Property offences ──────────────────────────────────────────────────
    "THEFT": [
        {"keywords": ["theft"], "description": "allegation of theft"},
        {"keywords": ["stolen"], "description": "allegation of stolen property"},
        {"keywords": ["stole"], "description": "allegation of stealing"},
        {"keywords": ["dishonestly took"], "description": "allegation of dishonest taking"},
        {"keywords": ["missing property"], "description": "allegation of missing property"},
    ],
    "EXTORTION": [
        {"keywords": ["extort"], "description": "allegation of extortion"},
        {"keywords": ["coerce"], "description": "allegation of coercion to deliver property"},
    ],
    "ROBBERY_DACOITY": [
        {"keywords": ["robbery"], "description": "allegation of robbery"},
        {"keywords": ["dacoity"], "description": "allegation of dacoity"},
        {"keywords": ["rob"], "description": "allegation of robbing"},
        {"keywords": ["loot"], "description": "allegation of looting"},
    ],
    "MISAPPROPRIATION_BREACH_OF_TRUST": [
        {"keywords": ["misappropriat"], "description": "allegation of misappropriation"},
        {"keywords": ["breach of trust"], "description": "allegation of criminal breach of trust"},
        {"keywords": ["embezzl"], "description": "allegation of embezzlement"},
        {"keywords": ["entrust"], "description": "allegation of breach of an entrusted relationship"},
    ],
    "STOLEN_PROPERTY": [
        {"keywords": ["stolen property"], "description": "allegation of receiving stolen property"},
        {"keywords": ["receiving stolen"], "description": "allegation of receiving stolen goods"},
        {"keywords": ["dishonestly receiv"], "description": "allegation of dishonestly receiving property"},
    ],
    "CHEATING": [
        {"keywords": ["cheat"], "description": "allegation of cheating"},
        {"keywords": ["deceiv"], "description": "allegation of deception"},
        {"keywords": ["fraud"], "description": "allegation of fraud"},
        {"keywords": ["false representation"], "description": "allegation of false representation"},
        {"keywords": ["misrepresent"], "description": "allegation of misrepresentation"},
        {"keywords": ["induced to deliver"], "description": "allegation of inducing delivery of property"},
    ],
    "FRAUDULENT_TRANSFER": [
        {"keywords": ["fraudulent transfer"], "description": "allegation of fraudulent transfer"},
        {"keywords": ["fraudulent deed"], "description": "allegation of fraudulent deed"},
        {"keywords": ["defeat creditor"], "description": "allegation of defeating creditors"},
    ],
    "MISCHIEF": [
        {"keywords": ["damage"], "description": "allegation of damaging property"},
        {"keywords": ["destroy"], "description": "allegation of destroying property"},
        {"keywords": ["demolish"], "description": "allegation of demolishing property"},
        {"keywords": ["mischief"], "description": "allegation of mischief"},
    ],
    "TRESPASS": [
        {"keywords": ["trespass"], "description": "allegation of trespass"},
        {"keywords": ["broke in"], "description": "allegation of breaking in"},
        {"keywords": ["unlawfully enter"], "description": "allegation of unlawful entry"},
    ],
    # ── Documentation & evidence ───────────────────────────────────────────
    "FORGERY": [
        {"keywords": ["forgery"], "description": "allegation of forgery"},
        {"keywords": ["forged"], "description": "allegation of a forged document"},
        {"keywords": ["false document"], "description": "allegation of a false document"},
        {"keywords": ["fake document"], "description": "allegation of a fake document"},
        {"keywords": ["fabricated document"], "description": "allegation of a fabricated document"},
        {"keywords": ["falsification"], "description": "allegation of falsification of records"},
    ],
    "TRADEMARK_CURRENCY": [
        {"keywords": ["counterfeit currency"], "description": "allegation of counterfeit currency"},
        {"keywords": ["fake currency"], "description": "allegation of fake currency"},
        {"keywords": ["fake note"], "description": "allegation of fake currency notes"},
        {"keywords": ["false trademark"], "description": "allegation of a false trade mark"},
    ],
    "FALSE_EVIDENCE_JUSTICE": [
        {"keywords": ["false evidence"], "description": "allegation of giving false evidence"},
        {"keywords": ["fabricat"], "description": "allegation of fabricating evidence"},
        {"keywords": ["destroy evidence"], "description": "allegation of destroying evidence"},
        {"keywords": ["screen offender"], "description": "allegation of screening an offender"},
        {"keywords": ["perjury"], "description": "allegation of perjury"},
    ],
    # ── Persons, authority & public order ──────────────────────────────────
    "CONTEMPT_OF_AUTHORITY": [
        {"keywords": ["disobey"], "description": "allegation of disobeying a public servant"},
        {"keywords": ["obstruct"], "description": "allegation of obstructing a public servant"},
        {"keywords": ["absconding"], "description": "allegation of absconding"},
        {"keywords": ["disobeyed summons"], "description": "allegation of disobeying a summons"},
    ],
    "CORRUPTION": [
        {"keywords": ["brib"], "description": "allegation of bribery"},
        {"keywords": ["corrupt"], "description": "allegation of corruption"},
        {"keywords": ["gratif"], "description": "allegation of illegal gratification"},
        {"keywords": ["election offence"], "description": "allegation of an election offence"},
    ],
    "PUBLIC_ORDER": [
        {"keywords": ["riot"], "description": "allegation of rioting"},
        {"keywords": ["unlawful assembly"], "description": "allegation of unlawful assembly"},
        {"keywords": ["affray"], "description": "allegation of affray"},
        {"keywords": ["communal"], "description": "allegation of communal offence"},
    ],
    "PUBLIC_HEALTH_SAFETY_NUISANCE": [
        {"keywords": ["disease"], "description": "allegation of spreading disease"},
        {"keywords": ["infection"], "description": "allegation of spreading infection"},
        {"keywords": ["adulterat"], "description": "allegation of adulteration"},
        {"keywords": ["rash driving"], "description": "allegation of rash driving"},
        {"keywords": ["nuisance"], "description": "allegation of public nuisance"},
        {"keywords": ["hazardous"], "description": "allegation of creating a hazard"},
    ],
    "RELIGION": [
        {"keywords": ["religion"], "description": "allegation of a religion-related offence"},
        {"keywords": ["place of worship"], "description": "allegation of offence against a place of worship"},
        {"keywords": ["religious feeling"], "description": "allegation of outraging religious feelings"},
    ],
    "MARRIAGE_CRUELTY": [
        {"keywords": ["cruelty"], "description": "allegation of cruelty"},
        {"keywords": ["dowry"], "description": "allegation of dowry harassment or demand"},
        {"keywords": ["harass"], "description": "allegation of harassment"},
        {"keywords": ["domestic violence"], "description": "allegation of domestic violence"},
        {"keywords": ["498a"], "description": "reference to Section 498A"},
    ],
    "MARRIAGE_RELATED": [
        {"keywords": ["bigamy"], "description": "allegation of bigamy"},
        {"keywords": ["second marriage"], "description": "allegation of a second marriage"},
        {"keywords": ["deceitful marriage"], "description": "allegation of deceitful marriage"},
        {"keywords": ["adultery"], "description": "allegation of adultery"},
    ],
    "DEFAMATION": [
        {"keywords": ["defamation"], "description": "allegation of defamation"},
        {"keywords": ["reputation"], "description": "allegation of harming reputation"},
        {"keywords": ["imputation"], "description": "allegation of defamatory imputation"},
        {"keywords": ["libel"], "description": "allegation of libel"},
        {"keywords": ["slander"], "description": "allegation of slander"},
    ],
    "INTIMIDATION_INSULT": [
        {"keywords": ["intimidat"], "description": "allegation of criminal intimidation"},
        {"keywords": ["threat"], "description": "allegation of threatening conduct"},
        {"keywords": ["criminal intimidation"], "description": "allegation of criminal intimidation"},
        {"keywords": ["insult"], "description": "allegation of intentional insult"},
        {"keywords": ["inappropriate message"], "description": "allegation of inappropriate or offensive messages"},
        {"keywords": ["inappropriate", "message"], "description": "allegation of inappropriate messaging"},
        {"keywords": ["offensive message"], "description": "allegation of offensive messages"},
        {"keywords": ["modesty"], "description": "allegation of insulting modesty of a woman"},
        {"keywords": ["privacy"], "description": "allegation of intruding upon privacy"},
        {"keywords": ["gesture"], "description": "allegation of offensive word, gesture or act"},
        {"keywords": ["abusive"], "description": "allegation of abusive words or communication"},
        {"keywords": ["harass"], "description": "allegation of harassment through communication"},
    ],
    "OFFENCE_AGAINST_STATE": [
        {"keywords": ["sedition"], "description": "allegation of sedition"},
        {"keywords": ["waging war"], "description": "allegation of waging war against the state"},
        {"keywords": ["treason"], "description": "allegation of treason"},
    ],
    "COUNTERFEIT_COIN_STAMPS": [
        {"keywords": ["counterfeit coin"], "description": "allegation of counterfeiting coins"},
        {"keywords": ["government stamp"], "description": "allegation of counterfeiting government stamps"},
        {"keywords": ["counterfeit stamp"], "description": "allegation of counterfeiting stamps"},
    ],
    # ── Structural / derivative families (always pass-through if fact_ids exist) ──
    "ABETMENT": [
        {"keywords": [], "description": "abetment is structurally derived from the primary offence facts"},
    ],
    "CONSPIRACY": [
        {"keywords": [], "description": "conspiracy is structurally derived from the primary offence facts"},
    ],
    "COMMON_INTENTION": [
        {"keywords": [], "description": "common intention is structurally derived from joint-actor facts"},
    ],
    "ATTEMPT": [
        {"keywords": [], "description": "attempt is structurally derived from the primary offence facts"},
    ],
}



def _kw_present(keyword: str, combined_text: str) -> bool:
    """Case-insensitive substring presence check (no full-word boundary needed for root forms)."""
    return keyword.lower() in combined_text


def _family_trigger_satisfied(family_code: str, text: str) -> bool:
    """Returns True if text satisfies at least one factual trigger rule for family_code."""
    code = str(family_code or "").strip().upper()
    rules = FAMILY_TRIGGER_RULES.get(code)
    if rules is None:
        return True
    if all(not r.get("keywords") for r in rules):
        return True
    low_text = str(text or "").lower()
    for rule in rules:
        kws = rule.get("keywords", [])
        if all(_kw_present(kw, low_text) for kw in kws):
            return True
    return False


@dataclass
class FamilyGateResult:
    supported: List[Any] = field(default_factory=list)    # status=SUPPORTED (all key elements evidenced)
    contingent: List[Any] = field(default_factory=list)   # status=CONTINGENT (plausible, carries unresolved_elements)
    unsupported: List[Any] = field(default_factory=list)  # status=UNSUPPORTED (contradicted / unrelated, blocked)
    gate_notes: List[str] = field(default_factory=list)


def _set_gate(fam: Any, *, satisfied: bool, status: str, reason: str, unresolved: Optional[List[str]] = None) -> None:
    """Mutates the family object (Pydantic model or dict) with gate verdict fields."""
    if hasattr(fam, "trigger_satisfied"):
        fam.trigger_satisfied = satisfied
        fam.status = status
        fam.reason = reason
        if unresolved and hasattr(fam, "unresolved_elements"):
            existing = set(getattr(fam, "unresolved_elements", []) or [])
            fam.unresolved_elements = list(existing | set(unresolved))
        if status == "CONTINGENT" and hasattr(fam, "tier"):
            fam.tier = "CONDITIONAL"
    elif isinstance(fam, dict):
        fam["trigger_satisfied"] = satisfied
        fam["status"] = status
        fam["reason"] = reason
        if unresolved:
            existing = set(fam.get("unresolved_elements") or [])
            fam["unresolved_elements"] = list(existing | set(unresolved))
        if status == "CONTINGENT":
            fam["tier"] = "CONDITIONAL"


def _run_element_gate_llm(llm: Any, facts: List[Any], families: List[Any], narrative: str) -> Dict[str, Dict[str, Any]]:
    """Calls LLM with STAGE1_ELEMENT_GATE_SYSTEM_PROMPT to evaluate proposed families against statutory elements."""
    from .prompts import STAGE1_ELEMENT_GATE_SYSTEM_PROMPT
    from .config import extract_json_from_text
    from langchain_core.messages import SystemMessage, HumanMessage

    facts_text = "\n".join(
        f"  - [{_obj(f, 'fact_id', '')}]: \"{_obj(f, 'verbatim_quote', '') or _obj(f, 'description', '')}\""
        for f in facts
    )
    fam_text = "\n".join(
        f"  - Family: {str(_obj(fam, 'family', '')).upper()} (cited facts: {', '.join(map(str, _obj(fam, 'fact_ids', []) or []))}; phrase: \"{_obj(fam, 'conduct_phrase', '')}\")"
        for fam in families
    )
    user_msg = f"NARRATIVE:\n{narrative}\n\nFACTUAL ALLEGATIONS:\n{facts_text}\n\nPROPOSED OFFENCE FAMILIES:\n{fam_text}\n\nEvaluate each proposed family against its statutory elements."
    resp = llm.invoke([
        SystemMessage(content=STAGE1_ELEMENT_GATE_SYSTEM_PROMPT),
        HumanMessage(content=user_msg)
    ])
    raw = resp.content if hasattr(resp, "content") else str(resp)
    parsed = extract_json_from_text(raw)
    evals = parsed.get("evaluations") or [] if isinstance(parsed, dict) else []
    out = {}
    for ev in evals:
        if isinstance(ev, dict) and "family" in ev:
            out[str(ev["family"]).strip().upper()] = ev
    return out


def gate_families(
    facts: Iterable[Any],
    families: Iterable[Any],
    narrative: str = "",
    llm: Optional[Any] = None,
) -> FamilyGateResult:
    """
    Evidence-backed Statutory Element Entailment Gate.

    1. Programmatic Substring Grounding:
       Verifies that each cited verbatim_quote is a valid substring of the case narrative,
       and populates start_char and end_char.

    2. Three-State Element Entailment Check:
       Evaluates whether the cited facts plausibly satisfy any limb of the family's sections:
       - SUPPORTED: all key elements are evidenced.
       - CONTINGENT: the family is plausible but some elements are unknown. Pass it through carrying unresolved_elements.
       - UNSUPPORTED: block it only when the facts contradict it or are unrelated.
    """
    facts = list(facts or [])
    families = list(families or [])
    result = FamilyGateResult()

    # 1. Programmatic verbatim substring check and character span population
    if narrative:
        for f in facts:
            quote = str(_obj(f, "verbatim_quote") or "").strip()
            if quote:
                idx = narrative.find(quote)
                if idx == -1:
                    idx = narrative.lower().find(quote.lower())
                if idx != -1:
                    if hasattr(f, "start_char"):
                        f.start_char = idx
                        f.end_char = idx + len(quote)
                    elif isinstance(f, dict):
                        f["start_char"] = idx
                        f["end_char"] = idx + len(quote)

    if not families:
        return result

    # 2. Element entailment check via LLM if available
    evaluations: Dict[str, Dict[str, Any]] = {}
    if llm is not None:
        try:
            evaluations = _run_element_gate_llm(llm, facts, families, narrative)
        except Exception as e:
            result.gate_notes.append(f"[gate] LLM element gate error: {e}, using deterministic evaluation.")
            evaluations = {}

    fact_text: Dict[str, str] = {}
    for f in facts:
        fid = str(_obj(f, "fact_id", ""))
        text = str(_obj(f, "verbatim_quote") or _obj(f, "description") or "").lower()
        fact_text[fid] = text

    for fam in families:
        code = str(_obj(fam, "family", "")).strip().upper()
        refs = [str(x) for x in (_obj(fam, "fact_ids", []) or [])]
        combined = " ".join(fact_text.get(r, "") for r in refs).strip().lower()
        phrase = str(_obj(fam, "conduct_phrase", "") or "").lower()
        full_context = (combined + " " + phrase + " " + (narrative or "").lower()).strip()

        # Check if LLM returned a valid evaluation
        if code in evaluations:
            ev = evaluations[code]
            status = str(ev.get("status", "SUPPORTED")).upper()
            reason = str(ev.get("reason", ""))
            unresolved = list(ev.get("unresolved_elements") or [])
            if status == "SUPPORTED":
                _set_gate(fam, satisfied=True, status="SUPPORTED", reason=reason)
                result.supported.append(fam)
            elif status == "CONTINGENT":
                _set_gate(fam, satisfied=True, status="CONTINGENT", reason=reason, unresolved=unresolved)
                result.contingent.append(fam)
            else:
                _set_gate(fam, satisfied=False, status="UNSUPPORTED", reason=reason)
                result.unsupported.append(fam)
                result.gate_notes.append(f"[gate] {code}: UNSUPPORTED — {reason}")
            continue

        # Deterministic fallback element entailment check:
        # Derivative/structural families pass if facts cited
        if code in ("ABETMENT", "CONSPIRACY", "COMMON_INTENTION", "ATTEMPT"):
            if refs:
                _set_gate(fam, satisfied=True, status="SUPPORTED", reason=f"Structural family {code} grounded in primary facts.")
                result.supported.append(fam)
            else:
                _set_gate(fam, satisfied=False, status="UNSUPPORTED", reason=f"Derivative family {code} cites no facts.")
                result.unsupported.append(fam)
            continue

        # Offence-specific statutory limb evaluations:
        if code == "KIDNAPPING_TRAFFICKING":
            if any(k in full_context for k in ["kidnap", "abduct", "traffick", "taken away", "took away", "lured", "enticed", "induced to go", "taken from"]):
                _set_gate(fam, satisfied=True, status="SUPPORTED", reason="Allegation of taking, enticing or inducing minor.")
                result.supported.append(fam)
            else:
                reason = "No allegation that the girl was induced to go somewhere, enticed, or taken away from lawful custody."
                _set_gate(fam, satisfied=False, status="UNSUPPORTED", reason=reason)
                result.unsupported.append(fam)
                result.gate_notes.append(f"[gate] {code}: UNSUPPORTED — {reason}")
            continue

        if code in ("RESTRAINT_ASSAULT", "WRONGFUL_RESTRAINT_CONFINEMENT", "CRIMINAL_FORCE_ASSAULT"):
            if any(k in full_context for k in ["restrain", "confin", "assault", "criminal force", "outraging modesty", "grabbed", "detain", "held", "push", "physical contact"]):
                _set_gate(fam, satisfied=True, status="SUPPORTED", reason="Allegation of physical restraint, force, or physical assault.")
                result.supported.append(fam)
            else:
                reason = "No allegation of physical restraint, physical confinement, assault, or physical force."
                _set_gate(fam, satisfied=False, status="UNSUPPORTED", reason=reason)
                result.unsupported.append(fam)
                result.gate_notes.append(f"[gate] {code}: UNSUPPORTED — {reason}")
            continue

        if code == "HOMICIDE":
            if any(k in full_context for k in ["death", "died", "kill", "murder", "dead", "cause death"]):
                _set_gate(fam, satisfied=True, status="SUPPORTED", reason="Allegation of causing death.")
                result.supported.append(fam)
            else:
                reason = "No allegation of death or killing."
                _set_gate(fam, satisfied=False, status="UNSUPPORTED", reason=reason)
                result.unsupported.append(fam)
            continue

        if code == "HURT":
            if any(k in full_context for k in ["hurt", "injur", "wound", "beat", "struck", "pain", "fracture", "bleed"]):
                _set_gate(fam, satisfied=True, status="SUPPORTED", reason="Allegation of bodily injury or hurt.")
                result.supported.append(fam)
            else:
                reason = "No allegation of bodily pain, wounding, or physical injury."
                _set_gate(fam, satisfied=False, status="UNSUPPORTED", reason=reason)
                result.unsupported.append(fam)
            continue

        if code == "SEXUAL_OFFENCE":
            has_explicit = any(k in full_context for k in ["rape", "sexual assault", "molest", "penetrat", "intercourse", "voyeur", "stalk"])
            has_electronic = any(k in full_context for k in ["repeatedly contact", "repeatedly", "social media", "personal relationship", "personal interaction", "inappropriate message", "inappropriate communication", "sexual harassment", "unwelcome"])
            if has_explicit or has_electronic:
                if has_electronic and not has_explicit:
                    unresolved = ["content of messages unknown, not stated whether sexually coloured", "clear disinterest not explicitly stated"]
                    _set_gate(fam, satisfied=True, status="CONTINGENT", reason="Allegation of repeated electronic contact / messaging; specific message content unknown.", unresolved=unresolved)
                    result.contingent.append(fam)
                else:
                    _set_gate(fam, satisfied=True, status="SUPPORTED", reason="Allegation of sexual offence / stalking conduct.")
                    result.supported.append(fam)
            else:
                reason = "No allegation of sexual assault, stalking, or sexually coloured communication."
                _set_gate(fam, satisfied=False, status="UNSUPPORTED", reason=reason)
                result.unsupported.append(fam)
            continue

        if code == "INTIMIDATION_INSULT":
            has_threat = any(k in full_context for k in ["threat", "intimidat", "criminal intimidation"])
            has_modesty_privacy = any(k in full_context for k in ["inappropriate message", "inappropriate", "message", "communication", "insult", "modesty", "privacy", "words", "expressions", "vulgar", "objectionable", "lewd", "suggestive"])
            if has_threat:
                _set_gate(fam, satisfied=True, status="SUPPORTED", reason="Allegation of threatening conduct or criminal intimidation.")
                result.supported.append(fam)
            elif has_modesty_privacy:
                unresolved = ["content of messages unknown, not stated whether insulting to modesty or intruding upon privacy"]
                _set_gate(fam, satisfied=True, status="CONTINGENT", reason="Allegation of inappropriate messaging / communication; message content unstated.", unresolved=unresolved)
                result.contingent.append(fam)
            else:
                reason = "No allegation of threats, insult, or communication insulting modesty/privacy."
                _set_gate(fam, satisfied=False, status="UNSUPPORTED", reason=reason)
                result.unsupported.append(fam)
            continue

        if code == "POCSO":
            is_minor = any(k in full_context for k in ["minor", "child", "under 18", "below 18"])
            has_conduct = any(k in full_context for k in ["contact", "message", "sexual", "relationship", "harass"])
            if is_minor and has_conduct:
                unresolved = ["content of messages unknown, not stated whether sexually explicit"]
                _set_gate(fam, satisfied=True, status="CONTINGENT", reason="Allegation of contact/messaging with minor below 18 years; message content unstated.", unresolved=unresolved)
                result.contingent.append(fam)
            else:
                reason = "Victim not identified as child under 18 or no contact alleged."
                _set_gate(fam, satisfied=False, status="UNSUPPORTED", reason=reason)
                result.unsupported.append(fam)
            continue

        # Default for any other family
        if combined:
            _set_gate(fam, satisfied=True, status="CONTINGENT", reason=f"Plausible connection to {code} from cited facts.", unresolved=["Applicability to be established downstream"])
            result.contingent.append(fam)
        else:
            _set_gate(fam, satisfied=False, status="UNSUPPORTED", reason=f"No factual support cited for {code}.")
            result.unsupported.append(fam)

    return result

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def reciprocal_rank_fusion(
    rankings: List[List[Tuple[int, float, List[str], float]]],
    k: int = 60,
) -> List[Tuple[int, float, List[str], float]]:
    """
    Combines multiple independent rankings using Reciprocal Rank Fusion (RRF).
    Formula: RRF_score(d) = sum_{r in rankings} 1.0 / (k + rank_r(d))
    """
    rrf_scores: Dict[int, float] = {}
    doc_matched: Dict[int, Set[str]] = {}
    doc_mass: Dict[int, float] = {}

    for ranking in rankings:
        for rank_idx, (doc_idx, _score, matched, mass) in enumerate(ranking, start=1):
            rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0.0) + (1.0 / (k + rank_idx))
            doc_matched.setdefault(doc_idx, set()).update(matched)
            doc_mass[doc_idx] = max(doc_mass.get(doc_idx, 0.0), mass)

    fused = [
        (doc_idx, rrf_score, sorted(doc_matched[doc_idx]), doc_mass[doc_idx])
        for doc_idx, rrf_score in rrf_scores.items()
    ]
    fused.sort(key=lambda x: x[1], reverse=True)
    return fused


class FamilyRetriever:
    def __init__(self, prefilter: Optional[StatuteClassifierPrefilter] = None):
        self.pf = prefilter or StatuteClassifierPrefilter()
        self.records = self.pf.sections_db
        self.idx_by_sec = {r["section_number"]: i for i, r in enumerate(self.records)}
        self.family_members: Dict[str, List[int]] = {}
        for i, r in enumerate(self.records):
            if self.pf._is_non_offence_section(r):
                continue
            for cat in ipc_categories(r["section_number"]):
                self.family_members.setdefault(cat, []).append(i)
        # Short offence titles ("mischief", "public nuisance") name the base offence that derived sections build on.
        self.offence_names: Dict[str, str] = {}
        for r in self.records:
            if self.pf._is_non_offence_section(r):
                continue
            title = (r.get("title") or "").strip().lower().rstrip(".")
            if title and len(title.split()) <= 3 and not title.startswith("punishment"):
                self.offence_names.setdefault(title, r["section_number"])
        self.punishment_links = self._build_punishment_links()
        self._add_reference_links()
        self.negligence_sections = self._build_negligence_sections()

    def _add_reference_links(self) -> None:
        """Links a "Punishment ..." section to the definition its ingredients cite when the heading match found
        none (290 "Punishment for public nuisance ..." cites s. 268, 22 sections earlier)."""
        try:
            statute_db = StatuteRepository.get_instance().get_statute_db() or {}
        except Exception:
            return
        for rec in self.records:
            sec = rec["section_number"]
            if sec in self.punishment_links or not re.match(r"(?i)\s*punishment\s", rec.get("title") or ""):
                continue
            ings = " ".join(str(i) for i in ((statute_db.get(f"IPC_{sec}") or {}).get("ingredients") or []))
            for ref in re.findall(r"\b(?:section|s\.)\s*(\d+[A-Z]*)", ings, re.IGNORECASE):
                ref = ref.upper()
                if ref in self.idx_by_sec and ref != sec and ref not in _GENERIC_PUNISHMENT_SECTIONS:
                    self.punishment_links.setdefault(sec, set()).add(ref)
                    self.punishment_links.setdefault(ref, set()).add(sec)

    def _build_negligence_sections(self) -> Set[str]:
        """Sections whose fault element is rashness or negligence, read from their title and ingredients."""
        try:
            statute_db = StatuteRepository.get_instance().get_statute_db() or {}
        except Exception:
            statute_db = {}
        out: Set[str] = set()
        for rec in self.records:
            sec = rec["section_number"]
            ext = statute_db.get(f"IPC_{sec}") or {}
            text = " ".join([rec.get("title") or ""] + [str(i) for i in (ext.get("ingredients") or [])])
            if re.search(r"\b(rash\w*|negligen\w*)\b", text, re.IGNORECASE):
                out.add(sec)
        return out

    # -- definition <-> punishment links, derived from ipc.json headings --
    def _build_punishment_links(self) -> Dict[str, Set[str]]:
        """
        Pairs each "Punishment for/of X" section with the preceding section(s) in the same chapter
        whose heading best matches X (highest Jaccard over stemmed heading tokens; ties kept).
        A definition is linked only to the nearest punishment section that chose it, so
        107 -> 109 (not 110), 442 -> 448, 321 -> 323, 191/192 -> 193.
        """
        best_defs: Dict[str, List[str]] = {}
        for i, rec in enumerate(self.records):
            sec, head = rec["section_number"], rec.get("title") or ""
            m = re.match(r"(?i)\s*punishment\s+(?:for|of)\s+(.*)", head)
            if not m or sec in _GENERIC_PUNISHMENT_SECTIONS:
                continue
            target = set(_tokenize(m.group(1)))
            if not target:
                continue
            scored = []
            for j in range(max(0, i - 15), i):
                cand = self.records[j]
                if cand.get("chapter") != rec.get("chapter"):
                    continue
                if re.match(r"(?i)\s*punishment\s", cand.get("title") or ""):
                    continue
                ctoks = set(_tokenize(cand.get("title") or ""))
                if not ctoks:
                    continue
                inter = len(target & ctoks)
                coverage = inter / len(ctoks)          # how much of the definition heading is named
                jac = inter / len(target | ctoks)      # tie-breaker
                if coverage >= 0.5:
                    scored.append(((coverage, jac), cand["section_number"]))
            if scored:
                top = max(s for s, _ in scored)
                best_defs[sec] = [d for s, d in scored if s == top]

        links: Dict[str, Set[str]] = {}
        claimed: Set[str] = set()
        for psec, defs in best_defs.items():  # records order == statute order
            links.setdefault(psec, set()).update(defs)
            for d in defs:
                if d not in claimed:
                    links.setdefault(d, set()).add(psec)
                    claimed.add(d)
        return links

    def _score(self, idxs: Iterable[int], text: str) -> List[Tuple[int, float, List[str], float]]:
        """Returns [(record index, bm25 score, matched terms, coverage of query IDF mass)] best-first."""
        from .retriever import get_retriever, toks
        r = get_retriever()
        qt = toks(text)
        if not qt:
            return []
        idxs = list(idxs)
        t_scores = r._norm(r.bm_text.get_scores(qt))
        kw_scores = r._norm(r.bm_kw.get_scores(qt))
        out = []
        for i in idxs:
            sec_num = self.records[i]["section_number"]
            if sec_num in r.ids:
                ridx = r.ids.index(sec_num)
                phr_bonus = min(r._phrase_bonus(text, sec_num), 4)
                sc = (kw_scores[ridx] + 0.3 * t_scores[ridx] + 0.12 * phr_bonus) * r.K[sec_num]['retrieval_prior']
                if sc > 0:
                    kw_corpus = " ".join((r.K[sec_num].get('layman_keywords') or []) + (r.K[sec_num].get('auto_keywords') or [])).lower()
                    sec_corpus = (self.records[i].get("title", "") + " " + self.records[i].get("text", "")).lower()
                    matched = [w for w in qt if w in kw_corpus or w in sec_corpus]
                    out.append((i, float(sc), matched or ["matched"], 1.0))
        out.sort(key=lambda x: x[1], reverse=True)
        return out

    def retrieve(
        self,
        facts: Iterable[Any],
        families: Optional[Iterable[Any]] = None,
        per_family: int = 3,
        family_min_rel: float = 0.5,
        per_fact_safety_net: int = 8,
        safety_net_min_coverage: float = 0.3,
        per_negligent: int = 2,
    ) -> Tuple[List[CandidateSectionMatch], Dict[str, Any]]:
        facts = list(facts or [])
        fact_text = {str(_obj(f, "fact_id", "")): (_obj(f, "verbatim_quote") or _obj(f, "description") or "")
                     for f in facts}
        chosen: Dict[str, Dict[str, Any]] = {}
        diag: Dict[str, Any] = {"by_family": {}, "safety_net": {}, "linked": {}}

        def add(i: int, score: float, matched: List[str], via: str, classification: str = "PRIMARY") -> None:
            rec = self.records[i]
            key = rec["section_number"]
            if key not in chosen or score > chosen[key]["score"]:
                chosen[key] = {
                    "rec": rec,
                    "score": score,
                    "matched": matched,
                    "via": [via],
                    "classification": classification,
                }
            elif via not in chosen[key]["via"]:
                chosen[key]["via"].append(via)

        # 1. Family-restricted ranking with Reciprocal Rank Fusion across 3 query views
        for fam in families or []:
            code = str(_obj(fam, "family", "")).strip().upper()
            if code not in OFFENCE_FAMILIES:
                continue
            members = self.family_members.get(code, [])
            if not members:
                diag["by_family"][code] = []
                continue

            refs = [str(x) for x in (_obj(fam, "fact_ids", []) or [])]
            phrase = str(_obj(fam, "conduct_phrase", "") or "")
            text = " ".join(fact_text.get(r, "") for r in refs) + " " + phrase

            # View 1: Combined family facts + conduct phrase
            r_combined = self._score(members, text)
            rankings = [r_combined] if r_combined else []

            # View 2: Individual facts
            if len(refs) > 1:
                for r in refs:
                    r_indiv = self._score(members, fact_text.get(r, ""))
                    if r_indiv:
                        rankings.append(r_indiv)

            # View 3: the conduct phrase on its own. The generic family description is not used as a
            # query: its example words ("acid", "fire") outranked the facts (e.g. 326A for a bridge collapse).
            if phrase:
                r_phrase = self._score(members, phrase)
                if r_phrase:
                    rankings.append(r_phrase)

            if not rankings or not rankings[0]:
                diag["by_family"][code] = []
                continue

            # Fuse rankings using RRF
            fused = reciprocal_rank_fusion(rankings, k=60)
            if not fused:
                diag["by_family"][code] = []
                continue

            top_rrf = fused[0][1]
            picked = [x for x in fused[:per_family] if x[1] / top_rrf >= family_min_rel]

            diag["by_family"][code] = [self.records[i]["section_number"] for i, *_ in picked]
            for i, rrf_score, matched, _cov in picked:
                norm_score = round(min(1.0, rrf_score / top_rrf), 3)
                add(i, norm_score, matched, f"family:{code}", classification="PRIMARY")

            # Rash / negligent forms of the family are ranked separately so that intention-based sections
            # cannot crowd them out (a collapse injuring people must surface 337/338, not only 323-326).
            # Whether the conduct was in fact rash or negligent is decided in Stage 4.
            fault = str(_obj(fam, "fault_mode", "UNSTATED") or "UNSTATED").upper()
            neg_members = [i for i in members if self.records[i]["section_number"] in self.negligence_sections]
            if neg_members and fault not in {"INTENTIONAL", "KNOWING"}:
                r_neg = self._score(neg_members, text)
                for i, raw, matched, _cov in r_neg[:per_negligent]:
                    add(i, round(min(1.0, raw / r_neg[0][1]) * 0.8, 3), matched, f"family:{code}", classification="PRIMARY")
                    if self.records[i]["section_number"] not in diag["by_family"][code]:
                        diag["by_family"][code].append(self.records[i]["section_number"])

        # 2. Family-independent safety net over every charge-bearing fact
        all_idx = [i for members in self.family_members.values() for i in members]
        all_idx = sorted(set(all_idx))
        for f in facts:
            if str(_obj(f, "conduct_type", "ACT")).upper() not in _CHARGE_BEARING:
                continue
            fid = str(_obj(f, "fact_id", ""))
            ranked = self._score(all_idx, fact_text.get(fid, ""))
            if not ranked:
                continue
            top = ranked[0][1]
            n_tokens = len(set(_tokenize(fact_text.get(fid, ""))) - _QUERY_ONLY_STOP_STEMS)
            if n_tokens == 1:
                picked = [x for x in ranked[:per_fact_safety_net] if x[3] >= safety_net_min_coverage][:1]
            else:
                picked = [x for x in ranked[:per_fact_safety_net]
                          if x[3] >= safety_net_min_coverage and len(set(x[2])) >= 2]
            diag["safety_net"][fid] = [self.records[i]["section_number"] for i, *_ in picked]
            for i, raw, matched, _cov in picked:
                add(i, round(0.5 * raw / top, 3), matched, f"fact:{fid}", classification="CONDITIONAL")

        # 3. Definition <-> punishment links (data-derived)
        for sec in list(chosen):
            for linked in sorted(self.punishment_links.get(sec, ())):
                if linked not in chosen and linked in self.idx_by_sec:
                    i = self.idx_by_sec[linked]
                    add(i, chosen[sec]["score"], ["linked"], f"linked:{sec}", classification="AUGMENTED")
                    diag["linked"].setdefault(sec, []).append(linked)

        matches = [
            CandidateSectionMatch(
                section_identifier=v["rec"]["identifier"], statute=v["rec"]["statute"],
                section_number=k, title=v["rec"]["title"], chapter=v["rec"]["chapter"],
                score=v["score"], matched_terms=v["matched"][:5], matched_concepts=v["via"],
                classification=v.get("classification", "PRIMARY"),
            )
            for k, v in chosen.items()
        ]
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches, diag


# ---------------------------------------------------------------------------
# Deterministic top-up of the LLM's family tagging (no case-specific rules)
# ---------------------------------------------------------------------------
_JOINT_FAMILIES = (
    ("COMMON_INTENTION", "whether the accused shared a common intention"),
    ("ABETMENT", "whether one accused instigated or intentionally aided the other"),
    ("CONSPIRACY", "whether there was an agreement between the accused"),
)
_ACTOR_SPLIT = re.compile(r"\s*(?:,|;|&|\band\b|\balong with\b|\btogether with\b)\s*", re.IGNORECASE)

_RETRIEVER_SINGLETON: Optional["FamilyRetriever"] = None


def get_family_retriever() -> "FamilyRetriever":
    global _RETRIEVER_SINGLETON
    if _RETRIEVER_SINGLETON is None:
        _RETRIEVER_SINGLETON = FamilyRetriever()
    return _RETRIEVER_SINGLETON


def augment_families(
    facts: Iterable[Any],
    families: Iterable[Any],
    retriever: Optional["FamilyRetriever"] = None,
    top_n: int = 3,
    min_coverage: float = 0.3,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Adds offence families the LLM did not tag, from two structural signals:
      1. retrieval over sections, then roll up to families: run r.retrieve() on each atomic
         fact (CB1, CB2, CB3), not on compound allegations. Group section hits by family and
         take the top-N families per fact by rank, not score.
      2. joint conduct: a fact's actor field names two or more persons -> joint-liability families
         as CONDITIONAL, with the unestablished element recorded.
    Returns (families as dicts, notes). Never removes or edits what the LLM produced.
    """
    r = retriever or get_family_retriever()
    facts = list(facts or [])
    fams: List[Dict[str, Any]] = []
    for f in families or []:
        d = f.model_dump() if hasattr(f, "model_dump") else dict(f)
        d["family"] = str(d.get("family", "")).upper()
        d.setdefault("fact_ids", [])
        fams.append(d)
    by_code = {d["family"]: d for d in fams}
    notes: List[str] = []

    def ensure(code: str, fid: str, tier: str, unresolved: Optional[List[str]] = None, why: str = "",
               phrase: str = "") -> None:
        if code not in OFFENCE_FAMILIES:
            return
        if code in by_code:
            if fid not in by_code[code]["fact_ids"]:
                by_code[code]["fact_ids"].append(fid)
            return
        d = {"family": code, "fact_ids": [fid], "tier": tier, "conduct_phrase": phrase,
             "unresolved_elements": list(unresolved or [])}
        fams.append(d)
        by_code[code] = d
        notes.append(f"Family {code} added for {fid} ({why}).")

    # 1. Identify compound facts whose content has been split into child atomic facts
    compound_ids = set()
    charge_facts = [
        f for f in facts
        if str(_obj(f, "conduct_type", "ACT")).upper() in _CHARGE_BEARING
    ]
    for parent in charge_facts:
        p_quote = _norm_ws(_obj(parent, "verbatim_quote") or _obj(parent, "description") or "")
        if not p_quote:
            continue
        p_id = str(_obj(parent, "fact_id", ""))
        child_facts = [
            ch for ch in charge_facts
            if str(_obj(ch, "fact_id", "")) != p_id
            and (_obj(ch, "parent_fact_id") == p_id or (
                _norm_ws(_obj(ch, "verbatim_quote") or "")
                and _norm_ws(_obj(ch, "verbatim_quote") or "") in p_quote
                and len(_norm_ws(_obj(ch, "verbatim_quote") or "").split()) < len(p_quote.split())
            ))
        ]
        if child_facts:
            compound_ids.add(p_id)

    atomic_facts = [
        f for f in charge_facts
        if str(_obj(f, "fact_id", "")) not in compound_ids
    ]

    # 2. Retrieve over sections on each atomic fact, then roll up to families by rank
    for f in atomic_facts:
        fid = str(_obj(f, "fact_id", ""))
        text = _obj(f, "verbatim_quote") or _obj(f, "description") or ""
        matches, _ = r.retrieve([f], families=None, per_fact_safety_net=8, safety_net_min_coverage=min_coverage)
        if not matches:
            continue

        n_tokens = len(set(_tokenize(text)) - _QUERY_ONLY_STOP_STEMS)
        fam_hits: Dict[str, List[str]] = {}
        fam_ranks: Dict[str, List[int]] = {}

        for rank, m in enumerate(matches):
            sec = m.section_number
            for code in ipc_categories(sec):
                if code in OFFENCE_FAMILIES:
                    fam_hits.setdefault(code, []).append(sec)
                    fam_ranks.setdefault(code, []).append(rank)

        if not fam_ranks:
            continue

        # Noise control: require direct term match signal and >= 2 distinct section hits (or >= 1 for 1-token facts)
        direct_matches = [m for m in matches if m.matched_terms != ["linked"]]
        direct_secs = {m.section_number for m in direct_matches}

        valid_families = []
        for code, ranks in fam_ranks.items():
            distinct_hits = len(set(fam_hits[code]))
            code_direct = direct_secs & set(fam_hits[code])
            if n_tokens == 1:
                if distinct_hits >= 1:
                    valid_families.append(code)
            elif len(code_direct) >= 2 or (len(code_direct) >= 1 and any(m.score >= 0.35 and len(set(m.matched_terms)) >= 2 for m in direct_matches if m.section_number in code_direct)) or (len(code_direct) >= 1 and distinct_hits >= 2 and any(len(set(m.matched_terms)) >= 2 for m in direct_matches if m.section_number in code_direct)):
                valid_families.append(code)

        # Order families by best section rank, not score
        ranked_families = sorted(
            valid_families,
            key=lambda c: (min(fam_ranks[c]), -len(set(fam_hits[c])))
        )[:top_n]

        for code in ranked_families:
            secs_str = ", ".join(sorted(set(fam_hits[code]))[:3])
            ensure(code, fid, "SECONDARY", why=f"quote matches IPC {secs_str}")

    # 3. Joint liability
    for f in facts:
        fid = str(_obj(f, "fact_id", ""))
        if str(_obj(f, "conduct_type", "ACT")).upper() not in _CHARGE_BEARING:
            continue
        actors = [a for a in _ACTOR_SPLIT.split(str(_obj(f, "actor", "") or "")) if a.strip()]
        if len(actors) >= 2:
            act_str = ", ".join(actors)
            for code, element in _JOINT_FAMILIES:
                ensure(code, fid, "CONDITIONAL", [element], why=f"joint actors: {act_str}",
                       phrase=OFFENCE_FAMILIES.get(code, code))

    return fams, notes


# ---------------------------------------------------------------------------
# Deterministic Stage 2 mapping for family-tagged queries (0 LLM calls)
# ---------------------------------------------------------------------------
def build_family_mapping(
    query_obj: Any,
    retriever: Optional["FamilyRetriever"] = None,
    nominations: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    excluded: Optional[Dict[str, List[Dict[str, str]]]] = None,
) -> Dict[str, Any]:
    """
    Builds a Stage2BatchedMappingResponse-shaped dict from family retrieval:
      * one mapping per Stage 1 sub-query (one sub-query per family, same order);
      * a section retrieved inside a family goes to that family's sub-query with the family's tier;
      * with LLM nominations for a family (section_nominator), the nominations decide which of that family's
        sections pass and each carries its own tier; BM25 hits that were not nominated are dropped (listed in
        "retrieval_only_not_nominated"), and nominated sections BM25 missed are added;
      * a section linked from another (definition <-> punishment) follows its source section;
      * a section found only by the fact-level safety net goes to the first sub-query citing that
        fact, as CONDITIONAL (its family was not chosen, so applicability is open).
    Applicability is decided in Stage 4.
    """
    r = retriever or get_family_retriever()
    families = list(_obj(query_obj, "offence_families", []) or [])
    sub_queries = list(_obj(query_obj, "sub_queries", []) or [])
    facts = list(_obj(query_obj, "factual_allegations", []) or [])
    matches, _diag = r.retrieve(facts, families)

    nominations = {k.upper(): v for k, v in (nominations or {}).items() if v}
    nom_by_family: Dict[str, Dict[str, Dict[str, Any]]] = {
        code: {n["section"]: n for n in noms} for code, noms in nominations.items()
    }
    dropped: List[str] = []
    if nom_by_family:
        kept = []
        for m in matches:
            fam_vias = [v.partition(":")[2] for v in m.matched_concepts if v.startswith("family:")]
            judged = [c for c in fam_vias if c in nom_by_family]
            if judged and not any(m.section_number in nom_by_family[c] for c in judged):
                dropped.append(m.section_number)
                continue
            kept.append(m)
        matches = kept
        present = {m.section_number for m in matches}
        for code, noms in nom_by_family.items():
            for sec in noms:
                for s, via in [(sec, f"family:{code}")] + [(l, f"linked:{sec}") for l in sorted(r.punishment_links.get(sec, ()))]:
                    if s in present or s not in r.idx_by_sec:
                        continue
                    rec = r.records[r.idx_by_sec[s]]
                    matches.append(CandidateSectionMatch(
                        section_identifier=rec["identifier"], statute=rec["statute"], section_number=s,
                        title=rec["title"], chapter=rec["chapter"], score=0.0, matched_terms=[], matched_concepts=[via],
                    ))
                    present.add(s)

    sq_by_family: Dict[str, Any] = {}
    for fam, sq in zip(families, sub_queries):
        sq_by_family[str(_obj(fam, "family", "")).upper()] = (fam, sq)
    fact_to_sq: Dict[str, Any] = {}
    for fam, sq in zip(families, sub_queries):
        for fid in _obj(fam, "fact_ids", []) or []:
            fact_to_sq.setdefault(str(fid), (fam, sq))

    mappings: Dict[str, Dict[str, Any]] = {}
    for fam, sq in zip(families, sub_queries):
        sid = _obj(sq, "id", "")
        mappings[sid] = {
            "sub_query_id": sid, "sub_query_text": _obj(sq, "query", ""),
            "target_parties": list(_obj(sq, "target_parties", []) or []),
            "facts_extracted": [], "ingredients_matched": [],
            "candidate_chapters": [str(_obj(fam, "family", ""))],
            "primary_candidate_sections": [], "secondary_candidate_sections": [],
            "conditional_candidate_sections": [], "not_triggered_sections": [],
            "candidate_sections": [], "relevance_reasoning": f"Family-constrained retrieval ({_obj(fam, 'family', '')}).",
        }

    placed: Dict[str, Tuple[str, str]] = {}  # section -> (sub_query_id, tier)
    pending = list(matches)
    for _ in range(3):  # linked sections follow their source, which may be placed in an earlier pass
        rest = []
        for m in pending:
            target = None
            for via in m.matched_concepts:
                kind, _, val = via.partition(":")
                if kind == "family" and val in sq_by_family:
                    fam, sq = sq_by_family[val]
                    nom = nom_by_family.get(val, {}).get(m.section_number)
                    if nom:
                        missing = [nom["missing_element"]] if nom.get("missing_element") else []
                        target = (_obj(sq, "id", ""), nom["tier"], missing, nom)
                    elif val in nom_by_family:
                        continue  # this family was judged and did not nominate the section
                    else:
                        target = (_obj(sq, "id", ""), str(_obj(fam, "tier", "PRIMARY")).upper(), list(_obj(fam, "unresolved_elements", []) or []), None)
                    break
                if kind == "linked" and val in placed:
                    sid, tier = placed[val]
                    target = (sid, tier, [], None)
                    break
                if kind == "fact" and val in fact_to_sq:
                    fam, sq = fact_to_sq[val]
                    target = (_obj(sq, "id", ""), "CONDITIONAL", ["Offence family not tagged in Stage 1; applicability to be established"], None)
                    break
            if target is None:
                rest.append(m)
                continue
            sid, tier, unresolved, nom = target
            placed[m.section_number] = (sid, tier)
            key = {"PRIMARY": "primary_candidate_sections", "SECONDARY": "secondary_candidate_sections"}.get(tier, "conditional_candidate_sections")
            sources: List[str] = []
            if m.score > 0 and any(v.partition(":")[0] in ("family", "fact") for v in m.matched_concepts):
                sources.append("bm25")
            if nom:
                sources.append(f"family_screening:{tier}")
            sources += [f"graph_link:{v.partition(':')[2]}" for v in m.matched_concepts if v.startswith("linked:")]
            sources += ["fact_safety_net" for v in m.matched_concepts if v.startswith("fact:")][:1]
            if nom:
                why = f"Family screening verdict {tier}: {nom.get('reason', '')}"
            else:
                why = "Retrieved via " + ", ".join(m.matched_concepts) + (f"; matched terms: {', '.join(m.matched_terms)}" if m.matched_terms else "")
            mappings[sid][key].append({
                "section_number": m.section_number, "section_title": m.title, "statute": m.statute,
                "candidate_type": tier, "score": float(m.score),
                # The score is the lexical (BM25) score only; 0.0 means "not found lexically", not "irrelevant".
                "score_breakdown": {"bm25": float(m.score)},
                "retrieval_sources": sources,
                "ingredients_matched": list(nom.get("fact_ids", [])) if nom else [], "missing_facts": unresolved,
                "relevance_reasoning": why,
            })
            mappings[sid]["candidate_sections"].append(m.section_number)
        pending = rest
        if not pending:
            break
    # Sections the family screening judged NOT_APPLICABLE are listed, so the exclusion is visible.
    for code, items in (excluded or {}).items():
        if code not in sq_by_family:
            continue
        sid = _obj(sq_by_family[code][1], "id", "")
        for it in items:
            if it["section"] in placed or it["section"] not in r.idx_by_sec:
                continue
            mappings[sid]["not_triggered_sections"].append({
                "section_number": it["section"], "section_title": r.records[r.idx_by_sec[it["section"]]]["title"],
                "statute": "IPC", "not_triggered_reason": f"Family screening: not applicable - {it.get('reason', '')}",
                "missing_mandatory_ingredients": [],
            })
    result = {"schema_version": "1.0", "mappings": list(mappings.values())}
    if nom_by_family:
        result["retrieval_only_not_nominated"] = sorted(set(dropped))
    return result


# ---------------------------------------------------------------------------
# Clause backstop: retrieval granularity must not depend on how finely the LLM split facts
# ---------------------------------------------------------------------------
_CLAUSE_SPLIT = re.compile(r",\s*(?:and\s+)?|;\s*|\s+and\s+(?=[a-z]+(?:ed|ing)\b)", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def clause_backstop(narrative: str, facts: Iterable[Any], min_words: int = 2) -> List[Dict[str, Any]]:
    """
    For every narrative sentence that contains an alleged (charge-bearing) fact quote, splits the sentence
    into clauses and returns clauses not already covered by an existing fact as new facts. Clauses are
    verbatim spans of the narrative, and only allegation sentences are used (sentences the LLM itself
    grounded an act/omission/result in), so defence statements are not turned into allegations.
    """
    facts = list(facts or [])
    quotes = [(f, _norm_ws(_obj(f, "verbatim_quote") or "")) for f in facts
              if str(_obj(f, "conduct_type", "")).upper() in _CHARGE_BEARING and _obj(f, "verbatim_quote")]
    if not narrative or not quotes:
        return []
    existing_tokens = [set(_tokenize(q)) for _, q in quotes]
    existing_ids = {str(_obj(f, "fact_id", "")) for f in facts if _obj(f, "fact_id", "")}
    new: List[Dict[str, Any]] = []
    n = 0
    for sent in _SENTENCE_SPLIT.split(narrative):
        ns = _norm_ws(sent)
        anchors = [f for f, q in quotes if q and q in ns]
        if not anchors:
            continue
        # Only the part of the sentence from the first alleged act onwards (skip preambles such as
        # "The complainant, a relative of the deceased, alleges that ...").
        start = min(ns.find(q) for f, q in quotes if q and q in ns)
        region = re.sub(r"\s+", " ", sent).strip()[start:]
        for clause in _CLAUSE_SPLIT.split(region):
            clause = clause.strip(" .")
            if len(clause.split()) < min_words:
                continue
            ctoks = set(_tokenize(clause))
            if not ctoks:
                continue
            # Covered only if an existing quote is about this clause (inside it, or nearly the same
            # words) - not merely because a broad quote spanning several acts contains it.
            covered = any(
                (q and q in _norm_ws(clause)) or (et and len(ctoks & et) / len(ctoks | et) >= 0.6)
                for (_, q), et in zip(quotes, existing_tokens)
            )
            if covered:
                continue
            n += 1
            cand_id = f"CB{n}"
            while cand_id in existing_ids:
                n += 1
                cand_id = f"CB{n}"
            existing_ids.add(cand_id)
            # The clause keeps the type and actor of the fact whose quote contains it (a split RESULT is a RESULT).
            ncl = _norm_ws(clause)
            parent = next((f for f, q in quotes if f is not None and q and ncl in q), None)
            ctype = str(_obj(parent, "conduct_type", "ACT") or "ACT").upper() if parent is not None else "ACT"
            new.append({
                "fact_id": cand_id, "verbatim_quote": clause, "conduct_type": ctype, "factual_status": "ALLEGED",
                "description": f"Separate {ctype.lower()} split from a compound allegation (clause backstop)",
                "actor": _obj(parent, "actor", None) if parent is not None else None,
                "affected_party_or_object": None,
                "parent_fact_id": _obj(parent, "fact_id", None) if parent is not None else None,
            })
            existing_tokens.append(ctoks)
            quotes.append((None, _norm_ws(clause)))
    return new


# ---------------------------------------------------------------------------
# Defence backstop: the accused's denial / alternative explanation as structured STATEMENT facts
# ---------------------------------------------------------------------------
_DEFENCE_VERB = re.compile(r"\b(denie[sd]|deny|contends?|contended|submits?|submitted|claims?|claimed|asserts?|"
                           r"pleads?|pleaded|maintains?|argues?)\b", re.IGNORECASE)
_DEFENCE_SPLIT = re.compile(r"\s+and\s+(?=(?:denie|deny|contend|submit|claim|assert|plead|maintain|argue)\w*\b)"
                            r"|;\s*|,\s*(?:and\s+)?(?=(?:denie|deny|contend|submit|claim|assert|plead|maintain|argue)\w*\b)",
                            re.IGNORECASE)
_ALT_CAUSE = re.compile(r"\b(caused by|due to|because of|result(?:ed)? from|attributable to|owing to)\b", re.IGNORECASE)
_COMPLIANCE = re.compile(r"\b(compl(?:y|ied|iance)|followed|adhered|in accordance with|as per|precautions?|"
                         r"procedures?|standards?)\b", re.IGNORECASE)


def defence_backstop(narrative: str, facts: Iterable[Any], accused: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Sentences in which the accused denies, contends, submits or claims something become STATEMENT facts
    (factual_status DISPUTED), one per clause, unless an existing fact already quotes them. Each is labelled as a
    denial, an alternative causal explanation or an assertion of compliance, so Stage 4 can weigh a specific
    defence fact against the allegation it answers instead of treating every denial alike.
    """
    facts = list(facts or [])
    existing = [_norm_ws(_obj(f, "verbatim_quote") or "") for f in facts if _obj(f, "verbatim_quote")]
    ids = {str(_obj(f, "fact_id", "")) for f in facts}
    out: List[Dict[str, Any]] = []
    n = 0
    for sent in _SENTENCE_SPLIT.split(narrative or ""):
        if not _DEFENCE_VERB.search(sent):
            continue
        clauses: List[str] = []
        for clause in _DEFENCE_SPLIT.split(re.sub(r"\s+", " ", sent).strip()):
            clause = clause.strip(" .")
            if len(clause.split()) < 3 or not _DEFENCE_VERB.search(clause):
                continue
            # "caused by X despite compliance with Y" holds two defence facts: an alternative cause and compliance.
            parts = re.split(r"\s+(?=(?:despite|notwithstanding|in spite of)\b)", clause, flags=re.IGNORECASE)
            if len(parts) > 1 and _ALT_CAUSE.search(parts[0]) and _COMPLIANCE.search(" ".join(parts[1:])):
                clauses += [p.strip(" ,.") for p in parts]
            else:
                clauses.append(clause)
        for clause in clauses:
            nc = _norm_ws(clause)
            if len(clause.split()) < 3:
                continue
            if any(q and (q in nc or nc in q) for q in existing):
                continue
            kinds = []
            if re.search(r"\bden(?:ie[sd]|y)\b", clause, re.IGNORECASE):
                kinds.append("denial")
            if _ALT_CAUSE.search(clause):
                kinds.append("alternative causal explanation")
            if _COMPLIANCE.search(clause):
                kinds.append("assertion of compliance")
            n += 1
            fid = f"D{n}"
            while fid in ids:
                n += 1
                fid = f"D{n}"
            ids.add(fid)
            out.append({
                "fact_id": fid, "verbatim_quote": clause, "conduct_type": "STATEMENT", "factual_status": "DISPUTED",
                "description": "Defence " + (" / ".join(kinds) or "assertion"),
                "actor": accused, "affected_party_or_object": None,
            })
            existing.append(nc)
    return out
