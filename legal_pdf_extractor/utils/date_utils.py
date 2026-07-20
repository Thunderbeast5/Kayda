"""
date_utils.py — Date parsing for Indian legal documents
"""
import re
from datetime import datetime
from typing import Optional

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

DATE_PATTERNS = [
    r'(\d{1,2})[thstndrd]*\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})',
    r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
    r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',
    r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(\d{4})',
]


def parse_date(text: str) -> Optional[str]:
    """Parse date string to ISO format YYYY-MM-DD."""
    if not text:
        return None
    text_lower = text.lower().strip()
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            groups = m.groups()
            try:
                if len(groups) == 3:
                    g = [str(x) for x in groups]
                    # "12 january 2023" or "january 12 2023"
                    if g[0].isdigit() and not g[1].isdigit():
                        day, month_str, year = int(g[0]), g[1], int(g[2])
                        month = MONTH_MAP.get(month_str)
                    elif not g[0].isdigit() and g[1].isdigit():
                        month_str, day, year = g[0], int(g[1]), int(g[2])
                        month = MONTH_MAP.get(month_str)
                    elif len(g[0]) == 4:
                        year, month, day = int(g[0]), int(g[1]), int(g[2])
                    else:
                        day, month, year = int(g[0]), int(g[1]), int(g[2])
                    if month:
                        return f"{year:04d}-{month:02d}-{day:02d}"
            except Exception:
                continue
    return None


def extract_year(text: str) -> Optional[int]:
    m = re.search(r'\b(19|20)\d{2}\b', text)
    return int(m.group()) if m else None
