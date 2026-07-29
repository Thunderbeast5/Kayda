"""
Phase 2 — Automated validation of extracted records.

Checks every field in every record for correctness, completeness,
and data quality. Run this after run_extraction.py.

Exit code 0 = all records pass ERROR-level checks.
Exit code 1 = one or more records have ERROR-level failures.

Produces manifest/validation_report.json with full issue list.
"""

import json
import re
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

EXTRACTED_RECORDS_DIR = Path("extracted_records")
MANIFEST_DIR = Path("manifest")
REPORT_PATH = MANIFEST_DIR / "validation_report.json"

VALID_OUTCOMES = {"granted", "modified", "deleted", "refused", "dismissed"}
RS_PATTERN = re.compile(r"Rs\.?\s*[\d,]+", re.IGNORECASE)


def _err(issues: list, fname: str, check: str, detail: str):
    issues.append({"file": fname, "severity": "ERROR", "check": check, "detail": detail})


def _warn(issues: list, fname: str, check: str, detail: str):
    issues.append({"file": fname, "severity": "WARNING", "check": check, "detail": detail})


def validate_record(rec: dict, fname: str) -> list[dict]:
    issues: list[dict] = []

    # ── 1. Section 438 must be present ─────────────────────────────────────
    referred = rec.get("referred_acts", [])
    if not any("438" in act for act in referred):
        _err(issues, fname, "section_438_missing",
             f"referred_acts={referred} — not an anticipatory bail case or extraction failed")

    # ── 2. Critical fields not empty ────────────────────────────────────────
    for fld in ["referred_acts", "headnote_raw", "numbered_paragraphs", "final_verdict"]:
        if not rec.get(fld):
            _err(issues, fname, "critical_field_empty", f"'{fld}' is empty or null")

    # ── 3. Headnote points successfully parsed ──────────────────────────────
    if rec.get("headnote_raw") and not rec.get("headnote_points"):
        _warn(issues, fname, "headnote_points_empty",
              "headnote_raw present but A/B/C splitting produced no points")

    # ── 4. Headnote not truncated (ends with bare 'Rs.') ───────────────────
    hn = rec.get("headnote_raw", "") or ""
    if re.search(r"Rs\.\s*$", hn):
        _err(issues, fname, "headnote_truncated",
             "headnote_raw ends with bare 'Rs.' — page-break healing failed mid-sentence")

    # ── 5. Paragraph count plausible ────────────────────────────────────────
    paras = rec.get("numbered_paragraphs", [])
    if len(paras) == 0 and rec.get("headnote_raw"):
        _err(issues, fname, "no_paragraphs",
             "Headnote present but zero numbered paragraphs — paragraph splitting failed")
    if len(paras) > 50:
        _warn(issues, fname, "high_paragraph_count",
              f"{len(paras)} paragraphs — verify extraction is correct")

    # ── 6. Bail outcome must be determined ──────────────────────────────────
    outcome = rec.get("bail_outcome")
    if not outcome:
        _warn(issues, fname, "bail_outcome_missing",
              "bail_outcome not determined — add signal phrase for this case pattern")
    elif outcome not in VALID_OUTCOMES:
        _err(issues, fname, "bail_outcome_invalid",
             f"bail_outcome='{outcome}' not in valid set {VALID_OUTCOMES}")

    # ── 7. Bail amount format ────────────────────────────────────────────────
    for fld in ["bail_amount_original", "bail_amount_modified"]:
        val = rec.get(fld)
        if val and not RS_PATTERN.search(val):
            _warn(issues, fname, "bail_amount_format",
                  f"'{fld}' value '{val}' does not match Rs. pattern")

    # ── 8. Headnote points have non-empty text ──────────────────────────────
    for pt in rec.get("headnote_points", []):
        if not pt.get("text", "").strip():
            _warn(issues, fname, "headnote_point_empty",
                  f"Headnote point '{pt.get('label')}' has empty text")

    # ── 9. Appeal type not truncated ────────────────────────────────────────
    at = rec.get("appeal_type", "") or ""
    if at.endswith(" of"):
        _warn(issues, fname, "appeal_type_truncated",
              f"appeal_type ends with ' of' — possible truncation: '{at[-60:]}'")

    # ── 10. Year parsed ─────────────────────────────────────────────────────
    if not rec.get("decided_on_year"):
        _warn(issues, fname, "year_not_parsed",
              f"decided_on_year is null (decided_on='{rec.get('decided_on')}')")

    # ── 11. Equivalent citations look valid ─────────────────────────────────
    for cit in rec.get("equivalent_citations", []):
        if len(cit) < 6:
            _warn(issues, fname, "equiv_citation_fragment",
                  f"Suspicious short citation: '{cit}'")

    # ── 12. Case citation present ────────────────────────────────────────────
    if not rec.get("case_citation"):
        _warn(issues, fname, "case_citation_missing",
              "No LAWS(...) citation found — deduplication harder")

    # ── 13. Judgment author captured (informational) ─────────────────────────
    if not rec.get("judgment_author"):
        _warn(issues, fname, "judgment_author_missing",
              "No judge byline found before paragraph (1.) — may not be present in this PDF")

    return issues


