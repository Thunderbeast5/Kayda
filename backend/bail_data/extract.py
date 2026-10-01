#!/usr/bin/env python3
"""
Precedent extractor for Indian Supreme Court judgments (SCR-format PDFs + LawSuperOnline JSON).

Pipeline:  deterministic parse -> LLM structured extraction -> deterministic verification
           -> repair pass -> independent LLM verifier -> case JSON + retrieval chunks.

pip install pymupdf pydantic openai rapidfuzz python-dotenv
export OPENAI_API_KEY=...
python extract_precedents.py gurubaksh_sibbia.pdf P__CHIDAMBARAM.pdf Batch1__TheLawsSuperOnline-1.json --out out
(OCR fallback for scanned pages needs tesseract installed.)
"""
from __future__ import annotations
import argparse, bisect, json, os, re, statistics, time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import fitz  # PyMuPDF
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from rapidfuzz import fuzz

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", os.getenv("MODEL_STAGE6", "gpt-4o"))
VERIFY_MODEL = os.getenv("VERIFY_MODEL", os.getenv("MODEL_STAGE1", "gpt-4o-mini"))  # deliberately a different model

# --------------------------------------------------------------------------- schema
Side = Literal["accused", "prosecution", "neutral"]
Speaker = Literal["supreme_court", "lower_court", "appellant_counsel", "respondent_counsel",
                  "quoted_authority", "law_commission_or_statute"]
Treatment = Literal["followed", "applied", "relied_on", "referred_to", "distinguished",
                    "overruled", "not_followed", "quoted", "other"]


class Statute(BaseModel):
    act: str = Field(description="e.g. 'CrPC 1973', 'PMLA 2002', 'IPC'")
    section: str = Field(description="e.g. '438', '438(2)', '45'")
    how_used: Literal["interpreted", "applied", "charged", "distinguished", "referred"]
    note: Optional[str] = Field(None, description="What the court said about this section, if interpreted")


class Proposition(BaseModel):
    id: str = Field(description="p1, p2, ...")
    text: str = Field(description="One self-contained legal rule in neutral wording. No party names/amounts/dates.")
    speaker: Speaker = Field(description="WHO says this. Only 'supreme_court' can create law in this judgment.")
    kind: Literal["ratio", "obiter", "rejected_view", "argument"] = Field(
        description="ratio=court's own necessary holding; obiter=court's passing remark; "
                    "rejected_view=a lower-court/counsel view the court REJECTED; argument=counsel position")
    is_holding: bool
    favors: Side = Field(description="accused = expands bail/liberty or limits investigative reach; "
                                     "prosecution = restricts bail or protects investigative freedom; neutral = procedural")
    conditions: list[str] = Field(default_factory=list, description="Limits/exceptions/preconditions attached")
    statutes: list[str] = Field(default_factory=list)
    anchors: list[str] = Field(description="Paragraph ids exactly as shown in [[ ]] in the judgment text")
    quote: str = Field(description="Verbatim excerpt (<=40 words) copied from one of the anchors")


class Issue(BaseModel):
    question: str
    short_answer: str
    anchors: list[str]


class Contention(BaseModel):
    side: Literal["appellant", "respondent"]
    text: str
    outcome: Literal["accepted", "rejected", "partly", "not_decided"]
    anchors: list[str]


class Authority(BaseModel):
    name: str
    citation: Optional[str] = None
    treatment: Treatment
    used_for: Optional[str] = Field(None, description="Proposition it was cited for, one line")
    where: Optional[str] = Field(None, description="paragraph id(s) in this judgment")


class CaseLLM(BaseModel):
    case_name: str
    petitioner: str
    respondent: str
    court: str
    coram: list[str]
    judgment_author: Optional[str] = None
    procedural_stage: Literal["pre_arrest", "post_arrest_bail", "trial", "conviction_appeal", "quashing", "other"]
    offence_types: list[str] = Field(description="normalised, e.g. 'corruption', 'money laundering', 'economic offence'")
    dispute_nature: Literal["serious_criminal", "economic_offence", "civil_dispute", "political", "other"]
    abstract_facts: str = Field(description="3-5 sentences, anonymised, describing WHAT kind of case this is")
    lower_court_outcome: str
    disposition: str
    statutes: list[Statute]
    issues: list[Issue]
    propositions: list[Proposition]
    contentions: list[Contention]
    authorities: list[Authority]


