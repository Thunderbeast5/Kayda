"""
Precedent Retrieval Pipeline -- Batch-Screen Flow.

Orchestrates the complete precedent retrieval workflow:
1. Deterministic statute-IDF shortlist  (_shortlist_by_statutes, no LLM, <=20)
2. ONE batch LLM screen over the shortlist (BatchPrecedentScreen.screen)
3. ONE verifier LLM call + deterministic hallucination checks (inside screen)
4. Ranking and output construction via PrecedentRelevanceBatchEvaluator helpers

Total LLM calls per run = 2.
"""

from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from .precedent_retrieval import PrecedentRetriever, PrecedentCandidate, build_profile
from .precedent_batch_screen import BatchPrecedentScreen
from .precedent_relevance_agent import PrecedentRelevanceBatchEvaluator
from .precedent_selection import select_sections
from .schemas import (
    RoleSpecificPrecedentRetrievalObject,
    PrecedentRetrievalResult,
    PrecedentRetrievalIssue,
)
from lexigraphbe.schemas import CaseContextObject, StatutoryVerificationObject


def _shortlist_by_statutes(
    retriever: PrecedentRetriever,
    stage4_result: Dict,
    case_context: Optional[Dict],
    max_shortlist: int = 20,
) -> List[PrecedentCandidate]:
    """
    Statute-IDF deterministic shortlist.

    Builds a RetrievalProfile, scans every judgment, keeps only those that
    pass the subject-matter gate inside match_judgment, and returns the top
    max_shortlist by neutral retrieval_score.
    """
    profile = build_profile(retriever.matcher, stage4_result, case_context)
    if not profile.statutes:
        print("[PrecedentRetriever] No statutes found in Stage 4 result; shortlist empty.")
        return []

    print(
        f"[PrecedentRetriever] Profile: stage_mode={profile.stage_mode}, "
        f"input_stage={profile.input_stage}, "
        f"categories={sorted(profile.facets)}"
    )

    judgment_files = retriever.get_judgment_files()
    print(f"[PrecedentIndex] {len(judgment_files)} judgments indexed")

    candidates: List[PrecedentCandidate] = []
    seen_names: set = set()

    for jf in judgment_files:
        data = retriever.load_judgment(jf)
        if data is None:
            continue
        case_name = str((data.get("case") or {}).get("case_name") or "").strip().lower()
        if case_name and case_name in seen_names:
            continue
        cand = retriever.match_judgment(profile.statutes, data, profile)
        if cand:
            candidates.append(cand)
            if case_name:
                seen_names.add(case_name)

    candidates.sort(key=lambda c: c.retrieval_score, reverse=True)
    shortlist = candidates[:max_shortlist]

    generic_keys = [
        s["section"] for s in profile.statutes
        if s.get("kind") == "procedural"
    ]
    print(
        f"[PrecedentRetriever] Statute shortlist: {len(candidates)} judgments share a key, "
        f"{len(shortlist)} kept (generic keys: {generic_keys})"
    )
    return shortlist


