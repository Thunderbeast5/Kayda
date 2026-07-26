import json
from pathlib import Path
from typing import List, Dict, Any

def parse_principles_data(file_path: Path) -> List[Dict[str, Any]]:
    """
    Parses legal principles from the given JSON file path.
    """
    if not file_path.exists():
        print(f"[parse_principles] Warning: File not found at {file_path}")
        return []
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    parsed_principles = []
    for item in data:
        parsed_principles.append({
            "name": str(item.get("name") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "source": str(item.get("source") or "").strip(),
            "linked_sections": item.get("linked_sections") or []
        })
        
    return parsed_principles

if __name__ == "__main__":
    # Test execution
    data_dir = Path(__file__).resolve().parent.parent.parent / "data" / "new"
    principles = parse_principles_data(data_dir / "legal_principles.json")
    print(f"Parsed {len(principles)} principles.")
    for p in principles[:2]:
        print(p)
