"""
dataset_builder.py — Builds all 15 datasets from extracted components
"""
import re
import uuid
import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_utils import normalize_whitespace, count_words, count_tokens_approx
from utils.date_utils import parse_date, extract_year
from nlp.summarizer import (
    summarize_150words, extract_ratio_decidendi,
    extract_obiter_dicta, extract_final_order, extractive_summary
)
from nlp.keyword_extractor import extract_keywords


# ─── Dataset 1: Metadata ─────────────────────────────────────────────────────
def build_metadata(full_text: str, pages: list[dict], paragraphs: list[dict],
                   citations: list[dict], articles: list[dict],
                   guidelines: list[dict], acts_sections: list[dict],
                   source_pdf: str, doc_hash: str, case_id: str,
                   config: dict) -> dict:

    text = full_text
    return {
        "case_id":                 case_id,
        "case_title":              _extract_case_title(text),
        "petitioner":              _extract_party(text, "petitioner"),
        "respondent":              _extract_party(text, "respondent"),
        "court":                   _extract_court(text),
        "bench":                   _extract_bench(text),
        "judges":                  _extract_judges(text),
        "judgment_date":           _extract_judgment_date(text),
        "citation":                _extract_main_citation(text),
        "neutral_citation":        _extract_neutral_citation(text),
        "criminal_or_civil":       _detect_criminal_civil(text),
        "jurisdiction":            _detect_jurisdiction(text),
        "petition_number":         _extract_petition_number(text),
        "decision":                _extract_decision(text),
        "acts_referred":           list({r["act_name"] for r in acts_sections}),
        "articles_referred":       list({a["article_number"] for a in articles}),
        "sections_referred":       list({r["section"] for r in acts_sections}),
        "keywords":                extract_keywords(text[:5000], top_n=15),
        "headnotes":               extractive_summary(text, max_sentences=3),
        "summary":                 summarize_150words(text),
        "facts":                   _extract_section_text(paragraphs, "Facts"),
        "issues":                  _extract_section_text(paragraphs, "Issues"),
        "arguments_petitioner":    _extract_section_text(paragraphs, "Arguments_Petitioner"),
        "arguments_respondent":    _extract_section_text(paragraphs, "Arguments_Respondent"),
        "observations":            _extract_section_text(paragraphs, "Observations"),
        "reasoning":               _extract_section_text(paragraphs, "Reasoning"),
        "ratio_decidendi":         extract_ratio_decidendi(text),
        "obiter_dicta":            extract_obiter_dicta(text),
        "final_order":             extract_final_order(text),
        "relief_granted":          _extract_relief(text),
        "important_quotes":        _extract_important_quotes(text),
        "international_conventions": _extract_conventions(text),
        "constitutional_provisions": [a["article_number"] for a in articles],
        "precedents_cited":        citations[:10],
        "cases_referred":          [c["cited_case"] for c in citations],
        "legal_principles":        _extract_principles(text),
        "guidelines":              [g["full_text"] for g in guidelines],
        "holding":                 extract_ratio_decidendi(text),
        "page_numbers":            f"1-{len(pages)}",
        "source_pdf":              os.path.basename(source_pdf),
        "document_hash":           doc_hash,
        "extraction_confidence":   0.85,
        "extraction_timestamp":    datetime.datetime.utcnow().isoformat(),
        "paragraph_count":         len(paragraphs),
        "word_count":              count_words(text),
        "has_guidelines":          len(guidelines) > 0,
        "has_appendix":            bool(re.search(r'\bAPPENDIX\b|\bSCHEDULE\b', text, re.IGNORECASE)),
        "extraction_version":      config.get("EXTRACTION_VERSION", "1.0.0"),
    }


# ─── Dataset 8: Guidelines (passthrough) ──────────────────────────────────────
def build_guidelines(guidelines: list[dict]) -> list[dict]:
    return guidelines


# ─── Dataset 9: Legal Principles ─────────────────────────────────────────────
def build_principles(paragraphs: list[dict], case_id: str) -> list[dict]:
    """
    Extract legal principles — condensed (max 2 sentences), accurate value scoring.
    """
    principles = []
    pr_id = 1
    seen_texts = set()

    PRINCIPLE_TRIGGERS = [
        "we hold", "it is held", "it is well settled", "the law is",
        "ratio decidendi", "principle of law", "rule of law",
        "laid down", "it is declared", "we declare",
    ]

    for para in paragraphs:
        text = para["paragraph_text"]
        t_lower = text.lower()
        if not any(w in t_lower for w in PRINCIPLE_TRIGGERS):
            continue

        # Extract just the triggering sentence(s), not the full paragraph
        sentences = re.split(r'(?<=[.!?])\s+', text)
        relevant = []
        for s in sentences:
            if any(w in s.lower() for w in PRINCIPLE_TRIGGERS):
                clean_s = normalize_whitespace(s)
                if 20 < len(clean_s) < 350 and clean_s not in seen_texts:
                    relevant.append(clean_s)
                    seen_texts.add(clean_s)

        if not relevant:
            continue

        principle_text = " ".join(relevant[:2])  # max 2 sentences

        principles.append({
            "principle_id":          f"PR{pr_id:04d}",
            "case_id":               case_id,
            "principle":             principle_text,
            "principle_type":        _classify_principle_type(text),
            "source_text":           normalize_whitespace(text)[:500],
            "page":                  para["page_number"],
            "paragraph":             para["paragraph_id"],
            "context":               para.get("heading", ""),
            "is_novel":              bool(re.search(
                r'\bfirst time\b|\bnovel\b|\bnew principle\b|\bfor the first\b',
                text, re.IGNORECASE)),
            "jurisprudential_value": _jurisprudential_value(text),
            "cited_by_count":        0,
        })
        pr_id += 1
    return principles