class Verdict(BaseModel):
    id: str
    verdict: Literal["supported", "overstated", "unsupported"]
    favors_correct: bool
    note: str = ""


class Verdicts(BaseModel):
    items: list[Verdict]


# --------------------------------------------------------------------------- loading
@dataclass
class Doc:
    source: str
    fmt: str
    meta: dict
    headnote: str
    paras: dict            # id -> {"text","page_start","page_end"}
    authority_table: list = field(default_factory=list)
    flags: list = field(default_factory=list)


MARK = re.compile(r"^⟦p(\d+)⟧$")
HDR_PATTERNS = [re.compile(p) for p in [
    r"^\s*\d{2,4}\s+SUPREME\s+COURT\s+.*$",
    r"^\s*SUPREME\s+COURT\s+REPORTS.*$",
    r"^\s*\[\d{4}\]\s*\d+\s*S\.?C\.?R\.?\s*\d*\s*$",
    r"^\s*\d{2,4}A?\s*$",
    r"^\s*[A-Z][A-Z\.\s,&':]+\b[vV]\.\s[A-Z][A-Z\.\s,&':]+(\(.*?\))?\s*\d{0,4}[A-H]?\s*$",
    r"^\s*\[[A-Z\.\s,]+J\.\]\s*$",
    r"^\s*[A-H]\s*$",                     # margin letters
]]
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def detect_page(raw: str) -> Optional[int]:
    head = raw.splitlines()[:14]
    for ln in head:
        m = re.match(r"^\s*(\d{2,4})\s+SUPREME\s+COURT", ln)
        if m:
            return int(m.group(1))
    for ln in head:
        m = (re.match(r"^\s*(\d{2,4})A?\s*$", ln)
             or re.match(r"^[A-Z][^\n]{0,70}\b[vV]\.\s[^\n]{0,50}?\s(\d{3,4})\s*[A-H]?\s*$", ln))
        if m:
            return int(m.group(1))
    return None


def assign_pages(raws: list[str]) -> list[int]:
    det = [detect_page(r) for r in raws]
    votes = Counter(d - i for i, d in enumerate(det) if d)
    base = votes.most_common(1)[0][0] if votes else 1
    pages, prev = [], None
    for i, d in enumerate(det):
        exp = base + i if prev is None else prev + 1
        pages.append(d if d and abs(d - exp) <= 1 else exp)
        prev = pages[-1]
    return pages


def clean_page(raw: str) -> list[str]:
    return [l.rstrip() for l in raw.splitlines() if l.strip() and not any(p.match(l) for p in HDR_PATTERNS)]


def read_pdf_pages(path: str) -> list[str]:
    doc, out = fitz.open(path), []
    for pg in doc:
        t = pg.get_text("text")
        if len(t.strip()) < 200:                       # scanned page -> OCR fallback
            try:
                t = pg.get_text("text", textpage=pg.get_textpage_ocr(dpi=300, full=True))
            except Exception:
                pass
        out.append(t)
    return out


def noise_score(text: str) -> float:
    toks = text.split() or ["x"]
    bad = sum(bool(re.search(r"[A-Za-z][^\w\s.,;:'\"()\-\[\]/&–—][A-Za-z]|\b\w*\d\w*[a-z]\w*\b", t)) for t in toks)
    return bad / len(toks)


def segment_numbered(body: str):
    hits, last = [], 0
    for m in re.finditer(r"(?m)^\s*(\d{1,3})\.\s+(?=[A-Z“\"(])", body):
        if int(m.group(1)) == last + 1:
            hits.append((m.start(), int(m.group(1)), m.end()))
            last += 1
    return hits


def to_paras_numbered(body: str, hits) -> dict:
    marks = [(m.start(), int(m.group(1))) for m in re.finditer(r"⟦p(\d+)⟧", body)]
    pos = [p for p, _ in marks]

    def page_at(i):
        j = bisect.bisect_right(pos, i) - 1
        return marks[j][1] if j >= 0 else None

    paras = {}
    for k, (s, n, e) in enumerate(hits):
        end = hits[k + 1][0] if k + 1 < len(hits) else len(body)
        txt = re.sub(r"⟦p\d+⟧", " ", body[e:end])
        paras[f"P{n}"] = {"text": re.sub(r"\s+", " ", txt).strip(),
                          "page_start": page_at(s), "page_end": page_at(end - 1)}
    return paras


