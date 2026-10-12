"""
pipeline_debug_service.py

Comprehensive debug logging service to track GraphRAG pipeline flow.
Logs decisions at each stage: retrieval → verification → filtering → ranking → prompt → output.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class PipelineStage:
    """Represents a single stage in the pipeline with inputs, outputs, and decisions."""
    stage_name: str
    timestamp: str
    input_count: int
    output_count: int
    discarded_count: int
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseDecision:
    """Tracks why a case was included or excluded."""
    case_name: str
    citation: str
    court: str
    decision: str  # "included" | "excluded"
    stage: str
    reason: str
    scores: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SectionDecision:
    """Tracks why a section was included or excluded."""
    section: str
    act: str
    title: str
    decision: str  # "included" | "excluded" | "rejected"
    stage: str
    reason: str
    scores: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineDebugService:
    """
    Tracks and logs decisions throughout the GraphRAG pipeline.
    Provides comprehensive visibility into case and section filtering at each stage.
    """

    def __init__(self):
        self.stages: List[PipelineStage] = []
        self.case_decisions: List[CaseDecision] = []
        self.section_decisions: List[SectionDecision] = []
        self.query_info: Dict[str, Any] = {}
        self.enabled = False

    def enable(self):
        """Enable debug tracking."""
        self.enabled = True

    def disable(self):
        """Disable debug tracking."""
        self.enabled = False

    def reset(self):
        """Reset all tracking data."""
        self.stages = []
        self.case_decisions = []
        self.section_decisions = []
        self.query_info = {}

    def log_query(self, original_query: str, expanded_queries: List[str], intent: str, keywords: List[str]):
        """Log the initial query and expansion."""
        if not self.enabled:
            return

        self.query_info = {
            "original_query": original_query,
            "expanded_queries": expanded_queries,
            "primary_intent": intent,
            "keywords": keywords,
            "timestamp": datetime.now().isoformat()
        }

    def log_stage(self, stage_name: str, input_count: int, output_count: int, 
                  metadata: Optional[Dict[str, Any]] = None):
        """Log a pipeline stage with input/output counts."""
        if not self.enabled:
            return

        stage = PipelineStage(
            stage_name=stage_name,
            timestamp=datetime.now().isoformat(),
            input_count=input_count,
            output_count=output_count,
            discarded_count=input_count - output_count,
            metadata=metadata or {}
        )
        self.stages.append(stage)

    def log_case_decision(self, case_name: str, citation: str, court: str, 
                          decision: str, stage: str, reason: str,
                          scores: Optional[Dict[str, float]] = None,
                          metadata: Optional[Dict[str, Any]] = None):
        """Log a decision about including/excluding a case."""
        if not self.enabled:
            return

        case_decision = CaseDecision(
            case_name=case_name,
            citation=citation,
            court=court,
            decision=decision,
            stage=stage,
            reason=reason,
            scores=scores or {},
            metadata=metadata or {}
        )
        self.case_decisions.append(case_decision)

    def log_section_decision(self, section: str, act: str, title: str,
                            decision: str, stage: str, reason: str,
                            scores: Optional[Dict[str, float]] = None,
                            metadata: Optional[Dict[str, Any]] = None):
        """Log a decision about including/excluding a section."""
        if not self.enabled:
            return

        section_decision = SectionDecision(
            section=section,
            act=act,
            title=title,
            decision=decision,
            stage=stage,
            reason=reason,
            scores=scores or {},
            metadata=metadata or {}
        )
        self.section_decisions.append(section_decision)

    def get_case_journey(self, case_name: str) -> List[CaseDecision]:
        """Get all decisions for a specific case across stages."""
        return [cd for cd in self.case_decisions if cd.case_name == case_name]

    def get_section_journey(self, section: str) -> List[SectionDecision]:
        """Get all decisions for a specific section across stages."""
        return [sd for sd in self.section_decisions if sd.section == section]

    def get_discarded_cases(self) -> List[CaseDecision]:
        """Get all cases that were excluded."""
        return [cd for cd in self.case_decisions if cd.decision == "excluded"]

    def get_discarded_sections(self) -> List[SectionDecision]:
        """Get all sections that were excluded or rejected."""
        return [sd for sd in self.section_decisions if sd.decision in ["excluded", "rejected"]]

    def print_summary(self):
        """Print a comprehensive summary of pipeline decisions."""
        if not self.enabled:
            print("[PipelineDebug] Debug mode is disabled.")
            return

        print("\n" + "=" * 100)
        print("PIPELINE DEBUG SUMMARY")
        print("=" * 100)

        # Query Information
        print("\n[QUERY INFORMATION]")
        print(f"Original Query: {self.query_info.get('original_query', 'N/A')}")
        print(f"Primary Intent: {self.query_info.get('primary_intent', 'N/A')}")
        print(f"Keywords: {', '.join(self.query_info.get('keywords', []))}")
        print(f"Expanded Queries: {len(self.query_info.get('expanded_queries', []))}")

        # Stage-by-stage flow
        print("\n[PIPELINE FLOW]")
        for stage in self.stages:
            print(f"\n{stage.stage_name}:")
            print(f"  Input Count    : {stage.input_count}")
            print(f"  Output Count   : {stage.output_count}")
            print(f"  Discarded      : {stage.discarded_count}")
            if stage.metadata:
                for key, value in stage.metadata.items():
                    print(f"  {key}: {value}")

        # Section decisions
        print("\n[SECTION DECISIONS]")
        included_sections = [sd for sd in self.section_decisions if sd.decision == "included"]
        rejected_sections = [sd for sd in self.section_decisions if sd.decision == "rejected"]
        excluded_sections = [sd for sd in self.section_decisions if sd.decision == "excluded"]

        print(f"\nIncluded Sections: {len(included_sections)}")
        for sd in included_sections:
            print(f"  ✓ {sd.act} {sd.section}: {sd.title}")
            print(f"    Stage: {sd.stage} | Reason: {sd.reason}")
            if sd.scores:
                print(f"    Scores: {json.dumps(sd.scores, indent=6)}")

        print(f"\nRejected Sections: {len(rejected_sections)}")
        for sd in rejected_sections:
            print(f"  ✗ {sd.act} {sd.section}: {sd.title}")
            print(f"    Stage: {sd.stage} | Reason: {sd.reason}")

        print(f"\nExcluded Sections: {len(excluded_sections)}")
        for sd in excluded_sections:
            print(f"  ⊗ {sd.act} {sd.section}: {sd.title}")
            print(f"    Stage: {sd.stage} | Reason: {sd.reason}")

        # Case decisions
        print("\n[CASE DECISIONS]")
        included_cases = [cd for cd in self.case_decisions if cd.decision == "included"]
        excluded_cases = [cd for cd in self.case_decisions if cd.decision == "excluded"]

        print(f"\nIncluded Cases: {len(included_cases)}")
        for cd in included_cases:
            print(f"  ✓ {cd.case_name} | {cd.citation} ({cd.court})")
            print(f"    Stage: {cd.stage} | Reason: {cd.reason}")
            if cd.scores:
                print(f"    Scores: {json.dumps(cd.scores, indent=6)}")

        print(f"\nExcluded Cases: {len(excluded_cases)}")
        for cd in excluded_cases:
            print(f"  ✗ {cd.case_name} | {cd.citation} ({cd.court})")
            print(f"    Stage: {cd.stage} | Reason: {cd.reason}")

        # Summary statistics
        print("\n[SUMMARY STATISTICS]")
        print(f"Total Stages            : {len(self.stages)}")
        print(f"Total Case Decisions    : {len(self.case_decisions)}")
        print(f"Total Section Decisions : {len(self.section_decisions)}")
        print(f"Cases Included          : {len(included_cases)}")
        print(f"Cases Excluded          : {len(excluded_cases)}")
        print(f"Sections Included       : {len(included_sections)}")
        print(f"Sections Rejected       : {len(rejected_sections)}")
        print(f"Sections Excluded       : {len(excluded_sections)}")

        print("\n" + "=" * 100 + "\n")

    def export_json(self) -> Dict[str, Any]:
        """Export all debug data as JSON."""
        return {
            "query_info": self.query_info,
            "stages": [
                {
                    "stage_name": s.stage_name,
                    "timestamp": s.timestamp,
                    "input_count": s.input_count,
                    "output_count": s.output_count,
                    "discarded_count": s.discarded_count,
                    "metadata": s.metadata
                }
                for s in self.stages
            ],
            "section_decisions": [
                {
                    "section": sd.section,
                    "act": sd.act,
                    "title": sd.title,
                    "decision": sd.decision,
                    "stage": sd.stage,
                    "reason": sd.reason,
                    "scores": sd.scores,
                    "metadata": sd.metadata
                }
                for sd in self.section_decisions
            ],
            "case_decisions": [
                {
                    "case_name": cd.case_name,
                    "citation": cd.citation,
                    "court": cd.court,
                    "decision": cd.decision,
                    "stage": cd.stage,
                    "reason": cd.reason,
                    "scores": cd.scores,
                    "metadata": cd.metadata
                }
                for cd in self.case_decisions
            ]
        }