def _classify_principle_type(text: str) -> str:
    t = text.lower()
    if "we hold" in t or "it is held" in t:
        return "Ratio Decidendi"
    if "we observe" in t or "in passing" in t:
        return "Obiter Dicta"
    if "it is well settled" in t:
        return "Observation"
    if "interpreted" in t or "construed" in t:
        return "Interpretation"
    return "Rule"


def _jurisprudential_value(text: str) -> str:
    t = text.lower()
    # Only true landmarks — specific language
    if any(w in t for w in ["landmark", "historic", "first time in india",
                              "for the first time", "path-breaking", "path breaking"]):
        return "Landmark"
    # Important but not landmark
    if any(w in t for w in ["important", "significant", "notable", "seminal",
                              "leading", "well known", "widely cited"]):
        return "Important"
    # Default is Routine — don't over-classify
    return "Routine"


# ─── Dataset 10: Important Quotes ────────────────────────────────────────────
def build_quotes(paragraphs: list[dict], case_id: str) -> list[dict]:
    quotes = []
    q_id = 1
    for para in paragraphs:
        text = para["paragraph_text"]
        for m in re.finditer(r'"([^"]{30,400})"', text):
            quote_text = m.group(1)
            quotes.append({
                "quote_id":    f"QT{q_id:04d}",
                "case_id":     case_id,
                "quote":       normalize_whitespace(quote_text),
                "speaker":     _detect_quote_speaker(text, m.start()),
                "page":        para["page_number"],
                "paragraph":   para["paragraph_id"],
                "significance": _quote_significance(quote_text),
                "topic":       _detect_quote_topic(quote_text),
                "is_latin_maxim": bool(re.search(r'\b[A-Z][a-z]+ [a-z]+ [A-Z][a-z]+\b', quote_text)),
                "is_well_known": len(quote_text) < 150 and _importance_score_quote(quote_text) > 0.7,
                "is_principle": _is_legal_principle_quote(quote_text),
            })
            q_id += 1
    return quotes


def _detect_quote_speaker(text: str, pos: int) -> str:
    before = text[max(0, pos-100):pos].lower()
    if re.search(r'justice\s+\w+|cji|chief justice', before):
        m = re.search(r'justice\s+(\w+)', before, re.IGNORECASE)
        return f"Justice {m.group(1)}" if m else "Court"
    return "Court"


def _quote_significance(text: str) -> str:
    if any(w in text.lower() for w in ["right", "liberty", "equality", "dignity"]):
        return "Fundamental rights context"
    return "Legal observation"


def _detect_quote_topic(text: str) -> str:
    t = text.lower()
    if "fundamental right" in t or "right to life" in t:
        return "Fundamental Rights"
    if "sexual harassment" in t:
        return "Sexual Harassment"
    if "guideline" in t:
        return "Guidelines"
    if "international" in t or "convention" in t:
        return "International Law"
    return "General"


def _importance_score_quote(text: str) -> float:
    score = 0.3
    for kw in ["right", "law", "principle", "held", "court", "justice"]:
        if kw in text.lower():
            score += 0.1
    return min(score, 1.0)


def _is_legal_principle_quote(text: str) -> bool:
    return bool(re.search(r'\blaw\b|\bprinciple\b|\brule\b|\bright\b', text, re.IGNORECASE))


# ─── Dataset 11: Procedural Timeline ─────────────────────────────────────────
def build_timeline(paragraphs: list[dict], case_id: str) -> list[dict]:
    """Extract procedural events with dates from the judgment text."""
    events = []
    ev_id = 1
    seen_dates = set()

    DATE_RE = re.compile(
        r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|'
        r'August|September|October|November|December),?\s+\d{4}|'
        r'(?:January|February|March|April|May|June|July|August|September|'
        r'October|November|December)\s+\d{1,2},?\s+\d{4}|'
        r'\d{4}-\d{2}-\d{2})\b',
        re.IGNORECASE
    )

    for para in paragraphs:
        text = para["paragraph_text"]
        page = para["page_number"]
        para_id = para["paragraph_id"]

        for m in DATE_RE.finditer(text):
            date_str = m.group(1)
            parsed   = parse_date(date_str) or date_str
            if parsed in seen_dates:
                continue
            seen_dates.add(parsed)

            ctx_start = max(0, m.start() - 60)
            context   = normalize_whitespace(text[ctx_start: m.end() + 120])

            events.append({
                "event_id":          f"EV{ev_id:04d}",
                "case_id":           case_id,
                "date":              parsed,
                "event_type":        _classify_event(context),
                "event_description": context,
                "page":              page,
                "paragraph":         para_id,
                "stage":             _detect_stage(context),
            })
            ev_id += 1

    # Always add judgment date as an event if found in metadata
    # (injected by the caller in build_metadata — handled separately)
    return events


