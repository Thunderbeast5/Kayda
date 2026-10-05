#!/usr/bin/env python3
"""
Precedent extractor for Indian Supreme Court judgments (SCR / SCC / AIR / slip PDFs + LawSuperOnline JSON).

Pipeline:  deterministic parse (judgment_parser) -> LLM structured extraction -> deterministic verification
           -> repair pass -> independent LLM verifier -> case JSON + retrieval chunks.

Robustness rules in this version
  * Enum-like fields never crash validation: unknown/variant values ("approved", "Relied upon", None ...) are
    coerced to a canonical value or a conservative default, and every coercion is logged into needs_review.
  * Free-text / list fields accept the wrong JSON type (int, list, None) and are coerced.
  * Anchors are normalised ("[[P5]]", "p5", "5", "Para 5" -> real paragraph id) before checking.
  * A schema failure triggers ONE retry that feeds the validation error back to the model.
  * One bad file never kills the batch: errors go to <out>/errors.jsonl and the run continues.
  * Resumable: finished cases are skipped (use --force to redo); chunks.jsonl is never blindly truncated.
  * The repair note is appended AFTER prompt truncation, so it can no longer be cut off.

pip install pymupdf pydantic openai rapidfuzz python-dotenv
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import traceback
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, BeforeValidator, Field, ValidationError
from rapidfuzz import fuzz

from judgment_parser import Doc, load_document

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv()

EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", os.getenv("MODEL_STAGE6", "gpt-4o"))
VERIFY_MODEL = os.getenv("VERIFY_MODEL", os.getenv("MODEL_STAGE1", "gpt-4o-mini"))  # deliberately a different model

# --------------------------------------------------------------------------- lenient coercion helpers
COERCIONS: list[str] = []          # filled by validators during one model_validate(); drained per case


def _key(v: Any) -> str:
    return re.sub(r"[\s\-/.]+", "_", str(v).strip().lower()).strip("_")


def enum_field(canon: tuple[str, ...], default: Optional[str], synonyms: Optional[dict] = None, label: str = ""):
    """BeforeValidator: map any variant of an enum value onto `canon`; fall back to `default`
    (conservative) and log it. default=None means 'no safe default' -> let validation fail -> retry."""
    syn = {_key(k): v for k, v in (synonyms or {}).items()}

    def f(v):
        if v is None:
            if default is None:
                return v
            COERCIONS.append(f"{label}: null -> '{default}'")
            return default
        k = _key(v)
        if k in canon:
            return k
        if k in syn:
            COERCIONS.append(f"{label}: '{v}' -> '{syn[k]}'")
            return syn[k]
        for c in canon:                                    # e.g. "relied_upon_by_court" contains "relied"
            if c in k or (len(k) >= 4 and k in c):
                COERCIONS.append(f"{label}: '{v}' -> '{c}'")
                return c
        if default is None:
            return v
        COERCIONS.append(f"{label}: unrecognised '{v}' -> default '{default}'")
        return default
    return BeforeValidator(f)


def _to_str(v):
    if v is None:
        return None
    if isinstance(v, (list, tuple, set)):
        return "; ".join(str(x) for x in v if x is not None)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _to_str_req(v):
    return "" if v is None else _to_str(v)


def _to_list(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [str(x) for x in v if x is not None]
    if isinstance(v, str):
        parts = [p.strip() for p in re.split(r"[;\n]|,(?![^()]*\))", v) if p.strip()]
        return parts or []
    return [str(v)]


def _to_bool(v):
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1")
    return bool(v)


OptStr = Annotated[Optional[str], BeforeValidator(_to_str)]
Str = Annotated[str, BeforeValidator(_to_str_req)]
StrList = Annotated[list[str], BeforeValidator(_to_list)]
Bool = Annotated[bool, BeforeValidator(_to_bool)]

# --------------------------------------------------------------------------- schema
_SIDE = ("accused", "prosecution", "neutral")
_SPEAKER = ("supreme_court", "lower_court", "appellant_counsel", "respondent_counsel",
            "quoted_authority", "law_commission_or_statute")
_TREAT = ("followed", "applied", "relied_on", "referred_to", "distinguished", "overruled",
          "not_followed", "quoted", "other")
_KIND = ("ratio", "obiter", "rejected_view", "argument")
_USED = ("interpreted", "applied", "charged", "distinguished", "referred", "discussed")
_STAGE = ("pre_arrest", "post_arrest_bail", "trial", "conviction_appeal", "quashing", "other")
_NATURE = ("serious_criminal", "economic_offence", "civil_dispute", "political", "other")
_OUTCOME = ("accepted", "rejected", "partly", "not_decided")
_VERD = ("supported", "overstated", "unsupported")

Side = Annotated[Literal[_SIDE], enum_field(_SIDE, "neutral", {"petitioner": "accused", "defence": "accused",
                  "state": "prosecution", "complainant": "prosecution", "both": "neutral", "none": "neutral"}, "favors")]
Speaker = Annotated[Literal[_SPEAKER], enum_field(_SPEAKER, "quoted_authority", {   # conservative: never invent a holding
    "court": "supreme_court", "sc": "supreme_court", "this_court": "supreme_court", "high_court": "lower_court",
    "trial_court": "lower_court", "counsel": "appellant_counsel", "appellant": "appellant_counsel",
    "respondent": "respondent_counsel", "state": "respondent_counsel", "statute": "law_commission_or_statute",
    "law_commission": "law_commission_or_statute", "quoted": "quoted_authority", "authority": "quoted_authority",
    "cited_case": "quoted_authority"}, "speaker")]
Treatment = Annotated[Literal[_TREAT], enum_field(_TREAT, "other", {
    "approved": "followed", "approved_of": "followed", "affirmed": "followed", "upheld": "followed",
    "followed_with_approval": "followed", "relied_upon": "relied_on", "relied": "relied_on",
    "reliance_placed": "relied_on", "referred": "referred_to", "cited": "referred_to", "considered": "referred_to",
    "discussed": "referred_to", "noticed": "referred_to", "mentioned": "referred_to",
    "distinguished_on_facts": "distinguished", "reversed": "overruled", "overruled_in_part": "overruled",
    "disapproved": "not_followed", "doubted": "not_followed", "declined_to_follow": "not_followed",
    "extracted": "quoted", "reproduced": "quoted", "adopted": "applied", "affirmed_and_applied": "applied"},
    "authority.treatment")]
Kind = Annotated[Literal[_KIND], enum_field(_KIND, "obiter", {                       # conservative: not a holding
    "holding": "ratio", "ratio_decidendi": "ratio", "rule": "ratio", "dictum": "obiter", "obiter_dictum": "obiter",
    "rejected": "rejected_view", "overruled_view": "rejected_view", "contention": "argument",
    "submission": "argument", "counsel_argument": "argument"}, "kind")]
HowUsed = Annotated[Literal[_USED], enum_field(_USED, "referred", {
    "interpret": "interpreted", "construed": "interpreted", "applies": "applied", "invoked": "applied",
    "framed": "charged", "referred_to": "referred", "cited": "referred", "mentioned": "referred",
    "considered": "discussed", "analysed": "discussed", "analyzed": "discussed"}, "statute.how_used")]
Stage = Annotated[Literal[_STAGE], enum_field(_STAGE, "other", {
    "anticipatory_bail": "pre_arrest", "pre_arrest_bail": "pre_arrest", "section_438": "pre_arrest",
    "regular_bail": "post_arrest_bail", "bail": "post_arrest_bail", "post_arrest": "post_arrest_bail",
    "custody": "post_arrest_bail", "appeal": "conviction_appeal", "quash": "quashing",
    "investigation": "pre_arrest", "cancellation_of_bail": "post_arrest_bail"}, "procedural_stage")]
Nature = Annotated[Literal[_NATURE], enum_field(_NATURE, "other", {
    "criminal": "serious_criminal", "violent": "serious_criminal", "murder": "serious_criminal",
    "heinous": "serious_criminal", "economic": "economic_offence", "financial": "economic_offence",
    "fraud": "economic_offence", "cheating": "economic_offence", "commercial": "civil_dispute",
    "civil": "civil_dispute", "business": "civil_dispute", "matrimonial": "other"}, "dispute_nature")]
Outcome = Annotated[Literal[_OUTCOME], enum_field(_OUTCOME, "not_decided", {
    "accept": "accepted", "upheld": "accepted", "allowed": "accepted", "reject": "rejected", "dismissed": "rejected",
    "partially": "partly", "partly_accepted": "partly", "partial": "partly", "undecided": "not_decided",
    "left_open": "not_decided", "not_considered": "not_decided"}, "contention.outcome")]
Verd = Annotated[Literal[_VERD], enum_field(_VERD, "unsupported", {                  # conservative: flags for review
    "support": "supported", "ok": "supported", "correct": "supported", "overstate": "overstated",
    "partially_supported": "overstated", "partly_supported": "overstated", "not_supported": "unsupported"}, "verdict")]
ContSide = Annotated[Literal["appellant", "respondent"], enum_field(
    ("appellant", "respondent"), None, {"petitioner": "appellant", "accused": "appellant", "state": "respondent",
                                        "complainant": "appellant", "opposite_party": "respondent"}, "contention.side")]


class Statute(BaseModel):
    act: Str = Field(description="e.g. 'CrPC 1973', 'PMLA 2002', 'IPC'")
    section: Str = Field(description="e.g. '438', '438(2)', '45'")
    how_used: HowUsed = "referred"
    note: OptStr = Field(None, description="What the court said about this section, if interpreted")


class Proposition(BaseModel):
    id: Str = Field(description="p1, p2, ...")
    text: Str = Field(description="One self-contained legal rule in neutral wording. No party names/amounts/dates.")
    speaker: Speaker = Field(description="WHO says this. Only 'supreme_court' can create law in this judgment.")
    kind: Kind = Field(description="ratio=court's own necessary holding; obiter=court's passing remark; "
                                   "rejected_view=a lower-court/counsel view the court REJECTED; argument=counsel position")
    is_holding: Bool = False
    favors: Side = Field(description="accused = expands bail/liberty or limits investigative reach; "
                                     "prosecution = restricts bail or protects investigative freedom; neutral = procedural")
    conditions: StrList = Field(default_factory=list, description="Limits/exceptions/preconditions attached")
    statutes: StrList = Field(default_factory=list)
    anchors: StrList = Field(description="Paragraph ids exactly as shown in [[ ]] in the judgment text")
    quote: Str = Field("", description="Verbatim excerpt (<=40 words) copied from one of the anchors")


class Issue(BaseModel):
    question: Str
    short_answer: Str = ""
    anchors: StrList = Field(default_factory=list)


class Contention(BaseModel):
    side: ContSide
    text: Str
    outcome: Outcome = "not_decided"
    anchors: StrList = Field(default_factory=list)


class Authority(BaseModel):
    name: Str
    citation: OptStr = None
    treatment: Treatment = "other"
    used_for: OptStr = Field(None, description="Proposition it was cited for, one line")
    where: OptStr = Field(None, description="paragraph id(s) in this judgment")


class CaseLLM(BaseModel):
    case_name: Str
    petitioner: Str = ""
    respondent: Str = ""
    court: Str = ""
    coram: StrList = Field(default_factory=list)
    judgment_author: OptStr = None
    procedural_stage: Stage = "other"
    offence_types: StrList = Field(default_factory=list,
                                   description="normalised, e.g. 'corruption', 'money laundering', 'economic offence'")
    dispute_nature: Nature = "other"
    abstract_facts: Str = Field("", description="3-5 sentences, anonymised, describing WHAT kind of case this is")
    lower_court_outcome: Str = ""
    disposition: Str = ""
    statutes: list[Statute] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    propositions: list[Proposition] = Field(default_factory=list)
    contentions: list[Contention] = Field(default_factory=list)
    authorities: list[Authority] = Field(default_factory=list)


class Verdict(BaseModel):
    id: Str
    verdict: Verd = "unsupported"
    favors_correct: Bool = True
    note: Str = ""


class Verdicts(BaseModel):
    items: list[Verdict] = Field(default_factory=list)


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
   'treatment' MUST be exactly one of: followed, applied, relied_on, referred_to, distinguished, overruled,
   not_followed, quoted, other. Map hint words onto these (e.g. approved->followed, considered->referred_to).
8. If the text is OCR-noisy, do not repair names/numbers by guessing.
9. Use ONLY the enum values listed in the schema, spelled exactly. Paragraph ids in anchors are copied exactly as in [[ ]]."""

