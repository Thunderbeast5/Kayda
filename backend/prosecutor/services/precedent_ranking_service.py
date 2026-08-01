"""
precedent_ranking_service.py

Multi-factor precedent scoring across IPC, BNS, CrPC, BNSS, IEA, BSA, POCSO, and DPA acts.
"""

from typing import Dict, Any, List, Optional
import re


class PrecedentRankingService:
    """
    Ranks retrieved precedent cases using multi-factor scoring to prioritize
    the most relevant cases for legal arguments.
    """

    WEIGHT_SEMANTIC_SIMILARITY = 0.40
    WEIGHT_OFFENCE_MATCH = 0.20
    WEIGHT_PROCEDURAL_STAGE = 0.20
    WEIGHT_BAIL_TYPE = 0.10
    WEIGHT_COURT_HIERARCHY = 0.10

    COURT_SCORES = {
        "supreme court": 1.0,
        "supreme": 1.0,
        "sc": 1.0,
        "high court": 0.7,
        "hc": 0.7,
        "district court": 0.4,
        "sessions court": 0.3,
        "magistrate": 0.2,
    }

    PROCEDURAL_STAGES = {
        "anticipatory_bail": [
            "anticipatory bail", "pre-arrest bail", "section 438", "section 482",
            "anticipatory", "pre arrest"
        ],
        "regular_bail": [
            "regular bail", "section 437", "section 439", "bail application"
        ],
        "appeal": [
            "appeal", "appellate", "criminal appeal", "special leave petition", "slp"
        ],
        "revision": [
            "revision", "criminal revision", "revisional"
        ],
        "quashing": [
            "quashing", "section 482", "quash", "482 crpc", "482 bnss"
        ],
        "trial": [
            "trial", "framing of charges", "charge", "acquittal", "conviction"
        ],
        "investigation": [
            "investigation", "fir", "complaint", "chargesheet"
        ]
    }

    BAIL_TYPES = {
        "anticipatory": ["anticipatory", "pre-arrest", "pre arrest"],
        "regular": ["regular bail", "bail application"],
        "interim": ["interim bail", "interim"],
        "default": ["default bail", "statutory bail"],
        "cancellation": ["cancellation of bail", "bail cancellation"]
    }

    def __init__(self):
        pass

    def rank_cases(
        self,
        cases: List[Dict[str, Any]],
        query: str,
        offence_sections: List[str],
        debug: bool = False
    ) -> List[Dict[str, Any]]:
        """Rank cases using multi-factor scoring."""
        if not cases:
            return []

        query_lower = query.lower()
        query_procedural_stage = self._detect_procedural_stage(query_lower)
        query_bail_type = self._detect_bail_type(query_lower)

        ranked_cases = []

        for case in cases:
            scores = self._compute_case_scores(
                case=case,
                query_lower=query_lower,
                offence_sections=offence_sections,
                query_procedural_stage=query_procedural_stage,
                query_bail_type=query_bail_type
            )

            final_score = (
                scores["semantic_similarity"] * self.WEIGHT_SEMANTIC_SIMILARITY +
                scores["offence_match"] * self.WEIGHT_OFFENCE_MATCH +
                scores["procedural_stage"] * self.WEIGHT_PROCEDURAL_STAGE +
                scores["bail_type"] * self.WEIGHT_BAIL_TYPE +
                scores["court_hierarchy"] * self.WEIGHT_COURT_HIERARCHY
            )

            ranked_case = {**case}
            ranked_case["ranking_score"] = round(final_score, 4)
            ranked_case["ranking_breakdown"] = scores if debug else None

            ranked_cases.append(ranked_case)

        ranked_cases.sort(key=lambda c: c["ranking_score"], reverse=True)

        if debug:
            self._print_ranking_summary(ranked_cases, query_procedural_stage, query_bail_type)

        return ranked_cases

    def _compute_case_scores(
        self,
        case: Dict[str, Any],
        query_lower: str,
        offence_sections: List[str],
        query_procedural_stage: Optional[str],
        query_bail_type: Optional[str]
    ) -> Dict[str, float]:
        semantic_similarity = float(case.get("similarity") or case.get("case_similarity") or case.get("vector_similarity") or 0.0)
        offence_match = self._score_offence_match(case, offence_sections)
        procedural_stage = self._score_procedural_stage(case, query_procedural_stage)
        bail_type = self._score_bail_type(case, query_bail_type)
        court_hierarchy = self._score_court_hierarchy(case)

        return {
            "semantic_similarity": semantic_similarity,
            "offence_match": offence_match,
            "procedural_stage": procedural_stage,
            "bail_type": bail_type,
            "court_hierarchy": court_hierarchy
        }

    def _score_offence_match(self, case: Dict[str, Any], offence_sections: List[str]) -> float:
        if not offence_sections:
            return 0.5

        case_sections = self._extract_case_sections(case)
        if not case_sections:
            return 0.3

        normalized_query_sections = [self._normalize_section(s) for s in offence_sections]
        normalized_case_sections = [self._normalize_section(s) for s in case_sections]

        exact_matches = sum(
            1 for qs in normalized_query_sections
            if any(qs == cs for cs in normalized_case_sections)
        )

        partial_matches = 0
        for qs in normalized_query_sections:
            qs_num = re.findall(r'\d+[A-Za-z]*', qs)
            if qs_num:
                for cs in normalized_case_sections:
                    cs_num = re.findall(r'\d+[A-Za-z]*', cs)
                    if qs_num == cs_num and qs != cs:
                        partial_matches += 1
                        break

        if exact_matches > 0:
            return 1.0
        elif partial_matches > 0:
            return 0.6
        else:
            return 0.2

    def _score_procedural_stage(self, case: Dict[str, Any], query_stage: Optional[str]) -> float:
        if not query_stage:
            return 0.5

        case_stage = self._detect_case_procedural_stage(case)
        if not case_stage:
            return 0.5

        if case_stage == query_stage:
            return 1.0
        else:
            related_stages = {
                "anticipatory_bail": ["quashing", "regular_bail"],
                "regular_bail": ["anticipatory_bail", "appeal"],
                "appeal": ["trial", "regular_bail"],
                "quashing": ["anticipatory_bail", "investigation"]
            }
            if case_stage in related_stages.get(query_stage, []):
                return 0.6
            else:
                return 0.2

    def _score_bail_type(self, case: Dict[str, Any], query_bail_type: Optional[str]) -> float:
        if not query_bail_type:
            return 0.5

        case_bail_type = self._detect_case_bail_type(case)
        if not case_bail_type:
            return 0.5

        return 1.0 if case_bail_type == query_bail_type else 0.2

    def _score_court_hierarchy(self, case: Dict[str, Any]) -> float:
        court = str(case.get("court", "")).lower()
        for court_keyword, score in self.COURT_SCORES.items():
            if court_keyword in court:
                return score
        return 0.3

    def _detect_procedural_stage(self, text: str) -> Optional[str]:
        for stage, keywords in self.PROCEDURAL_STAGES.items():
            if any(kw in text for kw in keywords):
                return stage
        return None

    def _detect_bail_type(self, text: str) -> Optional[str]:
        for bail_type, keywords in self.BAIL_TYPES.items():
            if any(kw in text for kw in keywords):
                return bail_type
        return None

    def _detect_case_procedural_stage(self, case: Dict[str, Any]) -> Optional[str]:
        case_text = " ".join([
            str(case.get("case_name", "")),
            str(case.get("facts", "")),
            str(case.get("summary", "")),
            str(case.get("reasoning", ""))
        ]).lower()
        return self._detect_procedural_stage(case_text)

    def _detect_case_bail_type(self, case: Dict[str, Any]) -> Optional[str]:
        case_text = " ".join([
            str(case.get("case_name", "")),
            str(case.get("facts", "")),
            str(case.get("summary", ""))
        ]).lower()
        return self._detect_bail_type(case_text)

    def _extract_case_sections(self, case: Dict[str, Any]) -> List[str]:
        """Extract section references from case metadata supporting all criminal & special acts."""
        sections = []

        if "interprets" in case and case["interprets"]:
            if isinstance(case["interprets"], list):
                sections.extend(case["interprets"])
            else:
                sections.append(str(case["interprets"]))

        if "applies_section" in case:
            sections.append(str(case["applies_section"]))

        case_text = " ".join([
            str(case.get("case_name", "")),
            str(case.get("facts", "")),
            str(case.get("summary", ""))
        ])

        # Updated regex patterns covering IPC, BNS, CrPC, BNSS, IEA, BSA, POCSO, DPA, and DOWRY
        ACT_PATTERN = r'(IPC|BNS|BNSS|CRPC|BSA|IEA|POCSO|DPA|DOWRY)'
        patterns = [
            rf'Section\s+(\d+[A-Za-z]*)\s+{ACT_PATTERN}',
            rf'{ACT_PATTERN}\s+(\d+[A-Za-z]*)',
            rf'(\d+[A-Za-z]*)\s+{ACT_PATTERN}',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, case_text, re.IGNORECASE)
            for match in matches:
                if len(match) == 2:
                    if match[0].isdigit() or match[0][0].isdigit():
                        sections.append(f"{match[1].upper()} {match[0]}")
                    else:
                        sections.append(f"{match[0].upper()} {match[1]}")

        return list(set(sections))

    def _normalize_section(self, section: str) -> str:
        return re.sub(r'\s+', '', section.upper())

    def _print_ranking_summary(
        self,
        ranked_cases: List[Dict[str, Any]],
        query_stage: Optional[str],
        query_bail_type: Optional[str]
    ):
        print("\n" + "=" * 100)
        print("PRECEDENT RANKING SUMMARY")
        print("=" * 100)
        print(f"Query Procedural Stage: {query_stage or 'Unknown'}")
        print(f"Query Bail Type: {query_bail_type or 'Unknown'}")
        print(f"Total Cases Ranked: {len(ranked_cases)}")
        print("\nTop 10 Ranked Cases:")
        print("-" * 100)

        for i, case in enumerate(ranked_cases[:10], 1):
            print(f"\n#{i}. {case.get('case_name', 'Unknown Case')} | {case.get('citation', 'N/A')}")
            print(f"    Court: {case.get('court', 'Unknown')}")
            print(f"    Final Score: {case['ranking_score']:.4f}")
            
            if case.get("ranking_breakdown"):
                breakdown = case["ranking_breakdown"]
                print(f"    Breakdown:")
                print(f"      - Semantic Similarity : {breakdown['semantic_similarity']:.3f} (weight: {self.WEIGHT_SEMANTIC_SIMILARITY})")
                print(f"      - Offence Match      : {breakdown['offence_match']:.3f} (weight: {self.WEIGHT_OFFENCE_MATCH})")
                print(f"      - Procedural Stage   : {breakdown['procedural_stage']:.3f} (weight: {self.WEIGHT_PROCEDURAL_STAGE})")
                print(f"      - Bail Type          : {breakdown['bail_type']:.3f} (weight: {self.WEIGHT_BAIL_TYPE})")
                print(f"      - Court Hierarchy    : {breakdown['court_hierarchy']:.3f} (weight: {self.WEIGHT_COURT_HIERARCHY})")

        print("\n" + "=" * 100 + "\n")

    def filter_by_quality(
        self,
        ranked_cases: List[Dict[str, Any]],
        min_score: float = 0.5,
        max_cases: int = 10
    ) -> List[Dict[str, Any]]:
        filtered = [
            case for case in ranked_cases
            if case.get("ranking_score", 0.0) >= min_score
        ]
        return filtered[:max_cases]

    def prioritize_supreme_court(
        self,
        ranked_cases: List[Dict[str, Any]],
        sc_boost: float = 0.1
    ) -> List[Dict[str, Any]]:
        for case in ranked_cases:
            court = str(case.get("court", "")).lower()
            if any(kw in court for kw in ["supreme", "sc", "supreme court"]):
                case["ranking_score"] = min(1.0, case["ranking_score"] + sc_boost)
                if case.get("ranking_breakdown"):
                    case["ranking_breakdown"]["supreme_court_boost"] = sc_boost

        ranked_cases.sort(key=lambda c: c.get("ranking_score", 0.0), reverse=True)
        return ranked_cases