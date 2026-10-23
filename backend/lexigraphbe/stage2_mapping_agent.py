"""
Stage 2 Sub-Query to Section Mapping Agent.

Definition-grounded mapping in three LLM steps, none of which carries section-specific rules:
  Elements      Each retrieved section's ipc.json entry (plus the IPC Chapter II definitions of terms it
                uses) is decomposed once, without any case facts, into atomic elements grouped into a
                COMMON limb and alternative limbs. The result is cached in ipc_elements.json, so every
                query grades the same fixed element list for a section.
  Ground truth  One call reads the case narrative and the Stage 1 decomposition, evaluates the
                decomposition critically, and establishes the facts (allegations, defence claims, parties).
  Grading       For each sub-query, its top-k BM25 sections are sent with their full entries, definitions
                and elements; the LLM grades every element against the ground truth.

The code then enforces what the prompts ask for:
  - every retrieved section and every element gets a grade (skipped ones are re-asked once, then reported);
  - evidence must exist in the narrative or the ground-truth party attributes, never in a defence claim;
  - an act (CONDUCT) cannot be inferred;
  - claimed evidence for surviving sections is re-checked in a separate strict call;
  - a section that needs a role, relationship, object or state of mind the facts never mention is
    NOT_TRIGGERED; one whose act is alleged but missing a detail (or a second act of the same limb)
    is CONDITIONAL;
  - each verdict is derived from the grades, not taken from the model.

Model: gpt-4o-mini (MODEL_STAGE2).
"""

import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE2
from .prompts import (
    STAGE2_CLAIM_CHECK_SYSTEM_PROMPT,
    STAGE2_CLAIM_CHECK_USER_PROMPT_TEMPLATE,
    STAGE2_ELEMENT_DECOMPOSITION_SYSTEM_PROMPT,
    STAGE2_ELEMENT_DECOMPOSITION_USER_PROMPT_TEMPLATE,
    STAGE2_GROUND_TRUTH_SYSTEM_PROMPT,
    STAGE2_GROUND_TRUTH_USER_PROMPT_TEMPLATE,
    STAGE2_SECTION_EVALUATION_SYSTEM_PROMPT,
    STAGE2_SECTION_EVALUATION_USER_PROMPT_TEMPLATE,
)
from .batch_utils import (
    NotTriggeredSectionItem,
    SectionMappingCandidate,
    Stage2BatchedMappingResponse,
    SubQueryChapterMapping,
)
from .schemas.stage1 import LegalQueryObject
from .retriever import toks


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ELEMENTS_CACHE_PATH = os.path.join(BASE_DIR, "ipc_elements.json")

# Bump when the decomposition prompt changes so cached decompositions are rebuilt.
_ELEMENTS_VERSION = "4"

# BM25 candidates retrieved per sub-query.
_TOP_K = 20

# Sections graded per LLM call; calls run in parallel. gpt-4o-mini's grade for a section shifts with the
# other sections in the same call, so each section is graded on its own.
_BATCH_SIZE = 1
_MAX_PARALLEL_CALLS = 8

# Fixed sampling seed so repeated runs of the same query are as reproducible as the provider allows.
_SEED = 7

# A Chapter II term used by more than this share of sections ("act", "offence", "section", ...) explains
# nothing specific about a section, so its definition is not attached.
_DEFINITION_MAX_COVERAGE = 0.25
_DEFINITION_MAX_CHARS = 900
_GENERAL_EXPLANATIONS_CHAPTER = "II"

# Stage 1 fields that carry Stage 1's own verdicts rather than facts. Stage 2 forms its own view
# from the facts, so these are withheld instead of being passed on as conclusions to follow.
_STAGE1_DECOMPOSITION_FIELDS = (
    "case_type", "legal_regime", "entities", "relationship", "factual_allegations",
    "legal_concepts", "sub_queries", "offence_families", "procedural_events", "important_facts",
)
_STAGE1_VERDICT_KEYS = {
    "legal_concepts": ("description",),  # taxonomy boilerplate, not facts of this case
    "offence_families": ("status", "reason", "trigger_satisfied"),
}

# ipc.json bookkeeping fields that say nothing about the law of the section.
_ENTRY_SKIP_FIELDS = {"page", "is_omitted", "is_repealed", "_chapter"}

