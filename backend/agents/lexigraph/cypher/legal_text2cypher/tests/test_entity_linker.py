"""
Unit tests for the Entity Linker.
"""

import pytest
from unittest.mock import patch, MagicMock

from backend.agents.lexigraph.cypher.legal_text2cypher.schemas.models import ExtractedEntities, LinkedEntities, LinkedNode
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker import link_entities, _deduplicate


class TestDeduplicate:
    def test_removes_duplicates(self):
        nodes = [
            LinkedNode(node_id="A", label="Crime", name="murder", score=0.9),
            LinkedNode(node_id="A", label="Crime", name="murder", score=0.95),
            LinkedNode(node_id="B", label="Crime", name="theft", score=0.8),
        ]
        result = _deduplicate(nodes)
        assert len(result) == 2
        # Should keep the higher score
        a_node = [n for n in result if n.node_id == "A"][0]
        assert a_node.score == 0.95

    def test_empty_list(self):
        assert _deduplicate([]) == []


class TestLinkEntities:
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.get_cached_entity_linking", return_value=None)
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.cache_entity_linking")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.fulltext_search_crimes")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.find_section_by_number")
    def test_links_ipc_section(self, mock_find, mock_ft_crimes, mock_cache_put, mock_cache_get):
        mock_find.return_value = {
            "node_id": "IPC_302",
            "section": "302",
            "act": "IPC",
            "title": "Murder",
            "description": "desc",
            "punishment": "Death",
            "label": "LawSection",
        }
        entities = ExtractedEntities(ipc_sections=["302"])
        result = link_entities(entities)
        assert len(result.section_nodes) >= 1
        assert result.section_nodes[0].node_id == "IPC_302"

    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.get_cached_entity_linking", return_value=None)
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.cache_entity_linking")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.fulltext_search_crimes")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.run_cypher")
    def test_links_crime(self, mock_run, mock_ft_crimes, mock_cache_put, mock_cache_get):
        mock_ft_crimes.return_value = [
            {"node_id": "crime_murder", "name": "Murder", "score": 0.95, "label": "Crime"}
        ]
        mock_run.return_value = [
            {"node_id": "IPC_302", "act": "IPC", "section": "302",
             "title": "Murder", "description": "desc", "punishment": "Death", "label": "LawSection"}
        ]
        entities = ExtractedEntities(crimes=["murder"])
        result = link_entities(entities)
        assert len(result.crime_nodes) >= 1
        assert result.crime_nodes[0].name == "Murder"