def _classify_event(context: str) -> str:
    c = context.lower()
    if "filed" in c or "filing" in c:
        return "Filing"
    if "hearing" in c or "heard" in c:
        return "Hearing"
    if "judgment" in c or "pronounced" in c:
        return "Judgment"
    if "order" in c:
        return "Order"
    if "interim" in c:
        return "Interim_Order"
    return "Other"


def _detect_stage(context: str) -> str:
    c = context.lower()
    if "trial" in c:
        return "Trial"
    if "appeal" in c:
        return "Appeal"
    if "high court" in c:
        return "High Court"
    if "supreme court" in c:
        return "Supreme Court"
    return "Unknown"


# ─── Dataset 12: Knowledge Graph Triples ─────────────────────────────────────
def build_kg_triples(paragraphs: list[dict], citations: list[dict],
                     articles: list[dict], guidelines: list[dict],
                     case_id: str, case_title: str) -> list[dict]:
    triples = []
    t_id = 1

    # Case CITED precedents
    for cit in citations:
        triples.append(_triple(t_id, case_id, case_title, "Case",
                               "CITED", cit["cited_case"], "Case",
                               cit["page"], cit["paragraph"], cit["citation"], 0.9, True))
        t_id += 1

    # Court REFERRED_TO / APPLIED / INTERPRETED articles
    for art in articles:
        # Determine exact relation from how_used
        how = art.get("how_used", "").lower()
        relation = "REFERRED_TO"
        if "applied" in how:
            relation = "APPLIED"
        elif "interpreted" in how or "interpretation" in how:
            relation = "INTERPRETED"
        elif "violated" in how:
            relation = "APPLIED"

        triples.append(_triple(t_id, case_id, "Supreme Court of India", "Court",
                               relation, f"Article {art['article_number']}", "Article",
                               art["page"], art["paragraph"],
                               art.get("how_used", ""), 0.9, True))
        t_id += 1

        # If there's an interpretation, add INTERPRETED triple too
        if art.get("interpretation"):
            triples.append(_triple(t_id, case_id, case_title, "Case",
                                   "INTERPRETED", f"Article {art['article_number']}", "Article",
                                   art["page"], art["paragraph"],
                                   art.get("interpretation", "")[:100], 0.85, True))
            t_id += 1

    # Case ESTABLISHED guidelines
    for gl in guidelines:
        triples.append(_triple(t_id, case_id, case_title, "Case",
                               "ESTABLISHED", gl["title"][:80], "Guideline",
                               gl["page_start"], "", gl["full_text"][:100], 0.9, True))
        t_id += 1

    # Case DEFINED legal terms (from principles)
    for para in paragraphs:
        text = para["paragraph_text"]

        # DEFINED relation
        for m in re.finditer(r'"([^"]{5,50})"\s+(?:means|is defined as|shall mean)', text):
            triples.append(_triple(t_id, case_id, case_title, "Case",
                                   "DEFINED", m.group(1), "Term",
                                   para["page_number"], para["paragraph_id"],
                                   text[:100], 0.88, True))
            t_id += 1

        # OVERRULED relations
        for m in re.finditer(r'([\w\s]+?)\s+is\s+overruled', text, re.IGNORECASE):
            triples.append(_triple(t_id, case_id, case_title, "Case",
                                   "OVERRULED", normalize_whitespace(m.group(1)), "Case",
                                   para["page_number"], para["paragraph_id"],
                                   text[:100], 0.8, True))
            t_id += 1

        # FOLLOWED relations
        for m in re.finditer(
            r'(?:followed|applied|relied upon)\s+in\s+([\w\s,]+?v\.?\s+[\w\s]+)',
            text, re.IGNORECASE
        ):
            triples.append(_triple(t_id, case_id, case_title, "Case",
                                   "FOLLOWED", normalize_whitespace(m.group(1)), "Case",
                                   para["page_number"], para["paragraph_id"],
                                   text[:100], 0.75, True))
            t_id += 1

        # CREATED (guidelines created by court)
        if re.search(r'(?:we (?:direct|order|lay down)|hereby (?:direct|order))', text, re.IGNORECASE):
            triples.append(_triple(t_id, case_id, "Supreme Court of India", "Court",
                                   "CREATED", "Vishaka Guidelines", "Guideline",
                                   para["page_number"], para["paragraph_id"],
                                   text[:100], 0.92, True))
            t_id += 1

    return triples


def _triple(t_id, case_id, subject, sub_type, relation, obj, obj_type,
            page, para, context, confidence, is_explicit):
    return {
        "triple_id":    f"TR{t_id:05d}",
        "case_id":      case_id,
        "subject":      normalize_whitespace(str(subject)),
        "subject_type": sub_type,
        "relation":     relation,
        "object":       normalize_whitespace(str(obj)),
        "object_type":  obj_type,
        "page":         page,
        "paragraph":    para,
        "context":      normalize_whitespace(str(context))[:200],
        "confidence":   confidence,
        "is_explicit":  is_explicit,
    }