class PrecedentPipeline:
    """
    Complete pipeline for Role-Specific Precedent Retrieval.

    Workflow:
    1. Statute-IDF shortlist (deterministic, no LLM, <=20 candidates)
    2. BatchPrecedentScreen.screen() -- ONE LLM call + ONE verifier call
    3. Build RoleSpecificPrecedentItem objects via PrecedentRelevanceBatchEvaluator helpers
    4. Rank + select + return RoleSpecificPrecedentRetrievalObject
    """

    def __init__(
        self,
        retriever: Optional[PrecedentRetriever] = None,
        screen: Optional[BatchPrecedentScreen] = None,
        max_candidates: int = 20,
        max_prosecution_precedents: int = 10,
        max_defense_precedents: int = 10,
        precedent_dir: Optional[Path] = None,
        tagged_dir: Optional[Path] = None,
    ):
        self.retriever = retriever or PrecedentRetriever(
            precedent_dir=precedent_dir or tagged_dir,
            max_candidates=max_candidates,
        )
        self.screen = screen or BatchPrecedentScreen()
        self._evaluator = PrecedentRelevanceBatchEvaluator()
        self.max_candidates = max_candidates
        self.max_prosecution_precedents = max_prosecution_precedents
        self.max_defense_precedents = max_defense_precedents

    def _extract_case_summary(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str],
    ) -> str:
        """Extract a plain-text case summary from any supported input type."""
        if isinstance(case_context, str):
            return case_context.strip() or "Case summary not available"

        if isinstance(case_context, dict):
            parts: List[str] = []
            # Stage 0 nests the narrative under case_profile.case_facts
            facts = case_context.get("case_facts") or (case_context.get("case_profile") or {}).get("case_facts") or {}
            if isinstance(facts, str) and facts.strip():
                parts.append(facts.strip())
            elif isinstance(facts, dict):
                if facts.get("factual_summary"):
                    parts.append(f"Facts: {facts['factual_summary']}")
                if isinstance(facts.get("allegations"), list):
                    parts.append(
                        "Allegations: " + "; ".join(str(a) for a in facts["allegations"][:4])
                    )
            profile = case_context.get("case_profile") or {}
            if isinstance(profile, dict):
                for k in ("case_type", "dispute_nature", "procedural_stage"):
                    if profile.get(k):
                        parts.append(f"{k.replace('_', ' ').title()}: {profile[k]}")
            for k in ("requested_relief", "relief"):
                if case_context.get(k):
                    parts.append(f"Requested Relief: {case_context[k]}")
            if parts:
                return "\n".join(parts)
            for k in ("facts", "summary", "text", "description"):
                if isinstance(case_context.get(k), str) and case_context[k].strip():
                    return case_context[k].strip()

        if hasattr(case_context, "case_facts"):
            cf = case_context.case_facts
            if hasattr(cf, "factual_summary") and cf.factual_summary:
                return cf.factual_summary
            if isinstance(cf, str) and cf.strip():
                return cf.strip()

        return str(case_context) if case_context else "Case summary not available"

    def _extract_input_statutes(
        self,
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str],
    ) -> List[Dict[str, str]]:
        """Extract ALL input statutes from Stage 4 output (IPC/BNS, BNSS/CrPC, BSA/IEA, Special Acts)."""
        if isinstance(statutory_object, str):
            return []

        if isinstance(statutory_object, dict):
            statutes: List[Dict[str, str]] = []
            for offence in statutory_object.get("verified_offences", []):
                sec = offence.get("section_number", "")
                if sec:
                    statutes.append({"act": offence.get("statute", "IPC"), "section": sec})
            for key in ("bnss_output", "bsa_output"):
                sub = statutory_object.get(key) or {}
                if isinstance(sub, dict):
                    for item in sub.get("verified_sections", []):
                        sec = item.get("section_number", "")
                        if sec:
                            statutes.append({
                                "act": item.get("statute", key.upper().split("_")[0]),
                                "section": sec,
                            })
            aro = statutory_object.get("act_router_output") or {}
            if isinstance(aro, dict):
                for rd in aro.get("routing_decisions", []):
                    if rd.get("routed", False):
                        act_name = rd.get("target_act", "")
                        for si in rd.get("retrieved_sections", []):
                            sec = si.get("section_number", "")
                            if sec and act_name:
                                statutes.append({"act": act_name, "section": sec})
            return statutes

        statutes = []
        if hasattr(statutory_object, "verified_offences"):
            for off in statutory_object.verified_offences:
                statutes.append({
                    "act": getattr(off, "statute", "IPC"),
                    "section": off.section_number,
                })
        return statutes

    def _to_dict(self, obj: Union[Dict, Any]) -> Dict[str, Any]:
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        return {}

    def _extract_stage4_summary(self, stage4_dict: Dict) -> str:
        return self._evaluator._extract_stage4_summary(stage4_dict)

    def run(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str],
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str],
        correction_feedback: Optional[str] = None,
        legal_issues: Optional[List[str]] = None,
    ) -> PrecedentRetrievalResult:
        """
        Run complete precedent retrieval pipeline.

        Args:
            case_context:        CaseContextObject (or dict / str) from Stage 0
            statutory_object:    StatutoryVerificationObject (or dict) from Stage 4
            correction_feedback: Optional feedback from a previous verification attempt
            legal_issues:        List of plain-text legal questions from Stage 1

        Returns:
            PrecedentRetrievalResult containing a verified RoleSpecificPrecedentRetrievalObject
        """
        print("\n" + "=" * 80)
        print("ROLE-SPECIFIC PRECEDENT RETRIEVAL PIPELINE (batch-screen flow)")
        print("=" * 80)

        statutory_dict = self._to_dict(statutory_object)
        case_context_dict = (
            self._to_dict(case_context) if not isinstance(case_context, str) else {}
        )
        if isinstance(case_context, str) and not case_context_dict:
            case_context_dict = {
                "case_facts": case_context,
                "requested_relief": (
                    "Anticipatory Bail" if "anticipatory" in case_context.lower() else "Bail"
                ),
            }
        elif isinstance(case_context_dict, dict) and "requested_relief" not in case_context_dict:
            if "anticipatory" in self._extract_case_summary(case_context).lower():
                case_context_dict["requested_relief"] = "Anticipatory Bail"

        input_case_summary = self._extract_case_summary(case_context)
        input_statutes = self._extract_input_statutes(statutory_object)
        stage4_summary = self._extract_stage4_summary(statutory_dict)
        legal_issues_list: List[str] = list(legal_issues or [])

        if not input_statutes:
            print("[PrecedentPipeline] WARNING: No statutes found in Stage 4 output -- skipping retrieval")
            return PrecedentRetrievalResult(
                status="VERIFIED",
                issues=[],
                feedback="No statutes found in Stage 4 output -- no precedent retrieval performed",
                verified_precedent_object=RoleSpecificPrecedentRetrievalObject(
                    input_case_summary=input_case_summary,
                    input_statutes=[],
                    total_judgments_scanned=0,
                    candidates_after_statutory_match=0,
                    prosecution_precedents=[],
                    defense_precedents=[],
                    shared_precedents=[],
                    verification_status="VERIFIED",
                ),
            )

        print(f"\n[PrecedentPipeline] Input statutes: {input_statutes}")
        print(f"[PrecedentPipeline] Legal issues: {len(legal_issues_list)} supplied")

        # Step 1 -- Deterministic statute-IDF shortlist (no LLM)
        print("\n" + "-" * 80)
        print("STEP 1: DETERMINISTIC STATUTE-IDF SHORTLIST")
        print("-" * 80)

        shortlist = _shortlist_by_statutes(
            self.retriever,
            statutory_dict,
            case_context_dict,
            max_shortlist=self.max_candidates,
        )
        total_scanned = len(self.retriever.get_judgment_files())

        if not shortlist:
            print("[PrecedentPipeline] No precedent candidates found after statutory shortlisting")
            return PrecedentRetrievalResult(
                status="VERIFIED",
                issues=[],
                feedback="No precedent candidates matched statutory criteria",
                verified_precedent_object=RoleSpecificPrecedentRetrievalObject(
                    input_case_summary=input_case_summary,
                    input_statutes=input_statutes,
                    total_judgments_scanned=total_scanned,
                    candidates_after_statutory_match=0,
                    prosecution_precedents=[],
                    defense_precedents=[],
                    compact_prosecution_summaries=[],
                    compact_defense_summaries=[],
                    shared_precedents=[],
                    verification_status="VERIFIED",
                ),
            )

        print(f"[PrecedentPipeline] Shortlist: {len(shortlist)} candidates")

        # Step 2 -- Batch screen (1 LLM call) + verifier (1 LLM call)
        print("\n" + "-" * 80)
        print("STEP 2: BATCH LLM SCREEN + VERIFIER (2 LLM calls total)")
        print("-" * 80)

        screen_result = self.screen.screen(
            candidates=shortlist,
            input_case=input_case_summary,
            legal_issues=legal_issues_list,
            stage4_summary=stage4_summary,
        )

        rpt = screen_result.get("report", {})
        kept = rpt.get("kept", 0)
        rejected_n = rpt.get("rejected", 0)
        penalised_n = len(rpt.get("penalised", []))
        llm_calls = rpt.get("llm_calls", 2)
        print(
            f"[PrecedentPipeline] Batch screen: {kept} kept, {rejected_n} rejected, "
            f"{penalised_n} penalised, LLM calls={llm_calls}"
        )

        prosecution_evals = screen_result.get("prosecution", [])
        defense_evals = screen_result.get("defense", [])
        rejected_list = screen_result.get("rejected", [])

        # Log rejection reasons so the caller can diagnose why candidates were dropped.
        if rejected_list:
            print(f"\n[PrecedentPipeline] Rejected candidates ({len(rejected_list)}):")
            for r in rejected_list:
                cid = r.get("case_id", "?")
                name = r.get("case_name", "?")
                reason = r.get("reason", "no reason")
                print(f"  [-] {name} ({cid}): {reason}")

        # Step 3 -- Build RoleSpecificPrecedentItem objects
        print("\n" + "-" * 80)
        print("STEP 3: BUILDING ROLE-SPECIFIC PRECEDENT LISTS")
        print("-" * 80)

        prosecution_items = self._evaluator.build_role_specific_precedent_items(
            prosecution_evals, role="prosecution"
        )[: self.max_prosecution_precedents]

        defense_items = self._evaluator.build_role_specific_precedent_items(
            defense_evals, role="defense"
        )[: self.max_defense_precedents]

        compact_prosecution = [
            item.compact_summary for item in prosecution_items if item.compact_summary
        ]
        compact_defense = [
            item.compact_summary for item in defense_items if item.compact_summary
        ]

        # Distinguish zero-result origin so the caller can diagnose the gap:
        #   "0 in corpus"       → no judgments in DB matched the statutes at all
        #   "0 shortlisted"     → statute match found candidates but screen kept 0
        #   "0 qualified by LLM"→ screen kept some but scorer/selector produced 0 items for this role
        shortlist_n = len(shortlist)
        for role_label, role_evals, role_items in (
            ("Prosecution", prosecution_evals, prosecution_items),
            ("Defense",     defense_evals,     defense_items),
        ):
            if len(role_items) == 0:
                if total_scanned == 0 or shortlist_n == 0:
                    print(
                        f"[PrecedentPipeline] {role_label} precedents: 0 "
                        f"(0 candidates in corpus for these statutes — {total_scanned} judgments indexed)"
                    )
                elif kept == 0:
                    print(
                        f"[PrecedentPipeline] {role_label} precedents: 0 "
                        f"(0 of {shortlist_n} shortlisted candidates passed the LLM screen)"
                    )
                elif len(role_evals) == 0:
                    print(
                        f"[PrecedentPipeline] {role_label} precedents: 0 "
                        f"({kept} kept by screen, but 0 qualified for {role_label.lower()} role "
                        f"— all stances were OPPOSING/DISTINGUISHABLE for this side)"
                    )
                else:
                    print(
                        f"[PrecedentPipeline] {role_label} precedents: 0 "
                        f"({len(role_evals)} evaluated but scored below threshold or all filtered out)"
                    )
            else:
                print(f"[PrecedentPipeline] {role_label} precedents: {len(role_items)}")

        pros_ids = {item.case_id for item in prosecution_items}
        def_ids = {item.case_id for item in defense_items}
        shared_precedents = list(pros_ids & def_ids)
        if shared_precedents:
            print(f"[PrecedentPipeline] Shared precedents: {shared_precedents}")

        # Step 4 -- Selection metadata
        pros_selection = select_sections(prosecution_items, principle_ids=[])
        def_selection = select_sections(defense_items, principle_ids=[])

        principle_ids = list(
            set(pros_selection["sections"].get("principle", []))
            | set(def_selection["sections"].get("principle", []))
        )
        background_ids = list(
            set(pros_selection.get("background_ids", []))
            | set(def_selection.get("background_ids", []))
        )

        screen_report_safe = {k: v for k, v in rpt.items() if k != "penalised"}

        # Step 5 -- Construct output object
        print("\n" + "-" * 80)
        print("STEP 4: CONSTRUCTING OUTPUT")
        print("-" * 80)

        precedent_object = RoleSpecificPrecedentRetrievalObject(
            input_case_summary=input_case_summary,
            input_statutes=input_statutes,
            total_judgments_scanned=total_scanned,
            candidates_after_statutory_match=len(shortlist),
            prosecution_precedents=prosecution_items,
            defense_precedents=defense_items,
            compact_prosecution_summaries=compact_prosecution,
            compact_defense_summaries=compact_defense,
            shared_precedents=shared_precedents,
            verification_status="VERIFIED",
            retrieval_metadata={
                "sections": {
                    "prosecution": pros_selection["sections"],
                    "defense": def_selection["sections"],
                },
                "screen_report": screen_report_safe,
                "screen_rejected": rejected_list,
                # Authority each side must meet or distinguish, and neutral doctrine, kept separate
                # from the sides' own lists so no judgment is presented as supporting both sides.
                "adverse": screen_result.get("adverse", {"prosecution": [], "defense": []}),
                "doctrine": screen_result.get("doctrine", []),
                "principle_ids": principle_ids,
                "background_ids": background_ids,
                "max_candidates": self.max_candidates,
                "max_prosecution_precedents": self.max_prosecution_precedents,
                "max_defense_precedents": self.max_defense_precedents,
                "correction_feedback": correction_feedback,
                "llm_calls": llm_calls,
            },
        )

        # Step 6 -- Validation
        issues: List[PrecedentRetrievalIssue] = []
        if not prosecution_items and not defense_items:
            issues.append(
                PrecedentRetrievalIssue(
                    target="overall",
                    issue="No relevant precedents found for either prosecution or defense",
                    feedback=(
                        "Consider expanding search criteria or reviewing statutory matching. "
                        "screen_rejected contains the full rejection list."
                    ),
                )
            )

        status = "VERIFIED" if not issues else "RETRY"
        feedback = (
            "Precedent retrieval completed successfully"
            if status == "VERIFIED"
            else f"Found {len(issues)} issues requiring review"
        )

        print(f"\n[PrecedentPipeline] Pipeline status: {status}")
        print(f"[PrecedentPipeline] Feedback: {feedback}")
        print("=" * 80 + "\n")

        return PrecedentRetrievalResult(
            status=status,
            issues=issues,
            feedback=feedback,
            verified_precedent_object=precedent_object,
        )


# Alias for backward compatibility
Stage5PrecedentPipeline = PrecedentPipeline