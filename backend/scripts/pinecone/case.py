import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# backend/scripts/pinecone -> backend/bail_cases
input_folder = BASE_DIR.parent.parent / "bail_cases"

print("Checking input folder:", input_folder)
print("Folder exists:", input_folder.exists())


def extract_sections(act_sections):
    sections = []
    acts = set()

    for a in act_sections:
        act = a.get("act_short_name", "")
        sec = a.get("section", "")
        if act:
            acts.add(act)
        if act and sec:
            sections.append(f"{act} {sec}")

    return list(acts), sections


def infer_bail_type(case):
    text = (
        (case.get("headnote_raw") or "") +
        " " +
        (case.get("ratio_decidendi") or "")
    ).lower()

    if "anticipatory bail" in text or "438" in text:
        return "anticipatory"

    return "unknown"


def build_document(case):
    acts, sections = extract_sections(case.get("act_sections", []))

    embedding_text = f"""
Case: {case.get('appellant','')} v. {case.get('respondent','')}

Court: {case.get('court','')}
Year: {case.get('decided_on_year','')}

Bail Type:
{infer_bail_type(case)}

Issue:
{case.get('headnote_raw','')}

Ratio:
{case.get('ratio_decidendi','')}

Outcome:
{case.get('bail_outcome','')}

Applicable Sections:
{", ".join(sections)}

Conditions:
{" ".join(case.get("bail_conditions", []))}
""".strip()

    metadata = {
        "case_name": f"{case.get('appellant','')} v. {case.get('respondent','')}",
        "citation": case.get("case_citation"),
        "court": case.get("court"),
        "year": case.get("decided_on_year"),
        "bail_type": infer_bail_type(case),
        "outcome": case.get("bail_outcome"),
        "acts": acts,
        "sections": sections,
        "appeal_type": case.get("appeal_type")
    }

    return {
        "id": case.get("case_citation", ""),
        "text": embedding_text,
        "metadata": metadata
    }


# -------------------------
# Convert all JSON files
# -------------------------

output = []

# Finds all .json files in backend/bail_cases (including subfolders)
files = list(input_folder.rglob("*.json"))

print(f"Found {len(files)} JSON files")

# Note: Remove `[:10]` if you want to process ALL files instead of just the first 10
for file_path in files:
    print(f"Processing: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        case = json.load(f)

    output.append(build_document(case))

with open("pinecone_documents.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"Created {len(output)} Pinecone documents.")