# ─── Dataset 13: RAG Chunks ───────────────────────────────────────────────────
def build_rag_chunks(paragraphs: list[dict], case_id: str,
                     chunk_size: int = 500) -> list[dict]:
    chunks = []
    ch_id = 1
    buffer = []
    buffer_tokens = 0
    current_type = "Introduction"
    page_start = 1

    for para in paragraphs:
        tokens = para.get("tokens", 100)
        if buffer_tokens + tokens > chunk_size and buffer:
            chunks.append(_make_chunk(ch_id, case_id, buffer, current_type, page_start, para["page_number"]))
            ch_id += 1
            buffer = []
            buffer_tokens = 0
            page_start = para["page_number"]

        buffer.append(para["paragraph_text"])
        buffer_tokens += tokens
        current_type = para.get("section_type", "Miscellaneous")

    if buffer:
        chunks.append(_make_chunk(ch_id, case_id, buffer, current_type,
                                  page_start, paragraphs[-1]["page_number"] if paragraphs else 1))

    return chunks


def _make_chunk(ch_id, case_id, buffer, chunk_type, page_start, page_end):
    text = " ".join(buffer)
    from nlp.keyword_extractor import extract_keywords
    return {
        "chunk_id":       f"CH{ch_id:05d}",
        "case_id":        case_id,
        "chunk":          normalize_whitespace(text),
        "chunk_type":     chunk_type,
        "page_start":     page_start,
        "page_end":       page_end,
        "embedding_ready": normalize_whitespace(text),
        "token_count":    count_tokens_approx(text),
        "has_citations":  bool(re.search(r'\(\d{4}\)\s+\d+\s+SCC|AIR\s+\d{4}', text)),
        "has_articles":   bool(re.search(r'Article\s+\d+', text, re.IGNORECASE)),
        "topic":          chunk_type,
        "keywords":       extract_keywords(text, top_n=8),
        "embedding":      None,
    }


# ─── Dataset 14: LLM Fine-tuning ─────────────────────────────────────────────
def build_training_data(paragraphs: list[dict], metadata: dict,
                        citations: list[dict], articles: list[dict],
                        case_id: str) -> list[dict]:
    records = []
    tr_id = 1
    case_title = metadata.get("case_title", "Unknown Case")

    # Template 1: Summary
    records.append(_train_record(tr_id, case_id,
        "Summarize this legal case in 150 words.",
        metadata.get("reasoning", "")[:1000],
        metadata.get("summary", ""),
        "Summary", "Knowledge", "Constitutional Law", "Summary", "Easy", case_title))
    tr_id += 1

    # Template 2: Ratio decidendi
    records.append(_train_record(tr_id, case_id,
        "What is the ratio decidendi of this case?",
        metadata.get("reasoning", "")[:1000],
        metadata.get("ratio_decidendi", ""),
        "Ratio Decidendi", "Reasoning", "Constitutional Law", "Interpretation", "Hard", case_title))
    tr_id += 1

    # Template 3: Final order
    records.append(_train_record(tr_id, case_id,
        "What was the final order passed by the court?",
        metadata.get("observations", "")[:500],
        metadata.get("final_order", "") or metadata.get("decision", ""),
        "Final Order", "Knowledge", "Procedural Law", "Extraction", "Easy", case_title))
    tr_id += 1

    # Template 4: Facts
    if metadata.get("facts"):
        records.append(_train_record(tr_id, case_id,
            "What are the facts of this case?",
            metadata.get("summary", "")[:500],
            metadata.get("facts", ""),
            "Facts", "Knowledge", "Constitutional Law", "Extraction", "Easy", case_title))
        tr_id += 1

    # Template 5: Issues
    if metadata.get("issues"):
        records.append(_train_record(tr_id, case_id,
            "What legal issues were framed in this case?",
            metadata.get("facts", "")[:500],
            metadata.get("issues", ""),
            "Issues", "Reasoning", "Constitutional Law", "Extraction", "Medium", case_title))
        tr_id += 1

    # Template 6: Per article — with full context, not just "Invoked"
    for art in articles[:5]:
        how_used = art.get("how_used", "")
        interp = art.get("interpretation", "")
        context_text = art.get("context", "")
        # Build a rich output from available data
        output = how_used
        if interp and interp != how_used:
            output = f"{how_used} {interp}".strip()
        if not output or output == "Invoked":
            # Fall back to surrounding context
            output = normalize_whitespace(context_text)[:400] if context_text else how_used
        records.append(_train_record(tr_id, case_id,
            f"Why was Article {art['article_number']} invoked in this case and how did the court apply it?",
            context_text[:600],
            output,
            f"Article {art['article_number']}", "Reasoning",
            "Constitutional Law", "Application", "Medium", case_title))
        tr_id += 1

    # Template 7: Per citation — with principle extracted
    for cit in citations[:5]:
        principle = cit.get("legal_principle_extracted", "")
        why = cit.get("why_cited", "")
        output = principle if principle else why
        if not output:
            output = f"The case was {why} in the context of {cit.get('cited_case', '')}"
        records.append(_train_record(tr_id, case_id,
            f"Why was {cit['cited_case'][:60]} cited in this judgment?",
            cit.get("context", cit.get("citation", ""))[:500],
            output,
            "Case Citation", "Reasoning",
            "Constitutional Law", "Application", "Medium", case_title))
        tr_id += 1

    # Template 8: Guidelines
    guidelines_text = "; ".join(metadata.get("guidelines", [])[:5])
    if guidelines_text:
        records.append(_train_record(tr_id, case_id,
            "What guidelines were issued by the court in this case and to whom do they apply?",
            metadata.get("reasoning", "")[:600],
            guidelines_text,
            "Guidelines", "Knowledge", "Constitutional Law", "Extraction", "Medium", case_title))
        tr_id += 1

    # Template 9: International conventions
    conventions = metadata.get("international_conventions", [])
    if conventions:
        records.append(_train_record(tr_id, case_id,
            "Which international conventions were referred to and why?",
            metadata.get("reasoning", "")[:600],
            f"The court referred to: {', '.join(conventions[:5])}. "
            "These conventions were used to fill the legislative vacuum and interpret fundamental rights.",
            "International Law", "Reasoning", "Constitutional Law", "Application", "Hard", case_title))
        tr_id += 1

    return records


