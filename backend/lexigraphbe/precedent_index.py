"""
Persistent, incremental index over the tagged judgment corpus (built for 20K+ judgments).

Why: the old retriever opened and scored every tagged_*.json on every query. This module parses each judgment once,
keeps only compact per-case records in memory, and answers queries from three structures:

  statute postings   canonical statute key (old-regime, e.g. "IPC:420", "CRPC:438") -> case indices
  fact space         sparse TF-IDF over abstract_facts          (cosine similarity to the input's facts)
  issue space        sparse TF-IDF over issues + holdings text  (cosine similarity to the input's legal issues)

plus a citation graph (who cites whom inside the corpus) used as an authority signal, and per-case offence
categories from offence_taxonomy. Full judgment JSON is loaded lazily, only for the few cases that are returned.

Everything is data-driven: no case names, no section lists, no keyword lists tied to any fact pattern. Similarity
scales are calibrated from the corpus itself (calibrate()), so thresholds follow the corpus as it grows.

The TF-IDF spaces can be supplemented with dense embeddings by passing an `embedder` (any object with
`encode(list[str]) -> list[list[float]]`); the score then takes max(tfidf, dense) per space. Without one the index
is pure python with no extra dependencies.
"""

import json
import math
import pickle
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .offence_taxonomy import categories_for, category_vector

# ----------------------------------------------------------------------------
# Text processing
# ----------------------------------------------------------------------------

_STOP = set("""
a an and are as at be been being but by can could did do does for from had has have he her his if in into is it its
may might not of on or our shall she should so such than that the their them then there these they this those to
under upon was we were what when where which while who whom why will with would you your also any all both each few
more most other some than too very can said per via
appellant respondent petitioner complainant court case section sections state india accused applicant
alleged allegations allegation filed order high supreme judgment appeal hereby thereof therein
""".split())

_SUFFIXES = ("ations", "ation", "ingly", "ments", "ment", "ities", "ness", "ings", "ing", "ies", "ied", "ed", "es", "s")


def stem(tok: str) -> str:
    for suf in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            return tok[: -len(suf)] + ("y" if suf in ("ies", "ied") else "")
    return tok


def tokenize(text: str) -> List[str]:
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [stem(t) for t in toks if len(t) >= 3 and t not in _STOP]


# ----------------------------------------------------------------------------
# Stage inference (kept here so the index and the retriever agree)
# ----------------------------------------------------------------------------
ANTICIPATORY_MARKERS = ("anticipatory bail", "pre-arrest bail", "section 438", "bnss 482", "s. 438")
CANCEL_MARKERS = ("cancel", "set aside", "setting aside", "quash the order granting")


def cites_anticipatory_provision(statutes: List[Dict[str, Any]]) -> bool:
    for st in statutes or []:
        act = re.sub(r"[^A-Z]", "", str(st.get("act") or "").upper())
        sec = str(st.get("section") or "").strip().upper()
        how = str(st.get("how_used") or "").lower()
        if how not in ("interpreted", "applied", "considered", "relied"):
            continue
        if (act.startswith("CRPC") and sec.startswith("438")) or (act.startswith("BNSS") and sec.startswith("482")):
            return True
    return False


def infer_case_stage(case: Dict[str, Any]) -> str:
    """pre_arrest | anticipatory_cancel | quashing | post_arrest_bail | other (corpus tag is only a fallback)."""
    tag = str(case.get("procedural_stage") or "other").strip().lower()
    if tag in ("pre_arrest", "quashing"):
        return tag
    head = " ".join([str(case.get("abstract_facts") or ""), str(case.get("disposition") or "")]).lower()
    props = " ".join(str(p.get("text") or "") for p in case.get("propositions", []) or []).lower()
    if any(m in head for m in ANTICIPATORY_MARKERS) or cites_anticipatory_provision(case.get("statutes")):
        if any(m in head or m in props for m in CANCEL_MARKERS):
            return "anticipatory_cancel"
        return "pre_arrest"
    return tag if tag in ("post_arrest_bail",) else "other"


SIDE_OF_FAVORS = {"prosecution": "prosecution", "accused": "defense", "defense": "defense", "defence": "defense"}


