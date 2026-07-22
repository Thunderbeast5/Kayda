"""
dataset_builder.py
Converts validated cases into instruction-tuning format for LLM fine-tuning.
Output format: Alpaca-style  {instruction, input, output}
"""
import json
import random
import re
from pathlib import Path
from typing import Dict, List, Tuple
from collections import Counter
from sklearn.model_selection import train_test_split
from tqdm import tqdm
from loguru import logger


# ── IPC → BNS mapping (based on official BNS 2023) ───────────────────────────
IPC_TO_BNS = {
    "34": "3(5)", "109": "48", "120B": "61(2)",
    "302": "101", "303": "102", "304": "105", "304A": "106",
    "304B": "80", "305": "108", "306": "108",
    "307": "109", "308": "110", "309": "226",
    "319": "114", "320": "115", "321": "114", "322": "115",
    "323": "115(2)", "324": "117(2)", "325": "116(2)",
    "326": "117(3)", "326A": "124", "326B": "125",
    "354": "74", "354A": "75", "354B": "76",
    "354C": "77", "354D": "78",
    "363": "137(2)", "363A": "138", "364": "139",
    "364A": "140", "365": "141", "366": "142",
    "366A": "143", "366B": "144", "367": "145",
    "370": "143", "370A": "144",
    "375": "63", "376": "64", "376A": "66",
    "376AB": "65", "376B": "67", "376C": "68",
    "376D": "70", "376DA": "70(2)", "376DB": "70(3)",
    "376E": "71",
    "377": "None (decriminalised under BNS)",
    "378": "303", "379": "303(2)", "380": "305",
    "382": "307", "383": "308", "384": "308(2)",
    "385": "309", "386": "310", "390": "309",
    "391": "310", "392": "309(1)", "393": "309(4)",
    "394": "309(3)", "395": "310(2)", "396": "311",
    "397": "312", "406": "316(2)", "409": "316(3)",
    "411": "317", "420": "318(4)",
    "465": "334", "467": "336", "468": "337",
    "469": "338", "471": "340",
    "499": "356", "500": "356(2)", "506": "351",
}

# Instruction templates — varied to improve generalisation
INSTRUCTION_TEMPLATES = [
    (
        "You are a legal expert in Indian criminal law. Given the following case facts "
        "from the Supreme Court of India, identify all applicable IPC sections and provide "
        "their BNS equivalents."
    ),
    (
        "Analyze the following Indian Supreme Court case and predict the IPC sections "
        "that were applied. Also provide the corresponding BNS (Bharatiya Nyaya Sanhita "
        "2023) section numbers."
    ),
    (
        "You are an AI assistant trained on Indian case law. Based on the legal facts "
        "provided below, determine which sections of the Indian Penal Code (IPC) are "
        "applicable and map them to their BNS counterparts."
    ),
    (
        "As an expert in Indian criminal jurisprudence, examine the following case "
        "summary and identify the relevant IPC sections charged, along with their "
        "Bharatiya Nyaya Sanhita equivalents."
    ),
]


