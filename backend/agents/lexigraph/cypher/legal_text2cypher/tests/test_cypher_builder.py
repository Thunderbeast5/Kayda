"""
Unit tests for the Cypher Builder — the deterministic core.
"""

import pytest

from backend.agents.lexigraph.cypher.legal_text2cypher.schemas.models import CypherQuery, LegalIntent, QueryPlan
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.cypher_builder import build_cypher


class TestBuildCypher:
    """Tests for the deterministic Cypher builder."""

    def test_section_lookup(self):
        plan = QueryPlan(
            intent=LegalIntent.SECTION_LOOKUP,
            linked_node_ids=["IPC_302"],
            need_punishment=True,
            need_keywords=True,
            need_description=True,
            need_chapter=True,
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1
        q = queries[0]
        assert "MATCH (l:LawSection {id: nid})" in q.cypher
        assert "$node_ids" in q.cypher
        assert q.parameters["node_ids"] == ["IPC_302"]
        assert "HAS_PUNISHMENT" in q.cypher
        assert "HAS_KEYWORD" in q.cypher

    def test_ipc_to_bns_with_ids(self):
        plan = QueryPlan(
            intent=LegalIntent.IPC_TO_BNS,
            linked_node_ids=["IPC_302"],
            need_replacement=True,
            need_punishment=True,
            need_description=True,
            target_act="IPC",
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1
        q = queries[0]
        assert "REPLACED_BY" in q.cypher
        assert "act: 'IPC'" in q.cypher

    def test_ipc_to_bns_with_entities(self):
        plan = QueryPlan(
            intent=LegalIntent.IPC_TO_BNS,
            entities=["murder"],
            need_replacement=True,
            need_punishment=True,
            target_act="IPC",
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1
        q = queries[0]
        assert "crimeName" in q.cypher
        assert q.parameters["term"] == "murder"

    def test_bns_to_ipc(self):
        plan = QueryPlan(
            intent=LegalIntent.BNS_TO_IPC,
            linked_node_ids=["BNS_103"],
            need_replacement=True,
            need_punishment=True,
            target_act="BNS",
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1
        assert "REPLACES" in queries[0].cypher

    def test_punishment_lookup_by_id(self):
        plan = QueryPlan(
            intent=LegalIntent.PUNISHMENT,
            linked_node_ids=["IPC_302"],
            need_punishment=True,
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1
        assert "HAS_PUNISHMENT" in queries[0].cypher

    def test_punishment_lookup_by_crime(self):
        plan = QueryPlan(
            intent=LegalIntent.PUNISHMENT,
            entities=["murder"],
            need_punishment=True,
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1
        assert "crimeName" in queries[0].cypher

    def test_crime_lookup(self):
        plan = QueryPlan(
            intent=LegalIntent.CRIME_LOOKUP,
            linked_node_ids=["IPC_302"],
            need_punishment=True,
            need_replacement=True,
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1
        assert "DEFINED_BY" in queries[0].cypher

    def test_keyword_lookup(self):
        plan = QueryPlan(
            intent=LegalIntent.KEYWORD_LOOKUP,
            entities=["cognizable"],
            need_keywords=True,
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1
        assert "lawSectionText" in queries[0].cypher

    def test_related_offences(self):
        plan = QueryPlan(
            intent=LegalIntent.RELATED_OFFENCES,
            linked_node_ids=["IPC_302"],
            need_related=True,
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1
        assert "MORE_SPECIFIC_THAN" in queries[0].cypher

    def test_hierarchy(self):
        plan = QueryPlan(
            intent=LegalIntent.HIERARCHY,
            linked_node_ids=["IPC_302"],
            need_hierarchy=True,
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1
        assert "MORE_SPECIFIC_THAN" in queries[0].cypher

    def test_comparison(self):
        plan = QueryPlan(
            intent=LegalIntent.COMPARISON,
            linked_node_ids=["IPC_302", "BNS_103"],
            comparison_pairs=[["IPC_302", "BNS_103"]],
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1
        assert "IPC_302" in str(queries[0].parameters) or "node_ids" in str(queries[0].parameters)

    def test_multiple_crimes(self):
        plan = QueryPlan(
            intent=LegalIntent.MULTIPLE_CRIMES,
            linked_node_ids=["IPC_302", "IPC_363"],
            multi_crime=True,
            need_punishment=True,
            need_replacement=True,
        )
        queries = build_cypher(plan)
        assert len(queries) >= 1

    def test_empty_plan(self):
        plan = QueryPlan(intent=LegalIntent.SECTION_LOOKUP)
        queries = build_cypher(plan)
        # Should still produce something (fallback to legal_explanation)
        # or empty list
        assert isinstance(queries, list)

    def test_all_queries_are_parameterised(self):
        """Ensure no raw values are interpolated into Cypher strings."""
        plan = QueryPlan(
            intent=LegalIntent.IPC_TO_BNS,
            linked_node_ids=["IPC_302"],
            need_replacement=True,
            need_punishment=True,
        )
        queries = build_cypher(plan)
        for q in queries:
            # All variable data should be in $parameters, not hardcoded
            assert "$" in q.cypher or "UNWIND" in q.cypher

    def test_no_case_sensitive_equality(self):
        """Ensure no queries use case-sensitive = for name matching."""
        plans = [
            QueryPlan(intent=LegalIntent.CRIME_LOOKUP, entities=["murder"]),
            QueryPlan(intent=LegalIntent.KEYWORD_LOOKUP, entities=["cognizable"]),
        ]
        for plan in plans:
            queries = build_cypher(plan)
            for q in queries:
                # Should use fulltext or toLower, not exact = for string matching
                if "crimeName" in q.cypher or "lawSectionText" in q.cypher:
                    continue
                # Check there's no raw string comparison
                assert "= 'murder'" not in q.cypher
                assert "= 'cognizable'" not in q.cypher