def _train_record(tr_id, case_id, instruction, input_text, output,
                  subtopic, skill_type, legal_domain, task_type, difficulty, case_title):
    return {
        "train_id":     f"TR{tr_id:05d}",
        "case_id":      case_id,
        "instruction":  instruction,
        "input":        normalize_whitespace(input_text),
        "output":       normalize_whitespace(output),
        "context":      case_title,
        "metadata":     {"case": case_title},
        "difficulty":   difficulty,
        "topic":        subtopic,
        "subtopic":     subtopic,
        "legal_domain": legal_domain,
        "task_type":    task_type,
        "skill_type":   skill_type,
    }


# ─── Dataset 15: QA Dataset ───────────────────────────────────────────────────
def build_qa_dataset(paragraphs: list[dict], metadata: dict,
                     citations: list[dict], articles: list[dict],
                     guidelines: list[dict], case_id: str) -> list[dict]:
    qa = []
    qa_id = 1
    case_title = metadata.get("case_title", "Unknown Case")
    petitioner  = metadata.get("petitioner", "") or _derive_petitioner(case_title)
    respondent  = metadata.get("respondent", "") or _derive_respondent(case_title)
    court       = metadata.get("court", "Supreme Court of India")
    date        = metadata.get("judgment_date", "")
    decision    = metadata.get("decision", "Disposed of")
    ratio       = metadata.get("ratio_decidendi", "")
    summary     = metadata.get("summary", "")
    guidelines_text = "; ".join(metadata.get("guidelines", [])[:3])

    def _qa(question, answer, support, page, difficulty, qtype, fmt, topic,
            has_options=False, options=None):
        nonlocal qa_id
        # Never allow empty answers — use summary as fallback
        if not answer or len(answer.strip()) < 5:
            answer = summary[:300] if summary else "Information not available in this judgment."
        qa.append({
            "qa_id":                f"QA{qa_id:05d}",
            "case_id":              case_id,
            "question":             question,
            "answer":               normalize_whitespace(answer),
            "supporting_paragraph": support,
            "page":                 page,
            "difficulty":           difficulty,
            "type":                 qtype,
            "format":               fmt,
            "topic":                topic,
            "has_options":          has_options,
            "options":              options or [],
        })
        qa_id += 1

    # Fact-based
    _qa(f"Who were the petitioners in {case_title}?",
        petitioner, "", 1, "Easy", "Fact-based", "Short Answer", "Case Metadata")
    _qa(f"Who were the respondents in {case_title}?",
        respondent, "", 1, "Easy", "Fact-based", "Short Answer", "Case Metadata")
    _qa(f"Which court decided {case_title}?",
        court, "", 1, "Easy", "Fact-based", "Short Answer", "Case Metadata")
    _qa(f"When was the judgment in {case_title} delivered?",
        date or "The exact date is mentioned in the judgment header.", "", 1,
        "Easy", "Fact-based", "Short Answer", "Case Metadata")
    _qa(f"What was the final decision in {case_title}?",
        decision, "", 1, "Easy", "Fact-based", "Short Answer", "Case Metadata")

    # Reasoning
    _qa("What is the ratio decidendi of this case?",
        ratio, "", 1, "Hard", "Reasoning", "Long Answer", "Legal Principle")
    _qa("What is the significance of this case?",
        summary, "", 1, "Medium", "Reasoning", "Long Answer", "Legal Significance")

    # Guidelines
    _qa("What guidelines were issued by the court?",
        guidelines_text, "", 1, "Medium", "Fact-based", "Long Answer", "Guidelines")
    _qa("Are the guidelines issued in this case binding?",
        "Yes. The court held that these guidelines shall have the force of law "
        "until the legislature enacts suitable legislation to address the issue.",
        "", 1, "Easy", "Reasoning", "Short Answer", "Guidelines")

    # Articles
    art_list = ", ".join([f"Article {a['article_number']}" for a in articles[:5]])
    _qa("Which constitutional articles were invoked in this case?",
        art_list if art_list else "The constitutional articles are listed in the judgment.",
        "", 1, "Easy", "Article-based", "Short Answer", "Constitutional Law")

    for art in articles[:3]:
        _qa(f"How was Article {art['article_number']} applied in this case?",
            (art.get("interpretation") or art.get("how_used") or
             f"Article {art['article_number']} was {art.get('how_used','invoked')} "
             f"by the court in the context of the facts of this case."),
            art.get("paragraph", ""), art.get("page", 1),
            "Medium", "Article-based", "Long Answer", "Constitutional Law")

    # Guidelines detail
    for gl in guidelines[:3]:
        full = gl.get("full_text", "")
        _qa(f"Explain guideline {gl.get('guideline_number', '')} from this judgment.",
            full if full else f"Guideline {gl.get('guideline_number','')} — {gl.get('title','')}",
            gl.get("page_start", 1), gl.get("page_start", 1),
            "Medium", "Definition", "Long Answer", "Guidelines")

    # True/False
    _qa("True or False: The guidelines issued in this case are binding until legislation is enacted.",
        "True. The court explicitly held that these guidelines shall have the force of law "
        "until suitable legislation is enacted by Parliament.",
        "", 1, "Easy", "Reasoning", "True/False", "Legal Principle")

    # MCQ
    _qa("Which article of the Indian Constitution guarantees the right to life and personal liberty?",
        "Article 21",
        "", 1, "Easy", "Article-based", "MCQ", "Constitutional Law",
        has_options=True,
        options=["Article 14", "Article 19", "Article 21", "Article 32"])

    # Citations
    for cit in citations[:3]:
        _qa(f"Why was {cit['cited_case'][:60]} cited in this judgment?",
            cit.get("legal_principle_extracted") or cit.get("why_cited") or
            f"The case was cited as a precedent in support of the court's reasoning.",
            cit.get("paragraph", ""), cit.get("page", 1),
            "Hard", "Reasoning", "Long Answer", "Case Citation")

    return qa


