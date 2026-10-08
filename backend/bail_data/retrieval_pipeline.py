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
        analyzer_model: str = "gpt-4o-mini",
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_favors(side: str) -> str:
        """
        Map pipeline side names to the 'favors' values actually stored in DB.
        DB uses 'accused' for defense propositions, 'prosecution' for state.
        """
        return {"defense": "accused", "prosecution": "prosecution"}.get(side, side)

    @staticmethod
    def _deduplicate_statute_aliases(statutes: List[str]) -> List[str]:
        """
        The normalizer expands IPC→BNS and CrPC→BNSS, producing both forms.
        Keep all of them so the DB OR-clause can hit both old and new code records,
        but deduplicate to avoid double-scoring.
        """
        return list(dict.fromkeys(statutes))  # preserves order, deduplicates
    
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
        Search database for candidate propositions.

        Strategy:
        1. Translate side name to DB favors value ('defense'→'accused').
        2. Deduplicate statute list (IPC + BNS aliases) so OR-match covers both.
        3. First pass: with stage filter.
        4. If zero results, retry WITHOUT stage filter (stage may be NULL in DB
           or stored under a different label for older records).
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

        # Normalise inputs
        db_favors = self._normalize_favors(favors) if favors else None
        clean_statutes = self._deduplicate_statute_aliases(statutes)

        print(f"    [DB] favors filter : {repr(db_favors)}  (raw side='{favors}')")
        print(f"    [DB] stage filter  : {repr(stage)}")
        print(f"    [DB] statutes ({len(clean_statutes)}): {clean_statutes[:6]}{'...' if len(clean_statutes)>6 else ''}")
        print(f"    [DB] tags ({len(tags)}): {tags[:5]}{'...' if len(tags)>5 else ''}")

        def _run_query(s, t, stg, fav, yr, lim) -> List[Dict]:
            try:
                self.cursor.execute(query, (s, t, stg, fav, yr, lim))
                rows = self.cursor.fetchall()
                return [
                    {
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
                        "db_relevance_score": float(row[11]),
                    }
                    for row in rows
                ]
            except Exception as e:
                print(f"Error searching database: {e}")
                # Roll back aborted transaction so subsequent queries work
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                return []

        # Pass 1: with stage filter
        candidates = _run_query(clean_statutes, tags, stage, db_favors, min_year, limit)
        print(f"    [DB] Pass 1 (stage={repr(stage)}): {len(candidates)} rows")

        # Pass 2: drop stage filter if nothing came back
        if not candidates and stage is not None:
            print(f"    [DB] Pass 2: retrying without stage filter...")
            candidates = _run_query(clean_statutes, tags, None, db_favors, min_year, limit)
            print(f"    [DB] Pass 2 (no stage): {len(candidates)} rows")

        # Pass 3: drop favors filter too (get everything and let LLM reranker filter)
        if not candidates and db_favors is not None:
            print(f"    [DB] Pass 3: retrying without favors filter (LLM will rerank)...")
            candidates = _run_query(clean_statutes, tags, None, None, min_year, limit)
            print(f"    [DB] Pass 3 (no favors/stage): {len(candidates)} rows")

        return candidates
    
    def _rerank_candidates(
        self,
        candidates: List[Dict],
        analysis: Dict[str, Any],
        side: str,
        is_adverse: bool = False,
    ) -> List[Dict]:
        """
        Rerank candidates using LLM with two-dimensional scoring.

        factual_specificity (60%) - does the case match the SPECIFIC FACTS?
        legal_relevance     (40%) - does the legal PRINCIPLE help this side?

        Score computed in Python (not from LLM) for consistent 60/40 arithmetic.
        When is_adverse=True the LLM also returns a 'distinguish' field showing
        how the *current* side (not `side`) would counter this adverse case.
        """
        if not candidates:
            return []

        questions_key = f"{side}_questions"
        questions = analysis.get(questions_key, [])

        # Bug 2 fix: use side-appropriate factual framing, not shared generic tags
        side_facts = analysis.get(f"{side}_material_facts") or analysis.get("material_facts", [])
        side_tags  = analysis.get(f"{side}_tags") or analysis.get("tags", [])
        factual_dims = "\n".join(f"  - {f}" for f in side_facts[:8])
        if side_tags:
            factual_dims += "\n  Tags: " + ", ".join(side_tags)

        # Format candidates
        candidates_text = ""
        for i, cand in enumerate(candidates[:30], 1):
            candidates_text += f"\n[{i}] {cand['case_name']} ({cand['decided_on']})\n"
            candidates_text += f"Court: {cand['court']} | Binding: {cand['binding_level']}\n"
            candidates_text += f"Tags: {', '.join((cand.get('tags') or [])[:4])}\n"
            candidates_text += f"Principle: {cand['text'][:350]}\n"
            candidates_text += f"Quote: {(cand.get('quote') or '')[:200]}\n"

        # Adverse-specific additions
        if is_adverse:
            current_side = "prosecution" if side == "defense" else "defense"
            distinguish_field = (
                f'- distinguish : one sentence - how the {current_side.upper()} would\n'
                f'  counter/distinguish this case (different facts, offence type,\n'
                f'  limiting observations, different outcome, etc.)'
            )
            distinguish_example = ',\n      "distinguish": "[Write a fresh counter-argument specific to this case]"'
        else:
            distinguish_field = ""
            distinguish_example = ""

        prompt = f"""You are a senior legal AI reranking bail-law precedents for the {side.upper()} side.

QUERY CASE - SPECIFIC FACTUAL DIMENSIONS:
{factual_dims}

Case summary   : {analysis.get('case_summary', '')}
Procedural stage: {analysis.get('procedural_stage', '')}
Key statutes   : {', '.join(analysis.get('normalized_statutes', [])[:6])}

LEGAL QUESTIONS FOR {side.upper()}:
{chr(10).join(f'{i+1}. {q}' for i, q in enumerate(questions))}

CANDIDATE PRECEDENTS:
{candidates_text}

For each candidate [1-{min(30, len(candidates))}] score TWO dimensions:

1. factual_specificity (0-10)
   HIGH (8-10) : Directly addresses the SPECIFIC FACTS above - commercial/property
                 dispute criminalised, forgery/cheating, custodial interrogation
                 contested, documentary evidence, no antecedents, civil remedy adequate.
   MED  (4-7)  : Overlaps partially (custodial interrogation discussed but different
                 offence, similar stage but different facts).
   LOW  (1-3)  : Generic anticipatory-bail principle (Section 438 procedure, bail
                 conditions fairness, abstract liberty). No factual overlap.
   ZERO (0)    : Irrelevant or contradictory.

2. legal_relevance (0-10)
   How directly does the LEGAL PRINCIPLE answer the {side}'s questions above?

Also provide:
{distinguish_field}
- applicability : "yes" / "partial" / "no"
- usage         : "apply directly" / "analogize" / "distinguish" / "ignore"
- reason        : one sentence - factual fit of THIS specific case
  (IMPORTANT: write a fresh, case-specific sentence; do NOT copy example text)

Return ONLY valid JSON:
{{
  "rankings": [
    {{
      "candidate_id": 1,
      "factual_specificity": 7.0,
      "legal_relevance": 6.0,
      "applicability": "partial",
      "usage": "analogize",
      "reason": "[Write a fresh, specific sentence about THIS case here]"{distinguish_example}
    }}
  ]
}}
"""

        try:
            response = openai.chat.completions.create(
                model=self.reranker_model,
                messages=[
                    {"role": "system", "content": "You are a legal AI that outputs only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )

            reranking = json.loads(response.choices[0].message.content)
            rankings = reranking.get("rankings", [])

            reranked = []
            for rank_data in rankings:
                cand_id = rank_data.get("candidate_id", 0)
                if 1 <= cand_id <= len(candidates):
                    cand = candidates[cand_id - 1].copy()

                    # Bug fix: compute score in Python, never trust LLM arithmetic
                    f_score  = float(rank_data.get("factual_specificity", 0))
                    l_score  = float(rank_data.get("legal_relevance", 0))
                    computed = round(0.6 * f_score + 0.4 * l_score, 1)

                    cand["llm_relevance_score"] = computed
                    cand["factual_specificity"]  = f_score
                    cand["legal_relevance"]      = l_score
                    cand["applicability"]        = rank_data.get("applicability", "unknown")
                    cand["usage"]               = rank_data.get("usage", "unknown")
                    cand["reasoning"]           = rank_data.get("reason", "")
                    cand["distinguish"]         = rank_data.get("distinguish", "")

                    # Raised floor to 5.5 to cut generic filler (was 3.0)
                    if cand["usage"] != "ignore" and computed >= 5.5:
                        reranked.append(cand)

            reranked.sort(key=lambda x: x["llm_relevance_score"], reverse=True)
            return reranked

        except Exception as e:
            print(f"Error reranking candidates: {e}")
            return candidates  # fallback to DB ordering
    
    def _verify_quotes(self, candidates: List[Dict]) -> List[Dict]:
        """
        All candidates already passed quote_verified=TRUE in the DB query.
        An LLM entailment check could be layered here for the top-5 if needed.
        """
        return candidates

    def _deduplicate_by_case(self, candidates: List[Dict]) -> List[Dict]:
        """
        Multiple DB rows often come from the same judgment (one row per proposition).
        Merge them into a single result per case_id so the final ranking never
        lists the same case twice.

        Merging rules:
        - case-level score  = max llm_relevance_score among all propositions
        - factual / legal   = from the highest-scoring proposition
        - usage / reasoning = from the highest-scoring proposition
        - principles        = list of unique (text, quote, score) tuples, sorted
                              by relevance descending, so format_output can show
                              all supporting principles under one case heading
        """
        from collections import defaultdict

        groups: Dict[str, List[Dict]] = defaultdict(list)
        for cand in candidates:
            groups[cand["case_id"]].append(cand)

        merged = []
        for case_id, props in groups.items():
            # Sort propositions within the case by score, best first
            props.sort(key=lambda x: x.get("llm_relevance_score", 0), reverse=True)
            best = props[0].copy()  # inherit all metadata from top proposition

            # Collect unique principles (deduplicate by text)
            seen_texts: set = set()
            principles = []
            for p in props:
                txt = (p.get("text") or "").strip()
                if txt and txt not in seen_texts:
                    seen_texts.add(txt)
                    principles.append({
                        "text":              txt,
                        "quote":             (p.get("quote") or "").strip(),
                        "relevance_score":   p.get("llm_relevance_score", 0),
                        "factual_specificity": p.get("factual_specificity", 0),
                        "usage":             p.get("usage", ""),
                        "reasoning":         p.get("reasoning", ""),
                    })

            best["principles"]      = principles
            best["principle_count"] = len(principles)
            merged.append(best)

        merged.sort(key=lambda x: x.get("llm_relevance_score", 0), reverse=True)
        return merged
    
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
            favors=side,          # _normalize_favors() maps 'defense'→'accused'
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
        
        # Step 3: Rerank with LLM (factual_specificity + legal_relevance scoring)
        print(f"\nStep 3: Reranking candidates with LLM (2-dimensional scoring)...")
        reranked = self._rerank_candidates(candidates, analysis, side)
        print(f"  ✓ Reranked to {len(reranked)} relevant precedents")

        # Step 4: Verify quotes (already done in DB)
        print(f"\nStep 4: Verifying quotes...")
        # Fetch extra before dedup so top_k survive after case merging
        verified = self._verify_quotes(reranked[:top_k * 5])
        print(f"  ✓ {len(verified)} precedents verified")

        # Step 4b: Deduplicate by case — merge multiple propositions from the
        # same judgment into one grouped result with a 'principles' list
        print(f"\nStep 4b: Deduplicating by case...")
        deduplicated = self._deduplicate_by_case(verified)
        print(f"  ✓ {len(deduplicated)} unique cases (from {len(verified)} propositions)")

        # Step 5: Get top K unique cases
        top_precedents = deduplicated[:top_k]
        
        # Step 6: Get adverse precedent if requested
        adverse_precedent = None
        if include_adverse:
            print(f"\nStep 6: Finding strongest adverse precedent...")
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
                    adverse_candidates, analysis, adverse_side,
                    is_adverse=True  # triggers 'distinguish' field in output
                )
                if adverse_reranked:
                    # Deduplicate adverse results too; pick the best unique case
                    adverse_deduped = self._deduplicate_by_case(adverse_reranked)
                    adverse_precedent = adverse_deduped[0]
                    print(f"  ✓ Found adverse precedent: {adverse_precedent['case_name']}")

        print(f"\n{'='*60}")
        print(f"RETRIEVAL COMPLETE")
        print(f"{'='*60}\n")

        return {
            "analysis": analysis,
            "precedents": top_precedents,
            "adverse_precedent": adverse_precedent,
            "total_candidates": len(candidates),
            "total_reranked": len(reranked),
            "total_unique_cases": len(deduplicated),
        }
    
    def format_output(self, result: Dict[str, Any]) -> str:
        """Format retrieval result as readable text.

        - Each case appears exactly once (deduplication already done).
        - When a case has multiple propositions, each shows its own
          principle text + quote + reasoning so they always match (Bug 3 fix).
        - Adverse section uses the 'distinguish' field from the is_adverse
          reranker call, not the side-level reasoning (Bug 1 fix).
        """
        output = []

        analysis   = result["analysis"]
        precedents = result["precedents"]
        adverse    = result.get("adverse_precedent")

        output.append("=" * 80)
        output.append("BAIL PRECEDENT RETRIEVAL RESULTS")
        output.append("=" * 80)

        output.append("\nCASE ANALYSIS:")
        output.append(f"Summary : {analysis.get('case_summary', '')}")
        output.append(f"Stage   : {analysis.get('procedural_stage', '')}")
        output.append(f"Statutes: {', '.join(analysis.get('normalized_statutes', []))}")
        output.append(f"Tags    : {', '.join(analysis.get('tags', []))}")

        n_cases = result.get("total_unique_cases", len(precedents))
        output.append("\n" + "=" * 80)
        output.append(
            f"TOP {len(precedents)} RELEVANT PRECEDENTS  "
            f"(from {result.get('total_candidates', '?')} candidates -> "
            f"{result.get('total_reranked', '?')} reranked -> "
            f"{n_cases} unique cases)"
        )
        output.append("=" * 80)

        for i, prec in enumerate(precedents, 1):
            score   = prec.get("llm_relevance_score", 0)
            f_score = prec.get("factual_specificity", 0)
            l_score = prec.get("legal_relevance", 0)
            n_prin  = prec.get("principle_count", 1)

            output.append(f"\n[{i}] {prec['case_name']}")
            output.append(
                f"    Citation  : {prec['case_id']} | "
                f"{prec['court']} | {prec['decided_on']}"
            )
            output.append(
                f"    Score     : {score:.1f}/10  "
                f"(factual={f_score:.1f}, legal={l_score:.1f}) | "
                f"Binding: {prec['binding_level']}"
            )
            output.append(
                f"    Usage     : {prec.get('usage', '')} | "
                f"Applicability: {prec.get('applicability', '')}"
            )

            # Bug 3 fix: reasoning shown per-principle (text and rationale always match)
            principles = prec.get("principles") or [
                {
                    "text":              prec.get("text", ""),
                    "quote":            prec.get("quote", ""),
                    "relevance_score":  score,
                    "factual_specificity": f_score,
                    "reasoning":        prec.get("reasoning", ""),
                }
            ]

            if len(principles) == 1:
                p = principles[0]
                output.append(f"\n    Principle:")
                output.append(f"      {p['text']}")
                if p.get("quote"):
                    output.append(f"    Quote:")
                    output.append(f'      "{p["quote"]}"')
                if p.get("reasoning"):
                    output.append(f"    Why       : {p['reasoning']}")
            else:
                output.append(f"\n    Supporting Principles ({n_prin}):")
                for j, p in enumerate(principles, 1):
                    p_score  = p.get("relevance_score", 0)
                    p_fscore = p.get("factual_specificity", 0)
                    output.append("")
                    output.append(
                        f"    [{i}.{j}] ({p_score:.1f}/10 | factual={p_fscore:.1f})  "
                        f"{p['text']}"
                    )
                    if p.get("quote"):
                        output.append(f'           Quote  : "{p["quote"][:250]}"')
                    if p.get("reasoning"):
                        output.append(f"           Why    : {p['reasoning']}")

            output.append("")

        # --- Adverse precedent ---
        if adverse:
            output.append("\n" + "=" * 80)
            output.append("STRONGEST ADVERSE PRECEDENT (Other Side Will Cite)")
            output.append("=" * 80)
            output.append(f"\n{adverse['case_name']}")
            output.append(
                f"Citation  : {adverse['case_id']} | "
                f"{adverse['court']} | {adverse['decided_on']}"
            )
            output.append(f"Score     : {adverse.get('llm_relevance_score', 0):.1f}/10")

            adv_principles = adverse.get("principles") or [
                {"text": adverse.get("text", ""), "quote": adverse.get("quote", ""),
                 "distinguish": adverse.get("distinguish", "")}
            ]
            if len(adv_principles) == 1:
                output.append(f"\nPrinciple : {adv_principles[0]['text']}")
                if adv_principles[0].get("quote"):
                    output.append(f'Quote     : "{adv_principles[0]["quote"]}"')
            else:
                output.append(f"\nAdverse Principles ({len(adv_principles)}):")
                for j, p in enumerate(adv_principles, 1):
                    output.append(f"  [{j}] {p['text']}")
                    if p.get("quote"):
                        output.append(f'       Quote: "{p["quote"][:250]}"')

            # Bug 1 fix: use 'distinguish' from is_adverse reranker, not leaked reasoning
            distinguish_text = (
                adverse.get("distinguish")
                or next(
                    (p.get("distinguish") for p in adv_principles if p.get("distinguish")),
                    None
                )
                or adverse.get("reasoning", "")
            )
            output.append(f"\nHow to Distinguish:")
            output.append(f"  {distinguish_text}")

        output.append("\n" + "=" * 80)
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