def to_paras_unnumbered(body: str) -> dict:
    lines = body.split("\n")
    widths = [len(l) for l in lines if len(l) > 30 and not l.startswith("⟦")]
    med = statistics.median(widths) if widths else 60
    paras, cur, page, cur_page, per_page = {}, [], None, None, Counter()

    def flush():
        nonlocal cur
        if cur:
            per_page[cur_page] += 1
            txt = re.sub(r"(\w-)\s+(\w)", r"\1\2", " ".join(cur))
            paras[f"p{cur_page}.{per_page[cur_page]}"] = {"text": re.sub(r"\s+", " ", txt).strip(),
                                                          "page_start": cur_page, "page_end": page}
        cur = []

    for l in lines:
        m = MARK.match(l.strip())
        if m:
            page = int(m.group(1))
            continue
        l = l.strip()
        if not l:
            continue
        if not cur:
            cur_page = page
        cur.append(l)
        if re.search(r"[.:;?\"”)]$", l) and len(l) < 0.8 * med:
            flush()
    flush()
    return paras


def parse_authority_table(headnote: str) -> list[dict]:
    rows = []
    for ln in headnote.splitlines():
        m = re.match(r"^\s*(?P<cite>[\[(]\d{4}[\])].*?)\s+(?P<treat>relied on|referred to|followed|distinguished|"
                     r"applied|overruled|approved)\s+Para\s+(?P<para>\d+)\s*$", ln)
        if m:
            rows.append({"cite": m["cite"], "treatment": m["treat"], "para": int(m["para"])})
    return rows


def load_pdf(path: str) -> Doc:
    raws = read_pdf_pages(path)
    pages = assign_pages(raws)
    head_raw = "\n".join(raws[:2])
    full = "\n".join(f"⟦p{pg}⟧\n" + "\n".join(clean_page(r)) for pg, r in zip(pages, raws))
    flags, meta = [], {"source_file": Path(path).name, "pdf_pages": len(raws)}

    m = re.search(r"\[(\d{4})\]\s*(\d+)\s*S\.?\s?C\.?\s?R", head_raw)
    if m:
        meta.update(year=int(m[1]), scr_volume=int(m[2]), scr_first_page=pages[0])
        meta["citation_scr"] = f"[{m[1]}] {m[2]} SCR {pages[0]}"
    d = re.search(rf"(?i)\b({MONTHS})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})", head_raw[:1500])
    try:
        meta["decided_on"] = datetime.strptime(f"{d[1].title()} {int(d[2])} {d[3]}", "%B %d %Y").date().isoformat()
    except Exception:
        flags.append("date_not_parsed")
    c = re.search(r"\[([^\[\]]*?\bJJ?\.?)\s*\]", head_raw[:1200], re.S)
    if c:
        toks = [t.strip() for t in re.split(r",|\bAND\b", c[1].replace("\n", " ")) if t.strip()]
        toks = [t for t in toks if not re.fullmatch(r"C?\.?\s?J{1,2}\.?", t)]
        meta["coram_raw"] = c[1].replace("\n", " ")
        meta["bench_strength_regex"] = len(toks)
        meta["constitution_bench"] = len(toks) >= 5
    else:
        flags.append("coram_not_parsed")

    juris = re.search(r"(?:CRIMINAL|CIVIL)\s*APPELLATE\s*JURISDICTION", full)
    marker = re.search(r"The Judgment of the Court was delivered by", full)
    if not (juris and marker):
        flags.append("zone_split_failed_using_whole_text")
    headnote = full[:juris.start()] if juris else ""
    body = full[marker.end():] if marker else full
    a = re.search(r"([A-Z][A-Z\.\s]{3,40}?),\s*(C\.\s?J\.|J\.)", body[:250])
    if a:
        meta["judgment_author_regex"] = a[1].strip()

    hits = segment_numbered(body)
    if len(hits) >= 5:
        paras, layout = to_paras_numbered(body, hits), "numbered_paras"
    else:
        paras, layout = to_paras_unnumbered(body), "unnumbered_page_anchored"
    meta["layout"] = layout
    ns = noise_score(full)
    meta["ocr_noise_score"] = round(ns, 4)
    if ns > 0.03:
        flags.append("ocr_noisy: copy quotes as printed; never 'correct' names or numbers by guessing")
    headnote = re.sub(r"⟦p\d+⟧", " ", headnote)
    return Doc(path, "scr_pdf", meta, headnote, paras, parse_authority_table(headnote), flags)


