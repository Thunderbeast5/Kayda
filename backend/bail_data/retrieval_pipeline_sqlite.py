"""
SQLite-Based Retrieval Pipeline
Complete precedent retrieval using SQLite (no PostgreSQL required)
"""

import json
import sqlite3
from typing import Dict, List, Any
import openai
import os
from dotenv import load_dotenv
from analyzer import CaseAnalyzer
from verifier import PrecedentVerifier

load_dotenv()


class RetrievalPipelineSQLite:
    """Complete precedent retrieval pipeline using SQLite"""
    
    def __init__(
        self,
        db_path: str = "bail_precedents.db",
        analyzer_model: str = "gpt-4o",
        reranker_model: str = "gpt-4o-mini",
        enable_verification: bool = False
    ):
        self.db_path = db_path
        self.analyzer = CaseAnalyzer(model=analyzer_model)
        self.reranker_model = reranker_model
        self.enable_verification = enable_verification
        self.verifier = PrecedentVerifier() if enable_verification else None
        openai.api_key = os.getenv("OPENAI_API_KEY")
        
        # Connect to database
        self.conn = None
        self.cursor = None
        self._connect()
    
    def _connect(self):
        """Connect to database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Access columns by name
            self.cursor = self.conn.cursor()
        except Exception as e:
            print(f"Error connecting to database: {e}")
            raise
    
    def close(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
    
    def _has_overlap(self, list1_json: str, list2: List[str]) -> int:
        """Check overlap between JSON array and list"""
        try:
            list1 = json.loads(list1_json) if list1_json else []
            return len(set(list1) & set(list2))
        except:
            return 0
    
    def _candidate_search(
        self,
        statutes: List[str],
        tags: List[str],
        stage: str = None,
        favors: str = None,
        min_year: int = None,
        limit: int = 50
    ) -> List[Dict]:
        """Search database for candidate propositions"""
        
        query = """
            SELECT 
                p.proposition_id,
                p.case_id,
                c.case_name,
                c.court,
                c.decided_on,
                p.text,
                p.quote,
                p.favors,
                p.tags,
                p.normalized_statutes,
                p.binding_level,
                p.is_holding,
                c.procedural_stage
            FROM bail_propositions p
            JOIN bail_cases c ON p.case_id = c.case_id
            WHERE p.quote_verified = 1
        """
        
        params = []
        
        if stage:
            # Flexible stage matching
            stage_map = {
                "pre_arrest": ["pre_arrest", "anticipatory"],
                "post_arrest": ["post_arrest", "post_arrest_bail", "regular_bail"],
                "appeal": ["appeal", "revision"]
            }
            stage_variants = stage_map.get(stage, [stage])
            stage_placeholders = ",".join("?" * len(stage_variants))
            query += f" AND c.procedural_stage IN ({stage_placeholders})"
            params.extend(stage_variants)
        
        if favors:
            query += " AND p.favors = ?"
            params.append(favors)
        
        if min_year:
            query += " AND CAST(substr(c.decided_on, 1, 4) AS INTEGER) >= ?"
            params.append(min_year)
        
        query += " LIMIT ?"
        params.append(limit * 3)  # Get more to filter
        
        try:
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            
            # Score candidates
            candidates = []
            for row in rows:
                statute_overlap = self._has_overlap(row['normalized_statutes'], statutes)
                tag_overlap = self._has_overlap(row['tags'], tags)
                
                # Skip if no overlap
                if statute_overlap == 0 and tag_overlap == 0:
                    continue
                
                score = (
                    statute_overlap * 10 +
                    tag_overlap * 5 +
                    (3 if row['binding_level'] == 'binding' else 0) +
                    (2 if row['is_holding'] else 0) +
                    (2 if row['court'] == 'Supreme Court of India' else 0)
                )
                
                candidates.append({
                    "proposition_id": row['proposition_id'],
                    "case_id": row['case_id'],
                    "case_name": row['case_name'],
                    "court": row['court'],
                    "decided_on": row['decided_on'],
                    "text": row['text'],
                    "quote": row['quote'],
                    "favors": row['favors'],
                    "tags": json.loads(row['tags']) if row['tags'] else [],
                    "normalized_statutes": json.loads(row['normalized_statutes']) if row['normalized_statutes'] else [],
                    "binding_level": row['binding_level'],
                    "db_relevance_score": score
                })
            
            # Sort by score and limit
            candidates.sort(key=lambda x: x['db_relevance_score'], reverse=True)
            return candidates[:limit]
        
        except Exception as e:
            print(f"Error searching database: {e}")
            return []
    
    def _rerank_candidates(
        self,
        candidates: List[Dict],
        analysis: Dict[str, Any],
        side: str
    ) -> List[Dict]:
        """Rerank candidates using LLM"""
        if not candidates:
            return []
        
        # Get questions for this side
        questions_key = f"{side}_questions"
        questions = analysis.get(questions_key, [])
        
        # Format candidates compactly
        candidates_text = ""
        for i, cand in enumerate(candidates[:30], 1):
            candidates_text += f"\n[{i}] {cand['case_name']} ({cand['decided_on']})\n"
            candidates_text += f"Court: {cand['court']}\n"
            candidates_text += f"Favors: {cand['favors']} | Tags: {', '.join(cand['tags'][:3])}\n"
            candidates_text += f"Text: {cand['text'][:300]}...\n"
            candidates_text += f"Quote: {cand['quote'][:200]}...\n"
        
        prompt = f"""You are a legal AI reranking precedents for a {side} in a bail case.

