"""
citation_formatter_service.py

Utility service to format legal citations in human-readable format.
Replaces placeholder tags like [SECTION: 498A] with proper format like "Section 498A IPC"
"""

import re
from typing import Dict, Any, Optional


class CitationFormatterService:
    """
    Formats legal citations for human readability.
    Converts internal representations to proper legal citation format.
    """

    def __init__(self):
        pass

    def format_section_reference(self, act: str, section: str, include_prefix: bool = True) -> str:
        """
        Format a section reference in proper legal citation style.
        
        Args:
            act: Act name (IPC, BNS, POCSO, etc.)
            section: Section number
            include_prefix: Whether to include "Section" prefix
            
        Returns:
            Formatted string like "Section 498A IPC" or "498A IPC"
        """
        act_clean = str(act).strip().upper()
        section_clean = str(section).strip()
        
        # Handle cases where section already contains act prefix
        if section_clean.upper().startswith(act_clean):
            section_clean = section_clean[len(act_clean):].strip()
        
        # Remove any "Section" prefix from section number
        if section_clean.lower().startswith("section"):
            section_clean = section_clean[7:].strip()
        
        if include_prefix:
            return f"Section {section_clean} {act_clean}"
        else:
            return f"{section_clean} {act_clean}"

    def format_case_citation(self, case_name: str, citation: Optional[str] = None, 
                            year: Optional[int] = None, court: Optional[str] = None) -> str:
        """
        Format a case citation in proper legal style.
        
        Args:
            case_name: Name of the case
            citation: Citation reference
            year: Year of judgment
            court: Court name
            
        Returns:
            Formatted case citation
        """
        parts = []
        
        if case_name:
            parts.append(case_name.strip())
        
        if citation:
            parts.append(citation.strip())
        elif year:
            # If no citation but year available, add it in parentheses
            parts.append(f"({year})")
        
        if court and citation and citation not in court:
            # Add court abbreviation if not already in citation
            court_abbr = self._get_court_abbreviation(court)
            if court_abbr:
                parts.append(court_abbr)
        
        return " ".join(parts) if parts else "Unknown Case"

    def format_article_reference(self, article: str, include_prefix: bool = True) -> str:
        """
        Format a constitutional article reference.
        
        Args:
            article: Article number or full reference
            include_prefix: Whether to include "Article" prefix
            
        Returns:
            Formatted article reference like "Article 21" or "21"
        """
        article_clean = str(article).strip()
        
        # Extract article number if full reference provided
        match = re.search(r'\b(\d+[A-Za-z]*)\b', article_clean)
        if match:
            article_num = match.group(1)
            
            # Check if it already has "Article" prefix
            if article_clean.lower().startswith("article"):
                return article_clean
            
            if include_prefix:
                return f"Article {article_num}"
            else:
                return article_num
        
        return article_clean

    def replace_section_tags(self, text: str) -> str:
        """
        Replace [SECTION:...] tags with human-readable format.
        
        Examples:
            [SECTION:498A] -> Section 498A IPC
            [SECTION:IPC 498A] -> Section 498A IPC
            [SECTION:BNS 80] -> Section 80 BNS
        
        Args:
            text: Text containing section tags
            
        Returns:
            Text with formatted section references
        """
        # Pattern to match [SECTION:...] tags
        pattern = r'\[SECTION:\s*([^\]]+)\]'
        
        def replacer(match):
            content = match.group(1).strip()
            
            # Try to parse act and section
            parts = content.split()
            
            if len(parts) == 2:
                # Format: "IPC 498A" or "BNS 80"
                act, section = parts
                return self.format_section_reference(act, section, include_prefix=True)
            elif len(parts) == 1:
                # Format: "498A" - assume IPC by default
                section = parts[0]
                # Try to detect act from section format. Checked longest/most
                # specific act names FIRST (BNSS before BNS, BSA before BNS,
                # POCSO/DOWRY before generic) so e.g. "BNSS482" is never
                # mis-detected as act="BNS", section="S482" (a real bug: a
                # plain `.startswith("BNS")` check matches "BNSS..." too,
                # since "BNSS" starts with the substring "BNS").
                section_upper = section.upper()
                acts_by_specificity = ["BNSS", "CRPC", "POCSO", "DOWRY", "DPA", "BSA", "IEA", "BNS", "IPC"]
                for act_name in acts_by_specificity:
                    if section_upper.startswith(act_name):
                        return self.format_section_reference(act_name, section[len(act_name):], include_prefix=True)
                # Default to IPC for bare section numbers with no recognizable act prefix
                return self.format_section_reference("IPC", section, include_prefix=True)
            else:
                # Unknown format, return as-is with prefix
                return f"Section {content}"
        
        return re.sub(pattern, replacer, text)

    def replace_case_tags(self, text: str) -> str:
        """
        Replace [CASE:...] tags with formatted case citations.
        
        Args:
            text: Text containing case tags
            
        Returns:
            Text with formatted case citations
        """
        # Pattern to match [CASE:...] tags
        pattern = r'\[CASE:\s*([^\]]+)\]'
        
        def replacer(match):
            content = match.group(1).strip()
            # For now, return content as-is since it should already be case name
            # In future, could parse and reformat if needed
            return content
        
        return re.sub(pattern, replacer, text)

    def replace_article_tags(self, text: str) -> str:
        """
        Replace [ARTICLE:...] tags with formatted article references.
        
        Args:
            text: Text containing article tags
            
        Returns:
            Text with formatted article references
        """
        # Pattern to match [ARTICLE:...] tags
        pattern = r'\[ARTICLE:\s*([^\]]+)\]'
        
        def replacer(match):
            content = match.group(1).strip()
            return self.format_article_reference(content, include_prefix=True)
        
        return re.sub(pattern, replacer, text)

    def replace_all_tags(self, text: str) -> str:
        """
        Replace all legal citation tags with human-readable format.
        
        Args:
            text: Text containing various citation tags
            
        Returns:
            Text with all tags replaced with formatted citations
        """
        text = self.replace_section_tags(text)
        text = self.replace_case_tags(text)
        text = self.replace_article_tags(text)
        return text

    def format_spoken_argument(self, spoken_text: str) -> str:
        """
        Format a spoken argument by replacing all citation tags.
        This is the main method to call for final output formatting.
        
        Args:
            spoken_text: Raw spoken argument with citation tags
            
        Returns:
            Formatted spoken argument ready for display
        """
        return self.replace_all_tags(spoken_text)

    def _get_court_abbreviation(self, court: str) -> Optional[str]:
        """Get standard abbreviation for court name."""
        court_lower = court.lower()
        
        if "supreme" in court_lower:
            return "SC"
        elif "high" in court_lower:
            # Try to extract state name for HC abbreviation
            # e.g., "Delhi High Court" -> "Del HC"
            for state in ["delhi", "bombay", "madras", "calcutta", "allahabad"]:
                if state in court_lower:
                    return f"{state.title()[:3]} HC"
            return "HC"
        
        return None

    def format_section_list(self, sections: list) -> str:
        """
        Format a list of sections for display.
        
        Args:
            sections: List of section dicts with 'act' and 'section' keys
            
        Returns:
            Comma-separated formatted section list
        """
        formatted = []
        for sec in sections:
            if isinstance(sec, dict):
                act = sec.get('act', '')
                section = sec.get('section', '')
                if act and section:
                    formatted.append(self.format_section_reference(act, section, include_prefix=False))
            elif isinstance(sec, str):
                # Try to parse string. Guard against strings like "Section
                # 498A" (no act at all) being misread as act="Section",
                # section="498A" - the previous code took parts[0]/parts[1]
                # unconditionally. Only treat parts[0] as the act if it's one
                # of the acts this system actually knows about.
                parts = sec.split()
                known_acts = {"IPC", "BNS", "BNSS", "CRPC", "BSA", "IEA", "POCSO", "DPA", "DOWRY"}
                if len(parts) >= 2 and parts[0].strip().upper() in known_acts:
                    formatted.append(self.format_section_reference(parts[0], parts[1], include_prefix=False))
                elif len(parts) >= 2 and parts[0].strip().lower() == "section" and len(parts) >= 3 and parts[2].strip().upper() in known_acts:
                    # "Section 498A IPC" style
                    formatted.append(self.format_section_reference(parts[2], parts[1], include_prefix=False))
                else:
                    formatted.append(sec)
        
        if not formatted:
            return "No sections"
        
        if len(formatted) == 1:
            return f"Section {formatted[0]}"
        elif len(formatted) == 2:
            return f"Sections {formatted[0]} and {formatted[1]}"
        else:
            return f"Sections {', '.join(formatted[:-1])}, and {formatted[-1]}"


# Module-level singleton instance
_formatter_instance = None

def get_citation_formatter() -> CitationFormatterService:
    """Get singleton instance of CitationFormatterService."""
    global _formatter_instance
    if _formatter_instance is None:
        _formatter_instance = CitationFormatterService()
    return _formatter_instance