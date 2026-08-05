"""
Unit tests for the Graph Expander.
"""

import pytest
from unittest.mock import patch

from backend.agents.lexigraph.cypher.legal_text2cypher.schemas.models import LinkedEntities, LinkedNode
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.graph_expander import expand_graph, _get_punishments


class TestExpandGraph:
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.graph_expander.run_cypher")
    def test_expands_replacements(self, mock_run):
        """Test that REPLACED_BY/REPLACES are found during expansion."""
        # First call: expand outgoing, Second: expand incoming, Third: replacements, Fourth: punishments
        mock_run.side_effect = [
            # outgoing expansion
            [{"source_id": "IPC_302", "target_id": "IPC_299", "rel_type": "MORE_SPECIFIC_THAN",
              "rel_props": {}, "target_title": "Culpable homicide", "target_act": "IPC",
              "target_section": "299", "target_description": "desc", "target_punishment": "pun"}],
            # incoming expansion
            [],
            # replacement query (REPLACED_BY + REPLACES UNION)
            [{"source_id": "IPC_302", "target_id": "BNS_103", "rel_type": "REPLACED_BY",
              "rel_props": {"status": "active_mapping"}, "target_title": "Murder",
              "target_act": "BNS", "target_section": "103",
              "target_description": "desc", "target_punishment": "Death"}],
            # punishments
            [{"node_id": "p1", "name": "Death sentence", "label": "Punishment", "source_section": "IPC_302"}],
        ]

        linked = LinkedEntities(
            section_nodes=[LinkedNode(node_id="IPC_302", label="LawSection", name="Murder", score=1.0)]
        )
        result = expand_graph(linked, max_depth=1)
        assert len(result.relations) >= 1
        assert any(r.relationship == "MORE_SPECIFIC_THAN" for r in result.relations)

    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.graph_expander.run_cypher")
    def test_empty_linked(self, mock_run):
        mock_run.return_value = []
        linked = LinkedEntities()
        result = expand_graph(linked)
        assert len(result.relations) == 0
        assert len(result.punishment_nodes) == 0


class TestGetPunishments:
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.graph_expander.run_cypher")
    def test_gets_punishments(self, mock_run):
        mock_run.return_value = [
            {"node_id": "p1", "name": "Death sentence", "label": "Punishment", "source_section": "IPC_302"}
        ]
        result = _get_punishments(["IPC_302"])
        assert len(result) == 1
        assert result[0].name == "Death sentence"

    def test_empty_ids(self):
        result = _get_punishments([])
        assert result == []
