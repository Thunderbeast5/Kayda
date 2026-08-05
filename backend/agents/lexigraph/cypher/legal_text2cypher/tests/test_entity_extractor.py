"""
Unit tests for the Entity Extractor.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from backend.agents.lexigraph.cypher.legal_text2cypher.schemas.models import ExtractedEntities
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_extractor import extract_entities, _parse_entities_json


class TestParseEntitiesJson:
    """Tests for the JSON response parser."""

    def test_valid_json(self):
        raw = json.dumps({
            "crimes": ["murder", "kidnapping"],
            "ipc_sections": ["302", "363"],
            "bns_sections": ["103"],
            "acts": ["IPC", "BNS"],
            "chapters": [],
            "punishments": ["death penalty"],
            "keywords": ["cognizable"],
            "legal_concepts": ["mens rea"]
        })
        result = _parse_entities_json(raw)
        assert result.crimes == ["murder", "kidnapping"]
        assert result.ipc_sections == ["302", "363"]
        assert result.bns_sections == ["103"]
        assert "mens rea" in result.legal_concepts

    def test_invalid_json(self):
        result = _parse_entities_json("not json")
        assert result.crimes == []
        assert result.ipc_sections == []

    def test_partial_json(self):
        raw = json.dumps({"crimes": ["theft"], "extra_field": "ignored"})
        result = _parse_entities_json(raw)
        assert result.crimes == ["theft"]
        assert result.ipc_sections == []

    def test_markdown_wrapped(self):
        raw = '```json\n{"crimes": ["robbery"]}\n```'
        result = _parse_entities_json(raw)
        assert result.crimes == ["robbery"]


class TestExtractEntities:
    """Tests for the main extract_entities function."""

    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_extractor._get_llm")
    def test_murder_query(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({
                "crimes": ["murder"],
                "ipc_sections": ["302"],
                "bns_sections": [],
                "acts": ["IPC"],
                "chapters": [],
                "punishments": [],
                "keywords": [],
                "legal_concepts": []
            })
        )
        mock_get_llm.return_value = mock_llm

        result = extract_entities("What is the punishment for murder under IPC 302?")
        assert "murder" in result.crimes
        assert "302" in result.ipc_sections

    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_extractor._get_llm")
    def test_multi_crime_query(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({
                "crimes": ["kidnapping", "murder"],
                "ipc_sections": [],
                "bns_sections": [],
                "acts": [],
                "chapters": [],
                "punishments": [],
                "keywords": [],
                "legal_concepts": []
            })
        )
        mock_get_llm.return_value = mock_llm

        result = extract_entities("A child was kidnapped for ransom and murdered.")
        assert len(result.crimes) == 2

    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_extractor._get_llm")
    def test_llm_failure(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API Error")
        mock_get_llm.return_value = mock_llm

        result = extract_entities("test")
        assert result.crimes == []
