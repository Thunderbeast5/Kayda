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
    principles = []
    pr_id = 1
    for para in paragraphs:
        text = para["paragraph_text"]
        if not any(w in text.lower() for w in
                   ["we hold", "it is held", "principle", "ratio", "rule of law",
                    "it is well settled", "laid down", "the law is"]):
            continue
        principles.append({
            "principle_id":        f"PR{pr_id:04d}",
            "case_id":             case_id,
            "principle":           normalize_whitespace(text[:300]),
            "principle_type":      _classify_principle_type(text),
            "source_text":         normalize_whitespace(text),
            "page":                para["page_number"],
            "paragraph":           para["paragraph_id"],
            "context":             "",
            "is_novel":            bool(re.search(r'\bfirst time\b|\bnovel\b|\bnew\b', text, re.IGNORECASE)),
            "jurisprudential_value": _jurisprudential_value(text),
            "cited_by_count":      0,
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
    if any(w in t for w in ["landmark", "fundamental", "first time", "historic"]):
        return "Landmark"
    if any(w in t for w in ["important", "significant", "notable"]):
        return "Important"
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
    events = []
    ev_id = 1
    for para in paragraphs:
        text = para["paragraph_text"]
        date_matches = re.finditer(
            r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|'
            r'August|September|October|November|December)\s+\d{4}|\d{4}-\d{2}-\d{2})\b',
            text, re.IGNORECASE
        )
        for m in date_matches:
            date_str = m.group(1)
            context = normalize_whitespace(text[max(0, m.start()-50): m.end()+100])
            events.append({
                "event_id":          f"EV{ev_id:04d}",
                "case_id":           case_id,
                "date":              parse_date(date_str) or date_str,
                "event_type":        _classify_event(context),
                "event_description": context,
                "page":              para["page_number"],
                "paragraph":         para["paragraph_id"],
                "stage":             _detect_stage(context),
            })
            ev_id += 1
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

    # Court REFERRED_TO articles
    for art in articles:
        triples.append(_triple(t_id, case_id, "Supreme Court", "Court",
                               "REFERRED_TO", f"Article {art['article_number']}", "Article",
                               art["page"], art["paragraph"], art["how_used"], 0.9, True))
        t_id += 1

    # Case ESTABLISHED guidelines
    for gl in guidelines:
        triples.append(_triple(t_id, case_id, case_title, "Case",
                               "ESTABLISHED", gl["title"][:80], "Guideline",
                               gl["page_start"], "", gl["full_text"][:100], 0.85, True))
        t_id += 1

    # Paragraph-level relations
    for para in paragraphs:
        text = para["paragraph_text"]
        # Overruled patterns
        for m in re.finditer(r'([\w\s]+)\s+is\s+overruled', text, re.IGNORECASE):
            triples.append(_triple(t_id, case_id, case_title, "Case",
                                   "OVERRULED", m.group(1), "Case",
                                   para["page_number"], para["paragraph_id"], text[:100], 0.8, True))
            t_id += 1
        # Followed patterns
        for m in re.finditer(r'(?:followed|applied)\s+in\s+([\w\s,]+v\.?\s+[\w\s]+)', text, re.IGNORECASE):
            triples.append(_triple(t_id, case_id, case_title, "Case",
                                   "FOLLOWED", m.group(1), "Case",
                                   para["page_number"], para["paragraph_id"], text[:100], 0.75, True))
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
        metadata.get("final_order", ""),
        "Final Order", "Knowledge", "Procedural Law", "Extraction", "Easy", case_title))
    tr_id += 1

    # Template 4: Per article
    for art in articles[:5]:
        records.append(_train_record(tr_id, case_id,
            f"Why was Article {art['article_number']} invoked in this case?",
            art.get("context", "")[:500],
            art.get("how_used", "") + " " + art.get("interpretation", ""),
            f"Article {art['article_number']}", "Reasoning", "Constitutional Law", "Application", "Medium", case_title))
        tr_id += 1

    # Template 5: Per citation
    for cit in citations[:5]:
        records.append(_train_record(tr_id, case_id,
            f"Why was {cit['cited_case'][:60]} cited in this judgment?",
            cit.get("legal_principle_extracted", ""),
            cit.get("why_cited", ""),
            "Case Citation", "Reasoning", "Constitutional Law", "Application", "Medium", case_title))
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

    def _qa(instruction, answer, support, page, difficulty, qtype, fmt, topic):
        nonlocal qa_id
        qa.append({
            "qa_id":                f"QA{qa_id:05d}",
            "case_id":              case_id,
            "question":             instruction,
            "answer":               normalize_whitespace(answer),
            "supporting_paragraph": support,
            "page":                 page,
            "difficulty":           difficulty,
            "type":                 qtype,
            "format":               fmt,
            "topic":                topic,
            "has_options":          False,
            "options":              [],
        })
        qa_id += 1

    _qa(f"Who were the petitioners in {case_title}?",
        metadata.get("petitioner", ""), "", 1, "Easy", "Fact-based", "Short Answer", "Case Metadata")
    _qa(f"What was the final decision in {case_title}?",
        metadata.get("decision", ""), "", 1, "Easy", "Fact-based", "Short Answer", "Case Metadata")
    _qa("What is the ratio decidendi of this case?",
        metadata.get("ratio_decidendi", ""), "", 1, "Hard", "Reasoning", "Long Answer", "Legal Principle")
    _qa("What guidelines were issued by the court?",
        "; ".join(metadata.get("guidelines", [])[:3]),
        "", 1, "Medium", "Fact-based", "Long Answer", "Guidelines")
    _qa("Which constitutional articles were invoked?",
        ", ".join([f"Article {a['article_number']}" for a in articles[:5]]),
        "", 1, "Easy", "Article-based", "Short Answer", "Constitutional Law")

    for art in articles[:3]:
        _qa(f"How was Article {art['article_number']} applied in this case?",
            art.get("how_used", "") + " " + art.get("interpretation", ""),
            art.get("paragraph", ""), art.get("page", 1),
            "Medium", "Article-based", "Long Answer", "Constitutional Law")

    for gl in guidelines[:5]:
        _qa(f"Explain guideline {gl.get('guideline_number', '')} from this judgment.",
            gl.get("full_text", ""), gl.get("page_start", 1),
            gl.get("page_start", 1), "Medium", "Definition", "Long Answer", "Guidelines")

    # True/False
    _qa("True or False: The guidelines issued in this case are binding until legislation is enacted.",
        "True — The court held the guidelines shall have the force of law until legislative provisions are enacted.",
        "", 1, "Easy", "Reasoning", "True/False", "Legal Principle")

    return qa


