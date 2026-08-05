"""
Closed-Set Section Matcher & Leak Auditor for LexiGraph Stage 1.
Replaces brittle regex with accurate matching against the closed set of valid IPC/BNS section identifiers.
Prevents false-positives on FIR numbers, dates, monetary amounts, and paragraph references.
"""

import csv
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Fallback IPC & BNS closed section set (1 to 511 IPC + 1 to 358 BNS + lettered subsections)
FALLBACK_IPC_BNS_SECTIONS = {
    # Common criminal IPC sections
    "34", "120B", "120-B", "141", "142", "143", "147", "148", "149",
    "191", "192", "193", "201", "294", "295", "295A", "295-A",
    "299", "300", "302", "304", "304B", "304-B", "306", "307", "308",
    "319", "320", "323", "324", "325", "326", "326A", "326B",
    "339", "340", "341", "342", "351", "354", "354A", "354B", "354C", "354D",
    "362", "363", "364", "364A", "365", "366", "375", "376", "376A", "376B", "376C", "376D", "376DA", "376DB", "376E",
    "378", "379", "383", "384", "390", "391", "392", "395",
    "403", "405", "406", "409", "415", "416", "417", "420",
    "441", "442", "447", "448", "463", "464", "465", "468", "471",
    "498A", "498-A", "499", "500", "503", "504", "506", "509", "511"
}


from .statute_repository import StatuteRepository


def load_closed_section_identifiers() -> Set[str]:
    """
    Loads closed set of valid section numbers/identifiers from StatuteRepository
    or defaults to the robust built-in fallback set.
    """
    section_set = set(FALLBACK_IPC_BNS_SECTIONS)
    try:
        repo = StatuteRepository.get_instance()
        for item in repo.get_sections_db():
            sec_num = item.get("section_number")
            if sec_num:
                section_set.add(sec_num.upper().strip())
                section_set.add(sec_num.upper().replace("-", "").strip())
    except Exception:
        pass

    # Also add standard 1 to 511 numbers
    for i in range(1, 512):
        section_set.add(str(i))

    return section_set


class ClosedSetSectionAuditor:
    """
    Section leak auditor matching text against closed set of valid section identifiers.
    Requires presence of statutory markers (Section, Sec., u/s, IPC, BNS, CrPC, BNSS)
    paired with a section number from the closed set to eliminate false positives.
    """

    def __init__(self):
        self.closed_sections = load_closed_section_identifiers()

    def audit_text_for_leaks(self, text: str) -> List[Dict[str, str]]:
        """
        Audits input text string for explicit statutory section leaks.

        Returns list of dicts with keys:
            - matched_text: exact substring matched (e.g. "Section 498A", "u/s 420 IPC")
            - section: matched section number (e.g. "498A")
            - explanation: description of leak
        """
        leaks = []
        if not text:
            return leaks

        # Patterns pairing statutory markers with closed-set section numbers
        # Pattern 1: Statutory marker prefix + section number (e.g. "Section 498A", "Sec. 420", "u/s 304B", "under section 307")
        prefix_pattern = re.compile(
            r"\b(section|sec\.?|u/s|under\s+section|s\.)\s*([0-9]{1,4}[a-z\-]*)\b",
            re.IGNORECASE,
        )

        # Pattern 2: Statute name prefix/suffix + section number (e.g. "IPC 406", "498A IPC", "BNS 85", "304B CrPC")
        statute_pair_pattern = re.compile(
            r"\b((?:ipc|bns|crpc|bnss)\s*([0-9]{1,4}[a-z\-]*)|([0-9]{1,4}[a-z\-]*)\s*(?:ipc|bns|crpc|bnss))\b",
            re.IGNORECASE,
        )

        seen_sections = set()

        # Check prefix matches
        for match in prefix_pattern.finditer(text):
            marker, sec_raw = match.group(1), match.group(2)
            normalized_sec = sec_raw.upper().replace(" ", "").replace("-", "")

            # Verify sec_raw is in closed section set
            if normalized_sec in self.closed_sections or sec_raw.upper() in self.closed_sections:
                if normalized_sec not in seen_sections:
                    seen_sections.add(normalized_sec)
                    leaks.append({
                        "matched_text": match.group(0),
                        "section": normalized_sec,
                        "explanation": f"Explicit statutory section reference '{match.group(0)}' detected."
                    })

        # Check statute pair matches
        for match in statute_pair_pattern.finditer(text):
            sec_raw = match.group(2) or match.group(3)
            if sec_raw:
                normalized_sec = sec_raw.upper().replace(" ", "").replace("-", "")
                if normalized_sec in self.closed_sections or sec_raw.upper() in self.closed_sections:
                    if normalized_sec not in seen_sections:
                        seen_sections.add(normalized_sec)
                        leaks.append({
                            "matched_text": match.group(0),
                            "section": normalized_sec,
                            "explanation": f"Explicit statutory section reference '{match.group(0)}' detected."
                        })

        return leaks
