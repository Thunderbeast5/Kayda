"""
Data Normalizer for Bail Cases
Normalizes statutes, structures data for database ingestion
"""

import json
from pathlib import Path
from typing import List, Dict, Any
from statute_normalizer import StatuteNormalizer
from tqdm import tqdm


class CaseDataNormalizer:
    """Normalizes case data for database ingestion"""
    
    def __init__(self):
        self.statute_normalizer = StatuteNormalizer()
    
    def normalize_case_statutes(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize all statute references in a case"""
        case = case_data.get("case", {})
        
        # Normalize case-level statutes
        if "statutes" in case:
            normalized_case_statutes = []
            for statute_dict in case["statutes"]:
                normalized_list = self.statute_normalizer.normalize_statute_dict(statute_dict)
                normalized_case_statutes.extend(normalized_list)
            
            case["normalized_statutes"] = list(set(normalized_case_statutes))  # Deduplicate
        
        # Normalize proposition-level statutes
        if "propositions" in case:
            for prop in case["propositions"]:
                if "statutes" in prop:
                    normalized_prop_statutes = self.statute_normalizer.normalize_proposition_statutes(
                        prop["statutes"]
                    )
                    prop["normalized_statutes"] = normalized_prop_statutes
                else:
                    prop["normalized_statutes"] = []
        
        case_data["case"] = case
        return case_data
    
    def extract_db_records(self, case_data: Dict[str, Any]) -> Dict[str, List[Dict]]:
        """
        Extract structured records for database insertion
        Returns dict with 'cases' and 'propositions' lists
        """
        case = case_data.get("case", {})
        doc_meta = case_data.get("doc_meta", {})
        verdicts = case_data.get("verdicts", {})
        
        # Case-level record
        case_record = {
            "case_id": case_data.get("case_id"),
            "case_name": case.get("case_name"),
            "petitioner": case.get("petitioner"),
            "respondent": case.get("respondent"),
            "court": case.get("court"),
            "decided_on": doc_meta.get("decided_on"),
            "bench_strength": doc_meta.get("bench_strength_regex"),
            "procedural_stage": case.get("procedural_stage"),
            "offence_types": case.get("offence_types", []),
            "dispute_nature": case.get("dispute_nature"),
            "abstract_facts": case.get("abstract_facts"),
            "disposition": case.get("disposition"),
            "normalized_statutes": case.get("normalized_statutes", []),
            "lower_court_outcome": case.get("lower_court_outcome"),
        }
        
        # Proposition-level records
        proposition_records = []
        for prop in case.get("propositions", []):
            prop_id = prop.get("id")
            verdict = verdicts.get(prop_id, {})
            
            prop_record = {
                "case_id": case_data.get("case_id"),
                "proposition_id": prop_id,
                "text": prop.get("text"),
                "speaker": prop.get("speaker"),
                "kind": prop.get("kind"),
                "is_holding": prop.get("is_holding", False),
                "favors": prop.get("favors"),
                "conditions": prop.get("conditions", []),
                "normalized_statutes": prop.get("normalized_statutes", []),
                "tags": prop.get("tags", []),
                "binding_level": prop.get("binding_level", "persuasive"),
                "authorities": prop.get("authorities", []),
                "anchors": prop.get("anchors", []),
                "quote": prop.get("quote", ""),
                # Verification flags
                "quote_verified": verdict.get("verdict") == "supported",
                "favors_verified": verdict.get("favors_correct", True),
                "verification_note": verdict.get("note", ""),
            }
            
            proposition_records.append(prop_record)
        
        return {
            "case": case_record,
            "propositions": proposition_records
        }
    
    def process_all_cases(self, input_dir: str, output_file: str):
        """Process all tagged cases and create normalized output"""
        input_path = Path(input_dir)
        json_files = list(input_path.glob("*.json"))
        
        all_cases = []
        all_propositions = []
        
        print(f"Processing {len(json_files)} files...")
        
        for json_file in tqdm(json_files, desc="Normalizing"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    case_data = json.load(f)
                
                # Normalize statutes
                normalized_case = self.normalize_case_statutes(case_data)
                
                # Extract DB records
                records = self.extract_db_records(normalized_case)
                
                all_cases.append(records["case"])
                all_propositions.extend(records["propositions"])
            
            except Exception as e:
                print(f"\nError processing {json_file.name}: {e}")
                continue
        
        # Save normalized data
        output = {
            "cases": all_cases,
            "propositions": all_propositions,
            "metadata": {
                "total_cases": len(all_cases),
                "total_propositions": len(all_propositions),
                "version": "1.0"
            }
        }
        
        output_path = Path(output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Normalized data saved to: {output_path}")
        print(f"  - {len(all_cases)} cases")
        print(f"  - {len(all_propositions)} propositions")
        
        return output


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Normalize bail case data for database")
    parser.add_argument("--input-dir", default="tagged", help="Input directory with tagged JSON files")
    parser.add_argument("--output", default="normalized_bail_data.json", help="Output JSON file")
    
    args = parser.parse_args()
    
    normalizer = CaseDataNormalizer()
    normalizer.process_all_cases(args.input_dir, args.output)


if __name__ == "__main__":
    main()
