"""
Query Analyzer - Phase 3, Step 11
Analyzes input case and extracts statutes, stage, tags, and legal questions
"""

import json
import os
from typing import Dict, List, Any
import openai
from dotenv import load_dotenv
from statute_normalizer import StatuteNormalizer

load_dotenv()


class CaseAnalyzer:
    """Analyzes input case and structures it for retrieval"""
    
    def __init__(self, taxonomy_path: str = "taxonomy.json", model: str = "gpt-4o"):
        self.model = model
        openai.api_key = os.getenv("OPENAI_API_KEY")
        self.statute_normalizer = StatuteNormalizer()
        
        # Load taxonomy for reference
        with open(taxonomy_path, 'r', encoding='utf-8') as f:
            taxonomy_data = json.load(f)
        self.taxonomy = taxonomy_data["taxonomy"]
        self._build_taxonomy_text()
    
    def _build_taxonomy_text(self):
        """Build formatted taxonomy text for prompts"""
        lines = []
        for category, tags in self.taxonomy.items():
            lines.append(f"\n{category.upper()}:")
            for tag in tags:
                lines.append(f"  - {tag['tag']}: {tag['description']}")
        self.taxonomy_text = "\n".join(lines)
    
    def analyze_case(self, case_text: str, side: str = "both") -> Dict[str, Any]:
        """
        Analyze input case and extract structured information.

        Always generates BOTH sides' questions (needed for adverse-precedent
        reranking) plus side-specific tags and material facts so the reranker
        can use the correct factual framing per side.

        Args:
            case_text: Raw case facts and circumstances
            side: "prosecution", "defense", or "both" (kept for API compat)

        Returns:
            Dict with statutes, stage, shared tags, side-specific tags/facts,
            questions, and case_summary
        """

        prompt = f"""You are a legal AI analyzing a bail application under Indian law.
You must think from BOTH sides simultaneously and produce a balanced, adversarial analysis.

TAXONOMY OF BAIL LAW ISSUES:
{self.taxonomy_text}

INPUT CASE:
{case_text}

Produce the following in one JSON response:

1. statutes       – every applicable statute/section explicitly mentioned or implied
2. procedural_stage – pre_arrest | post_arrest | appeal
3. tags           – 4-8 NEUTRAL tags for database retrieval (cover both sides)
4. defense_tags   – 3-6 tags from the ACCUSED's perspective
                    (liberty, no custodial need, civil dispute criminalised, roots,
                     cooperation, prima facie weak case, right to liberty, etc.)
5. prosecution_tags – 3-6 tags from the STATE's perspective
                    (gravity of offence, economic offence, custodial interrogation
                     necessity, tampering risk, flight risk, investigation incomplete, etc.)
6. material_facts      – 5-8 neutral facts relevant to bail (used for DB retrieval)
7. defense_material_facts  – 4-6 facts that FAVOR the accused
                            (no antecedents, roots in community, documentary nature of
                             offence, repayment offer, cooperation, civil remedy adequate)
8. prosecution_material_facts – 4-6 facts that FAVOR the state
                            (large sum, forged documents, multiple victims, need to
                             trace proceeds, witnesses at risk, accused influential)
9. prosecution_questions – 2-3 precise legal questions the prosecution must answer
10. defense_questions    – 2-3 precise legal questions the defense must answer
11. case_summary – one neutral sentence describing the case

JSON schema (return ONLY valid JSON):
{{
  "statutes": [{{"act": "IPC", "section": "420"}}, {{"act": "CrPC", "section": "438"}}],
  "procedural_stage": "pre_arrest",
  "tags": ["anticipatory_bail", "commercial_vs_personal", "civil_dispute_criminalised"],
  "defense_tags": ["civil_dispute_criminalised", "right_to_liberty", "custodial_interrogation_necessity", "bail_not_jail"],
  "prosecution_tags": ["economic_offence", "custodial_interrogation_necessity", "tampering_risk", "investigation_incomplete"],
  "material_facts": [
    "Applicant accused of cheating and forgery in a property transaction",
    "FIR registered; applicant not yet arrested"
  ],
  "defense_material_facts": [
    "No criminal antecedents",
    "Offence is documentary in nature; no need for custodial interrogation",
    "Applicant has roots in community and is unlikely to abscond",
    "Dispute is essentially civil; criminal process is being misused"
  ],
  "prosecution_material_facts": [
    "Forged documents used to obtain property worth significant amount",
    "Custodial interrogation needed to trace money trail and co-conspirators",
    "Risk of evidence tampering if bail granted at pre-arrest stage"
  ],
  "prosecution_questions": [
    "Whether anticipatory bail should be refused when forgery involves large-scale economic fraud?",
    "Is custodial interrogation necessary to uncover the conspiracy and trace proceeds?"
  ],
  "defense_questions": [
    "Whether a civil property dispute criminalised through FIR justifies denial of anticipatory bail?",
    "Can liberty be curtailed solely on the gravity of accusation when the offence is documentary and no flight risk exists?"
  ],
  "case_summary": "Applicant seeks anticipatory bail in a property-transaction dispute involving allegations of cheating and forgery under IPC 420/406/465/468/471 and CrPC 438."
}}
"""

        try:
            response = openai.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a legal AI that outputs only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)

            # Normalize statutes
            normalized_statutes = []
            for statute_dict in result.get("statutes", []):
                normalized = self.statute_normalizer.normalize_statute_dict(statute_dict)
                normalized_statutes.extend(normalized)

            result["normalized_statutes"] = list(dict.fromkeys(normalized_statutes))  # ordered dedup

            # Ensure both sides' questions always present (used by adverse-precedent reranker)
            result.setdefault("defense_questions", [])
            result.setdefault("prosecution_questions", [])
            result.setdefault("defense_tags", result.get("tags", []))
            result.setdefault("prosecution_tags", result.get("tags", []))
            result.setdefault("defense_material_facts", result.get("material_facts", []))
            result.setdefault("prosecution_material_facts", result.get("material_facts", []))

            return result

        except Exception as e:
            print(f"Error analyzing case: {e}")
            return {
                "statutes": [],
                "normalized_statutes": [],
                "procedural_stage": "unknown",
                "tags": [],
                "defense_tags": [],
                "prosecution_tags": [],
                "material_facts": [],
                "defense_material_facts": [],
                "prosecution_material_facts": [],
                "prosecution_questions": [],
                "defense_questions": [],
                "case_summary": "Analysis failed",
                "error": str(e)
            }
    
    def analyze_from_file(self, file_path: str, side: str = "both") -> Dict[str, Any]:
        """Analyze case from text file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            case_text = f.read()
        
        return self.analyze_case(case_text, side)


def main():
    """Test the analyzer"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze bail case")
    parser.add_argument("--input", required=True, help="Input case text file or text")
    parser.add_argument("--side", default="both", choices=["prosecution", "defense", "both"])
    parser.add_argument("--output", help="Output JSON file")
    
    args = parser.parse_args()
    
    analyzer = CaseAnalyzer()
    
    # Check if input is a file
    if os.path.exists(args.input):
        result = analyzer.analyze_from_file(args.input, args.side)
    else:
        result = analyzer.analyze_case(args.input, args.side)
    
    # Print result
    print(json.dumps(result, indent=2))
    
    # Save if output specified
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        print(f"\n✓ Analysis saved to: {args.output}")


if __name__ == "__main__":
    main()
