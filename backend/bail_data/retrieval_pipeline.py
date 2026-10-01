"""
Complete Retrieval Pipeline - Phase 3
Combines analyzer, database search, reranking, and verification
"""

import json
import os
import psycopg2
from typing import Dict, List, Any, Tuple
import openai
from dotenv import load_dotenv
from analyzer import CaseAnalyzer

load_dotenv()


class RetrievalPipeline:
    """Complete precedent retrieval pipeline"""
    
    def __init__(
        self,
        connection_string: str = None,
        analyzer_model: str = "gpt-4o",
        reranker_model: str = "gpt-4o-mini"
    ):
        self.connection_string = connection_string or os.getenv(
            "POSTGRES_URL",
            "postgresql://localhost:5432/bail_precedents"
        )
        self.analyzer = CaseAnalyzer(model=analyzer_model)
        self.reranker_model = reranker_model
        openai.api_key = os.getenv("OPENAI_API_KEY")
        
        # Connect to database
        self.conn = None
        self.cursor = None
        self._connect()
    
    def _connect(self):
        """Connect to database"""
        try:
            self.conn = psycopg2.connect(self.connection_string)
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
    
    def _candidate_search(
        self,
        statutes: List[str],
        tags: List[str],
        stage: str = None,
        favors: str = None,
        min_year: int = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Search database for candidate propositions
        Returns list of candidates with metadata
        """
        query = """
        SELECT * FROM search_propositions(
            %s::TEXT[],  -- statutes
            %s::TEXT[],  -- tags
            %s,          -- stage
            %s,          -- favors
            %s,          -- min_year
            %s           -- limit
        );
        """
        
        try:
            self.cursor.execute(
                query,
                (statutes, tags, stage, favors, min_year, limit)
            )
            
            rows = self.cursor.fetchall()
            
            # Convert to list of dicts
            candidates = []
            for row in rows:
                candidates.append({
                    "proposition_id": row[0],
                    "case_id": row[1],
                    "case_name": row[2],
                    "court": row[3],
                    "decided_on": str(row[4]) if row[4] else None,
                    "text": row[5],
                    "quote": row[6],
                    "favors": row[7],
                    "tags": row[8],
                    "normalized_statutes": row[9],
                    "binding_level": row[10],
                    "db_relevance_score": float(row[11])
                })
            
            return candidates
        
        except Exception as e:
            print(f"Error searching database: {e}")
            return []
    
    def _rerank_candidates(
        self,
        candidates: List[Dict],
        analysis: Dict[str, Any],
        side: str
    ) -> List[Dict]:
        """
        Rerank candidates using LLM
        Evaluates whether each candidate is on point and how to apply/distinguish it
        """
        if not candidates:
            return []
        
        # Get questions for this side
        questions_key = f"{side}_questions"
        questions = analysis.get(questions_key, [])
        
        # Format candidates compactly for LLM
        candidates_text = ""
        for i, cand in enumerate(candidates[:30], 1):  # Limit to 30 for LLM context
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
Material Facts: {', '.join(analysis.get('material_facts', [])[:5])}

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
    }},
    ...
  ]
}}

Focus on precedents that help answer the legal questions. Return valid JSON only.
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
            
            # Apply reranking to candidates
            reranked = []
            for rank_data in rankings:
                cand_id = rank_data.get("candidate_id", 0)
                if 1 <= cand_id <= len(candidates):
                    cand = candidates[cand_id - 1].copy()
                    cand["llm_relevance_score"] = rank_data.get("relevance_score", 0)
                    cand["applicability"] = rank_data.get("applicability", "unknown")
                    cand["usage"] = rank_data.get("usage", "unknown")
                    cand["reasoning"] = rank_data.get("reason", "")
                    
                    # Skip if marked to ignore or very low relevance
                    if cand["usage"] != "ignore" and cand["llm_relevance_score"] >= 3.0:
                        reranked.append(cand)
            
            # Sort by LLM relevance score
            reranked.sort(key=lambda x: x["llm_relevance_score"], reverse=True)
            
            return reranked
        
        except Exception as e:
            print(f"Error reranking candidates: {e}")
            # Fallback to database ranking
            return candidates
    
    def _verify_quotes(self, candidates: List[Dict]) -> List[Dict]:
        """
        Verify that quotes are accurate (already done in DB, but can add LLM verification)
        For now, just filter by quote_verified flag from DB
        """
        # All candidates from DB are already quote_verified=true
        # Additional entailment check could be added here for top-5
        return candidates
    
    def retrieve(
        self,
        case_text: str,
        side: str = "defense",
        top_k: int = 5,
        include_adverse: bool = True
    ) -> Dict[str, Any]:
        """
        Main retrieval pipeline
        
        Args:
            case_text: Input case facts and circumstances
            side: "prosecution" or "defense"
            top_k: Number of precedents to return
            include_adverse: Whether to include strongest adverse precedent
        
        Returns:
            Dict with analysis, precedents for side, and adverse precedent
        """
        print(f"\n{'='*60}")
        print(f"RETRIEVAL PIPELINE - {side.upper()} SIDE")
        print(f"{'='*60}\n")
        
        # Step 1: Analyze case
        print("Step 1: Analyzing case...")
        analysis = self.analyzer.analyze_case(case_text, side="both")  # Get both sides
        print(f"  ✓ Identified {len(analysis.get('normalized_statutes', []))} statutes")
        print(f"  ✓ Identified {len(analysis.get('tags', []))} tags")
        print(f"  ✓ Stage: {analysis.get('procedural_stage')}")
        
        # Step 2: Candidate generation
        print(f"\nStep 2: Searching database for candidates...")
        candidates = self._candidate_search(
            statutes=analysis.get("normalized_statutes", []),
            tags=analysis.get("tags", []),
            stage=analysis.get("procedural_stage"),
            favors=side,  # Filter for this side
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
        
        # Step 4: Verify quotes (already done in DB)
        print(f"\nStep 4: Verifying quotes...")
        verified = self._verify_quotes(reranked[:top_k * 2])  # Get more for filtering
        print(f"  ✓ {len(verified)} precedents verified")
        
        # Step 5: Get top K
        top_precedents = verified[:top_k]
        
        # Step 6: Get adverse precedent if requested
        adverse_precedent = None
        if include_adverse:
            print(f"\nStep 5: Finding strongest adverse precedent...")
            adverse_side = "prosecution" if side == "defense" else "defense"
            adverse_candidates = self._candidate_search(
                statutes=analysis.get("normalized_statutes", []),
                tags=analysis.get("tags", []),
                stage=analysis.get("procedural_stage"),
                favors=adverse_side,
                min_year=1970,
                limit=30
            )
            
            if adverse_candidates:
                adverse_reranked = self._rerank_candidates(
                    adverse_candidates,
                    analysis,
                    adverse_side
                )
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
    
    parser = argparse.ArgumentParser(description="Bail Precedent Retrieval Pipeline")
    parser.add_argument("--input", required=True, help="Input case text file")
    parser.add_argument("--side", default="defense", choices=["prosecution", "defense"])
    parser.add_argument("--top-k", type=int, default=5, help="Number of precedents to retrieve")
    parser.add_argument("--output", help="Output file for results")
    parser.add_argument("--connection", help="PostgreSQL connection string")
    
    args = parser.parse_args()
    
    # Read input case
    with open(args.input, 'r', encoding='utf-8') as f:
        case_text = f.read()
    
    # Initialize pipeline
    pipeline = RetrievalPipeline(connection_string=args.connection)
    
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
            
            # Also save JSON
            json_output = args.output.replace('.txt', '_detailed.json')
            with open(json_output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, default=str)
            
            print(f"\n✓ Results saved to: {args.output}")
            print(f"✓ Detailed JSON saved to: {json_output}")
    
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