def load_laws_json(path: str) -> Doc:
    j = json.load(open(path, encoding="utf-8"))
    meta = {"source_file": Path(path).name, "citation_laws": j.get("case_citation"),
            "court": j.get("court"), "decided_on": j.get("decided_on"), "year": j.get("decided_on_year"),
            "coram_raw": j.get("coram"), "layout": "numbered_paras",
            "equivalent_citations": j.get("equivalent_citations"),
            "cited_by": j.get("cited_judgments")}          # NB: these are LATER citing cases, not authorities relied on
    flags = ["laws_json: 'cited_judgments' = cited_by; procedural_history date is unreliable (e.g. '11')"]
    paras = {f"P{p['number']}": {"text": re.sub(r"\s+", " ", p["text"]), "page_start": None, "page_end": None}
             for p in j.get("numbered_paragraphs", [])}
    return Doc(path, "laws_json", meta, j.get("headnote_raw", ""), paras, [], flags)


# --------------------------------------------------------------------------- LLM
SYSTEM = """You extract structured precedent data from an Indian Supreme Court judgment for a legal retrieval system.
Rules:
1. Use ONLY the text provided. Every proposition/issue/contention needs anchors that exist as [[id]] in the judgment,
   and every proposition needs a verbatim quote copied from one of its anchors.
2. The headnote is the reporter's summary, not the court's words. Use it as a map, never as an anchor.
3. SPEAKER DISCIPLINE. A proposition the court quotes and REJECTS (e.g. a High Court's eight-point summary that the
   Supreme Court reverses) is kind='rejected_view', speaker='lower_court', is_holding=false. Counsel submissions are
   kind='argument'. Passages quoted from other cases/reports are speaker='quoted_authority' unless the court adopts them,
   in which case restate as a supreme_court ratio and cite where it adopts them.
4. is_holding=true only for speaker='supreme_court' and kind='ratio'. Record conditions/exceptions the court attached
   (e.g. 'blanket orders should not generally be passed'); do not flatten them into absolute rules.
5. 'favors' is about who the rule helps in a bail contest, judged from the rule itself, not the case outcome.
6. Propositions must be atomic (one rule each), neutral, and free of party names. Aim for every distinct ratio.
7. authorities = cases relied on BY this judgment, with the treatment the court gives them. Use the AUTHORITY TABLE hints.
8. If the text is OCR-noisy, do not repair names/numbers by guessing."""


# ~4 chars per token; keep well under 30k TPM limit (leave room for output + system prompt)
_MAX_PROMPT_CHARS = 90_000


def _truncate_prompt(user: str) -> str:
    """If the prompt is too large, drop paragraphs from the tail until it fits."""
    if len(user) <= _MAX_PROMPT_CHARS:
        return user
    # Find the judgment body start and trim paragraphs from the end
    judgment_marker = "=== JUDGMENT ==="
    split_idx = user.find(judgment_marker)
    if split_idx == -1:
        return user[:_MAX_PROMPT_CHARS]  # fallback: hard truncate
    header = user[:split_idx + len(judgment_marker)]
    body = user[split_idx + len(judgment_marker):]
    # Each paragraph line starts with [[id]]
    para_lines = body.split("\n[[")
    while len(header) + sum(len(p) + 3 for p in para_lines) > _MAX_PROMPT_CHARS and len(para_lines) > 1:
        para_lines.pop()
    truncated = header + "\n[[" + "\n[[".join(para_lines)
    print(f"  [warn] Prompt truncated to {len(truncated):,} chars to fit token limit")
    return truncated


