#!/usr/bin/env python3
"""
Add Ingredients to IPC Sections in Neo4j

This script:
1. Reads IPC sections from ipc_structured.json
2. Uses LLM to extract statutory ingredients from section text
3. Creates Crime nodes with ingredients
4. Links them to LawSection nodes via DEFINED_BY relationship

Usage:
    python add_ipc_ingredients.py [--limit N] [--start N]
    
Options:
    --limit N   Process only N sections (for testing)
    --start N   Start from section N (for resuming)
    --dry-run   Print what would be done without executing
"""

import json
import os
import sys
import re
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

# Load environment
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Import Neo4j service
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from services.neo4j_service import Neo4jService

# Import LLM
try:
    from agents.config.llm_config import get_llm
except:
    try:
        from config.llm_config import get_llm
    except:
        # Fallback: use langchain directly
        from langchain_ollama import ChatOllama
        def get_llm(temperature=0.0, **kwargs):
            return ChatOllama(model="llama3.2:3b", temperature=temperature)


class IPCIngredientAdder:
    """Adds ingredients to IPC sections in Neo4j."""
    
    def __init__(self, dry_run=False):
        self.neo4j = Neo4jService()
        self.llm = get_llm(temperature=0.0)
        self.dry_run = dry_run
        self.stats = {
            "processed": 0,
            "crimes_created": 0,
            "ingredients_added": 0,
            "skipped": 0,
            "errors": 0,
        }
    
    def load_ipc_sections(self, filepath: str) -> List[Dict[str, Any]]:
        """Load IPC sections from JSON file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Filter for IPC sections only
        ipc_sections = [s for s in data if isinstance(s, dict) and s.get("id", "").startswith("IPC_")]
        print(f"Loaded {len(ipc_sections)} IPC sections from {filepath}")
        return ipc_sections
    
    def extract_ingredients(self, section: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to extract statutory ingredients from section text."""
        
        section_id = section.get("id", "")
        section_num = section.get("section_number", "")
        title = section.get("title", "")
        text = section.get("text", "")
        
        if not text:
            return None
        
        prompt = f"""You are a legal expert extracting statutory ingredients from IPC sections.

SECTION: {section_id} - {title}

STATUTORY TEXT:
{text[:1500]}

Extract the essential elements (ingredients) that must be proven to establish this offence.

For each ingredient, identify:
1. Element name (brief, 2-5 words)
2. Element type: one of [ACTUS_REUS, MENS_REA, CIRCUMSTANCE, RESULT, SUBJECT, OBJECT]
3. Whether it is MANDATORY or SUPPORTING

Example for IPC 406 (Criminal Breach of Trust):
{{
  "crime_name": "Criminal Breach of Trust",
  "ingredients": [
    {{"name": "entrustment of property", "type": "ACTUS_REUS", "mandatory": true}},
    {{"name": "dishonest misappropriation", "type": "MENS_REA", "mandatory": true}},
    {{"name": "dishonest conversion to own use", "type": "ACTUS_REUS", "mandatory": true}},
    {{"name": "violation of legal direction", "type": "ACTUS_REUS", "mandatory": true}}
  ]
}}

Example for IPC 420 (Cheating):
{{
  "crime_name": "Cheating and Dishonestly Inducing Delivery of Property",
  "ingredients": [
    {{"name": "deception or fraudulent means", "type": "ACTUS_REUS", "mandatory": true}},
    {{"name": "dishonest intention", "type": "MENS_REA", "mandatory": true}},
    {{"name": "inducement to deliver property", "type": "ACTUS_REUS", "mandatory": true}},
    {{"name": "delivery of property", "type": "RESULT", "mandatory": true}}
  ]
}}

Return ONLY valid JSON. Extract 3-8 ingredients.

{{
  "crime_name": "...",
  "ingredients": [
    {{"name": "...", "type": "...", "mandatory": true/false}}
  ]
}}"""

        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Clean markdown
            content = re.sub(r"```(?:json)?", "", content, flags=re.IGNORECASE).replace("```", "").strip()
            
            # Extract JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if not json_match:
                print(f"  ⚠️  No JSON found in LLM response for {section_id}")
                return None
            
            result = json.loads(json_match.group(0))
            
            # Validate
            if not result.get("crime_name") or not result.get("ingredients"):
                print(f"  ⚠️  Invalid structure for {section_id}")
                return None
            
            if not isinstance(result["ingredients"], list) or len(result["ingredients"]) == 0:
                print(f"  ⚠️  No ingredients extracted for {section_id}")
                return None
            
            print(f"  ✓ Extracted {len(result['ingredients'])} ingredients for {section_id}")
            return result
            
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON parse error for {section_id}: {e}")
            return None
        except Exception as e:
            print(f"  ✗ Error extracting ingredients for {section_id}: {e}")
            return None
    
    def add_ingredients_to_neo4j(
        self,
        section_id: str,
        section_num: str,
        crime_data: Dict[str, Any]
    ) -> bool:
        """Add Crime node and ingredients to Neo4j."""
        
        crime_name = crime_data["crime_name"]
        ingredients = crime_data["ingredients"]
        
        if self.dry_run:
            print(f"  [DRY RUN] Would create Crime: {crime_name} with {len(ingredients)} ingredients")
            return True
        
        try:
            # Create Crime node and link to LawSection
            query = """
            MATCH (law:LawSection {act: 'IPC', section: $section_num})
            
            // Create or merge Crime node
            MERGE (crime:Crime {name: $crime_name, section: $section_id})
            ON CREATE SET
                crime.act = 'IPC',
                crime.section_number = $section_num,
                crime.ingredient_count = $ingredient_count,
                crime.created_by = 'ingredient_script'
            
            // Link Crime to LawSection
            MERGE (crime)-[:DEFINED_BY]->(law)
            
            // Create Ingredient nodes
            WITH crime
            UNWIND $ingredients AS ing
            MERGE (ingredient:Ingredient {
                name: ing.name,
                crime: $crime_name
            })
            ON CREATE SET
                ingredient.element_type = ing.type,
                ingredient.mandatory = ing.mandatory,
                ingredient.created_by = 'ingredient_script'
            
            // Link Ingredient to Crime
            MERGE (crime)-[:HAS_INGREDIENT]->(ingredient)
            
            RETURN crime.name AS crime_name, count(ingredient) AS ingredient_count
            """
            
            params = {
                "section_id": section_id,
                "section_num": section_num,
                "crime_name": crime_name,
                "ingredient_count": len(ingredients),
                "ingredients": ingredients,
            }
            
            # Execute with WRITE mode (need to override the READ mode in Neo4jService)
            driver = self.neo4j._get_driver()
            with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
                result = session.run(query, params)
                record = result.single()
                
                if record:
                    print(f"  ✓ Created Crime '{record['crime_name']}' with {record['ingredient_count']} ingredients")
                    self.stats["crimes_created"] += 1
                    self.stats["ingredients_added"] += record['ingredient_count']
                    return True
                else:
                    print(f"  ⚠️  No result returned for {section_id}")
                    return False
            
        except Exception as e:
            print(f"  ✗ Neo4j error for {section_id}: {e}")
            self.stats["errors"] += 1
            return False
    
    def process_section(self, section: Dict[str, Any]) -> bool:
        """Process a single IPC section."""
        
        section_id = section.get("id", "")
        section_num = section.get("section_number", "")
        title = section.get("title", "")
        
        print(f"\nProcessing {section_id}: {title}")
        
        # Check if already has ingredients
        if not self.dry_run:
            check_query = """
            MATCH (crime:Crime)-[:DEFINED_BY]->(law:LawSection {act: 'IPC', section: $section_num})
            RETURN count(crime) AS crime_count
            """
            try:
                rows = self.neo4j.run_query(check_query, {"section_num": section_num})
                if rows and rows[0].get("crime_count", 0) > 0:
                    print(f"  ⊘ Already has {rows[0]['crime_count']} Crime node(s), skipping")
                    self.stats["skipped"] += 1
                    return True
            except Exception as e:
                print(f"  ⚠️  Error checking existing ingredients: {e}")
        
        # Extract ingredients using LLM
        crime_data = self.extract_ingredients(section)
        
        if not crime_data:
            self.stats["errors"] += 1
            return False
        
        # Add to Neo4j
        success = self.add_ingredients_to_neo4j(section_id, section_num, crime_data)
        
        if success:
            self.stats["processed"] += 1
        
        return success
    
    def process_all(
        self,
        sections: List[Dict[str, Any]],
        limit: int = None,
        start: int = 0
    ):
        """Process all IPC sections."""
        
        total = len(sections)
        
        if start > 0:
            sections = sections[start:]
            print(f"\nStarting from section {start}")
        
        if limit:
            sections = sections[:limit]
            print(f"Processing {len(sections)} sections (limited)\n")
        else:
            print(f"Processing {len(sections)} sections\n")
        
        for i, section in enumerate(sections, start=start+1):
            print(f"[{i}/{total}]", end=" ")
            self.process_section(section)
        
        print("\n" + "="*60)
        print("STATISTICS")
        print("="*60)
        print(f"Total processed:     {self.stats['processed']}")
        print(f"Crimes created:      {self.stats['crimes_created']}")
        print(f"Ingredients added:   {self.stats['ingredients_added']}")
        print(f"Skipped (existing):  {self.stats['skipped']}")
        print(f"Errors:              {self.stats['errors']}")
        print("="*60)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Add ingredients to IPC sections in Neo4j")
    parser.add_argument("--limit", type=int, help="Process only N sections")
    parser.add_argument("--start", type=int, default=0, help="Start from section N")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument("--file", default="ipc_structured.json", help="Input JSON file")
    
    args = parser.parse_args()
    
    # Find input file
    filepath = Path(args.file)
    if not filepath.exists():
        filepath = Path(__file__).parent / args.file
    
    if not filepath.exists():
        print(f"Error: File not found: {args.file}")
        sys.exit(1)
    
    print("="*60)
    print("IPC INGREDIENT ADDER")
    print("="*60)
    print(f"Input file: {filepath}")
    print(f"Dry run: {args.dry_run}")
    if args.limit:
        print(f"Limit: {args.limit} sections")
    if args.start:
        print(f"Starting from: section {args.start}")
    print("="*60)
    
    # Initialize
    adder = IPCIngredientAdder(dry_run=args.dry_run)
    
    # Load sections
    sections = adder.load_ipc_sections(str(filepath))
    
    # Process
    adder.process_all(sections, limit=args.limit, start=args.start)


if __name__ == "__main__":
    main()
