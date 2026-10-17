"""
Runner and CLI for Precedent Retrieval Pipeline.
Runs role-specific precedent retrieval on case context and statutory verification inputs.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .pipeline import PrecedentPipeline
from .schemas import RoleSpecificPrecedentRetrievalObject


def extract_legal_issues(legal_query_input: Optional[dict]) -> List[str]:
    """
    Extract plain-text sub-query / legal question strings from a LegalQueryObject dict.
    Collects string values of sub-query text fields found.
    """
    if not isinstance(legal_query_input, dict):
        return []

    TEXT_KEYS = ("sub_query", "query_text", "question", "text", "description")
    seen: set = set()
    result: List[str] = []

    def _harvest(obj: object) -> None:
        if len(result) >= 12:
            return
        if isinstance(obj, dict):
            for k in TEXT_KEYS:
                v = obj.get(k)
                if isinstance(v, str):
                    s = v.strip()
                    if s and s not in seen:
                        seen.add(s)
                        result.append(s)
                    break
            for v in obj.values():
                if len(result) >= 12:
                    return
                if isinstance(v, (dict, list)):
                    _harvest(v)
        elif isinstance(obj, list):
            for item in obj:
                if len(result) >= 12:
                    return
                _harvest(item)

    for top_key in ("sub_queries", "legal_sub_queries", "queries", "sub_query_items"):
        if top_key in legal_query_input:
            _harvest(legal_query_input[top_key])
    if not result:
        _harvest(legal_query_input)

    return result[:12]


def run_precedent_pipeline(
    case_context: Union[dict, str],
    statutory_input: dict,
    legal_query: Optional[dict] = None,
    legal_issues: Optional[List[str]] = None,
    max_prosecution_precedents: int = 10,
    max_defense_precedents: int = 10,
    precedent_dir: Optional[Path] = None,
) -> dict:
    """
    Executes the Precedent Retrieval Pipeline.

    Args:
        case_context: Case context dict or raw facts string.
        statutory_input: Stage 4 statutory verification output dict.
        legal_query: Stage 1 legal query dict (optional).
        legal_issues: Specific legal issue questions (optional).
        max_prosecution_precedents: Maximum prosecution precedents to return.
        max_defense_precedents: Maximum defense precedents to return.
        precedent_dir: Path to directory with precedent JSONs.

    Returns:
        RoleSpecificPrecedentRetrievalObject as dict.
    """
    pipeline = PrecedentPipeline(
        max_prosecution_precedents=max_prosecution_precedents,
        max_defense_precedents=max_defense_precedents,
        precedent_dir=precedent_dir,
    )
    issues = legal_issues or extract_legal_issues(legal_query)
    res = pipeline.run(case_context, statutory_input, legal_issues=issues)
    if res.verified_precedent_object:
        return res.verified_precedent_object.model_dump()
    return {
        "status": res.status,
        "feedback": res.feedback,
        "issues": [issue.model_dump() for issue in res.issues],
    }


def main():
    parser = argparse.ArgumentParser(description="Run Precedent Retrieval Pipeline")
    parser.add_argument("--case-file", type=str, help="Path to JSON file with case context")
    parser.add_argument("--statute-file", type=str, required=True, help="Path to JSON file with Stage 4 statutory output")
    parser.add_argument("--query-file", type=str, help="Path to JSON file with Stage 1 legal query")
    parser.add_argument("--output", "-o", type=str, help="Output JSON path")
    args = parser.parse_args()

    with open(args.statute_file, "r", encoding="utf-8") as f:
        statutory_input = json.load(f)

    case_context = {}
    if args.case_file:
        with open(args.case_file, "r", encoding="utf-8") as f:
            case_context = json.load(f)

    legal_query = {}
    if args.query_file:
        with open(args.query_file, "r", encoding="utf-8") as f:
            legal_query = json.load(f)

    result = run_precedent_pipeline(
        case_context=case_context,
        statutory_input=statutory_input,
        legal_query=legal_query,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Results saved to {args.output}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