def call(system: str, user: str, model_cls, model: str, max_tokens=12000):
    client = OpenAI()
    user = _truncate_prompt(user)
    tool = {"type": "function",
            "function": {"name": "record",
                         "description": "Record the structured result",
                         "parameters": model_cls.model_json_schema()}}
    for attempt in range(5):
        try:
            r = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                tools=[tool],
                tool_choice={"type": "function", "function": {"name": "record"}},
            )
            args = json.loads(r.choices[0].message.tool_calls[0].function.arguments)
            return model_cls.model_validate(args)
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = 60 * (attempt + 1)  # 60s, 120s, 180s ...
                print(f"  [rate limit] Waiting {wait}s before retry (attempt {attempt + 1}/5)...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Exceeded maximum retries due to rate limiting")


def build_prompt(doc: Doc) -> str:
    parts = [f"LAYOUT FLAGS: {doc.flags}",
             "DETERMINISTIC METADATA (trust over your own guess): " + json.dumps(
                 {k: v for k, v in doc.meta.items() if k != "cited_by"}, ensure_ascii=False),
             "AUTHORITY TABLE HINTS: " + json.dumps(doc.authority_table),
             "=== HEADNOTE (reporter's summary; not an anchor) ===", doc.headnote,
             "=== JUDGMENT ==="]
    parts += [f"[[{pid}]] {p['text']}" for pid, p in doc.paras.items()]
    return "\n".join(parts)


# --------------------------------------------------------------------------- verification
def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def quote_ok(quote: str, text: str) -> bool:
    q, t = norm(quote), norm(text)
    return bool(q) and (q in t or fuzz.partial_ratio(q, t) >= 90)


def check(rec: CaseLLM, doc: Doc) -> list[str]:
    ptxt = {k: v["text"] for k, v in doc.paras.items()}
    full = doc.headnote + " " + " ".join(ptxt.values())
    probs = []
    for p in rec.propositions:
        p.is_holding = (p.speaker == "supreme_court" and p.kind == "ratio")     # auto-enforce
        bad = [a for a in p.anchors if a not in ptxt]
        if bad or not p.anchors:
            probs.append(f"{p.id}: unknown/missing anchors {bad}")
        elif not quote_ok(p.quote, " ".join(ptxt[a] for a in p.anchors)):
            probs.append(f"{p.id}: quote not found in its anchors")
    for i in rec.issues:
        if any(a not in ptxt for a in i.anchors):
            probs.append(f"issue '{i.question[:40]}': unknown anchors")
    for s in rec.statutes:
        if not re.search(rf"\b{re.escape(s.section.split('(')[0])}\b", full):
            probs.append(f"statute {s.act} s.{s.section} not found in text")
    for a in rec.authorities:
        first = re.split(r"\s+v\.?\s+", a.name)[0]
        if not quote_ok(first, full):
            probs.append(f"authority '{a.name}' not found in text")
    return probs


def llm_verify(rec: CaseLLM, doc: Doc) -> dict[str, Verdict]:
    payload = [{"id": p.id, "proposition": p.text, "favors": p.favors, "speaker": p.speaker, "kind": p.kind,
                "anchor_text": " ".join(doc.paras[a]["text"] for a in p.anchors if a in doc.paras)}
               for p in rec.propositions]
    sys = ("You are a strict legal cite-checker. For each item decide if anchor_text supports the proposition exactly "
           "as worded (supported / overstated = broader or more absolute than the text / unsupported) and whether "
           "'favors' is correct for a bail contest. Also flag if a rejected view is presented as the court's own.")
    out = call(sys, json.dumps(payload, ensure_ascii=False), Verdicts, VERIFY_MODEL, 6000)
    return {v.id: v for v in out.items}


# --------------------------------------------------------------------------- outputs
def case_id(doc: Doc) -> str:
    m = doc.meta
    if m.get("citation_scr"):
        return re.sub(r"\W+", "_", m["citation_scr"])
    return re.sub(r"\W+", "_", str(m.get("citation_laws") or Path(doc.source).stem))