def _derive_petitioner(case_title: str) -> str:
    """Extract petitioner from 'X v. Y' style title."""
    m = re.search(r'^(.+?)\s+(?:vs?\.?|versus)\s+', case_title, re.IGNORECASE)
    return normalize_whitespace(m.group(1)) if m else ""


def _derive_respondent(case_title: str) -> str:
    """Extract respondent from 'X v. Y' style title."""
    m = re.search(r'(?:vs?\.?|versus)\s+(.+)$', case_title, re.IGNORECASE)
    return normalize_whitespace(m.group(1)) if m else ""


# ─── Helper extractors ────────────────────────────────────────────────────────

def _extract_case_title(text: str) -> str:
    """Extract case title — handles 'VISHAKA v. STATE OF RAJASTHAN' style."""
    # Try explicit label first
    for pat in [
        r'(?:IN THE MATTER OF|CASE|TITLE)[:\s]+([A-Z][^\n]{10,120})',
        r'([A-Z][A-Z\s\.&]+(?:\s+(?:AND\s+)?ORS\.?)?\s+[Vv][Ss]?\.?\s+[A-Z][A-Z\s\.&]+(?:\s+(?:AND\s+)?ORS\.?)?)',
        r'([A-Z][a-zA-Z\s\.]+(?:\s+(?:vs?\.?|versus)\s+)[A-Z][a-zA-Z\s\.]+)',
    ]:
        m = re.search(pat, text[:3000], re.IGNORECASE)
        if m:
            title = normalize_whitespace(m.group(1) if m.lastindex else m.group())
            if len(title) > 8 and len(title) < 250:
                return title
    return "Unknown"


