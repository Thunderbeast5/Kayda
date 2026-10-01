"""
LLM-based Proposition Tagger for Bail Cases
Tags each proposition with 1-3 taxonomy tags, adds binding level, and extracts authorities
"""

import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
import openai
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

class PropositionTagger:
    """Tags propositions with taxonomy tags using LLM"""
    
    def __init__(self, taxonomy_path: str = "taxonomy.json", model: str = "gpt-4o-mini"):
        self.model = model
        openai.api_key = os.getenv("OPENAI_API_KEY")
        
        # Load taxonomy
        with open(taxonomy_path, 'r', encoding='utf-8') as f:
            taxonomy_data = json.load(f)
        
        self.taxonomy = taxonomy_data["taxonomy"]
        self.flat_tags = self._flatten_taxonomy()
    
    def _flatten_taxonomy(self) -> List[Dict[str, str]]:
        """Flatten nested taxonomy into list of tags"""
        flat = []
        for category, tags in self.taxonomy.items():
            for tag_info in tags:
                flat.append({
                    "tag": tag_info["tag"],
                    "category": category,
                    "description": tag_info["description"],
                    "keywords": tag_info.get("keywords", [])
                })
        return flat
    
    def _create_tagging_prompt(self, proposition: Dict[str, Any], case_context: Dict[str, Any]) -> str:
        """Create prompt for tagging a proposition"""
        
        # Format taxonomy for prompt
        taxonomy_text = "Available tags (select 1-3 most relevant):\n\n"
        for tag_info in self.flat_tags:
            taxonomy_text += f"- {tag_info['tag']}: {tag_info['description']}\n"
        
        prompt = f"""You are a legal AI analyzing Indian bail law precedents.

CASE CONTEXT:
Case: {case_context.get('case_name', 'Unknown')}
Court: {case_context.get('court', 'Unknown')}
Stage: {case_context.get('procedural_stage', 'Unknown')}
Facts: {case_context.get('abstract_facts', '')[:300]}...

PROPOSITION TO TAG:
Text: {proposition['text']}
Speaker: {proposition.get('speaker', 'unknown')}
Kind: {proposition.get('kind', 'unknown')}
Favors: {proposition.get('favors', 'unknown')}
Conditions: {proposition.get('conditions', [])}

{taxonomy_text}

Your task:
1. Select 1-3 most relevant tags from the taxonomy that capture the legal issue/principle in this proposition
2. Determine the binding level: "binding" (ratio decidendi from superior court), "persuasive" (obiter or lower court), or "reference" (cited but not followed)
3. Extract any case authorities mentioned in the proposition text

Respond in JSON format:
{{
  "tags": ["tag1", "tag2"],
  "binding_level": "binding|persuasive|reference",
  "reasoning": "Brief explanation of tag selection",
  "authorities": [
    {{
      "case_name": "Full case name",
      "citation": "Citation if available",
      "relationship": "followed|distinguished|overruled|referred"
    }}
  ]
}}

IMPORTANT:
- Choose tags that reflect the LEGAL PRINCIPLE, not just keywords
- If it's ratio decidendi from Supreme Court, it's "binding"
- If it's obiter dicta or High Court, it's "persuasive"
- Only include authorities if they are explicitly mentioned in the proposition text
- Return valid JSON only, no markdown or explanation outside JSON
"""
        return prompt
    
    def tag_proposition(self, proposition: Dict[str, Any], case_context: Dict[str, Any]) -> Dict[str, Any]:
        """Tag a single proposition"""
        prompt = self._create_tagging_prompt(proposition, case_context)
        
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
            
            # Validate tags are in taxonomy
            valid_tags = [tag for tag in result.get("tags", []) 
                         if any(t["tag"] == tag for t in self.flat_tags)]
            
            if not valid_tags:
                # Fallback to basic heuristics
                valid_tags = self._fallback_tagging(proposition, case_context)
            
            return {
                "tags": valid_tags[:3],  # Max 3 tags
                "binding_level": result.get("binding_level", "persuasive"),
                "reasoning": result.get("reasoning", ""),
                "authorities": result.get("authorities", [])
            }
        
        except Exception as e:
            print(f"Error tagging proposition: {e}")
            # Fallback
            return {
                "tags": self._fallback_tagging(proposition, case_context),
                "binding_level": "persuasive",
                "reasoning": "Fallback tagging due to API error",
                "authorities": []
            }
    
    def _fallback_tagging(self, proposition: Dict[str, Any], case_context: Dict[str, Any]) -> List[str]:
        """Fallback keyword-based tagging if LLM fails"""
        prop_text = proposition.get("text", "").lower()
        context_text = case_context.get("abstract_facts", "").lower()
        combined = prop_text + " " + context_text
        
        tags = []
        
        # Check each tag's keywords
        for tag_info in self.flat_tags:
            keywords = tag_info.get("keywords", [])
            if any(keyword.lower() in combined for keyword in keywords):
                tags.append(tag_info["tag"])
                if len(tags) >= 3:
                    break
        
        # Default tags if none matched
        if not tags:
            if "anticipatory" in combined:
                tags.append("anticipatory_vs_regular")
            elif "economic" in combined:
                tags.append("economic_offence_gravity")
            else:
                tags.append("bail_not_jail")
        
        return tags[:3]
    
    def tag_case(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """Tag all propositions in a case"""
        case_context = case_data.get("case", {})
        propositions = case_context.get("propositions", [])
        
        print(f"\nTagging {len(propositions)} propositions for case: {case_context.get('case_name', 'Unknown')}")
        
        tagged_propositions = []
        for prop in tqdm(propositions, desc="Tagging"):
            tagging_result = self.tag_proposition(prop, case_context)
            
            # Add tagging results to proposition
            enhanced_prop = prop.copy()
            enhanced_prop.update({
                "tags": tagging_result["tags"],
                "binding_level": tagging_result["binding_level"],
                "tag_reasoning": tagging_result["reasoning"],
                "authorities": tagging_result.get("authorities", [])
            })
            
            tagged_propositions.append(enhanced_prop)
        
        # Update case data
        enhanced_case = case_data.copy()
        enhanced_case["case"]["propositions"] = tagged_propositions
        
        return enhanced_case
    
    def tag_all_cases(self, input_dir: str, output_dir: str):
        """Tag all cases in a directory"""
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        json_files = list(input_path.glob("*.json"))
        json_files = [f for f in json_files if f.name not in ["chunks.jsonl", "taxonomy.json"]]
        
        print(f"Found {len(json_files)} case files to process")
        
        for json_file in json_files:
            print(f"\n{'='*60}")
            print(f"Processing: {json_file.name}")
            print(f"{'='*60}")
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    case_data = json.load(f)
                
                # Tag the case
                tagged_case = self.tag_case(case_data)
                
                # Save tagged case
                output_file = output_path / f"tagged_{json_file.name}"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(tagged_case, f, indent=2, ensure_ascii=False)
                
                print(f"✓ Saved tagged case to: {output_file}")
            
            except Exception as e:
                print(f"✗ Error processing {json_file.name}: {e}")
                continue
        
        print(f"\n{'='*60}")
        print(f"Tagging complete! Tagged cases saved to: {output_dir}")
        print(f"{'='*60}")


def main():
    """Main function to run tagging"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Tag bail case propositions with taxonomy")
    parser.add_argument("--input-dir", default="out", help="Input directory with case JSON files")
    parser.add_argument("--output-dir", default="tagged", help="Output directory for tagged cases")
    parser.add_argument("--taxonomy", default="taxonomy.json", help="Path to taxonomy JSON")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model to use")
    
    args = parser.parse_args()
    
    # Initialize tagger
    tagger = PropositionTagger(taxonomy_path=args.taxonomy, model=args.model)
    
    # Tag all cases
    tagger.tag_all_cases(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