_MAX_BODY_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "90000"))


def build_prompt(doc: Doc, extra: str = "") -> str:
    """Header + judgment body (body truncated from the tail if too long) + `extra` (never truncated)."""
    head = [f"LAYOUT FLAGS: {doc.flags}",
            "DETERMINISTIC METADATA (trust over your own guess): " + json.dumps(
                {k: v for k, v in doc.meta.items() if k not in ("cited_by", "_sources", "footnotes")},
                ensure_ascii=False, default=str),
            "AUTHORITY TABLE HINTS: " + json.dumps(doc.authority_table, ensure_ascii=False),
            "=== HEADNOTE (reporter's summary; not an anchor) ===", doc.headnote[:12000],
            "=== JUDGMENT ==="]
    header = "\n".join(head)
    lines, used = [], len(header)
    for pid, p in doc.paras.items():
        ln = f"[[{pid}]] {p['text']}"
        if used + len(ln) + 1 > _MAX_BODY_CHARS and lines:
            print(f"  [warn] {Path(doc.source).name}: prompt truncated after {len(lines)}/{len(doc.paras)} paragraphs")
            lines.append("[[TRUNCATED: remaining paragraphs omitted - do not anchor to them]]")
            break
        lines.append(ln); used += len(ln) + 1
    return header + "\n" + "\n".join(lines) + (("\n" + extra) if extra else "")


