"""
data_validator.py
Loads and validates all 26,000 JSON files.
Handles the exact schema from your sample JSON (2025_INSC_1061.json).
"""
import json
import re
from pathlib import Path
from typing import Dict, List
from tqdm import tqdm
from loguru import logger


class DataValidator:
    """
    Required fields based on your actual JSON schema.
    Fields marked optional are used when present.
    """
    REQUIRED_FIELDS = ["case_id", "full_text", "ipc_sections_referred"]
    USEFUL_FIELDS   = [
        "headnotes", "issue_for_consideration", "judgment_text",
        "list_of_keywords", "list_of_acts", "bns_sections_referred",
        "acts_referred", "decision_date", "citation",
        "case_arising_from", "appearances"
    ]

    # IPC sections that appear in your training data
    VALID_IPC_SECTIONS = {
        "34","109","120B","302","304","304A","304B","306","307",
        "323","324","325","326","354","354A","354B","354C","354D",
        "363","363A","364","364A","366","366A","370","370A",
        "375","376","376A","376AB","376B","376C","376D","376DA","376DB","376E",
        "377","379","380","382","384","385","386","390","391","392",
        "393","394","395","396","397","406","409","411","420",
        "447","448","452","453","454","457","458","459","460",
        "465","467","468","469","471","499","500","501","506",
        "307","308","326A","326B",
    }

    def __init__(self, raw_data_path: str):
        self.raw_data_path = Path(raw_data_path)
        self.stats = {
            "total": 0, "valid": 0, "invalid": 0,
            "duplicates": 0, "no_sections": 0, "has_error": 0
        }

    def validate_and_load(self) -> List[Dict]:
        json_files = list(self.raw_data_path.glob("*.json"))
        logger.info(f"Found {len(json_files)} JSON files in {self.raw_data_path}")

        seen_ids  = set()
        valid     = []

        for fp in tqdm(json_files, desc="Validating"):
            self.stats["total"] += 1
            try:
                with open(fp, encoding="utf-8") as f:
                    case = json.load(f)

                # Skip cases flagged as errors by extractor
                if case.get("has_error"):
                    self.stats["has_error"] += 1
                    continue

                # Required fields
                if not self._has_required(case):
                    self.stats["invalid"] += 1
                    continue

                # Deduplicate
                cid = case["case_id"]
                if cid in seen_ids:
                    self.stats["duplicates"] += 1
                    continue
                seen_ids.add(cid)

                # Clean and enrich
                case = self._clean(case)

                if not case.get("ipc_sections_referred"):
                    self.stats["no_sections"] += 1
                    case["_has_sections"] = False
                else:
                    case["_has_sections"] = True

                valid.append(case)
                self.stats["valid"] += 1

            except Exception as e:
                logger.warning(f"Error reading {fp.name}: {e}")
                self.stats["invalid"] += 1

        logger.info(f"Stats: {self.stats}")
        return valid

    # ── helpers ───────────────────────────────────────────────────────────────

    def _has_required(self, case: Dict) -> bool:
        for f in self.REQUIRED_FIELDS:
            if not case.get(f):
                return False
        return True

    def _clean(self, case: Dict) -> Dict:
        # Normalise text fields
        for field in ["full_text", "judgment_text", "headnotes",
                       "issue_for_consideration"]:
            if case.get(field):
                case[field] = self._clean_text(case[field])

        # Standardise IPC sections
        case["ipc_sections_referred"] = self._std_sections(
            case.get("ipc_sections_referred", [])
        )
        case["bns_sections_referred"] = self._std_sections(
            case.get("bns_sections_referred", [])
        )

        # Ensure list fields are lists
        for f in ["list_of_keywords", "list_of_acts", "acts_referred", "judges"]:
            v = case.get(f, [])
            if isinstance(v, str):
                case[f] = [s.strip() for s in v.split(",") if s.strip()]
            elif not isinstance(v, list):
                case[f] = []

        return case

    def _clean_text(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\x08', '', text)   # backspace chars from SCC PDFs
        text = re.sub(r'\t', ' ', text)
        return text.strip()

    def _std_sections(self, sections) -> List[str]:
        """Return clean list like ['376', '376(2)', '34']"""
        if isinstance(sections, str):
            sections = [s.strip() for s in re.split(r'[,;]', sections)]
        if not isinstance(sections, list):
            return []

        out = []
        for s in sections:
            s = str(s).strip()
            s = re.sub(r'(?i)\bsection\s*', '', s).strip()
            s = re.sub(r'(?i)\bipc\b', '', s).strip()
            s = re.sub(r'[^\w\(\)/]', '', s)
            if s and re.search(r'\d', s):   # must contain a digit
                out.append(s)
        return out