def make_chunks(cid: str, rec: CaseLLM, doc: Doc, verdicts: dict) -> list[dict]:
    base = {"case_id": cid, "court": rec.court, "year": doc.meta.get("year"),
            "bench_strength": doc.meta.get("bench_strength_regex"),
            "statutes": [f"{s.act} {s.section}" for s in rec.statutes]}
    ch = []
    for p in rec.propositions:
        v = verdicts.get(p.id)
        ch.append({**base, "id": f"{cid}:{p.id}", "type": "proposition",
                   "text": p.text + (" Conditions: " + "; ".join(p.conditions) if p.conditions else ""),
                   "favors": p.favors, "kind": p.kind, "is_holding": p.is_holding, "speaker": p.speaker,
                   "anchors": p.anchors, "quote": p.quote, "verified": bool(v and v.verdict == "supported")})
    for k, i in enumerate(rec.issues):
        ch.append({**base, "id": f"{cid}:issue{k}", "type": "issue", "text": f"{i.question} {i.short_answer}",
                   "anchors": i.anchors})
    ch.append({**base, "id": f"{cid}:facts", "type": "facts",
               "text": f"{rec.abstract_facts} Stage: {rec.procedural_stage}. Nature: {rec.dispute_nature}. "
                       f"Offences: {', '.join(rec.offence_types)}."})
    for pid, p in doc.paras.items():                          # for BM25 / quote lookup
        ch.append({**base, "id": f"{cid}:{pid}", "type": "paragraph", "text": p["text"],
                   "page": p["page_start"]})
    return ch


def process(path: str, out: Path, verify=True):
    doc = load_pdf(path) if path.lower().endswith(".pdf") else load_laws_json(path)
    cid = case_id(doc)
    rec = call(SYSTEM, build_prompt(doc), CaseLLM, EXTRACT_MODEL)
    probs = check(rec, doc)
    if probs:                                                 # one repair round, failing items only
        note = ("\n\n=== VERIFICATION FAILURES: fix these and return the complete record. Use only real anchors "
                "and exact quotes; drop propositions you cannot ground ===\n" + "\n".join(probs) +
                "\n\nPREVIOUS OUTPUT:\n" + rec.model_dump_json())
        rec = call(SYSTEM, build_prompt(doc) + note, CaseLLM, EXTRACT_MODEL)
        probs = check(rec, doc)
    verdicts = llm_verify(rec, doc) if verify else {}
    review = list(probs)
    for pid, v in verdicts.items():
        if v.verdict != "supported" or not v.favors_correct:
            review.append(f"{pid}: verifier says {v.verdict}, favors_correct={v.favors_correct} - {v.note}")
    if doc.meta.get("bench_strength_regex") and len(rec.coram) != doc.meta["bench_strength_regex"]:
        review.append("coram count differs between regex and LLM")
    result = {"case_id": cid, "doc_meta": doc.meta, "flags": doc.flags, "case": rec.model_dump(),
              "authority_table": doc.authority_table, "verdicts": {k: v.model_dump() for k, v in verdicts.items()},
              "needs_review": review, "paragraphs": doc.paras, "headnote_raw": doc.headnote}
    (out / f"{cid}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(out / "chunks.jsonl", "a", encoding="utf-8") as f:
        for c in make_chunks(cid, rec, doc, verdicts):
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"{cid}: {len(rec.propositions)} propositions, {len(doc.paras)} paragraphs, {len(review)} need review")


_DEFAULT_INPUT_DIR = Path(__file__).parent / "Anticipatory bail application"

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Extract precedent data from bail judgment PDFs/JSONs."
    )
    ap.add_argument(
        "files", nargs="*",
        help="PDF or JSON files to process. "
             f"Defaults to all PDFs in '{_DEFAULT_INPUT_DIR.name}/' if omitted."
    )
    ap.add_argument("--out", default="out", help="Output directory (default: out/)")
    ap.add_argument("--no-verify", action="store_true", help="Skip LLM verification pass")
    a = ap.parse_args()

    if not a.files:
        a.files = sorted(str(p) for p in _DEFAULT_INPUT_DIR.glob("*.pdf"))
        if not a.files:
            ap.error(f"No PDF files found in '{_DEFAULT_INPUT_DIR}'. "
                     "Please pass file paths explicitly.")
        print(f"No files specified — processing {len(a.files)} PDFs from "
              f"'{_DEFAULT_INPUT_DIR.name}/':\n" +
              "\n".join(f"  {Path(f).name}" for f in a.files) + "\n")

    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "chunks.jsonl").write_text("", encoding="utf-8")
    for fp in a.files:
        process(fp, Path(a.out), verify=not a.no_verify)