_GRADES = {"SATISFIED", "INFERRED", "MISSING", "CONTRADICTED"}
_EVIDENCE_GRADES = {"SATISFIED", "INFERRED", "CONTRADICTED"}
_ELEMENT_TYPES = {"CONDUCT", "MENTAL", "CIRCUMSTANCE"}

_PUNCT_MAP = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
})


def _norm(text: Any) -> str:
    text = str(text or "").lower().translate(_PUNCT_MAP)
    return re.sub(r"\s+", " ", text).strip(" .,;:\"'")


def _quote_in(quote: str, haystack_norm: str) -> bool:
    """True if every part of the quote (split on ellipses) appears verbatim in the haystack."""
    parts = [p for p in (_norm(x) for x in re.split(r"\.\.\.|…", quote or "")) if p]
    return bool(parts) and all(p in haystack_norm for p in parts)


def _clean_section_number(value: Any) -> str:
    s = str(value or "").strip().upper()
    s = re.sub(r"^(SECTION|SEC\.?|S\.)\s*", "", s)
    s = re.sub(r"\s*(IPC|OF IPC)$", "", s)
    return s.replace(" ", "")


class Stage2SubQueryMappingAgent:
    """
    Stage 2 Agent mapping sub-queries to candidate IPC sections.
    BM25 retrieval (0 API calls) + element decomposition (cached per section) + 1 ground-truth call
    + 1 grading call per batch of sections per sub-query (run in parallel).
    """

    _cache_lock = threading.Lock()

    def __init__(
        self,
        llm: Optional[Any] = None,
        retriever: Optional[Any] = None,
        top_k: int = _TOP_K,
    ):
        self._llm = llm
        self._retriever = retriever
        self.top_k = top_k
        self._elements_cache: Optional[Dict[str, Any]] = None
        self._definitions_index: Optional[Dict[str, List[Dict[str, str]]]] = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.0, model_name=MODEL_STAGE2)
        return self._llm

    @property
    def retriever(self):
        if self._retriever is None:
            from .retriever import get_retriever
            self._retriever = get_retriever()
        return self._retriever

    # ------------------------------------------------------------------
    # LLM plumbing
    # ------------------------------------------------------------------

    def _invoke_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        llm = self.llm
        if type(llm).__name__ == "ChatOpenAI":
            llm = llm.bind(seed=_SEED, response_format={"type": "json_object"})
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        return extract_json_from_text(response.content if hasattr(response, "content") else str(response))

    @staticmethod
    def _batches(items: List[str]) -> List[List[str]]:
        return [items[i:i + _BATCH_SIZE] for i in range(0, len(items), _BATCH_SIZE)]

    # ------------------------------------------------------------------
    # Law: ipc.json entries, general definitions, element decomposition
    # ------------------------------------------------------------------

    def _entry(self, section_number: str) -> Dict[str, Any]:
        r = self.retriever
        return r.secs[r.ids.index(section_number)]

    def _general_definitions(self, section_number: str) -> List[Dict[str, str]]:
        """IPC Chapter II definitions of terms that this section's text uses."""
        if self._definitions_index is None:
            secs = self.retriever.secs
            texts = {s["section_number"]: f"{s.get('heading', '')} {s.get('text') or ''}".lower() for s in secs}
            index: Dict[str, List[Dict[str, str]]] = {sid: [] for sid in texts}
            for d in secs:
                if not str(d.get("_chapter", "")).startswith(f"Chapter {_GENERAL_EXPLANATIONS_CHAPTER} "):
                    continue
                terms = [t.strip().lower() for t in re.findall(r'["“]([^"”]+)["”]', d.get("heading", ""))]
                patterns = [re.compile(rf"\b{re.escape(t)}\b") for t in terms if t]
                users = [sid for sid, txt in texts.items() if sid != d["section_number"] and any(p.search(txt) for p in patterns)]
                if not users or len(users) > _DEFINITION_MAX_COVERAGE * len(texts):
                    continue
                item = {
                    "section": d["section_number"],
                    "heading": d.get("heading", ""),
                    "text": (d.get("text") or "")[:_DEFINITION_MAX_CHARS],
                }
                for sid in users:
                    index[sid].append(item)
            self._definitions_index = index
        return self._definitions_index.get(section_number, [])

    def _law_payload(self, section_number: str) -> Dict[str, Any]:
        sec = self._entry(section_number)
        payload = {k: v for k, v in sec.items() if k not in _ENTRY_SKIP_FIELDS and v not in (None, "", [])}
        payload["chapter"] = sec.get("_chapter", "")
        definitions = self._general_definitions(section_number)
        if definitions:
            payload["general_definitions"] = definitions
        return payload

    def _entry_hash(self, section_number: str) -> str:
        raw = json.dumps(self._law_payload(section_number), sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(f"{_ELEMENTS_VERSION}:{raw}".encode("utf-8")).hexdigest()

    def _load_elements_cache(self) -> Dict[str, Any]:
        if self._elements_cache is None:
            try:
                with open(_ELEMENTS_CACHE_PATH, encoding="utf-8") as f:
                    self._elements_cache = json.load(f)
            except (OSError, ValueError):
                self._elements_cache = {}
        return self._elements_cache

    @staticmethod
    def _parse_decomposition(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalises one section's decomposition and assigns stable element ids; None if unusable."""
        limbs_out: List[Dict[str, Any]] = []
        n = 0
        for limb in raw.get("limbs") or []:
            if not isinstance(limb, dict):
                continue
            label = str(limb.get("limb") or "").strip().upper()
            label = "COMMON" if label in ("", "COMMON", "ALL") else label
            elements = []
            for el in limb.get("elements") or []:
                if not isinstance(el, dict) or not str(el.get("element") or "").strip():
                    continue
                n += 1
                etype = str(el.get("element_type", "")).upper()
                elements.append({
                    "element_id": f"E{n}",
                    "element": str(el["element"]).strip(),
                    "element_type": etype if etype in _ELEMENT_TYPES else "CIRCUMSTANCE",
                    "construction": None if str(el.get("construction") or "").strip().lower() in ("", "null", "none") else el["construction"],
                })
            if elements:
                limbs_out.append({"limb": label, "elements": elements})
        kind = str(raw.get("provision_kind", "")).upper()
        if not limbs_out and kind != "NON_OFFENCE":
            return None
        return {"provision_kind": "NON_OFFENCE" if kind == "NON_OFFENCE" else "OFFENCE", "limbs": limbs_out}

    def _decompose_batch(self, batch: List[str]) -> Dict[str, Dict[str, Any]]:
        user_prompt = STAGE2_ELEMENT_DECOMPOSITION_USER_PROMPT_TEMPLATE.format(
            sections_json=json.dumps([self._law_payload(s) for s in batch], indent=2, ensure_ascii=False),
            section_list=", ".join(batch),
        )
        try:
            data = self._invoke_json(STAGE2_ELEMENT_DECOMPOSITION_SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            print(f"  [Stage 2] Element decomposition failed for {', '.join(batch)} ({e}).", flush=True)
            return {}
        wanted = {s.upper(): s for s in batch}
        out: Dict[str, Dict[str, Any]] = {}
        for raw in data.get("sections") or []:
            if not isinstance(raw, dict):
                continue
            sec = wanted.get(_clean_section_number(raw.get("section_number")))
            parsed = self._parse_decomposition(raw) if sec else None
            if parsed:
                out[sec] = parsed
        return out

    def _ensure_elements(self, section_numbers: List[str]) -> Dict[str, Dict[str, Any]]:
        """Returns the element decomposition of each section, decomposing and caching uncached ones."""
        cache = self._load_elements_cache()
        hashes = {s: self._entry_hash(s) for s in section_numbers}
        todo = [s for s in section_numbers if (cache.get(s) or {}).get("hash") != hashes[s]]
        for _ in range(2):  # second pass retries sections the first pass could not decompose
            if not todo:
                break
            batches = [[s] for s in todo]  # one section per call: decomposition needs full attention
            fresh: Dict[str, Dict[str, Any]] = {}
            with ThreadPoolExecutor(max_workers=min(_MAX_PARALLEL_CALLS, len(batches))) as pool:
                for result in pool.map(self._decompose_batch, batches):
                    fresh.update(result)
            if fresh:
                with self._cache_lock:
                    for sec, dec in fresh.items():
                        cache[sec] = {"hash": hashes[sec], **dec}
                    tmp = f"{_ELEMENTS_CACHE_PATH}.tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(cache, f, indent=1, ensure_ascii=False, sort_keys=True)
                    os.replace(tmp, _ELEMENTS_CACHE_PATH)
                print(f"  [Stage 2] Decomposed and cached elements for {len(fresh)} section(s).", flush=True)
            todo = [s for s in todo if s not in fresh]
        if todo:
            print(f"  [Stage 2] No element decomposition for: {', '.join(todo)}.", flush=True)
        return {s: cache[s] for s in section_numbers if s in cache and s not in todo}

    # ------------------------------------------------------------------
    # Facts: ground truth
    # ------------------------------------------------------------------

    @staticmethod
    def _stage1_decomposition(query_obj: LegalQueryObject) -> Dict[str, Any]:
        dumped = query_obj.model_dump()
        out = {k: dumped.get(k) for k in _STAGE1_DECOMPOSITION_FIELDS if dumped.get(k)}
        for field, keys in _STAGE1_VERDICT_KEYS.items():
            for item in out.get(field) or []:
                for k in keys:
                    item.pop(k, None)
        return out

    @staticmethod
    def _fallback_ground_truth(query_obj: LegalQueryObject) -> Dict[str, Any]:
        """Ground truth straight from Stage 1 allegations, used only if the LLM pass fails."""
        alleged, defence = [], []
        for f in query_obj.factual_allegations:
            item = {"quote": f.verbatim_quote or "", "description": f.description}
            if str(f.factual_status).upper() == "DISPUTED":
                defence.append({"claim_id": f.fact_id, **item})
            else:
                alleged.append({"fact_id": f.fact_id, **item})
        return {
            "alleged_facts": alleged,
            "defence_claims": defence,
            "parties": [],
            "unknowns": [],
            "decomposition_corrections": [],
        }

    def _establish_ground_truth(self, query_obj: LegalQueryObject, case_facts: str) -> Dict[str, Any]:
        facts_norm = _norm(case_facts)
        user_prompt = STAGE2_GROUND_TRUTH_USER_PROMPT_TEMPLATE.format(
            case_facts=case_facts,
            decomposition_json=json.dumps(self._stage1_decomposition(query_obj), indent=2, ensure_ascii=False),
        )
        try:
            gt = self._invoke_json(STAGE2_GROUND_TRUTH_SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            print(f"  [Stage 2] Ground truth pass failed ({e}); using Stage 1 allegations.", flush=True)
            return self._fallback_ground_truth(query_obj)

        # Keep only facts whose quotes actually exist in the narrative.
        for key in ("alleged_facts", "defence_claims"):
            items = [i for i in (gt.get(key) or []) if isinstance(i, dict)]
            kept = [i for i in items if _quote_in(i.get("quote", ""), facts_norm)]
            if len(kept) < len(items):
                print(f"  [Stage 2] Ground truth: dropped {len(items) - len(kept)} {key} with quotes not in case facts.", flush=True)
            gt[key] = kept

        if not gt.get("alleged_facts"):
            print("  [Stage 2] Ground truth has no grounded allegations; using Stage 1 allegations.", flush=True)
            return self._fallback_ground_truth(query_obj)
        return gt

    # ------------------------------------------------------------------
    # Grading
    # ------------------------------------------------------------------

    def _request_grades(
        self,
        sq_json: str,
        section_numbers: List[str],
        elements: Dict[str, Dict[str, Any]],
        case_facts: str,
        ground_truth_json: str,
        feedback_section: str,
    ) -> Tuple[str, Dict[str, Dict[str, Any]]]:
        sections = []
        for s in section_numbers:
            payload = self._law_payload(s)
            payload["provision_kind"] = elements[s]["provision_kind"]
            payload["elements"] = elements[s]["limbs"]
            sections.append(payload)
        user_prompt = STAGE2_SECTION_EVALUATION_USER_PROMPT_TEMPLATE.format(
            case_facts=case_facts,
            ground_truth_json=ground_truth_json,
            sub_query_json=sq_json,
            sections_json=json.dumps(sections, indent=2, ensure_ascii=False),
            correction_feedback_section=feedback_section,
            section_list=", ".join(section_numbers),
        )
        data = self._invoke_json(STAGE2_SECTION_EVALUATION_SYSTEM_PROMPT, user_prompt)
        wanted = {s.upper(): s for s in section_numbers}
        evaluations: Dict[str, Dict[str, Any]] = {}
        for ev in data.get("section_evaluations") or []:
            if not isinstance(ev, dict):
                continue
            sec = wanted.get(_clean_section_number(ev.get("section_number")))
            if sec and isinstance(ev.get("grades"), list):
                evaluations[sec] = ev
        return str(data.get("sub_query_analysis") or ""), evaluations

    @staticmethod
    def _fully_graded(decomposition: Dict[str, Any], ev: Dict[str, Any]) -> bool:
        graded = {str(g.get("element_id", "")).strip().upper() for g in ev.get("grades") or [] if isinstance(g, dict)}
        return all(el["element_id"] in graded for limb in decomposition["limbs"] for el in limb["elements"])

    @staticmethod
    def _conduct_alleged(item: Dict[str, Any]) -> bool:
        """An act is alleged if it is SATISFIED, or MISSING only as to a quality of it (DETAIL)."""
        return item["element_type"] == "CONDUCT" and (
            item["status"] == "SATISFIED" or (item["status"] == "MISSING" and item["gap_kind"] == "DETAIL")
        )

    @staticmethod
    def _foreign_gap(item: Dict[str, Any]) -> bool:
        """A missing role, relationship, object or state of mind the facts never mention at all."""
        return item["element_type"] != "CONDUCT" and item["status"] == "MISSING" and item["gap_kind"] == "NEW_MATTER"

    @classmethod
    def _limb_rank(cls, items: List[Dict[str, Any]]) -> Tuple[bool, bool, bool, int, int]:
        grades = [i["status"] for i in items]
        conduct_ok = any(i["element_type"] == "CONDUCT" and i["status"] == "SATISFIED" for i in items)
        conduct_alleged = any(cls._conduct_alleged(i) for i in items)
        no_foreign = not any(cls._foreign_gap(i) for i in items)
        return ("CONTRADICTED" not in grades and no_foreign, conduct_ok, conduct_alleged,
                -grades.count("MISSING"), grades.count("SATISFIED"))

    @classmethod
    def _audit_evaluation(
        cls,
        decomposition: Dict[str, Any],
        ev: Dict[str, Any],
        facts_norm: str,
        alleged_norms: List[str],
        defence_norms: List[str],
        party_attributes: List[str],
        rejected_claims: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], float, List[str], List[Dict[str, Any]]]:
        """
        Checks one section's grades against the ground truth and derives its verdict from them.
        rejected_claims maps element_id -> reason for claims the evidence check did not uphold.
        Returns (verdict, assessed_elements, support_score, audit_notes, all_elements).
        """
        rejected_claims = rejected_claims or {}
        notes: List[str] = []
        grades_by_id = {
            str(g.get("element_id", "")).strip().upper(): g
            for g in (ev.get("grades") or []) if isinstance(g, dict)
        }

        limbs: Dict[str, List[Dict[str, Any]]] = {}
        ungraded = []
        for limb in decomposition["limbs"]:
            for el in limb["elements"]:
                g = grades_by_id.get(el["element_id"])
                item = {**el, "limb": limb["limb"], **{k: (g or {}).get(k) for k in ("fact_ids", "evidence_source", "evidence_quote", "inference")}}
                gap = str((g or {}).get("gap_kind") or "").upper()
                item["gap_kind"] = gap if gap in ("DETAIL", "NEW_MATTER") else "DETAIL"
                item["status"] = str((g or {}).get("status", "")).upper()
                if g is None:
                    ungraded.append(el["element_id"])
                if item["status"] not in _GRADES:
                    item["status"] = "MISSING"
                name = el["element"]

                if item["element_type"] == "CONDUCT" and item["status"] == "INFERRED":
                    notes.append(f"'{name}' is an act and cannot be inferred; treated as MISSING.")
                    item["status"] = "MISSING"

                # A state of mind is SATISFIED only when the quoted fact speaks to it; otherwise it is inferred.
                if (item["element_type"] == "MENTAL" and item["status"] == "SATISFIED"
                        and not set(toks(name)) & set(toks(str(item.get("evidence_quote") or "")))):
                    item["status"] = "INFERRED"

                if item["status"] in _EVIDENCE_GRADES:
                    quote = str(item.get("evidence_quote") or "")
                    q_norm = _norm(quote)
                    if str(item.get("evidence_source", "")).upper() == "PARTY_ATTRIBUTE":
                        if not q_norm or not any(q_norm in a or a in q_norm for a in party_attributes):
                            notes.append(f"'{name}' graded {item['status']} on a party attribute not in the ground truth; treated as MISSING.")
                            item["status"] = "MISSING"
                    elif not _quote_in(quote, facts_norm):
                        notes.append(f"'{name}' graded {item['status']} on a quote not in case facts; treated as MISSING.")
                        item["status"] = "MISSING"
                    elif any(q_norm in d for d in defence_norms) and not any(q_norm in a for a in alleged_norms):
                        notes.append(f"'{name}' graded {item['status']} on a defence claim; treated as MISSING.")
                        item["status"] = "MISSING"
                if item["status"] in ("SATISFIED", "INFERRED") and el["element_id"] in rejected_claims:
                    notes.append(f"'{name}' was not upheld by the evidence check ({rejected_claims[el['element_id']]}); treated as MISSING.")
                    item["status"] = "MISSING"
                    item["gap_kind"] = "NEW_MATTER" if item["element_type"] == "CONDUCT" else "DETAIL"
                limbs.setdefault(limb["limb"], []).append(item)
        all_elements = [i for items in limbs.values() for i in items]
        if ungraded:
            notes.append(f"Elements {', '.join(ungraded)} were not graded; treated as MISSING.")

        # Assess the COMMON elements plus the single best-supported alternative limb.
        common = limbs.pop("COMMON", [])
        if limbs:
            best = max(limbs, key=lambda k: cls._limb_rank(common + limbs[k]))
            assessed = common + limbs[best]
        else:
            assessed = common
        grades = [i["status"] for i in assessed]

        if decomposition["provision_kind"] == "NON_OFFENCE":
            verdict = "NOT_TRIGGERED"
        elif "CONTRADICTED" in grades:
            verdict = "NOT_TRIGGERED"
        elif not any(cls._conduct_alleged(i) for i in assessed):
            verdict = "NOT_TRIGGERED"
        elif any(cls._foreign_gap(i) for i in assessed):
            # A missing act inside a limb whose other act is alleged is left to CONDITIONAL; the gate is for
            # sections that need a role, relationship, object or state of mind foreign to the facts.
            verdict = "NOT_TRIGGERED"
        elif "MISSING" in grades:
            verdict = "CONDITIONAL"
        elif "INFERRED" in grades:
            verdict = "SECONDARY"
        else:
            verdict = "PRIMARY"

        weights = {"SATISFIED": 1.0, "INFERRED": 0.5}
        support = sum(weights.get(g, 0.0) for g in grades) / len(grades) if grades else 0.0
        return verdict, assessed, round(support, 4), notes, all_elements

    def _check_claims(self, items: List[Dict[str, Any]], ground_truth_json: str) -> Dict[str, str]:
        """Asks the evidence checker about every fact-based SATISFIED/INFERRED element; returns rejected ids."""
        claims = [
            {
                "claim_id": i["element_id"],
                "element": i["element"],
                "status": i["status"],
                "quote": i.get("evidence_quote"),
                "inference": i.get("inference") if i["status"] == "INFERRED" else None,
            }
            for i in items
            if i["status"] in ("SATISFIED", "INFERRED")
            and str(i.get("evidence_source", "")).upper() != "PARTY_ATTRIBUTE"
        ]
        if not claims:
            return {}
        user_prompt = STAGE2_CLAIM_CHECK_USER_PROMPT_TEMPLATE.format(
            ground_truth_json=ground_truth_json,
            claims_json=json.dumps(claims, indent=2, ensure_ascii=False),
        )
        try:
            data = self._invoke_json(STAGE2_CLAIM_CHECK_SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            print(f"  [Stage 2] Evidence check failed ({e}); grades kept as given.", flush=True)
            return {}
        return {
            str(c.get("claim_id", "")).strip().upper(): str(c.get("reason") or "unsupported")
            for c in data.get("checks") or []
            if isinstance(c, dict) and c.get("supported") is False
        }

    def _map_sub_query(
        self,
        sq: Any,
        hits: List[Dict[str, Any]],
        elements: Dict[str, Dict[str, Any]],
        case_facts: str,
        ground_truth: Dict[str, Any],
        feedback_section: str,
    ) -> SubQueryChapterMapping:
        sq_id = getattr(sq, "id", "SQ1")
        sq_query = getattr(sq, "query", "") or ""
        hit_by_sec = {h["section_number"]: h for h in hits}
        section_numbers = list(hit_by_sec)

        sq_json = json.dumps(sq.model_dump() if hasattr(sq, "model_dump") else dict(sq), indent=2, ensure_ascii=False)
        gt_json = json.dumps(ground_truth, indent=2, ensure_ascii=False)

        def grade_batch(batch: List[str]) -> Tuple[str, Dict[str, Dict[str, Any]]]:
            try:
                return self._request_grades(sq_json, batch, elements, case_facts, gt_json, feedback_section)
            except Exception as e:
                print(f"  [Stage 2] {sq_id}: grading call failed for {', '.join(batch)} ({e}).", flush=True)
                return "", {}

        analysis = ""
        evaluations: Dict[str, Dict[str, Any]] = {}
        pending = [s for s in section_numbers if s in elements]
        for _ in range(2):  # second pass re-asks only for sections the first pass skipped
            if not pending:
                break
            batches = self._batches(pending)
            with ThreadPoolExecutor(max_workers=min(_MAX_PARALLEL_CALLS, len(batches))) as pool:
                for a, evs in pool.map(grade_batch, batches):
                    analysis = analysis or a
                    for sec, ev in evs.items():
                        # A partial grading is kept as a fallback but re-asked; a complete one replaces it.
                        if sec not in evaluations or self._fully_graded(elements[sec], ev):
                            evaluations[sec] = ev
            pending = [s for s in pending if s not in evaluations or not self._fully_graded(elements[s], evaluations[s])]

        facts_norm = _norm(case_facts)
        alleged_norms = [_norm(f.get("quote")) for f in ground_truth.get("alleged_facts", [])]
        defence_norms = [_norm(d.get("quote")) for d in ground_truth.get("defence_claims", [])]
        party_attributes = [
            _norm(a) for p in ground_truth.get("parties", []) if isinstance(p, dict)
            for a in (p.get("attributes") or []) if _norm(a)
        ]

        tiers: Dict[str, List[SectionMappingCandidate]] = {"PRIMARY": [], "SECONDARY": [], "CONDITIONAL": []}
        not_triggered: List[NotTriggeredSectionItem] = []
        chapters: List[str] = []
        matched_all: List[str] = []
        unevaluated: List[str] = []

        audit_args = (facts_norm, alleged_norms, defence_norms, party_attributes)

        # Sections that survive the first audit get their claimed evidence checked once more, each in its own call.
        def evidence_check(sec: str) -> Tuple[str, Dict[str, str]]:
            verdict, _, _, _, items = self._audit_evaluation(elements[sec], evaluations[sec], *audit_args)
            return sec, ({} if verdict == "NOT_TRIGGERED" else self._check_claims(items, gt_json))

        rejected: Dict[str, Dict[str, str]] = {}
        to_check = [s for s in section_numbers if s in evaluations]
        if to_check:
            with ThreadPoolExecutor(max_workers=min(_MAX_PARALLEL_CALLS, len(to_check))) as pool:
                rejected = dict(pool.map(evidence_check, to_check))

        for sec in section_numbers:
            hit = hit_by_sec[sec]
            title = str(hit.get("section_title") or f"Section {sec}")
            ev = evaluations.get(sec)
            if ev is None:
                unevaluated.append(sec)
                not_triggered.append(NotTriggeredSectionItem(
                    section_number=sec,
                    section_title=title,
                    statute="IPC",
                    not_triggered_reason="UNEVALUATED: no element analysis or grades could be obtained for this retrieved section.",
                    missing_mandatory_ingredients=[],
                ))
                continue

            verdict, assessed, support, notes, _ = self._audit_evaluation(
                elements[sec], ev, *audit_args, rejected_claims=rejected.get(sec)
            )
            new_matter = [i["element"] for i in assessed if self._foreign_gap(i)]
            if new_matter and verdict == "NOT_TRIGGERED":
                notes.append(f"Requires matter the facts do not mention: {'; '.join(new_matter)}.")
            if elements[sec]["provision_kind"] == "NON_OFFENCE":
                notes.append("Provision creates no offence.")
            reasoning = " ".join([str(ev.get("reasoning") or "").strip()] + [f"[audit] {n}" for n in notes]).strip()

            if verdict == "NOT_TRIGGERED":
                not_triggered.append(NotTriggeredSectionItem(
                    section_number=sec,
                    section_title=title,
                    statute="IPC",
                    not_triggered_reason=reasoning or "Elements not supported by the alleged facts.",
                    missing_mandatory_ingredients=[
                        f"{i['element']} [{i['status']}]" for i in assessed if i["status"] in ("MISSING", "CONTRADICTED")
                    ],
                ))
                continue

            matched = [
                f"{i['element']} [{i['status']}: {', '.join(i.get('fact_ids') or [])}]"
                for i in assessed if i["status"] in ("SATISFIED", "INFERRED")
            ]
            matched_all.extend(m for m in matched if m not in matched_all)
            chap = str(hit.get("chapter") or "")
            if chap and chap not in chapters:
                chapters.append(chap)
            tiers[verdict].append(SectionMappingCandidate(
                section_number=sec,
                section_title=title,
                statute="IPC",
                candidate_type=verdict,
                score=support,
                score_breakdown={"bm25_hybrid": float(hit.get("score", 0.0)), "ingredient_support": support},
                ingredients_matched=matched,
                missing_facts=[str(m) for m in (ev.get("missing_facts") or [])]
                or [f"{i['element']}" for i in assessed if i["status"] == "MISSING"],
                relevance_reasoning=reasoning,
                retrieval_sources=["bm25_hybrid"],
            ))

        sq_fact_ids = set(getattr(sq, "fact_ids", []) or [])
        facts_extracted = [
            f.get("quote", "") for f in ground_truth.get("alleged_facts", []) if f.get("fact_id") in sq_fact_ids
        ] or [sq_query]

        counts = {t: len(v) for t, v in tiers.items()}
        print(
            f"  [Stage 2] {sq_id}: {len(section_numbers)} retrieved -> P{counts['PRIMARY']} S{counts['SECONDARY']} "
            f"C{counts['CONDITIONAL']} NT{len(not_triggered)}" + (f" (unevaluated: {', '.join(unevaluated)})" if unevaluated else ""),
            flush=True,
        )

        return SubQueryChapterMapping(
            sub_query_id=sq_id,
            sub_query_text=sq_query,
            target_parties=list(getattr(sq, "target_parties", []) or []),
            facts_extracted=facts_extracted,
            ingredients_matched=matched_all,
            candidate_chapters=chapters,
            primary_candidate_sections=tiers["PRIMARY"],
            secondary_candidate_sections=tiers["SECONDARY"],
            conditional_candidate_sections=tiers["CONDITIONAL"],
            not_triggered_sections=not_triggered,
            relevance_reasoning=analysis or f"Evaluated top {len(section_numbers)} BM25 sections for {sq_id}.",
        )

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(
        self,
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        correction_feedback: Optional[str] = None,
    ) -> Stage2BatchedMappingResponse:
        """
        Runs Stage 2 mapping on a LegalQueryObject.

        Args:
            legal_query: LegalQueryObject from Stage 1.
            correction_feedback: Feedback from verifier if retrying.

        Returns:
            Stage2BatchedMappingResponse instance.
        """
        if isinstance(legal_query, LegalQueryObject):
            query_obj = legal_query
        elif isinstance(legal_query, dict):
            query_obj = LegalQueryObject.model_validate(legal_query)
        else:
            query_obj = LegalQueryObject.model_validate(json.loads(str(legal_query)))

        case_facts = str(getattr(query_obj, "case_facts", "") or "").strip() or " ".join(
            str(f.verbatim_quote or f.description or "") for f in query_obj.factual_allegations
        )

        sub_queries = list(query_obj.sub_queries or [])
        if not sub_queries:
            from .schemas import SubQueryItem
            sub_queries = [SubQueryItem(id="SQ1", concept="Case Allegations", query=case_facts)]

        feedback_section = (
            f"\nPREVIOUS STAGE 2 AUDIT FEEDBACK (address it where the facts and ipc.json support it):\n{correction_feedback}\n"
            if correction_feedback else ""
        )

        # BM25 on the sub-query's own (verbatim) text; the concept label is a Stage 1 opinion, not a fact.
        hits_per_sq = [
            self.retriever.retrieve_top_k(getattr(sq, "query", "") or getattr(sq, "concept", "") or "", k=self.top_k, mode="hybrid")
            for sq in sub_queries
        ]
        all_sections = list(dict.fromkeys(h["section_number"] for hits in hits_per_sq for h in hits))

        _ = self.llm  # build the client once, before worker threads share it
        with ThreadPoolExecutor(max_workers=2) as pool:
            gt_future = pool.submit(self._establish_ground_truth, query_obj, case_facts)
            elements = self._ensure_elements(all_sections)
            ground_truth = gt_future.result()

        with ThreadPoolExecutor(max_workers=min(4, len(sub_queries))) as pool:
            mappings = list(pool.map(
                lambda args: self._map_sub_query(args[0], args[1], elements, case_facts, ground_truth, feedback_section),
                zip(sub_queries, hits_per_sq),
            ))

        return Stage2BatchedMappingResponse(mappings=mappings)