# ─── Helper extractors ────────────────────────────────────────────────────────
def _extract_case_title(text: str) -> str:
    m = re.search(r'([\w\s\.]+(?:vs?\.?|versus)\s+[\w\s\.]+)', text[:2000], re.IGNORECASE)
    return normalize_whitespace(m.group())[:200] if m else "Unknown"


def _extract_party(text: str, party: str) -> str:
    patterns = {
        "petitioner": [r'Petitioner[s]?:?\s*([A-Z][^\n]+)', r'Appellant[s]?:?\s*([A-Z][^\n]+)'],
        "respondent": [r'Respondent[s]?:?\s*([A-Z][^\n]+)', r'Appellee[s]?:?\s*([A-Z][^\n]+)'],
    }
    for pat in patterns.get(party, []):
        m = re.search(pat, text[:3000])
        if m:
            return normalize_whitespace(m.group(1))[:150]
    return ""


def _extract_court(text: str) -> str:
    if re.search(r'Supreme Court of India', text, re.IGNORECASE):
        return "Supreme Court of India"
    m = re.search(r'(High Court of [\w\s]+)', text[:1000], re.IGNORECASE)
    return m.group(1) if m else "Unknown"


def _extract_bench(text: str) -> str:
    m = re.search(r'(?:BENCH|CORAM|Before):?\s*([^\n]+(?:\n[^\n]+)?)', text[:3000], re.IGNORECASE)
    return normalize_whitespace(m.group(1))[:200] if m else ""


def _extract_judges(text: str) -> list[str]:
    judges = re.findall(r'(?:Justice|J\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text[:3000])
    return list(set(judges))[:10]


def _extract_judgment_date(text: str) -> str:
    m = re.search(
        r'(?:Date of Judgment|Decided on|Pronounced on|Date):?\s*'
        r'(\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})',
        text[:3000], re.IGNORECASE
    )
    if m:
        from utils.date_utils import parse_date
        return parse_date(m.group(1)) or m.group(1)
    return ""


def _extract_main_citation(text: str) -> str:
    for pattern in [r'\(\d{4}\)\s+\d+\s+SCC\s+\d+', r'AIR\s+\d{4}\s+SC\s+\d+',
                    r'\d{4}\s+Supp\s+\(\d+\)\s+SCR\s+\d+']:
        m = re.search(pattern, text[:2000])
        if m:
            return m.group()
    return ""


def _extract_neutral_citation(text: str) -> str:
    m = re.search(r'\d{4}\s+INSC\s+\d+', text[:2000])
    return m.group() if m else ""


def _detect_criminal_civil(text: str) -> str:
    t = text[:3000].lower()
    if any(w in t for w in ["criminal", "fir", "accused", "ipc", "crpc", "murder", "rape"]):
        return "criminal"
    return "civil"


def _detect_jurisdiction(text: str) -> str:
    t = text[:2000].lower()
    if "original" in t:
        return "original"
    if "review" in t:
        return "review"
    return "appellate"


def _extract_petition_number(text: str) -> str:
    m = re.search(r'(?:Writ Petition|Criminal Appeal|Civil Appeal|SLP)'
                  r'\s*(?:\(Civil\)|\(Criminal\))?\s*No\.?\s*\d+\s*of\s*\d{4}',
                  text[:3000], re.IGNORECASE)
    return m.group() if m else ""


def _extract_decision(text: str) -> str:
    for decision in ["Allowed", "Dismissed", "Disposed of", "Quashed", "Remanded"]:
        if re.search(rf'\b{decision}\b', text[-3000:], re.IGNORECASE):
            return decision
    return "Unknown"


def _extract_relief(text: str) -> str:
    m = re.search(r'(?:Relief|Order):?\s*([^\n]{20,300})', text[-5000:], re.IGNORECASE)
    return normalize_whitespace(m.group(1))[:300] if m else ""


def _extract_important_quotes(text: str) -> list[str]:
    quotes = re.findall(r'"([^"]{50,400})"', text)
    return [normalize_whitespace(q) for q in quotes[:10]]


def _extract_conventions(text: str) -> list[str]:
    convs = re.findall(
        r'(CEDAW|Convention on[\w\s]+|International[\w\s]+Convention|'
        r'United Nations[\w\s]+Convention|UDHR|ICCPR)',
        text, re.IGNORECASE
    )
    return list(set(normalize_whitespace(c) for c in convs))


def _extract_principles(text: str) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    principles = []
    for s in sentences:
        if any(w in s.lower() for w in ["we hold", "it is held", "principle",
                                         "it is settled", "the law is"]):
            principles.append(normalize_whitespace(s)[:300])
    return principles[:10]


def _extract_section_text(paragraphs: list[dict], section_type: str) -> str:
    texts = [p["paragraph_text"] for p in paragraphs
             if p.get("section_type") == section_type]
    return " ".join(texts[:5])[:2000]