def direction_shares(propositions: List[Dict[str, Any]]) -> Dict[str, float]:
    """Share of holding propositions favouring each side (neutral/unknown counts half)."""
    holdings = [p for p in propositions if p.get("is_holding") or p.get("kind") == "ratio"]
    if not holdings:
        return {"prosecution": 0.5, "defense": 0.5}
    out = {"prosecution": 0.0, "defense": 0.0}
    for p in holdings:
        side = SIDE_OF_FAVORS.get(str(p.get("favors") or "").lower())
        for role in out:
            out[role] += 1.0 if side == role else (0.5 if side is None else 0.0)
    return {k: v / len(holdings) for k, v in out.items()}


# ----------------------------------------------------------------------------
# Record
# ----------------------------------------------------------------------------

@dataclass
class Record:
    idx: int = -1
    path: str = ""
    case_id: str = ""
    name: str = ""
    court_weight: float = 0.4
    decided_on: str = ""
    tag_stage: str = ""
    stage: str = "other"
    keys: Set[str] = field(default_factory=set)               # canonical statute keys (+ parent keys)
    substantive_keys: Set[str] = field(default_factory=set)   # subset: offences / special acts
    categories: Dict[str, float] = field(default_factory=dict)
    n_holdings: int = 0
    direction: Dict[str, float] = field(default_factory=dict)
    fact_tf: Dict[str, int] = field(default_factory=dict)
    issue_tf: Dict[str, int] = field(default_factory=dict)
    authority_names: List[Tuple[str, str]] = field(default_factory=list)   # (name, treatment)
    indegree: float = 0.0
    cites: List[int] = field(default_factory=list)    # resolved corpus judgments this one cites (citation graph)


def _norm_name(name: str) -> str:
    t = re.sub(r"\b(vs?\.?|versus|and|ors?|anr|another|others|state|of|the|etc|by|through)\b", " ", (name or "").lower())
    return " ".join(sorted(re.findall(r"[a-z0-9]{2,}", t)))


def _court_weight(court: str) -> float:
    c = (court or "").lower()
    if "supreme" in c:
        return 1.0
    if "high court" in c:
        return 0.6
    return 0.4