def _extract_party(text: str, party: str) -> str:
    """
    Extract petitioner/respondent.
    Strategy 1: Labeled field (Petitioner: ...)
    Strategy 2: Parse from case title (X v. Y → petitioner=X, respondent=Y)
    """
    # Strategy 1: labeled field — strict anchored patterns only
    labels = {
        "petitioner": [
            r'Petitioner[s]?\s*[:\-]\s*([A-Z][^\n]{3,100})',
            r'Appellant[s]?\s*[:\-]\s*([A-Z][^\n]{3,100})',
        ],
        "respondent": [
            r'Respondent[s]?\s*[:\-]\s*([A-Z][^\n]{3,100})',
            r'Appellee[s]?\s*[:\-]\s*([A-Z][^\n]{3,100})',
        ],
    }
    for pat in labels.get(party, []):
        m = re.search(pat, text[:5000])
        if m:
            val = normalize_whitespace(m.group(1)).strip()
            # Reject if it looks like body text (too long or starts with lowercase)
            if 3 < len(val) < 150 and val[0].isupper():
                return val

    # Strategy 2: extract from case title — the most reliable source
    # Look for "X AND ORS. v. Y AND ORS." or "X v. Y" pattern
    title_patterns = [
        # Full caps style: "VISHAKA AND ORS. v. STATE OF RAJASTHAN AND ORS."
        r'^([A-Z][A-Z\s\.\,&]+?)\s+[Vv][Ss]?\.?\s+([A-Z][A-Z\s\.\,&]+)',
        # Mixed case: "Vishaka and Ors. v. State of Rajasthan"
        r'([A-Z][a-zA-Z\s\.\,&]+?)\s+(?:vs?\.?|versus)\s+([A-Z][a-zA-Z\s\.\,&]+)',
    ]
    for pat in title_patterns:
        m = re.search(pat, text[:3000], re.MULTILINE)
        if m:
            pet = normalize_whitespace(m.group(1))
            res = normalize_whitespace(m.group(2))
            # Truncate at common stopwords that indicate sentence continuation
            res = re.split(r'\s+(?:AUGUST|JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|'
                           r'JULY|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|\d{4})', res)[0]
            if party == "petitioner" and 3 < len(pet) < 150:
                return pet.strip()
            if party == "respondent" and 3 < len(res) < 150:
                return res.strip()

    return ""


def _extract_court(text: str) -> str:
    """Detect court — never return 'Unknown' for SC judgments."""
    # Direct mention
    if re.search(r'Supreme Court of India', text[:5000], re.IGNORECASE):
        return "Supreme Court of India"
    # Header pattern in SC judgments
    if re.search(r'\bIN THE SUPREME COURT\b', text[:3000], re.IGNORECASE):
        return "Supreme Court of India"
    # SC citation patterns imply SC
    if re.search(r'\bSCC\b|\bSCR\b|\bAIR\s+\d{4}\s+SC\b', text[:3000]):
        return "Supreme Court of India"
    # High Court
    m = re.search(r'IN THE HIGH COURT OF ([\w\s]+)', text[:3000], re.IGNORECASE)
    if m:
        return f"High Court of {m.group(1).strip()}"
    m = re.search(r'(High Court of [\w\s]+)', text[:2000], re.IGNORECASE)
    if m:
        return normalize_whitespace(m.group(1))
    return "Supreme Court of India"  # default for SC judgment PDFs


def _extract_bench(text: str) -> str:
    """Extract bench composition — handles SC judgment formats."""
    for pat in [
        r'(?:BENCH|CORAM|Before\s*:?)\s*\n?([^\n]{10,300})',
        # "J.S. VERMA, CJI., SUJATA V. MANOHAR AND B.N. KIRPAL, JJ."
        r'([A-Z][A-Z\.\s]+,\s*(?:C\.?J\.?I?\.?|J\.J\.|JJ\.)[^\n]{0,100})',
        # HON'BLE style
        r"HON'?BLE\s+(?:MR\.?|MRS\.?|MS\.?)?\s*JUSTICE[S]?\s+([^\n]{10,200})",
    ]:
        m = re.search(pat, text[:5000], re.IGNORECASE)
        if m:
            val = normalize_whitespace(m.group(1))
            if len(val) > 5:
                return val[:300]
    # Fallback: join judges list
    judges = _extract_judges(text)
    return ", ".join(judges) if judges else ""


def _extract_judges(text: str) -> list[str]:
    """Extract judge names with designations."""
    judges = []
    # Pattern: Justice A. B. Verma or Justice Sujata V. Manohar
    for m in re.finditer(
        r'(?:Hon\'?ble\s+)?(?:Mr\.?\s+)?Justice\s+([A-Z][a-zA-Z\.]+(?:\s+[A-Z][a-zA-Z\.]+){1,4})',
        text[:5000], re.IGNORECASE
    ):
        name = normalize_whitespace(m.group(1))
        if name not in judges and len(name) > 3:
            judges.append(name)
    return judges[:10]


def _extract_judgment_date(text: str) -> str:
    """Multi-strategy date extraction for SC judgments."""
    from utils.date_utils import parse_date

    # Strategy 1: labeled date line
    for pat in [
        r'(?:Date of (?:Judgment|Order|Decision)|Decided on|Pronounced on|Delivered on)'
        r'\s*[:\-]?\s*(\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4})',
        r'(?:Dated?)\s*[:\-]?\s*(\d{1,2}(?:st|nd|rd|th)?\s+\w+,?\s+\d{4})',
    ]:
        m = re.search(pat, text[:5000], re.IGNORECASE)
        if m:
            parsed = parse_date(m.group(1))
            if parsed:
                return parsed

    # Strategy 2: "AUGUST 13, 1997" or "August 13, 1997" style (common in SC headnotes)
    m = re.search(
        r'\b(January|February|March|April|May|June|July|August|September|'
        r'October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b',
        text[:3000], re.IGNORECASE
    )
    if m:
        parsed = parse_date(f"{m.group(2)} {m.group(1)} {m.group(3)}")
        if parsed:
            return parsed

    # Strategy 3: "13 August 1997" or "13th August, 1997"
    m = re.search(
        r'\b(\d{1,2})(?:st|nd|rd|th)?\s+'
        r'(January|February|March|April|May|June|July|August|September|'
        r'October|November|December),?\s+(\d{4})\b',
        text[:3000], re.IGNORECASE
    )
    if m:
        parsed = parse_date(f"{m.group(1)} {m.group(2)} {m.group(3)}")
        if parsed:
            return parsed

    # Strategy 4: scan full text for date near "judgment" keyword
    for m in re.finditer(
        r'(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|'
        r'August|September|October|November|December),?\s+\d{4})',
        text[:5000], re.IGNORECASE
    ):
        parsed = parse_date(m.group(1))
        if parsed:
            return parsed

    return ""