QUERY CASE ANALYSIS:
Summary: {analysis.get('case_summary', '')}
Stage: {analysis.get('procedural_stage', '')}
Statutes: {', '.join(analysis.get('normalized_statutes', [])[:5])}
Tags: {', '.join(analysis.get('tags', []))}

LEGAL QUESTIONS FOR {side.upper()}:
{chr(10).join(f'{i+1}. {q}' for i, q in enumerate(questions))}

CANDIDATE PRECEDENTS:
{candidates_text}

Your task: For each candidate [1-{min(30, len(candidates))}], evaluate:
1. **Relevance**: Is it on point for the {side}'s arguments? (0-10 score)
2. **Applicability**: Do its conditions/facts match this case? (yes/no/partial)
3. **Usage**: How should {side} use it? (apply directly / analogize / distinguish / ignore)
4. **Reason**: One sentence explaining the reasoning

Respond in JSON format:
{{
  "rankings": [
    {{
      "candidate_id": 1,
      "relevance_score": 8.5,
      "applicability": "yes",
      "usage": "apply directly",
      "reason": "Direct precedent on same issue"
    }}
  ]
}}

Return valid JSON only.
"""
        
        try:
            response = openai.chat.completions.create(
                model=self.reranker_model,
                messages=[
                    {"role": "system", "content": "You are a legal AI that outputs only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            reranking = json.loads(response.choices[0].message.content)
            rankings = reranking.get("rankings", [])
            
            # Apply reranking
            reranked = []
            for rank_data in rankings:
                cand_id = rank_data.get("candidate_id", 0)
                if 1 <= cand_id <= len(candidates):
                    cand = candidates[cand_id - 1].copy()
                    cand["llm_relevance_score"] = rank_data.get("relevance_score", 0)
                    cand["applicability"] = rank_data.get("applicability", "unknown")
                    cand["usage"] = rank_data.get("usage", "unknown")
                    cand["reasoning"] = rank_data.get("reason", "")
                    
                    if cand["usage"] != "ignore" and cand["llm_relevance_score"] >= 3.0:
                        reranked.append(cand)
            
            reranked.sort(key=lambda x: x["llm_relevance_score"], reverse=True)
            return reranked
        
        except Exception as e:
            print(f"Error reranking candidates: {e}")
            return candidates
    
    def retrieve(
        self,
        case_text: str,
        side: str = "defense",
        top_k: int = 5,
        include_adverse: bool = True
    ) -> Dict[str, Any]:
        """Main retrieval pipeline"""
        
        print(f"\n{'='*60}")
        print(f"RETRIEVAL PIPELINE - {side.upper()} SIDE")
        print(f"{'='*60}\n")
        
        # Step 1: Analyze case
        print("Step 1: Analyzing case...")
        analysis = self.analyzer.analyze_case(case_text, side="both")
        print(f"  ✓ Identified {len(analysis.get('normalized_statutes', []))} statutes")
        print(f"  ✓ Identified {len(analysis.get('tags', []))} tags")
        print(f"  ✓ Stage: {analysis.get('procedural_stage')}")
        
        # Step 2: Candidate generation
        print(f"\nStep 2: Searching database for candidates...")
        # Map side to favors value in database (accused/prosecution)
        favors_map = {"defense": "accused", "prosecution": "prosecution"}
        candidates = self._candidate_search(
            statutes=analysis.get("normalized_statutes", []),
            tags=analysis.get("tags", []),
            stage=analysis.get("procedural_stage"),
            favors=favors_map.get(side, side),
            min_year=1970,
            limit=50
        )
        print(f"  ✓ Found {len(candidates)} candidates")
        
        if not candidates:
            return {
                "analysis": analysis,
                "precedents": [],
                "adverse_precedent": None,
                "message": "No relevant precedents found"
            }
        
        # Step 3: Rerank with LLM
        print(f"\nStep 3: Reranking candidates with LLM...")
        reranked = self._rerank_candidates(candidates, analysis, side)
        print(f"  ✓ Reranked to {len(reranked)} relevant precedents")
        
        # Step 4: Get top K
        top_precedents = reranked[:top_k]
        
        # Step 4.5: Optional LLM verification
        if self.enable_verification and top_precedents:
            print(f"\nStep 4.5: Verifying quotes with LLM...")
            top_precedents = self.verifier.verify_precedent_batch(
                top_precedents,
                check_entailment=True,
                check_overruled=False  # Set to True if needed (slower)
            )
            # Filter out any that fail verification
            verified_count = len(top_precedents)
            top_precedents = self.verifier.filter_verified_precedents(
                top_precedents,
                min_confidence="medium"
            )
            print(f"  ✓ {len(top_precedents)}/{verified_count} passed LLM verification")
        
        # Step 5: Get adverse precedent
        adverse_precedent = None
        if include_adverse:
            print(f"\nStep 4: Finding strongest adverse precedent...")
            adverse_side = "prosecution" if side == "defense" else "defense"
            adverse_favors = favors_map.get(adverse_side, adverse_side)
            adverse_candidates = self._candidate_search(
                statutes=analysis.get("normalized_statutes", []),
                tags=analysis.get("tags", []),
                stage=analysis.get("procedural_stage"),
                favors=adverse_favors,
                min_year=1970,
                limit=30
            )
            
            if adverse_candidates:
                adverse_reranked = self._rerank_candidates(adverse_candidates, analysis, adverse_side)
                if adverse_reranked:
                    adverse_precedent = adverse_reranked[0]
                    print(f"  ✓ Found adverse precedent: {adverse_precedent['case_name']}")
        
        print(f"\n{'='*60}")
        print(f"RETRIEVAL COMPLETE")
        print(f"{'='*60}\n")
        
        return {
            "analysis": analysis,
            "precedents": top_precedents,
            "adverse_precedent": adverse_precedent,
            "total_candidates": len(candidates),
            "total_reranked": len(reranked)
        }
    
    def format_output(self, result: Dict[str, Any]) -> str:
        """Format retrieval result as readable text"""
        output = []
        
        analysis = result["analysis"]
        precedents = result["precedents"]
        adverse = result.get("adverse_precedent")
        
        output.append("="*80)
        output.append("BAIL PRECEDENT RETRIEVAL RESULTS")
        output.append("="*80)
        
        output.append("\nCASE ANALYSIS:")
        output.append(f"Summary: {analysis.get('case_summary', '')}")
        output.append(f"Stage: {analysis.get('procedural_stage', '')}")
        output.append(f"Statutes: {', '.join(analysis.get('normalized_statutes', []))}")
        output.append(f"Tags: {', '.join(analysis.get('tags', []))}")
        
        output.append("\n" + "="*80)
        output.append(f"TOP {len(precedents)} RELEVANT PRECEDENTS")
        output.append("="*80)
        
        for i, prec in enumerate(precedents, 1):
            output.append(f"\n[{i}] {prec['case_name']}")
            output.append(f"Citation: {prec['case_id']} | {prec['court']} | {prec['decided_on']}")
            output.append(f"Relevance: {prec.get('llm_relevance_score', 0):.1f}/10 | Binding: {prec['binding_level']}")
            output.append(f"Usage: {prec.get('usage', '')} | Applicability: {prec.get('applicability', '')}")
            output.append(f"\nPrinciple:")
            output.append(f"  {prec['text']}")
            output.append(f"\nQuote:")
            output.append(f'  "{prec["quote"]}"')
            output.append(f"\nReasoning:")
            output.append(f"  {prec.get('reasoning', '')}")
            output.append("")
        
        if adverse:
            output.append("\n" + "="*80)
            output.append("STRONGEST ADVERSE PRECEDENT (Other Side Will Cite)")
            output.append("="*80)
            output.append(f"\n{adverse['case_name']}")
            output.append(f"Citation: {adverse['case_id']} | {adverse['court']} | {adverse['decided_on']}")
            output.append(f"\nPrinciple:")
            output.append(f"  {adverse['text']}")
            output.append(f"\nHow to Distinguish:")
            output.append(f"  {adverse.get('reasoning', '')}")
        
        output.append("\n" + "="*80)
        
        return "\n".join(output)


def main():
    """CLI for retrieval pipeline"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Bail Precedent Retrieval Pipeline (SQLite)")
    parser.add_argument("--input", required=True, help="Input case text file")
    parser.add_argument("--side", default="defense", choices=["prosecution", "defense"])
    parser.add_argument("--top-k", type=int, default=5, help="Number of precedents to retrieve")
    parser.add_argument("--output", help="Output file for results")
    parser.add_argument("--db", default="bail_precedents.db", help="SQLite database file")
    parser.add_argument("--verify", action="store_true", help="Enable LLM verification (slower, +$0.10)")
    
    args = parser.parse_args()
    
    # Read input case
    with open(args.input, 'r', encoding='utf-8') as f:
        case_text = f.read()
    
    # Initialize pipeline
    pipeline = RetrievalPipelineSQLite(db_path=args.db, enable_verification=args.verify)
    
    try:
        # Run retrieval
        result = pipeline.retrieve(
            case_text=case_text,
            side=args.side,
            top_k=args.top_k,
            include_adverse=True
        )
        
        # Format output
        formatted = pipeline.format_output(result)
        print(formatted)
        
        # Save if requested
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(formatted)
            
            json_output = args.output.replace('.txt', '_detailed.json')
            with open(json_output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, default=str)
            
            print(f"\n✓ Results saved to: {args.output}")
            print(f"✓ Detailed JSON saved to: {json_output}")
    
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
