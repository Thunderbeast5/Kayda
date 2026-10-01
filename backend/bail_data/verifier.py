"""
LLM-Based Quote and Entailment Verifier
Optional component for runtime verification of retrieved precedents
"""

import json
import openai
import os
from typing import Dict, List, Any
from dotenv import load_dotenv

load_dotenv()


class PrecedentVerifier:
    """Verifies quotes and legal propositions using LLM"""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        openai.api_key = os.getenv("OPENAI_API_KEY")
    
    def verify_quote_entailment(
        self,
        proposition_text: str,
        quote: str,
        case_context: str = None
    ) -> Dict[str, Any]:
        """
        Verify that the quote actually supports the proposition
        
        Args:
            proposition_text: The legal principle stated
            quote: The quote from the judgment
            case_context: Optional case name and context
        
        Returns:
            Dict with entailment result and explanation
        """
        
        prompt = f"""You are a legal AI verifying precedent citations.

TASK: Determine if the quote actually supports the legal proposition stated.

PROPOSITION (Legal Principle):
{proposition_text}

QUOTE (From Judgment):
"{quote}"

{f'CASE CONTEXT: {case_context}' if case_context else ''}

Questions to answer:
1. Does the quote actually say what the proposition claims? (yes/no/partial)
2. Is the quote taken out of context? (yes/no)
3. Does the quote support the proposition when read fairly? (yes/no/partial)
4. Confidence level? (high/medium/low)

Respond in JSON format:
{{
  "entailment": "yes|no|partial",
  "out_of_context": false,
  "supports_proposition": true,
  "confidence": "high|medium|low",
  "explanation": "Brief explanation of the verification",
  "issues": "Any issues found, or null"
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
            result["verified"] = True
            return result
        
        except Exception as e:
            return {
                "verified": False,
                "error": str(e),
                "entailment": "unknown",
                "confidence": "low"
            }
    
    def check_if_overruled(
        self,
        case_name: str,
        decided_date: str,
        current_date: str = "2026-09-30"
    ) -> Dict[str, Any]:
        """
        Check if a case might have been overruled or questioned
        
        NOTE: This is a simplified check. Real implementation would need:
        - Database of overruled cases
        - CiteSeer/SCC Online integration
        - Legislative changes database
        """
        
        # Placeholder - would need real database of overruled cases
        prompt = f"""You are a legal AI checking precedent validity.

CASE: {case_name}
DECIDED: {decided_date}
CURRENT DATE: {current_date}

Based on your knowledge up to your training cutoff, is this case:
1. Still good law? (yes/no/unknown)
2. Known to be overruled? (yes/no/unknown)
3. Subject to legislative changes? (yes/no/unknown)
4. Any warnings or caveats?

Respond in JSON format:
{{
  "still_good_law": "yes|no|unknown",
  "overruled": "no|unknown",
  "legislative_changes": "no|unknown",
  "status": "active|questioned|overruled|unknown",
  "warnings": "Any warnings or null",
  "confidence": "high|medium|low",
  "note": "Explanation"
}}

IMPORTANT: Be conservative. If uncertain, mark as "unknown" and note that manual verification is needed.

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
            result["checked"] = True
            return result
        
        except Exception as e:
            return {
                "checked": False,
                "error": str(e),
                "status": "unknown",
                "confidence": "low"
            }
    
    def verify_precedent_batch(
        self,
        precedents: List[Dict[str, Any]],
        check_entailment: bool = True,
        check_overruled: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Verify a batch of precedents
        
        Args:
            precedents: List of precedent dicts
            check_entailment: Whether to check quote-proposition entailment
            check_overruled: Whether to check if overruled (slow)
        
        Returns:
            List of precedents with verification results added
        """
        
        verified_precedents = []
        
        for prec in precedents:
            prec_copy = prec.copy()
            
            # Check entailment
            if check_entailment:
                entailment_result = self.verify_quote_entailment(
                    proposition_text=prec.get("text", ""),
                    quote=prec.get("quote", ""),
                    case_context=prec.get("case_name", "")
                )
                prec_copy["entailment_check"] = entailment_result
                prec_copy["entailment_verified"] = entailment_result.get("supports_proposition", False)
            
            # Check if overruled (optional, slower)
            if check_overruled:
                overruled_result = self.check_if_overruled(
                    case_name=prec.get("case_name", ""),
                    decided_date=prec.get("decided_on", "")
                )
                prec_copy["overruled_check"] = overruled_result
                prec_copy["status"] = overruled_result.get("status", "unknown")
            
            verified_precedents.append(prec_copy)
        
        return verified_precedents
    
    def filter_verified_precedents(
        self,
        precedents: List[Dict[str, Any]],
        min_confidence: str = "medium"
    ) -> List[Dict[str, Any]]:
        """
        Filter precedents to keep only well-verified ones
        
        Args:
            precedents: List with verification results
            min_confidence: Minimum confidence level
        
        Returns:
            Filtered list
        """
        
        confidence_order = {"low": 0, "medium": 1, "high": 2}
        min_level = confidence_order.get(min_confidence, 1)
        
        filtered = []
        for prec in precedents:
            # Check entailment confidence if available
            entailment = prec.get("entailment_check", {})
            conf_level = confidence_order.get(entailment.get("confidence", "low"), 0)
            
            # Check if supports proposition
            supports = entailment.get("supports_proposition", True)
            
            # Check if overruled
            status = prec.get("status", "active")
            
            # Keep if passes all checks
            if conf_level >= min_level and supports and status != "overruled":
                filtered.append(prec)
        
        return filtered


def main():
    """Test the verifier"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Verify precedent quotes")
    parser.add_argument("--input", required=True, help="JSON file with precedents")
    parser.add_argument("--output", help="Output verified JSON")
    parser.add_argument("--check-overruled", action="store_true", help="Check if overruled (slow)")
    
    args = parser.parse_args()
    
    # Load precedents
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    precedents = data.get("precedents", [])
    
    print(f"Verifying {len(precedents)} precedents...")
    
    # Initialize verifier
    verifier = PrecedentVerifier()
    
    # Verify
    verified = verifier.verify_precedent_batch(
        precedents,
        check_entailment=True,
        check_overruled=args.check_overruled
    )
    
    # Filter
    filtered = verifier.filter_verified_precedents(verified, min_confidence="medium")
    
    print(f"After verification: {len(filtered)} precedents passed")
    
    # Show results
    for i, prec in enumerate(filtered, 1):
        print(f"\n[{i}] {prec['case_name']}")
        entailment = prec.get("entailment_check", {})
        print(f"  Entailment: {entailment.get('entailment')} ({entailment.get('confidence')})")
        print(f"  Explanation: {entailment.get('explanation')}")
        if args.check_overruled:
            status = prec.get("overruled_check", {})
            print(f"  Status: {status.get('status')} - {status.get('note')}")
    
    # Save if output specified
    if args.output:
        output_data = data.copy()
        output_data["precedents"] = filtered
        output_data["verification_metadata"] = {
            "total_input": len(precedents),
            "total_verified": len(verified),
            "total_passed": len(filtered),
            "entailment_checked": True,
            "overruled_checked": args.check_overruled
        }
        
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, default=str)
        
        print(f"\n✓ Verified precedents saved to: {args.output}")


if __name__ == "__main__":
    main()
