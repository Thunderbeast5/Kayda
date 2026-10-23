"""
Offence taxonomy: maps ANY statute reference to broad offence categories, and derives gravity from punishment.

This replaces the keyword facets (land / deed / forgery ...), the disqualifying-facet lists (302 / 376 / 498A ...)
and the per-section gravity caps that used to live in the retriever and matcher. Nothing here is specific to one
input case: it is the structure of the IPC itself (its chapters), a table of special Acts, and the punishment
text already held in StatuteRepository.

Categories are used for two things:
  * category similarity between the input's charged offences and a precedent's charged offences
    (a murder precedent has no overlap with a cheating/forgery input, and vice-versa), and
  * default prosecution/defence argument themes for the retrieval profile.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# IPC chapter structure (sections inclusive). BNS / BNSS sections are first mapped back to IPC / CrPC through
# StatuteRepository, so one table covers both regimes.
# ---------------------------------------------------------------------------
IPC_FAMILY_REGISTRY = {
  "GENERAL_PROVISIONS": {
    "sections": "1-5",
    "describes": "Title, extent and operation of the Code, and its territorial reach. Not an offence family.",
    "not_for": "Any conduct allegation. Never propose from facts."
  },
  "GENERAL_EXPLANATIONS": {
    "sections": "6-52A",
    "describes": "Definitions and interpretive terms used across the Code: 'man', 'woman' (a female of any age), 'person', 'public servant', 'dishonestly', 'fraudulently', 'voluntarily', 'good faith', 'movable property'. Use to interpret other sections, not as offences.",
    "not_for": "Conduct allegations. Useful as supporting definitions (e.g. s.10: 'woman' includes a girl of any age)."
  },
  "PUNISHMENTS": {
    "sections": "53-75",
    "describes": "Types of punishment, fines, limits on punishment, enhanced punishment for repeat offenders (s.75).",
    "not_for": "Conduct allegations."
  },
  "GENERAL_EXCEPTIONS": {
    "sections": "76-106",
    "describes": "Defences: acts done by mistake, accident, in good faith, by children under seven (s.82) or seven to twelve (s.83), insanity (s.84), intoxication, consent, private defence of body and property (96-106).",
    "use_when": "The accused raises a defence such as self-defence, mistake, or lack of capacity."
  },
  "ABETMENT": {
    "sections": "107-120",
    "describes": "Instigating, helping or conspiring to get someone else to commit an offence; encouraging or assisting a crime; hiding a plan to commit an offence.",
    "use_when": "Someone is alleged to have incited, helped or encouraged another person's offence."
  },
  "CONSPIRACY": {
    "sections": "120A-120B",
    "describes": "Two or more people agreeing to commit an illegal act or a legal act by illegal means.",
    "use_when": "An agreement or plan between several persons is alleged."
  },
  "OFFENCE_AGAINST_STATE": {
    "sections": "121-130 (incl. 121A, 124A)",
    "describes": "Waging war against the government, conspiring against the State, sedition, collecting arms to wage war, assaulting high officials to compel them, aiding the escape of state prisoners.",
    "use_when": "Conduct is directed against the State or its sovereignty."
  },
  "OFFENCE_ARMED_FORCES": {
    "sections": "131-140",
    "describes": "Abetting mutiny, assaulting superior officers, desertion, harbouring deserters, wearing military uniform without authority.",
    "use_when": "Army, Navy or Air Force personnel or discipline are involved."
  },
  "PUBLIC_TRANQUILITY": {
    "sections": "141-160",
    "describes": "Unlawful assembly, rioting, armed rioting, promoting enmity between groups (153A), affray, fighting in public, joining or being present in a mob that commits violence.",
    "use_when": "A group, crowd or public disturbance is alleged."
  },
  "PUBLIC_SERVANT_OFFENCES": {
    "sections": "161-171 (excl. 171A-I)",
    "describes": "Public servants taking bribes or gifts, abetting bribery, disobeying the law, framing incorrect records, unlawfully buying property, wrongful personation of a public servant (170-171).",
    "use_when": "A government official or someone posing as one is involved."
  },
  "ELECTION_OFFENCE": {
    "sections": "171A-171I",
    "describes": "Bribing voters, undue influence at elections, personation of voters, false election statements, illegal payments for elections, failing to keep election accounts.",
    "use_when": "Voting, candidates or elections are involved."
  },
  "CONTEMPT_OF_AUTHORITY": {
    "sections": "172-190",
    "describes": "Avoiding service of summons or orders, not attending in obedience to an order, giving false information to a public servant, obstructing public servants, disobeying a lawful order (188), threatening a public servant, resisting arrest.",
    "use_when": "The accused avoided, defied, obstructed or threatened a public servant or court process."
  },
  "FALSE_EVIDENCE_JUSTICE": {
    "sections": "191-229A",
    "describes": "Perjury, giving or fabricating false evidence, destroying evidence, harbouring an offender, false charges (211), failing to give information of an offence, personation in legal proceedings, escape from custody, tampering with judicial proceedings.",
    "use_when": "Lying to a court or police, destroying or fabricating evidence, hiding an offender, filing a false case."
  },
  "COIN_GOVT_STAMPS": {
    "sections": "230-263A",
    "describes": "Counterfeiting coin, possessing or passing counterfeit coin, altering coin, counterfeiting or using false government stamps.",
    "use_when": "Fake coins or revenue stamps."
  },
  "WEIGHTS_MEASURES": {
    "sections": "264-267",
    "describes": "Using false weights or measures, possessing them, making them.",
    "use_when": "Trade fraud through weighing or measuring."
  },
  "PUBLIC_HEALTH_SAFETY_DECENCY": {
    "sections": "268-294A",
    "describes": "Public nuisance, spreading infection, adulterating food, drink or medicine, rash or negligent driving on public roads (279), negligent acts endangering life, and obscenity: selling, distributing or exhibiting obscene books, pictures or electronic material (292), selling or showing obscene objects to a person under twenty (293), obscene acts or songs in public (294), lottery offences.",
    "use_when": "Dangerous public conduct, adulteration, rash driving, OR sharing or sending obscene or sexually explicit material, including to young people."
  },
  "RELIGION": {
    "sections": "295-298",
    "describes": "Defiling a place of worship, deliberately insulting religious feelings (295A), disturbing a religious assembly, trespassing on burial places, uttering words to wound religious feelings.",
    "use_when": "Religious belief, places or feelings are targeted."
  },
  "HOMICIDE": {
    "sections": "299-311",
    "describes": "Culpable homicide, murder, death by negligence (304A), dowry death (304B), abetment of suicide (305-306), attempt to murder (307), attempt to commit culpable homicide (308), attempt to commit suicide (309), thugs (310-311).",
    "use_when": "A death, or an attempt or abetment that threatens life."
  },
  "MISCARRIAGE_CHILD": {
    "sections": "312-318",
    "describes": "Causing miscarriage (with or without consent), injury to an unborn child, causing death of a quick unborn child, abandoning a child under twelve, concealing a birth by secret disposal of a body.",
    "use_when": "Pregnancy, unborn children, abandonment of infants."
  },
  "HURT": {
    "sections": "319-338",
    "describes": "Causing physical pain, injury or disease (voluntarily causing hurt), grievous hurt (fractures, loss of sight, permanent disfigurement), hurt with dangerous weapons, acid attacks (326A-326B), hurt to extort or to compel, hurt by rash or negligent acts.",
    "use_when": "Physical injury is alleged."
  },
  "WRONGFUL_RESTRAINT_CONFINEMENT": {
    "sections": "339-348",
    "describes": "Stopping a person from moving in a direction they have a right to go (wrongful restraint), confining a person within limits (wrongful confinement), confining secretly, confining to extort or to compel.",
    "use_when": "Someone was physically blocked, locked in or held."
  },
  "CRIMINAL_FORCE_ASSAULT": {
    "sections": "349-358 (excl. 354 series)",
    "describes": "Using force, touching or making a gesture or preparation that causes someone to fear force (assault), assaulting a public servant, assaulting to dishonour, assault on provocation.",
    "use_when": "Force, touching, or threatening gestures causing fear of immediate force."
  },
  "KIDNAPPING_TRAFFICKING": {
    "sections": "359-374 (incl. 370, 370A)",
    "describes": "Taking or enticing a minor or person of unsound mind out of lawful guardianship (363), abduction, kidnapping for ransom or to compel marriage (366), procuring a minor girl (366A), importing a girl, buying or selling minors for prostitution (372-373), human trafficking, exploitation of a trafficked person, slavery, forced labour.",
    "use_when": "A person was taken, lured, transported, sold or exploited, or a minor was induced to leave a guardian."
  },
  "SEXUAL_OFFENCE": {
    "sections": "375-377 and 354, 354A-354D",
    "describes": "Rape and aggravated rape (375-376E); unnatural offences (377); assault or force to outrage a woman's modesty (354); sexual harassment, which includes unwelcome physical advances, a demand or request for sexual favours, showing pornography against her will, or making sexually coloured remarks (354A); assault to disrobe (354B); voyeurism (354C); stalking, which includes following a woman or repeatedly contacting or trying to contact her to foster personal interaction despite clear disinterest, or monitoring her internet, email or other electronic communication (354D).",
    "use_when": "Sexual conduct, sexually coloured words or messages, unwelcome repeated contact or following, watching or recording, including through electronic means."
  },
  "THEFT": {
    "sections": "378-382",
    "describes": "Dishonestly taking movable property out of someone's possession without consent; theft by a servant or clerk; theft after preparing for death or hurt.",
    "use_when": "Property was taken without consent."
  },
  "EXTORTION": {
    "sections": "383-389",
    "describes": "Putting a person in fear of injury to obtain property or a signed document, including by threatening accusations of an offence.",
    "use_when": "Threats were used to obtain money, property or a signature. Note: this concerns obtaining property, whereas pure threats go to INTIMIDATION_INSULT."
  },
  "ROBBERY_DACOITY": {
    "sections": "390-402",
    "describes": "Robbery (theft or extortion with violence or fear of death or hurt), dacoity (five or more persons), dacoity with murder, preparing or assembling to commit dacoity, belonging to a gang of robbers.",
    "use_when": "Violent taking of property, or gangs."
  },
  "CRIMINAL_MISAPPROPRIATION": {
    "sections": "403-404",
    "describes": "Dishonestly misappropriating or converting movable property to one's own use, including property of a deceased person.",
    "use_when": "Someone kept or used property that came to them innocently."
  },
  "BREACH_OF_TRUST": {
    "sections": "405-409",
    "describes": "Criminal breach of trust, by a carrier, clerk, servant, public servant, banker, merchant or agent, where property was entrusted and then dishonestly used.",
    "use_when": "Entrusted money or property was misused."
  },
  "STOLEN_PROPERTY": {
    "sections": "410-414",
    "describes": "Receiving, retaining, concealing or disposing of stolen property; habitually dealing in stolen property.",
    "use_when": "Possessing or dealing in property that was stolen or taken by crime."
  },
  "CHEATING": {
    "sections": "415-420",
    "describes": "Deceiving someone to induce delivery of property or to act against their interest, cheating by personation (416, 419), cheating that dishonestly induces delivery of property or alteration of valuable security (420), cheating a person whose interest the offender must protect.",
    "use_when": "Fraud, lying to gain property or advantage, impersonation to deceive, including online."
  },
  "FRAUDULENT_DEEDS": {
    "sections": "421-424",
    "describes": "Dishonestly removing or concealing property to defeat creditors, fraudulently executing deeds with false consideration.",
    "use_when": "Hiding or transferring assets to avoid creditors."
  },
  "MISCHIEF": {
    "sections": "425-440",
    "describes": "Destroying, damaging or diminishing the value of property, mischief by fire or explosive, mischief against railways or ships, mischief to water supply, damage to public works.",
    "use_when": "Property damage."
  },
  "CRIMINAL_TRESPASS": {
    "sections": "441-462",
    "describes": "Entering or remaining on another's property with intent to commit an offence or to intimidate, insult or annoy; house-trespass, lurking house-trespass, house-breaking, burglary (night-time housebreaking), breaking into places for theft.",
    "use_when": "Unlawful entry into premises."
  },
  "FORGERY": {
    "sections": "463-477A",
    "describes": "Making a false document or electronic record to cause damage or to support a claim, forgery for cheating, using a forged document as genuine, possessing forged documents, counterfeiting seals, falsifying accounts.",
    "use_when": "Fake or altered documents, records or signatures, including electronic records."
  },
  "PROPERTY_MARKS_CURRENCY": {
    "sections": "478-489E",
    "describes": "Using false trade marks or property marks, counterfeiting marks, and counterfeiting or using forged currency notes and banknotes (489A-489E).",
    "use_when": "Fake trademarks, false marks on goods, forged currency notes."
  },
  "SERVICE_CONTRACT_BREACH": {
    "sections": "490-492",
    "describes": "Breach of contract of service during voyage or journey, desertion by a servant, offences of contract labour.",
    "use_when": "Employment-contract breaches that are criminal."
  },
  "MARRIAGE_RELATED": {
    "sections": "493-498",
    "describes": "Deceitful cohabitation under a false belief of marriage (493), bigamy (494-495), fraudulent marriage ceremony (496), adultery (497, struck down), enticing or taking away a married woman (498).",
    "use_when": "Marriage, cohabitation, enticing a married woman."
  },
  "DOMESTIC_CRUELTY": {
    "sections": "498A",
    "describes": "Cruelty by a husband or his relatives against a wife: harassment, conduct likely to drive her to suicide or cause serious injury, or harassment for dowry.",
    "use_when": "Marital cruelty or dowry harassment."
  },
  "DEFAMATION": {
    "sections": "499-502",
    "describes": "Harming someone's reputation by words, signs or visible representations; printing or selling defamatory matter.",
    "use_when": "Statements damaging someone's reputation."
  },
  "INTIMIDATION_INSULT": {
    "sections": "503-510",
    "describes": "Threatening a person with injury to their body, reputation or property to alarm them or force them to act (criminal intimidation, 503/506, including by electronic messages); intentionally insulting someone to provoke a breach of the peace (504); circulating statements that cause public mischief (505); anonymous threatening communications (507); words, gestures or acts intended to insult the modesty of a woman, or intrusion on a woman's privacy, which covers obscene or offensive remarks, messages, sounds or gestures directed at a woman or girl (509); public misconduct by an intoxicated person (510).",
    "use_when": "Threatening, abusive, insulting, harassing or offensive words or messages were directed at a person. Covers messages sent online or by phone. Section 509 applies to any female, of any age, as 'woman' in the IPC includes a girl."
  },
  "ATTEMPT": {
    "sections": "511",
    "describes": "Attempting to commit an offence punishable with imprisonment, where the attempt stops short of the offence.",
    "use_when": "An offence was tried but not completed. Always paired with the main offence."
  },
}

# Individual IPC sections whose category is not obvious from their chapter (statute facts, not case facts).
_IPC_OVERRIDES: Dict[str, Set[str]] = {
    "120A": {"CONSPIRACY"}, "120B": {"CONSPIRACY"},
    "498A": {"MARRIAGE_CRUELTY"}, "304B": {"HOMICIDE", "MARRIAGE_CRUELTY"},
    "34": {"COMMON_INTENTION"}, "149": {"COMMON_INTENTION"}, "511": {"ATTEMPT"},
    "354A": {"SEXUAL_OFFENCE"}, "354B": {"SEXUAL_OFFENCE"}, "354C": {"SEXUAL_OFFENCE"}, "354D": {"SEXUAL_OFFENCE"},
    "493": {"MARRIAGE_RELATED"}, "494": {"MARRIAGE_RELATED"}, "496": {"MARRIAGE_RELATED"}, "497": {"MARRIAGE_RELATED"},
    "468": {"FORGERY", "CHEATING"},          # forgery *for the purpose of cheating*
    "471": {"FORGERY"}, "420": {"CHEATING"},
    # Rash / negligent endangerment is both an offence against the body and a public-safety offence.
    "336": {"HURT", "PUBLIC_HEALTH_SAFETY_NUISANCE"}, "337": {"HURT", "PUBLIC_HEALTH_SAFETY_NUISANCE"},
    "338": {"HURT", "PUBLIC_HEALTH_SAFETY_NUISANCE"},
}

# Categories that frequently co-occur and carry little information about the nature of the case.
ANCILLARY = {"CONSPIRACY": 0.3, "ABETMENT": 0.3, "COMMON_INTENTION": 0.1, "ATTEMPT": 0.3}


def _parse_section_range(sections_str: str) -> Optional[Tuple[int, int]]:
    """
    Parse section range strings like '1-5', '299-311', '354A-354D' into (low, high).
    Returns None if not a numeric range.
    """
    parts = sections_str.split('-')
    if len(parts) != 2:
        return None
    
    # Extract numeric parts
    low_match = re.match(r'(\d+)', parts[0].strip())
    high_match = re.match(r'(\d+)', parts[1].strip())
    
    if low_match and high_match:
        return (int(low_match.group(1)), int(high_match.group(1)))
    return None


# Build _IPC_RANGES dynamically from IPC_FAMILY_REGISTRY
_IPC_RANGES: List[Tuple[int, int, str]] = []
for family_code, entry in IPC_FAMILY_REGISTRY.items():
    sections = entry.get("sections", "")
    # Parse patterns like "299-311", "354, 354A-354D", "375-377 and 354, 354A-354D"
    # Split by common delimiters and extract ranges
    for part in re.split(r'[,\s]+(?:and|incl\.|excl\.)?[,\s]+|[,\s]+', sections):
        part = part.strip()
        if not part or part in ('and', 'incl.', 'excl.'):
            continue
        
        range_tuple = _parse_section_range(part)
        if range_tuple:
            _IPC_RANGES.append((range_tuple[0], range_tuple[1], family_code))


def _numeric_part(section: str) -> Optional[int]:
    m = re.match(r"\s*(\d+)", str(section or ""))
    return int(m.group(1)) if m else None


def ipc_categories(section: str) -> Set[str]:
    sec = re.sub(r"[\s\-]", "", str(section or "").upper())
    base = re.sub(r"\(.*", "", sec)
    if base in _IPC_OVERRIDES:
        return set(_IPC_OVERRIDES[base])
    n = _numeric_part(base)
    if n is None:
        return set()
    cats = {c for lo, hi, c in _IPC_RANGES if lo <= n <= hi}
    return cats


_SPECIAL_ACT_CATEGORY: Dict[str, str] = {
    "NI ACT": "CHEQUE_DISHONOUR",
    "NEGOTIABLE INSTRUMENTS ACT": "CHEQUE_DISHONOUR",
    "NDPS": "NARCOTICS",
    "NDPS ACT": "NARCOTICS",
    "NARCOTIC DRUGS AND PSYCHOTROPIC SUBSTANCES ACT": "NARCOTICS",
    "PMLA": "MONEY_LAUNDERING",
    "PREVENTION OF MONEY LAUNDERING ACT": "MONEY_LAUNDERING",
    "PC ACT": "CORRUPTION",
    "PREVENTION OF CORRUPTION ACT": "CORRUPTION",
    "UAPA": "TERRORISM",
    "UNLAWFUL ACTIVITIES (PREVENTION) ACT": "TERRORISM",
    "ARMS ACT": "ARMS",
    "IT ACT": "CYBER",
    "INFORMATION TECHNOLOGY ACT": "CYBER",
    "COMPANIES ACT": "CORPORATE_FRAUD",
    "CUSTOMS ACT": "CUSTOMS_SMUGGLING",
    "GST ACT": "TAX_OFFENCE",
    "CENTRAL GOODS AND SERVICES TAX ACT": "TAX_OFFENCE",
    "FEMA": "FOREIGN_EXCHANGE",
    "FOREIGN EXCHANGE MANAGEMENT ACT": "FOREIGN_EXCHANGE",
    "DOWRY PROHIBITION ACT": "MARRIAGE_CRUELTY",
    "SC/ST ACT": "ATROCITIES",
    "SCHEDULED CASTES AND SCHEDULED TRIBES (PREVENTION OF ATROCITIES) ACT": "ATROCITIES",
    "POCSO": "SEXUAL_OFFENCE",
    "POCSO ACT": "SEXUAL_OFFENCE",
    "PROTECTION OF CHILDREN FROM SEXUAL OFFENCES ACT": "SEXUAL_OFFENCE",
    "JUVENILE JUSTICE ACT": "JUVENILE",
    "THE JUVENILE JUSTICE (CARE AND PROTECTION OF CHILDREN) ACT": "JUVENILE",
}

_SPECIAL_ACT_KEYWORDS: List[Tuple[str, str]] = [
    ("NEGOTIABLE INSTRUMENT", "CHEQUE_DISHONOUR"), ("NARCOTIC", "NARCOTICS"), ("MONEY LAUNDERING", "MONEY_LAUNDERING"),
    ("CORRUPTION", "CORRUPTION"), ("UNLAWFUL ACTIVITIES", "TERRORISM"), ("EXPLOSIVE", "ARMS"), ("ARMS ACT", "ARMS"),
    ("COMPANIES", "CORPORATE_FRAUD"), ("INFORMATION TECHNOLOGY", "CYBER"), ("CUSTOMS", "CUSTOMS_SMUGGLING"),
    ("GOODS AND SERVICES", "TAX_OFFENCE"), ("FOREIGN EXCHANGE", "FOREIGN_EXCHANGE"), ("DOWRY", "MARRIAGE_CRUELTY"),
    ("SEXUAL OFFENCES", "SEXUAL_OFFENCE"), ("SCHEDULED CASTES", "ATROCITIES"), ("JUVENILE", "JUVENILE"),
    ("POCSO", "SEXUAL_OFFENCE"), ("CHILDREN FROM SEXUAL", "SEXUAL_OFFENCE"), ("NDPS", "NARCOTICS"),
]


def special_act_category(act_norm: str) -> Optional[str]:
    a = (act_norm or "").upper()
    if a in _SPECIAL_ACT_CATEGORY:
        return _SPECIAL_ACT_CATEGORY[a]
    for kw, cat in _SPECIAL_ACT_KEYWORDS:
        if kw in a:
            return cat
    return None


def categories_for(act_norm: str, section: str) -> Set[str]:
    """Categories for a CANONICAL (old-regime) statute reference. Procedural/evidence provisions give none."""
    a = (act_norm or "").upper()
    if a in ("IPC", "BNS"):
        return ipc_categories(section)
    if a in ("CRPC", "BNSS", "IEA", "BSA"):
        return set()
    cat = special_act_category(a)
    return {cat} if cat else set()


def category_vector(refs: Iterable[Tuple[str, str, float]]) -> Dict[str, float]:
    """[(act, section, weight)] -> {category: weight}; ancillary categories are down-weighted."""
    vec: Dict[str, float] = {}
    for act, sec, w in refs:
        for c in categories_for(act, sec):
            vec[c] = max(vec.get(c, 0.0), w * ANCILLARY.get(c, 1.0))
    return vec


# Sibling categories share a "family": a cheating precedent is partly relevant to a forgery input, a murder
# precedent is not. Family membership is part of the structure of the criminal law, not of any case.
_FAMILIES: Dict[str, Set[str]] = {
    "FAMILY_FRAUD": {"CHEATING", "FORGERY", "FRAUDULENT_TRANSFER", "FRAUDULENT_DEEDS",
                     "MISAPPROPRIATION_BREACH_OF_TRUST", "BREACH_OF_TRUST", "CRIMINAL_MISAPPROPRIATION",
                     "CORPORATE_FRAUD", "CHEQUE_DISHONOUR", "TRADEMARK_CURRENCY", "PROPERTY_MARKS_CURRENCY"},
    "FAMILY_VIOLENCE": {"HOMICIDE", "HURT", "RESTRAINT_ASSAULT", "WRONGFUL_RESTRAINT_CONFINEMENT",
                        "CRIMINAL_FORCE_ASSAULT", "MISCARRIAGE_CHILD"},
    "FAMILY_SEXUAL": {"SEXUAL_OFFENCE", "KIDNAPPING_TRAFFICKING", "POCSO"},
    "FAMILY_PROPERTY_CRIME": {"THEFT", "EXTORTION", "ROBBERY_DACOITY", "STOLEN_PROPERTY", "MISCHIEF",
                              "TRESPASS", "CRIMINAL_TRESPASS"},
    "FAMILY_ECONOMIC_REGULATORY": {"MONEY_LAUNDERING", "CORRUPTION", "PUBLIC_SERVANT_OFFENCES",
                                   "TAX_OFFENCE", "FOREIGN_EXCHANGE", "CUSTOMS_SMUGGLING"},
    "FAMILY_MARRIAGE": {"MARRIAGE_CRUELTY", "MARRIAGE_RELATED"},
}
FAMILY_CREDIT = 0.5


def _expand(vec: Dict[str, float]) -> Dict[str, float]:
    out = dict(vec)
    for fam, members in _FAMILIES.items():
        w = max((vec[c] for c in members if c in vec), default=0.0)
        if w:
            out[fam] = max(out.get(fam, 0.0), FAMILY_CREDIT * w)
    return out


def category_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Weighted Jaccard over categories (+ family credit), 0..1. Murder vs cheating -> 0; cheating vs forgery -> >0."""
    if not a or not b:
        return 0.0
    a, b = _expand(a), _expand(b)
    keys = set(a) | set(b)
    inter = sum(min(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    union = sum(max(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    return inter / union if union else 0.0


# ---------------------------------------------------------------------------
# Gravity from punishment (replaces per-section caps such as "423 -> 0.4")
# ---------------------------------------------------------------------------

def max_years_from_text(text: Optional[str]) -> Optional[float]:
    """'7 Years' -> 7, 'Life Imprisonment (or up to 10 Years)' -> 99, 'Death' -> 99, None -> None."""
    if not text:
        return None
    t = str(text).lower()
    if "life" in t or "death" in t:
        return 99.0
    m = re.findall(r"(\d+(?:\.\d+)?)\s*(?:year|yr)", t)
    if m:
        return max(float(x) for x in m)
    m = re.findall(r"(\d+(?:\.\d+)?)\s*month", t)
    if m:
        return max(float(x) for x in m) / 12.0
    return None


def gravity_factor(max_years: Optional[float]) -> float:
    """
    0.4 for <=2 years, rising linearly to 1.0 at >=7 years; unknown punishment -> 1.0 (no penalty).
    7 years is the CrPC 41A / Arnesh Kumar threshold, so it is a legal boundary, not a tuned constant.
    """
    if max_years is None:
        return 1.0
    if max_years >= 7:
        return 1.0
    if max_years <= 2:
        return 0.4
    return 0.4 + 0.6 * (max_years - 2) / 5.0


# ---------------------------------------------------------------------------
# Default argument themes per category (generic anticipatory-bail factors + category-specific hooks)
# ---------------------------------------------------------------------------
GENERIC_THEMES = {
    "prosecution": [
        "need for custodial interrogation / recovery",
        "gravity of the allegations and role of the accused",
        "risk of tampering with evidence or influencing witnesses",
        "antecedents and likelihood of absconding",
    ],
    "defense": [
        "no need for custodial interrogation; accused cooperating with investigation",
        "false implication / mala fides; personal liberty under Article 21",
        "no flight risk; roots in the community",
        "conditions can adequately protect the investigation",
    ],
}

CATEGORY_THEMES: Dict[str, Dict[str, List[str]]] = {
    "CHEATING": {
        "prosecution": ["dishonest intention at the inception of the transaction"],
        "defense": ["civil / commercial dispute given a criminal colour; no dishonest intention at inception"],
    },
    "FORGERY": {
        "prosecution": ["authenticity of documents and trail of the forged instrument"],
        "defense": ["genuineness of documents; documents already seized so custody is unnecessary"],
    },
    "MISAPPROPRIATION_BREACH_OF_TRUST": {
        "prosecution": ["entrustment and dishonest misappropriation; tracing funds"],
        "defense": ["accounting dispute between parties; repayment / settlement"],
    },
    "HOMICIDE": {
        "prosecution": ["gravity of offence against the person; role in the incident; recovery of weapon"],
        "defense": ["role not attributable; no motive or recovery requiring custody"],
    },
    "NARCOTICS": {
        "prosecution": ["statutory bail restrictions and commercial quantity"],
        "defense": ["quantity and compliance with procedural safeguards"],
    },
    "MARRIAGE_CRUELTY": {
        "prosecution": ["allegations of cruelty / dowry demand and entrustment of stridhan"],
        "defense": ["omnibus allegations against relatives; matrimonial discord; arrest safeguards"],
    },
    "CHEQUE_DISHONOUR": {
        "prosecution": ["dishonour and statutory presumption"],
        "defense": ["compoundable commercial dispute; legally enforceable debt"],
    },
}


def themes_for(categories: Iterable[str]) -> Dict[str, List[str]]:
    out = {"prosecution": list(GENERIC_THEMES["prosecution"]), "defense": list(GENERIC_THEMES["defense"])}
    for c in categories:
        for role in out:
            for t in CATEGORY_THEMES.get(c, {}).get(role, []):
                if t not in out[role]:
                    out[role].insert(0, t)
    return out