def call(system: str, user: str, model_cls, model: str, max_tokens: int = 12000):
    """Tool-call the model and validate. Retries: rate limits (backoff), transient API errors, and ONE schema retry
    that feeds the validation error back to the model."""
    client = OpenAI()
    tool = {"type": "function", "function": {"name": "record", "description": "Record the structured result",
                                             "parameters": model_cls.model_json_schema()}}
    feedback, schema_retry = "", True
    for attempt in range(6):
        try:
            COERCIONS.clear()
            r = client.chat.completions.create(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user + feedback}],
                tools=[tool], tool_choice={"type": "function", "function": {"name": "record"}})
            msg = r.choices[0].message
            if not msg.tool_calls:
                raise ValueError("model returned no tool call")
            raw = msg.tool_calls[0].function.arguments
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                args = json.loads(re.sub(r",\s*([}\]])", r"\1", raw))       # trailing commas
            return model_cls.model_validate(args)
        except (ValidationError, ValueError) as e:                         # schema/JSON problem (JSONDecodeError is a ValueError)
            if not schema_retry:
                raise
            schema_retry = False
            print(f"  [schema] {str(e)[:300].splitlines()[0]} ... retrying once with feedback")
            feedback = ("\n\n=== YOUR PREVIOUS OUTPUT FAILED SCHEMA VALIDATION. Fix and return the complete record. "
                        "Use only the enum values from the schema ===\n" + str(e)[:1500])
        except Exception as e:                                             # API-level
            s = str(e).lower()
            if "429" in s or "rate_limit" in s or "timeout" in s or "502" in s or "503" in s or "overloaded" in s:
                wait = min(60 * (attempt + 1), 240)
                print(f"  [retry] {type(e).__name__}; waiting {wait}s (attempt {attempt + 1}/6)")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Exceeded maximum retries")


