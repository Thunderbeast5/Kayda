"""
parse_bsa_hierarchy.py
======================
Parses `bsa_sections.csv` Description text to detect embedded statutory hierarchy:
- Subsections: (1), (2), (3)...
- Clauses: (a), (b), (c)...
- Explanations: Explanation.-- / Explanation 1
- Provisos: Provided that... / Provided further that...
- Illustrations: Illustrations / (a), (b)
- Exceptions: Exception.-- / Exception 1

Outputs structured hierarchy metadata:
- ParentSection
- NodeType
- HierarchyLevel
- ChildIdentifier
- TextSlice
"""

import re
import pandas as pd
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
bsa_csv_path = BASE_DIR / "backend" / "all_acts" / "bsa" / "bsa_sections.csv"
output_hierarchy_csv = BASE_DIR / "data" / "cleaned" / "bsa_hierarchy_metadata.csv"
output_hierarchy_json = BASE_DIR / "data" / "cleaned" / "bsa_hierarchy_report.json"


def parse_hierarchy_from_description(sec_num: str, desc: str) -> list[dict]:
    items = []
    if not desc or not desc.strip():
        return items

    # Pattern for subsections (1), (2), (3) at start of lines or segments
    sub_matches = list(re.finditer(r"(?:^|\n|\.\s+)\((\d+)\)\s+", desc))

    if sub_matches:
        for i, m in enumerate(sub_matches):
            sub_num = m.group(1)
            child_id = f"{sec_num}({sub_num})"
            start_pos = m.start()
            end_pos = sub_matches[i + 1].start() if i + 1 < len(sub_matches) else len(desc)
            sub_text = desc[start_pos:end_pos].strip()

            items.append({
                "ParentSection": sec_num,
                "NodeType": "SUBSECTION",
                "HierarchyLevel": 1,
                "ChildIdentifier": child_id,
                "TextSlice": sub_text[:150] + "..." if len(sub_text) > 150 else sub_text,
            })

            # Check for embedded clauses (a), (b), (c) inside this subsection
            clause_matches = list(re.finditer(r"(?:^|\n|\.\s+|;|\:\-\-|\,\s+)\(([a-z])\)\s+", sub_text))
            if clause_matches:
                for c_idx, cm in enumerate(clause_matches):
                    clause_letter = cm.group(1)
                    clause_id = f"{child_id}({clause_letter})"
                    c_start = cm.start()
                    c_end = clause_matches[c_idx + 1].start() if c_idx + 1 < len(clause_matches) else len(sub_text)
                    c_text = sub_text[c_start:c_end].strip()

                    items.append({
                        "ParentSection": child_id,
                        "NodeType": "CLAUSE",
                        "HierarchyLevel": 2,
                        "ChildIdentifier": clause_id,
                        "TextSlice": c_text[:150] + "..." if len(c_text) > 150 else c_text,
                    })

    # Pattern for Provisos
    prov_matches = list(re.finditer(r"(Provided (?:that|further that|also that)[^\.\:\;]+[\.\:\;])", desc, re.IGNORECASE))
    for p_idx, pm in enumerate(prov_matches):
        prov_text = pm.group(1).strip()
        prov_id = f"{sec_num}(Prov{p_idx + 1})" if len(prov_matches) > 1 else f"{sec_num}(Prov)"
        items.append({
            "ParentSection": sec_num,
            "NodeType": "PROVISO",
            "HierarchyLevel": 1,
            "ChildIdentifier": prov_id,
            "TextSlice": prov_text[:150] + "..." if len(prov_text) > 150 else prov_text,
        })

    # Pattern for Explanations
    expl_matches = list(re.finditer(r"(Explanation[^\.\n]*[\.\n]+[^\n]+)", desc, re.IGNORECASE))
    for e_idx, em in enumerate(expl_matches):
        expl_text = em.group(1).strip()
        expl_id = f"{sec_num}_EXPL{e_idx + 1}" if len(expl_matches) > 1 else f"{sec_num}_EXPL"
        items.append({
            "ParentSection": sec_num,
            "NodeType": "EXPLANATION",
            "HierarchyLevel": 1,
            "ChildIdentifier": expl_id,
            "TextSlice": expl_text[:150] + "..." if len(expl_text) > 150 else expl_text,
        })

    # Pattern for Exceptions
    exc_matches = list(re.finditer(r"(Exception[^\.\n]*[\.\n]+[^\n]+)", desc, re.IGNORECASE))
    for ex_idx, exm in enumerate(exc_matches):
        exc_text = exm.group(1).strip()
        exc_id = f"{sec_num}(Exc{ex_idx + 1})" if len(exc_matches) > 1 else f"{sec_num}(Exc)"
        items.append({
            "ParentSection": sec_num,
            "NodeType": "EXCEPTION",
            "HierarchyLevel": 1,
            "ChildIdentifier": exc_id,
            "TextSlice": exc_text[:150] + "..." if len(exc_text) > 150 else exc_text,
        })

    # Pattern for Illustrations
    ill_matches = list(re.finditer(r"(Illustrations?\.[^\n]+(?:\n\([a-z]\)[^\n]+)*)", desc, re.IGNORECASE))
    for i_idx, im in enumerate(ill_matches):
        ill_text = im.group(1).strip()
        ill_id = f"{sec_num}(Illus{i_idx + 1})" if len(ill_matches) > 1 else f"{sec_num}(Illus)"
        items.append({
            "ParentSection": sec_num,
            "NodeType": "ILLUSTRATION",
            "HierarchyLevel": 1,
            "ChildIdentifier": ill_id,
            "TextSlice": ill_text[:150] + "..." if len(ill_text) > 150 else ill_text,
        })

    return items


def main():
    print("=" * 80)
    print(" EXECUTING BSA HIERARCHY DETECTION PARSER")
    print("=" * 80)

    df_bsa = pd.read_csv(bsa_csv_path, dtype=str).fillna("")
    print(f"Loaded bsa_sections.csv: {len(df_bsa)} base section rows.")

    all_hierarchy_items = []
    type_counts = {}

    for idx, r in df_bsa.iterrows():
        sec_num = str(r["Section"]).strip()
        desc = str(r["Description"]).strip()

        h_items = parse_hierarchy_from_description(sec_num, desc)
        for item in h_items:
            all_hierarchy_items.append(item)
            nt = item["NodeType"]
            type_counts[nt] = type_counts.get(nt, 0) + 1

    df_hierarchy = pd.DataFrame(all_hierarchy_items)
    output_hierarchy_csv.parent.mkdir(parents=True, exist_ok=True)
    df_hierarchy.to_csv(output_hierarchy_csv, index=False)

    report = {
        "total_base_sections": len(df_bsa),
        "total_hierarchy_nodes_detected": len(all_hierarchy_items),
        "node_type_breakdown": type_counts,
        "sample_nodes": all_hierarchy_items[:15],
    }

    with open(output_hierarchy_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n--- HIERARCHY DETECTION SUMMARY ---")
    print(f"Total Base Sections Analyzed: {len(df_bsa)}")
    print(f"Total Hierarchy Nodes Detected: {len(all_hierarchy_items)}")
    for nt, c in type_counts.items():
        print(f"   * {nt:15s}: {c}")
    print(f"\nSaved metadata CSV to {output_hierarchy_csv}")
    print(f"Saved hierarchy report to {output_hierarchy_json}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