class PrecedentIndex:
    def __init__(
        self,
        tagged_dir: Optional[Path] = None,
        matcher: Any = None,
        cache_path: Optional[Path] = None,
        embedder: Any = None,
        precedent_dir: Optional[Path] = None,
    ):
        chosen_dir = precedent_dir or tagged_dir
        if chosen_dir is None:
            bail_data_dir = Path(__file__).parent.parent / "bail_data"
            if (bail_data_dir / "out").exists():
                chosen_dir = bail_data_dir / "out"
            elif (bail_data_dir / ".out").exists():
                chosen_dir = bail_data_dir / ".out"
            elif (bail_data_dir / "tagged").exists():
                chosen_dir = bail_data_dir / "tagged"
            else:
                chosen_dir = bail_data_dir / "out"
        self.precedent_dir = Path(chosen_dir)
        self.tagged_dir = self.precedent_dir
        self.matcher = matcher
        self.cache_path = Path(cache_path) if cache_path else self.precedent_dir.parent / ".precedent_index.pkl"
        self.embedder = embedder
        self.records: List[Record] = []
        self._stamps: Dict[str, Tuple[float, int]] = {}
        self._base: Dict[str, Record] = {}
        self.key_postings: Dict[str, List[int]] = {}
        self.fact_idf: Dict[str, float] = {}
        self.issue_idf: Dict[str, float] = {}
        self.fact_post: Dict[str, List[Tuple[int, float]]] = {}
        self.issue_post: Dict[str, List[Tuple[int, float]]] = {}
        self.fact_scale = 0.3     # cosine regarded as a "very close" fact match; calibrated from the corpus
        self.issue_scale = 0.3
        self.max_indegree = 1.0
        self.refresh()

    # -- canonicalisation --------------------------------------------------

    def canonical_keys(self, act: str, section: str) -> Tuple[Optional[str], Optional[str]]:
        """(main key, parent key) in old-regime terms, e.g. BNS 318(4) -> ('IPC:420', None); CrPC 439(2) -> ('CRPC:439(2)', 'CRPC:439')."""
        m = self.matcher
        eqs = m.get_equivalent_sections(act, section)
        pick = None
        for a, s in eqs:
            if a in ("IPC", "CRPC", "IEA"):
                pick = (a, s)
                break
        if pick is None:
            pick = eqs[0]
        main = f"{pick[0]}:{pick[1]}"
        parent = m.get_parent_section(pick[1])
        return main, (f"{pick[0]}:{parent}" if parent else None)

    # -- ingestion ---------------------------------------------------------

    def _parse_file(self, path: Path) -> Optional[Record]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[PrecedentIndex] skip {path.name}: {e}")
            return None
        if not isinstance(data, dict) or not isinstance(data.get("case"), dict):
            return None                      # not a tagged judgment (stray json in the folder)
        case = data.get("case") or {}
        meta = data.get("doc_meta") or {}
        r = Record(path=str(path), case_id=str(data.get("case_id") or path.stem), name=str(case.get("case_name") or ""),
                   court_weight=_court_weight(str(case.get("court") or "")), decided_on=str(meta.get("decided_on") or ""),
                   tag_stage=str(case.get("procedural_stage") or ""), stage=infer_case_stage(case))
        refs: List[Tuple[str, str, float]] = []
        for st in case.get("statutes", []) or []:
            act, sec = str(st.get("act") or ""), str(st.get("section") or "")
            if not act or not sec:
                continue
            main, parent = self.canonical_keys(act, sec)
            r.keys.add(main)
            if parent:
                r.keys.add(parent)
            act_c = main.split(":", 1)[0]
            if act_c not in ("CRPC", "BNSS", "IEA", "BSA"):
                r.substantive_keys.add(main)
                if parent:
                    r.substantive_keys.add(parent)
            refs.append((act_c, main.split(":", 1)[1], 1.0))
        r.categories = category_vector(refs)
        props = case.get("propositions", []) or []
        r.n_holdings = len([p for p in props if p.get("is_holding") or p.get("kind") == "ratio"])
        r.direction = direction_shares(props)
        r.fact_tf = dict(Counter(tokenize(str(case.get("abstract_facts") or ""))))
        issue_text = " ".join(
            [str(i.get("question") or "") + " " + str(i.get("short_answer") or "") for i in case.get("issues", []) or []]
            + [str(p.get("text") or "") for p in props if p.get("is_holding") or p.get("kind") == "ratio"]
        )
        r.issue_tf = dict(Counter(tokenize(issue_text)))
        for a in case.get("authorities", []) or []:
            if a.get("name"):
                r.authority_names.append((str(a["name"]), str(a.get("treatment") or "").lower()))
        return r

    def refresh(self) -> None:
        """Parse new/changed files only, drop deleted ones, rebuild derived structures."""
        if self.cache_path.exists() and not self._base:
            try:
                saved = pickle.loads(self.cache_path.read_bytes())
                self._stamps, self._base = saved["stamps"], saved["base"]
            except Exception as e:
                print(f"[PrecedentIndex] cache unreadable ({e}); rebuilding")
        files = {
            str(p): p for p in sorted(self.precedent_dir.glob("*.json"))
            if not p.name.startswith(".") and not p.name.startswith("_temp")
        }
        changed = 0
        for key, p in files.items():
            st = p.stat()
            stamp = (st.st_mtime, st.st_size)
            if self._stamps.get(key) != stamp or key not in self._base:
                rec = self._parse_file(p)
                if rec is not None:
                    self._base[key] = rec
                    self._stamps[key] = stamp
                    changed += 1
        for key in list(self._base):
            if key not in files:
                self._base.pop(key, None)
                self._stamps.pop(key, None)
                changed += 1
        if changed or not self.records:
            self._build_derived(list(self._base.values()))
            try:
                self.cache_path.write_bytes(pickle.dumps({"stamps": self._stamps, "base": self._base}))
            except Exception as e:  # read-only deployments still work
                print(f"[PrecedentIndex] could not write cache: {e}")
        print(f"[PrecedentIndex] {len(self.records)} judgments indexed ({changed} parsed/changed this run)")

    # -- derived structures -------------------------------------------------

    @staticmethod
    def _build_space(tfs: List[Dict[str, int]]) -> Tuple[Dict[str, float], Dict[str, List[Tuple[int, float]]]]:
        n = len(tfs)
        df: Counter = Counter()
        for tf in tfs:
            df.update(tf.keys())
        idf = {t: math.log((1 + n) / (1 + d)) + 1.0 for t, d in df.items()}
        post: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
        for i, tf in enumerate(tfs):
            w = {t: (1.0 + math.log(c)) * idf[t] for t, c in tf.items()}
            norm = math.sqrt(sum(x * x for x in w.values())) or 1.0
            for t, x in w.items():
                post[t].append((i, x / norm))
        return idf, dict(post)

    def _build_derived(self, recs: List[Record]) -> None:
        self.records = recs
        for i, r in enumerate(recs):
            r.idx = i
        self.key_postings = defaultdict(list)
        for r in recs:
            for k in r.keys:
                self.key_postings[k].append(r.idx)
        self.fact_idf, self.fact_post = self._build_space([r.fact_tf for r in recs])
        self.issue_idf, self.issue_post = self._build_space([r.issue_tf for r in recs])
        self._build_citation_graph()
        self.calibrate()

    def _build_citation_graph(self) -> None:
        by_key: Dict[str, int] = {}
        by_first: Dict[str, List[Tuple[Set[str], int]]] = defaultdict(list)
        for r in self.records:
            k = _norm_name(r.name)
            if k:
                by_key[k] = r.idx
                toks = set(k.split())
                for t in toks:
                    by_first[t].append((toks, r.idx))
            r.indegree = 0.0
            r.cites = []
        pos_treat = ("follow", "relied", "approved", "affirm", "applied")
        neg_treat = ("overrul", "distinguish", "doubt")
        for r in self.records:
            seen: Set[int] = set()
            for name, treat in r.authority_names:
                k = _norm_name(name)
                tgt = by_key.get(k)
                if tgt is None and k:
                    toks = set(k.split())
                    best, best_j = None, 0.0
                    for t in list(toks)[:2]:
                        for otoks, oidx in by_first.get(t, []):
                            j = len(toks & otoks) / len(toks | otoks)
                            if j > best_j:
                                best, best_j = oidx, j
                    tgt = best if best_j >= 0.8 else None
                if tgt is None or tgt == r.idx or tgt in seen:
                    continue
                seen.add(tgt)
                r.cites.append(tgt)
                w = 1.0 if any(p in treat for p in pos_treat) else (0.3 if any(n in treat for n in neg_treat) else 0.7)
                self.records[tgt].indegree += w
        self.max_indegree = max([r.indegree for r in self.records] + [1.0])

    def authority(self, idx: int) -> float:
        r = self.records[idx]
        return round(r.court_weight * math.log1p(r.indegree) / math.log1p(self.max_indegree), 4)

    # -- similarity ---------------------------------------------------------

    def _query_vec(self, text: str, idf: Dict[str, float]) -> Dict[str, float]:
        tf = Counter(t for t in tokenize(text) if t in idf)
        w = {t: (1.0 + math.log(c)) * idf[t] for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in w.values())) or 1.0
        return {t: x / norm for t, x in w.items()}

    def similarity(self, text: str, space: str = "fact") -> Dict[int, float]:
        """Cosine similarity of `text` to every judgment that shares at least one term (sparse)."""
        idf, post = (self.fact_idf, self.fact_post) if space == "fact" else (self.issue_idf, self.issue_post)
        qv = self._query_vec(text, idf)
        acc: Dict[int, float] = defaultdict(float)
        for t, qw in qv.items():
            for i, dw in post.get(t, ()):
                acc[i] += qw * dw
        return dict(acc)

    def calibrate(self, sample: int = 100) -> None:
        """Scale = median best-neighbour cosine of corpus judgments against each other (leave-one-out)."""
        n = len(self.records)
        if n < 5:
            return
        step = max(1, n // sample)
        max_df = max(50, n // 10)
        for space, attr in (("fact", "fact_scale"), ("issue", "issue_scale")):
            idf, post = (self.fact_idf, self.fact_post) if space == "fact" else (self.issue_idf, self.issue_post)
            bests: List[float] = []
            for r in self.records[::step]:
                tf = r.fact_tf if space == "fact" else r.issue_tf
                w = {t: (1.0 + math.log(c)) * idf[t] for t, c in tf.items() if t in idf}
                norm = math.sqrt(sum(x * x for x in w.values())) or 1.0
                acc: Dict[int, float] = defaultdict(float)
                for t, x in w.items():
                    plist = post.get(t, ())
                    if len(plist) > max_df:       # near-stopwords: negligible idf, expensive to scan
                        continue
                    for i, dw in plist:
                        if i != r.idx:
                            acc[i] += (x / norm) * dw
                if acc:
                    bests.append(max(acc.values()))
            if bests:
                bests.sort()
                setattr(self, attr, max(0.05, bests[len(bests) // 2]))

    # -- lookup --------------------------------------------------------------

    def candidates_by_keys(self, keys: Iterable[str]) -> Set[int]:
        out: Set[int] = set()
        for k in keys:
            out.update(self.key_postings.get(k, ()))
        return out

    def load_full(self, rec: Record) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(Path(rec.path).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[PrecedentIndex] cannot load {rec.path}: {e}")
            return None