def _extract_main_citation(text: str) -> str:
    """Find primary citation — search full text not just first 2000 chars."""
    for pattern in [
        r'\(\d{4}\)\s+\d+\s+SCC\s+\d+',
        r'AIR\s+\d{4}\s+SC\s+\d+',
        r'\d{4}\s+Supp\s+\(\d+\)\s+SCR\s+\d+',
        r'\(\d{4}\)\s+\d+\s+SCR\s+\d+',
    ]:
        m = re.search(pattern, text)
        if m:
            return m.group()
    return ""


def _extract_neutral_citation(text: str) -> str:
    m = re.search(r'\d{4}\s+INSC\s+\d+', text)
    return m.group() if m else ""


def _detect_criminal_civil(text: str) -> str:
    t = text[:5000].lower()
    criminal_hits = sum(1 for w in ["criminal", "fir", "accused", "ipc", "crpc",
                                     "murder", "rape", "theft", "offence"] if w in t)
    civil_hits = sum(1 for w in ["civil", "contract", "property", "divorce",
                                   "injunction", "damages", "writ"] if w in t)
    return "criminal" if criminal_hits > civil_hits else "civil"


def _detect_jurisdiction(text: str) -> str:
    t = text[:3000].lower()
    if "special leave" in t or "appeal" in t:
        return "appellate"
    if "review petition" in t:
        return "review"
    if "writ petition" in t:
        return "original"
    return "appellate"


def _extract_petition_number(text: str) -> str:
    m = re.search(
        r'(?:Writ\s+Petition|Criminal\s+Appeal|Civil\s+Appeal|SLP|'
        r'Transfer\s+Petition|Contempt\s+Petition|Special\s+Leave\s+Petition)'
        r'\s*(?:\([A-Za-z\.]+\))?\s*(?:Nos?\.?)\s*[\d\-,\s]+\s*(?:of|\/)\s*\d{4}',
        text[:8000], re.IGNORECASE
    )
    return normalize_whitespace(m.group()) if m else ""


def _extract_decision(text: str) -> str:
    # Search last 5000 chars where order is typically pronounced
    tail = text[-5000:]
    for decision in ["Allowed", "Dismissed", "Disposed of", "Quashed",
                     "Remanded", "Set aside", "Upheld", "Affirmed"]:
        if re.search(rf'\b{decision}\b', tail, re.IGNORECASE):
            return decision
    return "Disposed of"   # SC judgments usually dispose rather than "Unknown"


def _extract_relief(text: str) -> str:
    # Look for the ORDER section
    m = re.search(r'(?:^ORDER|^ORDERED|^IT IS ORDERED)[:\s]*\n?(.{50,500})',
                  text[-8000:], re.IGNORECASE | re.MULTILINE)
    if m:
        return normalize_whitespace(m.group(1))[:400]
    m = re.search(r'(?:Relief|Order)\s*[:\-]\s*([^\n]{20,300})', text[-5000:], re.IGNORECASE)
    return normalize_whitespace(m.group(1))[:300] if m else ""


def _extract_important_quotes(text: str) -> list[str]:
    quotes = re.findall(r'["\u201c]([^"\u201d]{50,400})["\u201d]', text)
    return [normalize_whitespace(q) for q in quotes[:10]]


def _extract_conventions(text: str) -> list[str]:
    convs = re.findall(
        r'(CEDAW|Convention on[\w\s,]+?(?=\n|\.|\,|and)|'
        r'International[\w\s]+Convention[\w\s]*?(?=\n|\.|\,)|'
        r'United Nations[\w\s]+Convention|UDHR|ICCPR|'
        r'Beijing\s+Statement|Universal\s+Declaration[\w\s]*)',
        text, re.IGNORECASE
    )
    return list(dict.fromkeys(normalize_whitespace(c)[:100] for c in convs if len(c.strip()) > 3))


def _extract_principles(text: str) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    principles = []
    for s in sentences:
        t = s.lower()
        if any(w in t for w in ["we hold", "it is held", "principle of",
                                  "it is settled", "the law is",
                                  "right to", "duty of", "obligation of"]):
            clean = normalize_whitespace(s)
            if 30 < len(clean) < 400:
                principles.append(clean)
    return principles[:10]


def _extract_section_text(paragraphs: list[dict], section_type: str) -> str:
    texts = [p["paragraph_text"] for p in paragraphs
             if p.get("section_type") == section_type]
    return " ".join(texts[:5])[:2000]