# --------------------------------------------------------------------------- verification
def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def quote_ok(quote: str, text: str) -> bool:
    q, t = norm(quote), norm(text)
    return bool(q) and (q in t or fuzz.partial_ratio(q, t) >= 90)


def make_anchor_resolver(doc: Doc):
    """Map whatever the model wrote ('[[P5]]', 'p5', '5', 'Para 5', 'paras 5-6') onto real paragraph ids."""
    ids = list(doc.paras)
    lower = {i.lower(): i for i in ids}
    def one(a: str) -> list[str]:
        a = re.sub(r"^\W+|\W+$", "", str(a)).strip()
        a = re.sub(r"(?i)^paras?\.?\s*", "", a)
        if a.lower() in lower:
            return [lower[a.lower()]]
        if f"P{a}".lower() in lower:
            return [lower[f"P{a}".lower()]]
        m = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", a)                        # 'P5-6' / '5-6' range
        if m:
            lo, hi = int(m[1]), int(m[2])
            got = [lower[f"p{n}"] for n in range(lo, min(hi, lo + 15) + 1) if f"p{n}" in lower]
            if got:
                return got
        return [a]                                                          # unknown -> reported by check()
    def resolve(anchors: list[str]) -> list[str]:
        out: list[str] = []
        for a in anchors:
            for x in one(a):
                if x not in out:
                    out.append(x)
        return out
    return resolve