def run_validation() -> None:
    record_paths = sorted(EXTRACTED_RECORDS_DIR.glob("*.json"))

    if not record_paths:
        logger.error(f"No records found in {EXTRACTED_RECORDS_DIR}/")
        sys.exit(1)

    logger.info(f"Validating {len(record_paths)} extracted records...")

    all_issues: list[dict] = []
    pass_count = 0
    fail_count = 0

    for path in record_paths:
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            all_issues.append({
                "file": path.name, "severity": "ERROR",
                "check": "json_parse", "detail": str(e)
            })
            fail_count += 1
            continue

        issues = validate_record(rec, path.name)
        errors = [i for i in issues if i["severity"] == "ERROR"]

        if errors:
            fail_count += 1
            logger.warning(f"  ✗ {path.name} — {len(errors)} ERROR(s), "
                           f"{len(issues)-len(errors)} warning(s)")
        else:
            pass_count += 1
            warn_count = len([i for i in issues if i["severity"] == "WARNING"])
            status = f"✓ {path.name}"
            if warn_count:
                status += f" — {warn_count} warning(s)"
            logger.info(f"  {status}")

        for issue in issues:
            lvl = logging.WARNING if issue["severity"] == "ERROR" else logging.DEBUG
            logger.log(lvl, f"    [{issue['severity']}] {issue['check']}: {issue['detail']}")

        all_issues.extend(issues)

    # ── Write report ─────────────────────────────────────────────────────────
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "total_records": len(record_paths),
        "passed": pass_count,
        "failed": fail_count,
        "total_issues": len(all_issues),
        "error_count": len([i for i in all_issues if i["severity"] == "ERROR"]),
        "warning_count": len([i for i in all_issues if i["severity"] == "WARNING"]),
        "issues": all_issues,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Summary ───────────────────────────────────────────────────────────────
    err_count = report["error_count"]
    warn_count = report["warning_count"]

    print(f"\n{'='*60}")
    print(f"  VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"  Total records  : {len(record_paths)}")
    print(f"  Passed (no ERR): {pass_count}")
    print(f"  Failed (ERR)   : {fail_count}")
    print(f"  Total errors   : {err_count}")
    print(f"  Total warnings : {warn_count}")
    print(f"  Report         : {REPORT_PATH}")
    print(f"{'='*60}")

    if fail_count > 0:
        print("\n  ⚠  Records with ERRORs must be fixed before building training data.")
        print("     Open manifest/validation_report.json for full issue list.")
        sys.exit(1)
    elif warn_count > 0:
        print(f"\n  ✓ All records passed (no ERRORs).")
        print(f"  ℹ  {warn_count} warnings — review manifest/validation_report.json")
    else:
        print("\n  ✓ All records passed with no issues.")


if __name__ == "__main__":
    run_validation()
