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
        Analyze input case and extract structured information
        
        Args:
            case_text: Raw case facts and circumstances
            side: "prosecution", "defense", or "both"
        
        Returns:
            Dict with statutes, stage, tags, questions, material_facts
        """
        
        prompt = f"""You are a legal AI analyzing a bail application case under Indian law.

TAXONOMY OF BAIL LAW ISSUES:
{self.taxonomy_text}

INPUT CASE:
{case_text}

Your task is to analyze this case and extract:

1. **Statutes**: All applicable statutes/sections (e.g., "IPC 420", "CrPC 438", "NDPS 20(b)")
2. **Procedural Stage**: pre_arrest, post_arrest, or appeal
3. **Tags**: 3-8 most relevant taxonomy tags that apply to this case
4. **Material Facts**: Key facts that matter for bail consideration (bullet points)
5. **Legal Questions**: For prosecution and defense

For PROSECUTION, formulate 2-3 questions like:
- "Is bail appropriate when accused has prior convictions for similar offences?"
- "Can anticipatory bail be granted in cases involving vulnerable victims?"

For DEFENSE, formulate 2-3 questions like:
- "Whether bail should be granted when investigation is complete and charge sheet filed?"
- "Can liberty be denied solely on gravity of accusation without considering individual circumstances?"

Respond in JSON format:
{{
  "statutes": [
    {{"act": "IPC", "section": "420"}},
    {{"act": "CrPC", "section": "438"}}
  ],
  "procedural_stage": "pre_arrest|post_arrest|appeal",
  "tags": ["tag1", "tag2", "tag3"],
  "material_facts": [
    "Fact 1",
    "Fact 2"
  ],
  "prosecution_questions": [
    "Question 1",
    "Question 2"
  ],
  "defense_questions": [
    "Question 1",
    "Question 2"
  ],
  "case_summary": "One-sentence summary of the case"
}}

Return valid JSON only.
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
            
            result["normalized_statutes"] = list(set(normalized_statutes))
            
            # Filter questions based on side
            if side == "prosecution":
                result.pop("defense_questions", None)
            elif side == "defense":
                result.pop("prosecution_questions", None)
            
            return result
        
        except Exception as e:
            print(f"Error analyzing case: {e}")
            # Return minimal fallback
            return {
                "statutes": [],
                "normalized_statutes": [],
                "procedural_stage": "unknown",
                "tags": [],
                "material_facts": [],
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