def normalise(rec: CaseLLM, doc: Doc) -> None:
    res = make_anchor_resolver(doc)
    for p in rec.propositions:
        p.anchors = res(p.anchors)
    for i in rec.issues:
        i.anchors = res(i.anchors)
    for c in rec.contentions:
        c.anchors = res(c.anchors)
    seen = set()
    for n, p in enumerate(rec.propositions, 1):                             # ids must be unique for verdict mapping
        if not p.id or p.id in seen:
            p.id = f"p{n}" if f"p{n}" not in seen else f"p{n}_{len(seen)}"
        seen.add(p.id)


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
        sec = s.section.split("(")[0].strip()
        if sec and not re.search(rf"\b{re.escape(sec)}\b", full):
            probs.append(f"statute {s.act} s.{s.section} not found in text")
    for a in rec.authorities:
        first = re.split(r"\s+v\.?s?\.?\s+", a.name)[0]
        if first.strip() and not quote_ok(first, full):
            probs.append(f"authority '{a.name}' not found in text")
    return probs


def llm_verify(rec: CaseLLM, doc: Doc) -> dict[str, Verdict]:
    if not rec.propositions:
        return {}
    payload = [{"id": p.id, "proposition": p.text, "favors": p.favors, "speaker": p.speaker, "kind": p.kind,
                "anchor_text": " ".join(doc.paras[a]["text"] for a in p.anchors if a in doc.paras)[:6000]}
               for p in rec.propositions]
    sys_ = ("You are a strict legal cite-checker. For each item decide if anchor_text supports the proposition exactly "
            "as worded (supported / overstated = broader or more absolute than the text / unsupported) and whether "
            "'favors' is correct for a bail contest. Also flag if a rejected view is presented as the court's own. "
            "verdict MUST be exactly one of: supported, overstated, unsupported. Return one item per input id.")
    out = call(sys_, json.dumps(payload, ensure_ascii=False), Verdicts, VERIFY_MODEL, 6000)
    return {v.id: v for v in out.items}


# --------------------------------------------------------------------------- outputs
def case_id(doc: Doc) -> str:
    m = doc.meta
    for k in ("citation_scr", "citation_scc", "citation_air", "citation_neutral", "citation_online", "citation_laws"):
        if m.get(k):
            return re.sub(r"\W+", "_", str(m[k]))
    return re.sub(r"\W+", "_", Path(doc.source).stem)


