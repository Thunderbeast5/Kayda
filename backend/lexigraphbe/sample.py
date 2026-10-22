import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from .classifier_prefilter import (
        CandidateSectionMatch,
        StatuteClassifierPrefilter,
        _kb_section_keys,
        get_effective_knowledge_base,
        promote_csv_record_to_kb,
    )
    from .schemas.stage1 import LegalQueryObject, LegalConceptItem as LegalConcept, SubQueryItem as SubQuery
except ImportError:
    from lexigraphbe.classifier_prefilter import (
        CandidateSectionMatch,
        StatuteClassifierPrefilter,
        _kb_section_keys,
        get_effective_knowledge_base,
        promote_csv_record_to_kb,
    )
    from lexigraphbe.schemas.stage1 import LegalQueryObject, LegalConceptItem as LegalConcept, SubQueryItem as SubQuery

sections_db: List[Dict[str, Any]] = []


def _load_datasets():
    """Loads IPC and BNS dataset records into local in-memory index."""
    candidate_ipc = [
        Path("data/new/ipc_sections.csv"),
        Path("../data/new/ipc_sections.csv"),
        Path("c:/proj/MootCourt/data/new/ipc_sections.csv"),
        Path("c:/MootCourt/data/new/ipc_sections.csv"),
    ]
    candidate_bns = [
        Path("data/new/bns_sections1.csv"),
        Path("c:/proj/MootCourt/data/new/bns_sections1.csv"),
        Path("data/new/bns_sections_clean.csv"),
        Path("../data/new/bns_sections_clean.csv"),
        Path("c:/proj/MootCourt/data/new/bns_sections_clean.csv"),
        Path("c:/MootCourt/data/new/bns_sections_clean.csv"),
    ]

    # 1. Load IPC dataset
    for p in candidate_ipc:
        if p.exists():
            try:
                with open(p, mode="r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        sec_id = (row.get("Section") or "").strip()
                        offense = (row.get("Offense") or "").strip()
                        desc = (row.get("Description") or "").strip()
                        if sec_id:
                            clean_num = sec_id.replace("IPC_", "").strip()
                            full_text = f"{offense} {desc} {clean_num}".lower()
                            sections_db.append({
                                "identifier": f"IPC {clean_num}",
                                "statute": "IPC",
                                "section_number": clean_num,
                                "title": offense or f"IPC Section {clean_num}",
                                "chapter": "IPC Offence Chapter",
                                "full_text": full_text,
                                "tokens": set(re.findall(r"\w+", full_text)),
                            })
                break
            except Exception:
                pass

    # 2. Load BNS dataset
    for p in candidate_bns:
        if p.exists():
            try:
                with open(p, mode="r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        sec_num = (row.get("Section") or "").strip()
                        title = (row.get("Title") or "").strip()
                        desc = (row.get("Description") or "").strip()
                        chap = (row.get("Chapter") or "").strip()
                        keywords = (row.get("Keywords") or "").strip()
                        if sec_num:
                            full_text = f"{title} {desc} {chap} {keywords} {sec_num}".lower()
                            sections_db.append({
                                "identifier": f"BNS {sec_num}",
                                "statute": "BNS",
                                "section_number": sec_num,
                                "title": title or f"BNS Section {sec_num}",
                                "chapter": chap,
                                "full_text": full_text,
                                "tokens": set(re.findall(r"\w+", full_text)),
                            })
                break
            except Exception:
                pass


def shortlist_candidates_for_query(
    legal_query_obj: LegalQueryObject,
    top_k: int = 10,
    target_regime: Optional[str] = None,
) -> list[CandidateSectionMatch]:
    """
    Pre-filters and shortlists top candidate sections for LegalQueryObject.
    Executes 100% locally in Python code with ZERO LLM calls.

    Args:
        legal_query_obj: Validated Stage 1 LegalQueryObject.
        top_k: Maximum number of candidate sections to return (default 10).
        target_regime: Optional 'IPC + CrPC' or 'BNS + BNSS' filter.

    Returns:
        List of CandidateSectionMatch objects sorted by relevance score descending.
    """
    # Collect concept terms and sub-query terms
    concept_phrases = [c.concept.lower() for c in legal_query_obj.legal_concepts if c.concept]
    query_terms = []
    for phrase in concept_phrases:
        query_terms.extend(re.findall(r"\w+", phrase))

    for sq in legal_query_obj.sub_queries:
        query_terms.extend(re.findall(r"\w+", sq.query.lower()))
        if sq.concept:
            concept_phrases.append(sq.concept.lower())
            query_terms.extend(re.findall(r"\w+", sq.concept.lower()))

    # Filter out common stop words
    stop_words = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "by", "with", "is", "was", "are", "were"}
    filtered_terms = [t for t in query_terms if t not in stop_words and len(t) > 2]
    unique_query_terms = set(filtered_terms)

    # Concept-to-keyword vocabulary bridge:
    # Legal concept phrases from Stage 1 use formal language that doesn't match
    # section titles directly. Expand known concept phrases into trigger keywords.
    _CONCEPT_KEYWORD_BRIDGE = {
        # ── Existing entries (violence / property offences) ─────────────────────────
        "dishonest inducement to deliver property": ["extortion", "extorted", "blackmail", "threatened", "induced delivery"],
        "dishonestly inducing delivery": ["extortion", "blackmail", "threatened", "induced delivery"],
        "criminal intimidation": ["threat", "threatened", "intimidat", "warning"],
        "physical assault": ["assault", "beaten", "hurt", "pushed", "shoved", "slapped",
                            "physical violence", "physical abuse", "physical incident",
                            "kicked", "punched", "struck", "bodily harm", "manhandled"],
        "voluntarily causing hurt": ["assault", "hurt", "beaten", "physical violence",
                                    "pushed", "shoved", "slapped", "manhandled"],
        "theft": ["theft", "stolen", "stole", "took away"],
        "criminal breach of trust": ["stridhan", "ornaments", "property not returned", "entrustment"],
        "extortion": ["extortion", "extorted", "blackmail", "threatened", "demanded money"],
        "cheating": ["cheated", "defrauded", "deceived", "fraud"],
        "robbery": ["robbery", "robbed", "looted", "snatched by force"],
        "wrongful restraint": ["restrained", "blocked", "stopped forcibly"],
        "wrongful confinement": ["confined", "locked", "detained"],
        "house trespass": ["trespass", "entered illegally", "barged in"],
        "criminal trespass": ["trespass", "entered illegally", "encroached"],
        "mischief": ["damaged", "destroyed property", "mischief"],
        "abetment of suicide": ["abetment of suicide", "instigated suicide", "harassment led to suicide"],

        # ── Homicide / death offences ───────────────────────────────────────────────
        # Map death-related concept phrases to ensure proper section matching.
        # Critical: "sudden quarrel" + "death" should trigger Section 300 (Murder with Exception 4)
        # and Section 304 (Culpable homicide not amounting to murder), NOT Section 301 (transferred malice).
        "causing death": ["death", "killed", "murder", "culpable homicide", "homicide"],
        "causing death during quarrel": ["death", "killed", "murder", "culpable homicide", "sudden quarrel", "sudden fight", "heat of passion"],
        "causing death during sudden quarrel": ["death", "killed", "murder", "culpable homicide", "sudden quarrel", "sudden fight", "heat of passion", "provocation"],
        "death in sudden fight": ["death", "killed", "murder", "culpable homicide", "sudden quarrel", "sudden fight", "heat of passion"],
        "culpable homicide": ["death", "killed", "murder", "culpable homicide"],

        # ── Forgery / document fraud ────────────────────────────────────────────────
        # Maps Stage 1 concept labels for document-fraud cases to trigger keywords that
        # match 463/465/467/468/471/423 entries in the KB and CSV.
        "forgery": ["forgery", "forged document", "fake signature", "fabricated", "false document"],
        "forgery of document": ["forgery", "forged document", "fabricated document", "false document"],
        "forgery of valuable security": [
            "forged document", "forgery", "sale deed", "title deed", "ownership document",
            "forged deed", "fake deed", "valuable security",
        ],
        "fraudulent document": ["forged document", "forgery", "false document", "fabricated", "fake deed"],
        "forged ownership documents": [
            "forged document", "forgery", "ownership document", "title deed", "sale deed",
            "fake ownership", "fabricated deed", "forged deed",
        ],
        "fraudulent deed": [
            "fraudulent deed", "false deed", "forged deed", "sale deed",
            "false consideration", "fake sale deed", "fraudulent sale deed",
        ],
        "fraudulent sale deed": [
            "fraudulent deed", "false deed", "forged deed", "sale deed",
            "false consideration", "fraudulent transfer",
        ],
        "making false document": ["forgery", "forged document", "false document", "fabricated"],
        "using forged document": ["forged document", "used forged document", "submitted fake document"],

        # ── Dishonest property transfer (Stage 1 concept labels for land-fraud) ─────
        # Stage 1 uses "Dishonest Transfer", "Fraudulent Sale", "Property Fraud" as
        # concept labels.  Map these to vocabulary that triggers 420 and 423.
        "dishonest transfer": [
            "dishonest transfer", "fraudulent transfer", "cheated", "defrauded",
            "fraudulent sale", "dishonestly transferred", "fraudulently transferred",
        ],
        "dishonest transfer of property": [
            "dishonest transfer", "fraudulent transfer", "cheated", "defrauded",
            "fraudulent sale", "property fraud", "false representation",
        ],
        "dishonest transfer of immovable property": [
            "dishonest transfer", "fraudulent transfer", "cheated", "defrauded",
            "fraudulent sale", "false representation", "dishonestly transferred",
        ],
        "fraudulent transfer": [
            "fraudulent transfer", "fraudulent sale", "cheated", "defrauded",
            "dishonest transfer", "fraudulently transferred",
        ],
        "fraudulent property transfer": [
            "fraudulent transfer", "cheated", "defrauded", "fraudulent sale",
            "false representation", "property fraud",
        ],
        "property fraud": [
            "cheated", "defrauded", "deceived", "fraud", "fraudulent transfer",
            "dishonest transfer", "property fraud",
        ],
        "fraudulent sale": [
            "fraudulent sale", "cheated", "defrauded", "fraudulent transfer",
            "sale deed", "fraudulent deed",
        ],

        # ── Anticipatory bail / bail procedural context ─────────────────────────────
        # Ensure the procedural enabling section is matched when Stage 1 identifies
        # the legal proceeding context as "Anticipatory Bail Application".
        "anticipatory bail": ["anticipatory bail", "pre-arrest bail", "apprehension of arrest"],
        "anticipatory bail application": ["anticipatory bail", "pre-arrest bail", "seeking anticipatory"],
        "bail application": ["anticipatory bail", "bail", "pre-arrest bail"],
    }
    full_concepts_lower = " ".join(concept_phrases).lower()
    for concept_key, extra_keywords in _CONCEPT_KEYWORD_BRIDGE.items():
        if concept_key in full_concepts_lower:
            unique_query_terms.update(extra_keywords)

    if not unique_query_terms or not sections_db:
        return []

    # Filter database by legal regime if requested
    regime_filter = None
    regime_str = target_regime or legal_query_obj.legal_regime or ""
    if "BNS" in regime_str.upper():
        regime_filter = "BNS"
    elif "IPC" in regime_str.upper():
        regime_filter = "IPC"

    matches: List[Tuple[Dict[str, Any], float, List[str]]] = []

    query_full_text = " ".join(concept_phrases) + " " + " ".join(unique_query_terms)

    for record in sections_db:
        if regime_filter and record["statute"] != regime_filter:
            continue

        sec_num = record["section_number"].upper()
        sec_statute = record["statute"].upper()

        # 1. Fatal Disqualification Check (reject 304B/307/376 if mandatory triggers missing)
        disqualified, _, _ = StatuteClassifierPrefilter.evaluate_fatal_disqualification(sec_num, sec_statute, query_full_text)
        if disqualified:
            continue

        record_text = record["full_text"]
        record_title = record["title"].lower()

        matched = [term for term in unique_query_terms if term in record_text]

        # 2. Knowledge Base Factual Trigger Matching (static + dynamic KB)
        kb_boost = 0.0
        for rule in get_effective_knowledge_base():
            rule_sec = rule.bns_equivalent if sec_statute == "BNS" else rule.section
            if sec_num == rule_sec.upper() or sec_num == rule.section.upper():
                if rule.factual_triggers:
                    if any(trig in query_full_text.lower() for trig in rule.factual_triggers):
                        kb_boost += 2.5
                break

        if not matched and kb_boost == 0.0:
            continue

        # Calculate base term score
        term_score = len(matched) / (len(unique_query_terms) ** 0.5) if matched else 0.5

        # Boost exact concept phrase matches, title matches, and KB triggers
        phrase_boost = 1.0 + kb_boost
        for phrase in concept_phrases:
            if len(phrase) > 3:
                if phrase in record_text:
                    phrase_boost += 1.5
                if phrase in record_title:
                    phrase_boost += 2.0
                words = [w for w in re.findall(r"\w+", phrase) if w not in stop_words]
                title_matches = [w for w in words if w in record_title]
                if title_matches:
                    phrase_boost += (len(title_matches) * 0.5)

        final_score = min(1.0, round((term_score * phrase_boost) / 4.0, 2))
        matches.append((record, final_score, matched))

    # Sort matches by score descending
    matches.sort(key=lambda x: x[1], reverse=True)

    results = []
    seen_identifiers = set()
    existing_kb_keys = _kb_section_keys()

    for rec, score, matched_list in matches[:top_k]:
        if rec["identifier"] not in seen_identifiers:
            seen_identifiers.add(rec["identifier"])

            # --- Dynamic KB promotion ------------------------------------------
            # If this CSV record has no SectionRule yet, auto-promote it so that
            # future queries get full KB-quality verification for this section.
            candidate_key = f"{rec['statute'].upper()}_{rec['section_number'].upper()}"
            if candidate_key not in existing_kb_keys:
                try:
                    from .statute_repository import StatuteRepository
                    fs_meta = StatuteRepository.get_instance().get_first_schedule_metadata(
                        rec["section_number"], rec["statute"]
                    )
                except Exception:
                    fs_meta = None
                promoted = promote_csv_record_to_kb(
                    csv_record=rec,
                    matched_query_terms=matched_list,
                    first_schedule_meta=fs_meta,
                )
                if promoted:
                    # Refresh key set so subsequent hits in the same loop see it
                    existing_kb_keys.add(candidate_key)
            # -------------------------------------------------------------------

            results.append(
                CandidateSectionMatch(
                    section_identifier=rec["identifier"],
                    statute=rec["statute"],
                    section_number=rec["section_number"],
                    title=rec["title"],
                    chapter=rec["chapter"],
                    score=score,
                    matched_terms=matched_list[:5],
                )
            )

    return results

if __name__ == "__main__":
    _load_datasets()
    dummy_query = LegalQueryObject(
        legal_concepts=[LegalConcept(concept="medical negligence", confidence=0.9)],
        sub_queries=[SubQuery(id="SQ1", concept="medical negligence", query="senior medical officer anticipatory bail death of patient")],
        legal_regime="BNS + BNSS",
    )
    res = shortlist_candidates_for_query(legal_query_obj=dummy_query)
    print(f"Shortlisted {len(res)} candidates.")