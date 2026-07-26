import json
from pathlib import Path
from typing import List, Dict, Any

def parse_constitution_data(file_path: Path) -> List[Dict[str, Any]]:
    """
    Parses constitutional articles from the given JSON file path.
    """
    if not file_path.exists():
        print(f"[parse_constitution] Warning: File not found at {file_path}")
        return []
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    parsed_articles = []
    for item in data:
        parsed_articles.append({
            "article": str(item.get("article") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "source": str(item.get("source") or "Constitution of India").strip(),
            "linked_sections": item.get("linked_sections") or []
        })
    
    return parsed_articles

if __name__ == "__main__":
    # Test execution
    data_dir = Path(__file__).resolve().parent.parent.parent / "data" / "new"
    articles = parse_constitution_data(data_dir / "constitution.json")
    print(f"Parsed {len(articles)} articles.")
    for a in articles[:2]:
        print(a)
