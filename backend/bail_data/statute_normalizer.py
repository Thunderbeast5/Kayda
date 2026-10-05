"""
Statute Normalizer for Indian Legal Acts
Converts various statute formats to canonical form: Act:Section
Maps IPC/CrPC/CPC to BNS/BNSS/BNS equivalents
"""

import re
from typing import List, Dict, Optional, Tuple

class StatuteNormalizer:
    """Normalizes statute references to canonical format"""
    
    # IPC to BNS mapping (major sections - expand as needed)
    IPC_TO_BNS = {
        "302": "103",  # Murder
        "304": "105",  # Culpable homicide not amounting to murder
        "307": "109",  # Attempt to murder
        "320": "114",  # Grievous hurt
        "323": "115",  # Voluntary causing hurt
        "376": "63",   # Rape
        "377": "377",  # Unnatural offences
        "406": "316",  # Criminal breach of trust
        "420": "318",  # Cheating
        "465": "336",  # Forgery (plain)
        "467": "336",  # Forgery of valuable security
        "468": "336",  # Forgery for purpose of cheating
        "471": "340",  # Using forged document
        "506": "351",  # Criminal intimidation
        "120B": "61",  # Criminal conspiracy
    }
    
    # CrPC to BNSS mapping (major sections)
    CRPC_TO_BNSS = {
        "154": "173",  # FIR
        "156": "176",  # Police investigation
        "161": "183",  # Examination of witnesses by police
        "173": "193",  # Report of investigation
        "207": "230",  # Supply of documents
        "227": "247",  # Discharge
        "228": "248",  # Framing of charge
        "313": "326",  # Examination of accused
        "437": "479",  # Bail in non-bailable offences
        "438": "482",  # Anticipatory bail
        "439": "483",  # Special powers of High Court/Sessions
        "482": "528",  # Inherent powers of High Court
    }
    
    # CPC to BNS mapping (selected sections)
    CPC_TO_BNS = {
        "9": "15",
        "11": "17",
        "151": "392",
    }
    
    # Act name variations to canonical names
    ACT_VARIATIONS = {
        # IPC variations
        "ipc": "IPC-1860",
        "indian penal code": "IPC-1860",
        "penal code": "IPC-1860",
        "i.p.c": "IPC-1860",
        "i.p.c.": "IPC-1860",
        
        # BNS variations
        "bns": "BNS-2023",
        "bharatiya nyaya sanhita": "BNS-2023",
        "bnss": "BNSS-2023",
        "bharatiya nagarik suraksha sanhita": "BNSS-2023",
        
        # CrPC variations
        "crpc": "CrPC-1973",
        "cr.p.c": "CrPC-1973",
        "cr.p.c.": "CrPC-1973",
        "code of criminal procedure": "CrPC-1973",
        "criminal procedure code": "CrPC-1973",
        "crpc 1973": "CrPC-1973",
        
        # CPC variations
        "cpc": "CPC-1908",
        "c.p.c": "CPC-1908",
        "c.p.c.": "CPC-1908",
        "code of civil procedure": "CPC-1908",
        "civil procedure code": "CPC-1908",
        
        # NDPS variations
        "ndps": "NDPS-1985",
        "ndps act": "NDPS-1985",
        "narcotic drugs and psychotropic substances act": "NDPS-1985",
        
        # PMLA variations
        "pmla": "PMLA-2002",
        "prevention of money laundering act": "PMLA-2002",
        
        # PC Act variations
        "pc act": "PC-1988",
        "prevention of corruption act": "PC-1988",
        
        # SC/ST Act variations
        "sc/st act": "SC/ST-1989",
        "sc st act": "SC/ST-1989",
        "scheduled castes and scheduled tribes (prevention of atrocities) act": "SC/ST-1989",
        
        # POCSO variations
        "pocso": "POCSO-2012",
        "pocso act": "POCSO-2012",
        "protection of children from sexual offences act": "POCSO-2012",
    }
    
    def __init__(self):
        # Compile regex patterns
        self.section_patterns = [
            # "Section 420 IPC" or "Sec 420 IPC"
            re.compile(r'\b(?:section|sec|s\.?)\s*(\d+[A-Z]?)\s+(?:of\s+)?(.+?)(?:\s|$|,|;)', re.IGNORECASE),
            # "IPC 420" or "IPC Section 420"
            re.compile(r'\b(.+?)\s+(?:section|sec|s\.?)?\s*(\d+[A-Z]?)\b', re.IGNORECASE),
            # Just section number in context
            re.compile(r'\b(\d+[A-Z]?)\b'),
        ]
    
    def normalize_act_name(self, act_str: str) -> str:
        """Normalize act name to canonical form"""
        act_clean = act_str.strip().lower()
        
        # Remove common suffixes
        act_clean = re.sub(r'\s*\d{4}\s*$', '', act_clean)
        act_clean = re.sub(r',?\s*act$', '', act_clean)
        
        # Look up in variations
        canonical = self.ACT_VARIATIONS.get(act_clean)
        if canonical:
            return canonical
        
        # If not found, return cleaned original
        return act_str.strip()
    
    def extract_section_number(self, text: str) -> Optional[str]:
        """Extract section number from text"""
        # Try various patterns
        for pattern in self.section_patterns:
            match = pattern.search(text)
            if match:
                groups = match.groups()
                # Find the group that looks like a section number
                for group in groups:
                    if group and re.match(r'^\d+[A-Z]?$', group.strip()):
                        return group.strip()
        return None
    
    def parse_statute(self, statute_text: str) -> Optional[Tuple[str, str]]:
        """
        Parse statute text and return (act, section) tuple
        Returns None if parsing fails
        """
        statute_text = statute_text.strip()
        
        # Try pattern: "Section X of Act" or "Act Section X"
        for pattern in self.section_patterns:
            match = pattern.search(statute_text)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    # Determine which is section and which is act
                    if re.match(r'^\d+[A-Z]?$', groups[0].strip()):
                        section = groups[0].strip()
                        act = groups[1].strip()
                    else:
                        act = groups[0].strip()
                        section = groups[1].strip() if len(groups) > 1 else ""
                    
                    if section:
                        return (self.normalize_act_name(act), section)
        
        return None
    
    def normalize_statute(self, act: str, section: str) -> str:
        """
        Normalize statute to canonical format: Act:Section
        Example: "IPC-1860:420"
        """
        canonical_act = self.normalize_act_name(act)
        section_clean = section.strip().upper()
        
        return f"{canonical_act}:{section_clean}"
    
    def get_bns_equivalent(self, ipc_section: str) -> Optional[str]:
        """Get BNS equivalent for IPC section"""
        section_num = ipc_section.strip().upper()
        bns_section = self.IPC_TO_BNS.get(section_num)
        if bns_section:
            return f"BNS-2023:{bns_section}"
        return None
    
    def get_bnss_equivalent(self, crpc_section: str) -> Optional[str]:
        """Get BNSS equivalent for CrPC section"""
        section_num = crpc_section.strip().upper()
        bnss_section = self.CRPC_TO_BNSS.get(section_num)
        if bnss_section:
            return f"BNSS-2023:{bnss_section}"
        return None
    
    def normalize_statute_dict(self, statute_dict: Dict) -> List[str]:
        """
        Normalize statute dictionary from case JSON
        Returns list of normalized statutes with both old and new code equivalents
        """
        act = statute_dict.get("act", "")
        section = statute_dict.get("section", "")
        
        if not act or not section:
            return []
        
        results = []
        
        # Normalize to canonical form
        canonical = self.normalize_statute(act, section)
        results.append(canonical)
        
        # Add BNS/BNSS equivalent if applicable
        canonical_act = self.normalize_act_name(act)
        
        if canonical_act == "IPC-1860":
            bns_equiv = self.get_bns_equivalent(section)
            if bns_equiv:
                results.append(bns_equiv)
        
        elif canonical_act == "CrPC-1973":
            bnss_equiv = self.get_bnss_equivalent(section)
            if bnss_equiv:
                results.append(bnss_equiv)
        
        return results
    
    def normalize_proposition_statutes(self, statutes: List[str]) -> List[str]:
        """
        Normalize list of statute strings from propositions
        Returns deduplicated list of normalized statutes
        """
        results = set()
        
        for statute_text in statutes:
            parsed = self.parse_statute(statute_text)
            if parsed:
                act, section = parsed
                canonical = self.normalize_statute(act, section)
                results.add(canonical)
                
                # Add equivalents
                canonical_act = self.normalize_act_name(act)
                if canonical_act == "IPC-1860":
                    bns_equiv = self.get_bns_equivalent(section)
                    if bns_equiv:
                        results.add(bns_equiv)
                elif canonical_act == "CrPC-1973":
                    bnss_equiv = self.get_bnss_equivalent(section)
                    if bnss_equiv:
                        results.add(bnss_equiv)
        
        return sorted(list(results))


def test_normalizer():
    """Test the statute normalizer"""
    normalizer = StatuteNormalizer()
    
    # Test cases
    test_cases = [
        {"act": "CrPC 1973", "section": "438"},
        {"act": "IPC", "section": "420"},
        {"act": "Indian Penal Code", "section": "302"},
        {"act": "NDPS Act", "section": "20"},
    ]
    
    print("Testing Statute Normalizer")
    print("=" * 60)
    
    for test in test_cases:
        normalized = normalizer.normalize_statute_dict(test)
        print(f"Input: {test}")
        print(f"Output: {normalized}")
        print()


if __name__ == "__main__":
    test_normalizer()