def make_chunks(cid: str, rec: CaseLLM, doc: Doc, verdicts: dict) -> list[dict]:
    base = {"case_id": cid, "court": rec.court or doc.meta.get("court_regex") or doc.meta.get("court"),
            "year": doc.meta.get("year"), "bench_strength": doc.meta.get("bench_strength_regex"),
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
        ch.append({**base, "id": f"{cid}:{pid}", "type": "paragraph", "text": p["text"], "page": p["page_start"]})
    return ch


def replace_chunks(path: Path, cid: str, new: list[dict]) -> None:
    """Rewrite chunks.jsonl without any old chunks of this case, then append the new ones."""
    keep = []
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            try:
                if ln.strip() and json.loads(ln).get("case_id") != cid:
                    keep.append(ln)
            except json.JSONDecodeError:
                continue
    keep += [json.dumps(c, ensure_ascii=False) for c in new]
    path.write_text("\n".join(keep) + "\n", encoding="utf-8")


def process(path: str, out: Path, verify: bool = True, force: bool = False) -> str:
    doc = load_document(path)
    cid = case_id(doc)
    target = out / f"{cid}.json"
    if target.exists():
        try:
            prev_src = json.loads(target.read_text(encoding="utf-8")).get("doc_meta", {}).get("source_file")
        except Exception:
            prev_src = None
        if prev_src == doc.meta.get("source_file") and not force:
            print(f"{cid}: already done - skipped (use --force to redo)")
            return "skipped"
        if prev_src and prev_src != doc.meta.get("source_file"):         # two different files, same citation
            stem = re.sub(r"\W+", "_", Path(path).stem)[:40]
            cid = f"{cid}__{stem}"
            target = out / f"{cid}.json"

    if not doc.paras:
        raise RuntimeError(f"no paragraphs extracted from {Path(path).name}; flags={doc.flags}")

    coerced: list[str] = []
    rec = call(SYSTEM, build_prompt(doc), CaseLLM, EXTRACT_MODEL)
    coerced += COERCIONS
    normalise(rec, doc)
    probs = check(rec, doc)
    if probs:                                                 # one repair round, failing items only
        note = ("\n\n=== VERIFICATION FAILURES: fix these and return the complete record. Use only real anchors "
                "(exactly as in [[ ]]) and exact quotes; drop propositions you cannot ground ===\n" + "\n".join(probs) +
                "\n\nPREVIOUS OUTPUT:\n" + rec.model_dump_json())
        try:
            rec2 = call(SYSTEM, build_prompt(doc, note), CaseLLM, EXTRACT_MODEL)
            coerced += COERCIONS
            normalise(rec2, doc)
            probs2 = check(rec2, doc)
            if len(probs2) <= len(probs):                     # never let a repair make things worse
                rec, probs = rec2, probs2
        except Exception as e:
            probs.append(f"repair pass failed: {type(e).__name__}: {str(e)[:200]}")

    verdicts: dict[str, Verdict] = {}
    review = list(probs)
    if verify:
        try:
            verdicts = llm_verify(rec, doc)
            coerced += COERCIONS
        except Exception as e:
            review.append(f"verifier failed: {type(e).__name__}: {str(e)[:200]}")
    for pr in rec.propositions:
        if verify and pr.id not in verdicts:
            review.append(f"{pr.id}: no verifier verdict returned")
    for pid, v in verdicts.items():
        if v.verdict != "supported" or not v.favors_correct:
            review.append(f"{pid}: verifier says {v.verdict}, favors_correct={v.favors_correct} - {v.note}")
    if doc.meta.get("bench_strength_regex") and len(rec.coram) != doc.meta["bench_strength_regex"]:
        review.append("coram count differs between regex and LLM")
    if not rec.propositions:
        review.append("no propositions extracted")
    review += [f"auto-coerced: {c}" for c in dict.fromkeys(coerced)]
    review += [f"parser flag: {f}" for f in doc.flags if not f.startswith("ocr_noisy")]

    result = {"case_id": cid, "doc_meta": doc.meta, "flags": doc.flags, "case": rec.model_dump(),
              "authority_table": doc.authority_table, "verdicts": {k: v.model_dump() for k, v in verdicts.items()},
              "needs_review": review, "paragraphs": doc.paras, "headnote_raw": doc.headnote}
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    replace_chunks(out / "chunks.jsonl", cid, make_chunks(cid, rec, doc, verdicts))
    print(f"{cid}: {len(rec.propositions)} propositions, {len(doc.paras)} paragraphs, {len(review)} need review")
    return "ok"


_DEFAULT_INPUT_DIR = Path(__file__).parent / "Anticipatory bail application"


def main():
    ap = argparse.ArgumentParser(description="Extract precedent data from bail judgment PDFs/JSONs.")
    ap.add_argument("files", nargs="*", help=f"PDF/JSON files. Defaults to all PDFs in '{_DEFAULT_INPUT_DIR.name}/'.")
    ap.add_argument("--out", default="out", help="Output directory (default: out/)")
    ap.add_argument("--no-verify", action="store_true", help="Skip LLM verification pass")
    ap.add_argument("--force", action="store_true", help="Re-process cases that already have output")
    a = ap.parse_args()

    if not a.files:
        a.files = sorted(str(p) for p in _DEFAULT_INPUT_DIR.glob("*.pdf"))
        if not a.files:
            ap.error(f"No PDF files found in '{_DEFAULT_INPUT_DIR}'. Please pass file paths explicitly.")
        print(f"No files specified - processing {len(a.files)} PDFs from '{_DEFAULT_INPUT_DIR.name}/'\n")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stats = {"ok": 0, "skipped": 0, "failed": 0}
    for fp in a.files:
        try:
            stats[process(fp, out, verify=not a.no_verify, force=a.force)] += 1
        except KeyboardInterrupt:
            raise
        except Exception as e:
            stats["failed"] += 1
            print(f"  [FAILED] {Path(fp).name}: {type(e).__name__}: {str(e)[:300]}")
            with open(out / "errors.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"file": fp, "error": f"{type(e).__name__}: {e}",
                                    "trace": traceback.format_exc()[-1500:]}, ensure_ascii=False) + "\n")
    print(f"\nDone: {stats['ok']} ok, {stats['skipped']} skipped, {stats['failed']} failed"
          + (f" (see {out / 'errors.jsonl'})" if stats["failed"] else ""))


if __name__ == "__main__":
    main()