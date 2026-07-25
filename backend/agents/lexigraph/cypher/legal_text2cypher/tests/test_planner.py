"""
Unit tests for the Query Planner.
"""

import pytest
from unittest.mock import patch, MagicMock

from backend.agents.lexigraph.cypher.legal_text2cypher.schemas.models import (
    ExpandedContext,
    ExtractedEntities,
    IntentResult,
    LegalIntent,
    LinkedEntities,
    LinkedNode,
    QueryPlan,
)
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.planner import create_query_plan, _deterministic_plan


class TestDeterministicPlan:
    """Tests for the deterministic (no-LLM) planner."""

    def _make_inputs(self, intent: LegalIntent, crimes=None, ipc_sections=None, bns_sections=None, node_ids=None):
        entities = ExtractedEntities(
            crimes=crimes or [],
            ipc_sections=ipc_sections or [],
            bns_sections=bns_sections or [],
        )
        nodes = [
            LinkedNode(node_id=nid, label="LawSection", name="test", score=1.0)
            for nid in (node_ids or [])
        ]
        linked = LinkedEntities(section_nodes=nodes)
        expanded = ExpandedContext(linked=linked)
        return entities, linked, expanded

    def test_punishment_plan(self):
        entities, linked, expanded = self._make_inputs(
            LegalIntent.PUNISHMENT, crimes=["murder"], node_ids=["IPC_302"]
        )
        plan = _deterministic_plan(LegalIntent.PUNISHMENT, entities, linked, expanded)
        assert plan is not None
        assert plan.intent == LegalIntent.PUNISHMENT
        assert plan.need_punishment is True
        assert plan.need_description is True

    def test_ipc_to_bns_plan(self):
        entities, linked, expanded = self._make_inputs(
            LegalIntent.IPC_TO_BNS, ipc_sections=["302"], node_ids=["IPC_302"]
        )
        plan = _deterministic_plan(LegalIntent.IPC_TO_BNS, entities, linked, expanded)
        assert plan is not None
        assert plan.need_replacement is True
        assert plan.target_act == "IPC"

    def test_section_lookup_plan(self):
        entities, linked, expanded = self._make_inputs(
            LegalIntent.SECTION_LOOKUP, ipc_sections=["302"], node_ids=["IPC_302"]
        )
        plan = _deterministic_plan(LegalIntent.SECTION_LOOKUP, entities, linked, expanded)
        assert plan is not None
        assert plan.need_punishment is True
        assert plan.need_keywords is True
        assert plan.need_chapter is True

    def test_multiple_crimes_plan(self):
        entities, linked, expanded = self._make_inputs(
            LegalIntent.MULTIPLE_CRIMES,
            crimes=["murder", "kidnapping"],
            node_ids=["IPC_302", "IPC_363"],
        )
        plan = _deterministic_plan(LegalIntent.MULTIPLE_CRIMES, entities, linked, expanded)
        assert plan is not None
        assert plan.multi_crime is True
        assert plan.need_related is True

    def test_comparison_plan(self):
        entities, linked, expanded = self._make_inputs(
            LegalIntent.COMPARISON,
            ipc_sections=["302"],
            bns_sections=["103"],
            node_ids=["IPC_302", "BNS_103"],
        )
        plan = _deterministic_plan(LegalIntent.COMPARISON, entities, linked, expanded)
        assert plan is not None
        assert len(plan.comparison_pairs) >= 1

    def test_graph_reasoning_returns_none(self):
        """Graph reasoning falls through to LLM planner."""
        entities, linked, expanded = self._make_inputs(
            LegalIntent.GRAPH_REASONING, node_ids=["IPC_302"]
        )
        plan = _deterministic_plan(LegalIntent.GRAPH_REASONING, entities, linked, expanded)
        assert plan is None


class TestCreateQueryPlan:
    """Tests for the full create_query_plan function."""

    @patch("legal_text2cypher.agents.planner.get_cached_planner_output", return_value=None)
    @patch("legal_text2cypher.agents.planner.cache_planner_output")
    def test_uses_deterministic_first(self, mock_cache, mock_get_cache):
        intent = IntentResult(intent=LegalIntent.PUNISHMENT, confidence=0.95)
        entities = ExtractedEntities(crimes=["murder"])
        linked = LinkedEntities(
            section_nodes=[LinkedNode(node_id="IPC_302", label="LawSection", name="Murder", score=1.0)]
        )
        expanded = ExpandedContext(linked=linked)

        plan = create_query_plan("punishment for murder", intent, entities, linked, expanded)
        assert plan.intent == LegalIntent.PUNISHMENT
        assert plan.need_punishment is True
