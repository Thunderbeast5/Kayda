import json
from pathlib import Path
from typing import List, Dict, Any, Tuple

def parse_cases_data(file_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parses court cases from the given JSON file path.
    Separates them into SupremeCourtCase and HighCourtCase lists based on the 'court' field.
    """
    if not file_path.exists():
        print(f"[parse_cases] Warning: File not found at {file_path}")
        return [], []
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    sc_cases = []
    hc_cases = []
    
    for item in data:
        court = str(item.get("court") or "").strip().lower()
        parsed_case = {
            "case_name": str(item.get("case_name") or "").strip(),
            "citation": str(item.get("citation") or "").strip(),
            "year": int(item.get("year") or 0),
            "summary": str(item.get("summary") or "").strip(),
            "court": str(item.get("court") or "").strip(),
            "source": str(item.get("source") or "").strip(),
            "linked_sections": item.get("linked_sections") or [],
            "cites_articles": item.get("cites_articles") or []
        }
        
        if "supreme court" in court:
            # SupremeCourtCase has 'ratio_decidendi'
            parsed_case["ratio_decidendi"] = str(item.get("ratio_decidendi") or "").strip()
            sc_cases.append(parsed_case)
        else:
            parsed_case["follows_sc_case"] = str(item.get("follows_sc_case") or "").strip()
            hc_cases.append(parsed_case)
            
    return sc_cases, hc_cases

if __name__ == "__main__":
    # Test execution
    data_dir = Path(__file__).resolve().parent.parent.parent / "data" / "new"
    sc, hc = parse_cases_data(data_dir / "court_cases.json")
    print(f"Parsed {len(sc)} Supreme Court cases, {len(hc)} High Court cases.")
    if sc:
        print("SC:", sc[0])
    if hc:
        print("HC:", hc[0])
