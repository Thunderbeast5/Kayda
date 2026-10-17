"""
Deterministic breadth expansion for Stage 1.

The LLM tends to emit one sub-query per factual act, which silently removes related
statutory headings (forgery, using as genuine, fabricating evidence, conspiracy,
common intention, abetment ...) before Stage 2 ever sees them. This module adds one
tiered sub-query per statutory heading that the alleged conduct can plausibly touch.

It only adds queries; it never edits or removes what the LLM produced, and it never
puts section numbers in query text (Stage 1 stays number-free).
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .schemas.stage1 import LegalConceptItem, LegalQueryObject, SubQueryItem

# (dedup keyword already present in existing concepts, concept heading, tier, query template, unresolved)
# {actors} / {conduct} are filled from the triggering fact.
_Rule = Tuple[str, str, str, str, List[str]]

_RECORD_RULES: List[_Rule] = [
    ("false document", "Making a false document — alteration of entries in a record to conceal wrongdoing", "PRIMARY",
     "Did {actors}'s alleged act ({conduct}) amount to making a false document with intent to cause damage or injury?",
     ["Whether the entries were made dishonestly or fraudulently"]),
    ("punishment for forgery", "Forgery — falsified record made with intent to cause damage or injury; punishment for forgery", "PRIMARY",
     "Did {actors}'s alleged falsification ({conduct}) constitute forgery, and what is the punishment for forgery?",
     ["Intent to cause damage or injury or to support a claim or title"]),
    ("as genuine", "Using as genuine a forged document — production of the falsified record as authentic", "PRIMARY",
     "If the falsified records were later produced before the investigating agency or any authority as authentic, did that amount to using a forged document as genuine?",
     ["Whether the records were actually produced or relied upon as genuine"]),
    ("fabricating false evidence", "Fabricating false evidence — falsified entries intended to be used in a proceeding", "PRIMARY",
     "Did {actors}'s alleged falsification ({conduct}), if done knowing the records may be used in a judicial or quasi-judicial proceeding, amount to fabricating false evidence?",
     ["Knowledge or intent that the records would be used in a proceeding"]),
    ("evidence known to be false", "Using evidence known to be false — corrupt use of falsified records in a proceeding", "PRIMARY",
     "If {actors} or any other party corruptly used the falsified records in a legal proceeding knowing them to be false, does that amount to an independent offence of using evidence known to be false?",
     ["Whether the records were used in any proceeding"]),
    ("falsification of accounts", "Falsification of accounts — records alleged to be books of account or required accounting records", "CONDITIONAL",
     "If the falsified records are shown to be books of account or legally required accounting records of the institution, did the alleged alteration with intent to defraud attract liability for falsification of accounts?",
     ["Whether the records qualify as books of account or accounting records",
      "Whether the accused acted as clerk, officer or servant with intent to defraud"]),
]

_DESTROY_RULES: List[_Rule] = [
    ("destruction of document", "Destruction of document to prevent its production as evidence — destruction of records", "PRIMARY",
     "Did {actors}'s alleged destruction of records ({conduct}), which could be compelled as evidence, amount to secreting or destroying a document to prevent its production as evidence?",
     ["Whether the records were compellable as evidence", "Intention to prevent production"]),
    ("disappearance of evidence", "Causing disappearance of evidence of offence, or giving false information to screen offender", "PRIMARY",
     "Did {actors}'s alleged conduct ({conduct}) amount to causing evidence of an offence to disappear, or giving false information, with intent to screen the offender from legal punishment?",
     ["Knowledge or belief that an offence had been committed", "Intent to screen the offender"]),
]

_INSTRUCT_RULES: List[_Rule] = [
    ("false information respecting", "Giving false information respecting an offence committed — suppression of the sequence of events", "SECONDARY",
     "Did {actors}'s alleged direction to staff ({conduct}) amount to causing false information to be given respecting an offence committed?",
     ["Whether any information was actually given", "Whether the information was false"]),
    ("criminal intimidation", "Criminal intimidation — pressure on junior staff to withhold information", "SECONDARY",
     "Did {actors}'s alleged direction to staff ({conduct}) amount to threatening them with injury to their person, reputation or livelihood in order to compel them to withhold information?",
     ["Whether any threat of injury was made", "Whether it was meant to alarm or compel"]),
    ("public servant to use lawful power", "False information with intent to cause public servant to use lawful power to the injury of another person", "SECONDARY",
     "If {actors} or any co-accused gave a statement to the investigating officer denying the true sequence of events while knowing it false, does that attract liability for furnishing false information to a public servant?",
     ["Whether any statement was made to a public servant", "Knowledge that the statement was false"]),
]

_JOINT_RULES: List[_Rule] = [
    ("abetment of a thing", "Abetment of a thing — participation by a co-accused in the primary acts", "SECONDARY",
     "Did the co-accused, by actively participating in or instigating the alleged acts ({conduct}), abet the offences allegedly committed by the other accused?",
     ["Whether instigation, conspiracy or intentional aid is shown"]),
    ("punishment of abetment", "Punishment of abetment if the act abetted is committed — where no express provision exists", "SECONDARY",
     "If the abetted acts ({conduct}) were committed in consequence of the abetment, what liability attaches where no express punishment is provided?",
     ["Whether the abetted act was committed in consequence of the abetment"]),
    ("definition of criminal conspiracy", "Definition of criminal conspiracy — agreement between the accused to do an illegal act", "PRIMARY",
     "Did the accused enter into an agreement to do the alleged illegal acts ({conduct}), constituting a criminal conspiracy?",
     ["Evidence of an agreement between the accused"]),
    ("punishment of criminal conspiracy", "Punishment of criminal conspiracy — conspiracy to commit cognizable offences", "PRIMARY",
     "If a conspiracy to commit the alleged offences ({conduct}) is made out, what is the punishment for criminal conspiracy?",
     ["Whether the conspiracy was to commit an offence"]),
    ("common intention", "Acts done by several persons in furtherance of common intention", "PRIMARY",
     "Were the alleged acts ({conduct}) done by the accused together in furtherance of a common intention, making each liable for the acts of all?",
     ["Whether a shared intention existed", "Whether each accused participated in the act"]),
]

_MEDICAL_CONDITIONAL_RULES: List[_Rule] = [
    ("cheating", "Cheating — deceptive inducement of the patient's family regarding the patient's condition or treatment", "CONDITIONAL",
     "If the patient's family was dishonestly induced by false representations about the patient's condition to consent to a procedure or continue treatment, did the conduct amount to cheating?",
     ["Deceptive representation to the family", "Resulting damage or harm"]),
    ("breach of trust", "Criminal breach of trust — entrustment arising from the physician-patient relationship", "CONDITIONAL",
     "Given the fiduciary relationship between a treating physician and a patient, did the alleged concealment of the cause of death and falsification of records amount to criminal breach of trust?",
     ["Whether property or dominion was entrusted", "Dishonest misappropriation or disposal"]),
]

_NEGLIGENCE_RULE: _Rule = (
    "death by negligence", "Causing death by negligence — failure to act on warnings and arrange timely care", "PRIMARY",
    "Did {actors}'s alleged conduct ({conduct}) constitute a rash or negligent act causing death?",
    ["Whether the negligence was the proximate cause of death"],
)

_RECORD_TRIGGER = re.compile(r"falsif|alter|fabricat|manipulat|false entr|entries|tamper", re.I)
_RECORD_NOUN = re.compile(r"record|document|entries|register|chart|file", re.I)
_DESTROY_TRIGGER = re.compile(r"destroy|erase|delet|shred|burn|disappear", re.I)
_INSTRUCT_TRIGGER = re.compile(r"instruct|direct(ed)?|told|not to disclose|suppress|pressur|silenc|dissuad|influenc", re.I)
_JOINT_TRIGGER = re.compile(r"along with|together|jointly|in collusion|co-accused|and the (hospital )?administrator", re.I)
_DEATH_TRIGGER = re.compile(r"death|died|dead|fatal", re.I)
_NEGLIGENCE_TRIGGER = re.compile(r"negligen|ignor|fail(ed|ure)|omission|delay|warning", re.I)
_MEDICAL_TRIGGER = re.compile(r"medical|doctor|physician|hospital|patient|surgery|treatment", re.I)


def _facts_matching(query_obj: LegalQueryObject, *patterns: re.Pattern):
    out = []
    for fact in query_obj.factual_allegations:
        # DISPUTED/STATEMENT facts are the other side's submissions, not alleged conduct.
        if (fact.conduct_type or "").upper() == "STATEMENT":
            continue
        text = fact.description or ""
        if all(p.search(text) for p in patterns):
            out.append(fact)
    return out


def _known(query_obj: LegalQueryObject, key: str) -> bool:
    key = key.lower()
    for c in query_obj.legal_concepts:
        if key in (c.concept or "").lower():
            return True
    for sq in query_obj.sub_queries:
        if key in (sq.concept or "").lower():
            return True
    return False


def _next_ids(query_obj: LegalQueryObject) -> Tuple[int, int]:
    def mx(prefix, items):
        best = 0
        for i in items:
            m = re.fullmatch(prefix + r"(\d+)", i or "")
            if m:
                best = max(best, int(m.group(1)))
        return best
    return (mx("LC", [c.concept_id for c in query_obj.legal_concepts]) + 1,
            mx("SQ", [s.id for s in query_obj.sub_queries]) + 1)


def expand_sub_queries(query_obj: LegalQueryObject) -> LegalQueryObject:
    lc_n, sq_n = _next_ids(query_obj)
    added = 0

    def add(rule: _Rule, facts, actors: List[str], conduct: str):
        nonlocal lc_n, sq_n, added
        key, concept, tier, template, unresolved = rule
        if _known(query_obj, key):
            return
        fact_ids = [f.fact_id for f in facts]
        actor_txt = " and ".join(actors) if actors else "the accused"
        text = template.format(actors=actor_txt, conduct=conduct.rstrip("."))
        cid = f"LC{lc_n}"
        query_obj.legal_concepts.append(LegalConceptItem(
            concept_id=cid, concept=concept,
            description=f"Provisional heading raised by: {conduct}", supporting_fact_ids=fact_ids,
            classification_status="PROVISIONAL" if tier != "CONDITIONAL" else "UNCERTAIN", confidence=0.7 if tier == "PRIMARY" else 0.6))
        query_obj.sub_queries.append(SubQueryItem(
            id=f"SQ{sq_n}", query=text, concept=concept, concept_id=cid, tier=tier,
            fact_ids=fact_ids, target_parties=actors, role_alleged=None,
            conduct_type="ACT", unresolved_elements=list(unresolved), confidence=0.7 if tier == "PRIMARY" else 0.6))
        lc_n += 1
        sq_n += 1
        added += 1

    def actors_of(facts) -> List[str]:
        names: List[str] = []
        for f in facts:
            for a in re.split(r",| and ", f.actor or ""):
                a = a.strip()
                if a and a not in names:
                    names.append(a)
        return names

    def conduct_of(facts) -> str:
        return "; ".join((f.description or "").rstrip(".") for f in facts)[:300]

    record_facts = _facts_matching(query_obj, _RECORD_TRIGGER, _RECORD_NOUN)
    destroy_facts = _facts_matching(query_obj, _DESTROY_TRIGGER, _RECORD_NOUN)
    instruct_facts = _facts_matching(query_obj, _INSTRUCT_TRIGGER)
    instruct_facts = [f for f in instruct_facts if f not in record_facts]
    negligence_facts = _facts_matching(query_obj, _NEGLIGENCE_TRIGGER)
    negligence_facts = [f for f in negligence_facts if f not in record_facts and f not in destroy_facts]
    all_text = " ".join((f.description or "") for f in query_obj.factual_allegations)
    has_death = bool(_DEATH_TRIGGER.search(all_text))

    if has_death and negligence_facts:
        add(_NEGLIGENCE_RULE, negligence_facts, actors_of(negligence_facts), conduct_of(negligence_facts))
    if record_facts:
        for rule in _RECORD_RULES:
            add(rule, record_facts, actors_of(record_facts), conduct_of(record_facts))
    if destroy_facts:
        for rule in _DESTROY_RULES:
            add(rule, destroy_facts, actors_of(destroy_facts), conduct_of(destroy_facts))
    if instruct_facts:
        for rule in _INSTRUCT_RULES:
            add(rule, instruct_facts, actors_of(instruct_facts), conduct_of(instruct_facts))

    joint_basis = destroy_facts + [f for f in instruct_facts if f not in destroy_facts]
    joint_actors = actors_of(joint_basis)
    if joint_basis and (len(joint_actors) >= 2 or any(_JOINT_TRIGGER.search(f.description or "") or _JOINT_TRIGGER.search(f.actor or "") for f in joint_basis)):
        for rule in _JOINT_RULES:
            add(rule, joint_basis, joint_actors, conduct_of(joint_basis))

    if record_facts and _MEDICAL_TRIGGER.search(all_text):
        for rule in _MEDICAL_CONDITIONAL_RULES:
            add(rule, record_facts, actors_of(record_facts), conduct_of(record_facts))

    return query_obj