class DatasetBuilder:
    def __init__(self, cases: List[Dict]):
        self.cases = cases
        logger.info(f"DatasetBuilder initialized with {len(cases)} cases")

    # ── Public API ────────────────────────────────────────────────────────────

    def build(self) -> List[Dict]:
        """Build the full instruction dataset."""
        records = []
        skipped = 0

        for case in tqdm(self.cases, desc="Building dataset"):
            try:
                record = self._build_record(case)
                if record:
                    records.append(record)
            except Exception as e:
                logger.debug(f"Skip {case.get('case_id')}: {e}")
                skipped += 1

        logger.info(f"Built {len(records)} records, skipped {skipped}")
        return records

    def split(self, records: List[Dict],
              val_ratio: float = 0.08,
              test_ratio: float = 0.07
              ) -> Tuple[List, List, List]:
        """
        Stratified split by IPC section frequency.
        Cases with valid sections → primary train set.
        Cases without sections → augment train only (never val/test).
        """
        with_sec  = [r for r in records if r["_meta"]["has_sections"]]
        without_s = [r for r in records if not r["_meta"]["has_sections"]]

        if len(with_sec) < 50:
            logger.warning("Very few cases with IPC sections — using all data for train")
            return records, [], []

        train, tmp  = train_test_split(with_sec,
                                       test_size=val_ratio + test_ratio,
                                       random_state=42)
        val, test   = train_test_split(tmp,
                                       test_size=test_ratio / (val_ratio + test_ratio),
                                       random_state=42)

        # Add no-section cases only to training
        train += without_s
        random.shuffle(train)

        logger.info(f"Split → train:{len(train)} val:{len(val)} test:{len(test)}")
        return train, val, test

    def save(self, records: List[Dict], output_dir: str):
        """Save in JSONL (for training) and CSV (for inspection)."""
        import pandas as pd
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # JSONL — exactly what SFTTrainer / HuggingFace Trainer expects
        with open(out / "dataset.jsonl", "w", encoding="utf-8") as f:
            for r in records:
                line = {
                    "instruction": r["instruction"],
                    "input":       r["input"],
                    "output":      r["output"],
                }
                f.write(json.dumps(line, ensure_ascii=False) + "\n")

        # CSV for human inspection
        rows = []
        for r in records:
            rows.append({
                "case_id":      r["_meta"]["case_id"],
                "citation":     r["_meta"]["citation"],
                "ipc_sections": ", ".join(r["_meta"]["ipc_sections"]),
                "bns_sections": ", ".join(r["_meta"]["bns_sections"]),
                "input_len":    len(r["input"]),
            })
        pd.DataFrame(rows).to_csv(out / "dataset_summary.csv", index=False)

        logger.info(f"Saved {len(records)} records to {output_dir}")

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_record(self, case: Dict) -> Dict | None:
        ipc_sections = case.get("ipc_sections_referred", [])
        bns_sections = self._map_to_bns(ipc_sections)

        # Build input text
        input_text = self._build_input(case)
        if not input_text or len(input_text) < 50:
            return None

        # Build structured output
        output_text = self._build_output(ipc_sections, bns_sections, case)

        # Pick a random instruction template for variety
        instruction = random.choice(INSTRUCTION_TEMPLATES)

        return {
            "instruction": instruction,
            "input":       input_text,
            "output":      output_text,
            "_meta": {
                "case_id":      case.get("case_id", ""),
                "citation":     case.get("citation", ""),
                "ipc_sections": ipc_sections,
                "bns_sections": bns_sections,
                "has_sections": case.get("_has_sections", False),
            }
        }

    def _build_input(self, case: Dict) -> str:
        """Build a comprehensive but focused input from available fields."""
        parts = []

        # 1. Issue — most important signal
        issue = case.get("issue_for_consideration", "").strip()
        if issue:
            parts.append(f"Issue: {issue[:600]}")

        # 2. Headnotes — contains IPC section references and held clauses
        headnotes = case.get("headnotes", "").strip()
        if headnotes:
            # Remove the section references from headnotes to avoid data leakage
            hn_clean = re.sub(
                r'\b(?:s\.|ss\.|Section|Sections)\s*[\d\(\)A-Za-z,\s]+',
                '', headnotes, flags=re.IGNORECASE
            )
            parts.append(f"Case Summary: {hn_clean[:800]}")

        # 3. Judgment text — first 600 chars (facts section)
        jt = case.get("judgment_text", "").strip()
        if jt:
            parts.append(f"Judgment Excerpt: {jt[:600]}")

        # 4. Keywords
        kw = case.get("list_of_keywords", [])
        if kw:
            parts.append(f"Keywords: {', '.join(kw[:12])}")

        # 5. Acts referred
        acts = case.get("acts_referred", []) or case.get("list_of_acts", [])
        if acts:
            parts.append(f"Acts: {', '.join(str(a) for a in acts[:8])}")

        return "\n".join(parts)

    def _build_output(self, ipc: List[str], bns: List[str],
                      case: Dict) -> str:
        """Build structured output string."""
        lines = []

        # IPC sections
        if ipc:
            lines.append(f"IPC Sections: {', '.join(ipc)}")
        else:
            lines.append("IPC Sections: None identified")

        # BNS equivalents
        if bns:
            lines.append(f"BNS Equivalents: {', '.join(bns)}")
        else:
            lines.append("BNS Equivalents: None")

        # Section-wise reasoning
        reasoning = self._generate_reasoning(ipc, case)
        if reasoning:
            lines.append(f"Reasoning: {reasoning}")

        return "\n".join(lines)

    def _map_to_bns(self, ipc_sections: List[str]) -> List[str]:
        bns = []
        for s in ipc_sections:
            clean = re.sub(r'[^\w\(\)]', '', s)
            mapped = IPC_TO_BNS.get(clean)
            if mapped and mapped != "None (decriminalised under BNS)":
                bns.append(f"BNS {mapped}")
            elif mapped:
                bns.append(mapped)
            # else: no BNS equivalent known — skip
        return bns

    def _generate_reasoning(self, sections: List[str], case: Dict) -> str:
        """Rule-based reasoning — no LLM needed, derived from section semantics."""
        category_map = {
            frozenset(["376", "376A", "376AB", "376B", "376C",
                       "376D", "376DA", "376DB", "376E"]):
                "sexual assault/rape",
            frozenset(["302", "303", "304", "304A", "304B"]):
                "homicide/culpable homicide",
            frozenset(["354", "354A", "354B", "354C", "354D"]):
                "assault/outraging modesty of women",
            frozenset(["363", "364", "364A", "365", "366", "366A", "367",
                       "368", "369", "370", "370A"]):
                "kidnapping/abduction/trafficking",
            frozenset(["392", "393", "394", "395", "396", "397"]):
                "robbery/dacoity",
            frozenset(["406", "408", "409"]):
                "criminal breach of trust",
            frozenset(["420", "415", "416", "417", "418", "419"]):
                "cheating/fraud",
            frozenset(["499", "500", "501", "502"]):
                "defamation",
            frozenset(["34", "120A", "120B"]):
                "common intention/criminal conspiracy",
        }

        categories = set()
        for cat_set, cat_name in category_map.items():
            if any(s in cat_set for s in sections):
                categories.add(cat_name)

        if not categories:
            return ""

        cat_str = " and ".join(sorted(categories))
        reasoning = f"The facts establish {cat_str}."

        # Add POCSO note for sections involving minors
        keywords = " ".join(case.get("list_of_keywords", [])).lower()
        acts = " ".join(str(a) for a in
                        case.get("acts_referred", []) +
                        case.get("list_of_acts", [])).lower()
        if "pocso" in acts or "minor" in keywords or "child" in keywords:
            reasoning += (
                " POCSO Act provisions additionally apply as the "
                "victim appears to be a minor."
            )

        return reasoning
