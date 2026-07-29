"""
Manifest / processing log.
Tracks every PDF's triage classification, extraction status, fields extracted,
missing anchors, and warnings.
Written to manifest/manifest.jsonl — one JSON line per file.
Append-only so a crashed run doesn't lose earlier entries.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MANIFEST_PATH = Path("manifest") / "manifest.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_entry(
    pdf_name: str,
    classification: str,
    status: str,                   # "SUCCESS" | "PARTIAL" | "FAILED" | "SKIPPED"
    page_count: int = 0,
    fields_extracted: list[str] | None = None,
    missing_anchors: list[str] | None = None,
    warnings: list[str] | None = None,
    error: str | None = None,
    output_file: str | None = None,
) -> None:
    """Append one manifest entry."""
    entry = {
        "timestamp": _utc_now(),
        "file": pdf_name,
        "classification": classification,
        "status": status,
        "page_count": page_count,
        "fields_extracted": fields_extracted or [],
        "missing_anchors": missing_anchors or [],
        "warnings": warnings or [],
        "error": error,
        "output_file": output_file,
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info(
        f"[manifest] {pdf_name} → {classification} | {status}"
        + (f" | WARNINGS: {warnings}" if warnings else "")
        + (f" | MISSING: {missing_anchors}" if missing_anchors else "")
    )


def load_manifest() -> list[dict]:
    """Load all manifest entries as a list of dicts."""
    if not MANIFEST_PATH.exists():
        return []
    entries = []
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def already_processed(pdf_name: str) -> bool:
    """
    Return True if this PDF already has a SUCCESS entry in the manifest.
    Allows resuming interrupted runs without re-processing completed files.
    """
    for entry in load_manifest():
        if entry.get("file") == pdf_name and entry.get("status") == "SUCCESS":
            return True
    return False


def print_summary() -> None:
    """Print a human-readable summary of the manifest to stdout."""
    all_entries = load_manifest()
    if not all_entries:
        print("No manifest entries found.")
        return

    # Deduplicate: keep only the most recent entry per file
    latest: dict[str, dict] = {}
    for entry in all_entries:
        fname = entry.get("file", "")
        latest[fname] = entry  # later entries overwrite earlier ones

    entries = list(latest.values())
    total = len(entries)
    by_status: dict[str, int] = {}
    by_class: dict[str, int] = {}
    needs_review: list[str] = []

    for e in entries:
        s = e.get("status", "UNKNOWN")
        c = e.get("classification", "UNKNOWN")
        by_status[s] = by_status.get(s, 0) + 1
        by_class[c] = by_class.get(c, 0) + 1
        if e.get("missing_anchors") or e.get("warnings"):
            needs_review.append(e["file"])

    print(f"\n{'='*55}")
    print(f"  EXTRACTION MANIFEST SUMMARY  ({total} unique files)")
    print(f"{'='*55}")
    for status, count in sorted(by_status.items()):
        print(f"  {status:<12} : {count}")
    print(f"{'─'*55}")
    for cls, count in sorted(by_class.items()):
        print(f"  {cls:<12} : {count}")
    if needs_review:
        print(f"\n  ⚠  Files needing review ({len(needs_review)}):")
        for f in needs_review:
            print(f"     - {f}")
    print(f"{'='*55}\n")
