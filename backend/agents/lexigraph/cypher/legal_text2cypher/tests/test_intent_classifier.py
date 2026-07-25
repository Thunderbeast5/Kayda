"""
Unit tests for the Intent Classifier.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from backend.agents.lexigraph.cypher.legal_text2cypher.schemas.models import IntentResult, LegalIntent
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.intent_classifier import classify_intent, _parse_intent_json


class TestParseIntentJson:
    """Tests for the JSON response parser."""

    def test_valid_json(self):
        raw = json.dumps({
            "intent": "punishment",
            "secondary_intents": ["crime_lookup"],
            "confidence": 0.95,
            "reasoning": "User asks about punishment"
        })
        result = _parse_intent_json(raw)
        assert result.intent == LegalIntent.PUNISHMENT
        assert LegalIntent.CRIME_LOOKUP in result.secondary_intents
        assert result.confidence == 0.95

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"intent": "ipc_to_bns", "confidence": 0.9}\n```'
        result = _parse_intent_json(raw)
        assert result.intent == LegalIntent.IPC_TO_BNS

    def test_invalid_json(self):
        raw = "This is not JSON at all"
        result = _parse_intent_json(raw)
        assert result.intent == LegalIntent.UNKNOWN
        assert result.confidence == 0.0

    def test_unknown_intent_value(self):
        raw = json.dumps({"intent": "completely_invalid", "confidence": 0.5})
        result = _parse_intent_json(raw)
        assert result.intent == LegalIntent.UNKNOWN

    def test_all_valid_intents(self):
        for intent in LegalIntent:
            raw = json.dumps({"intent": intent.value, "confidence": 0.8})
            result = _parse_intent_json(raw)
            assert result.intent == intent


class TestClassifyIntent:
    """Tests for the main classify_intent function."""

    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.intent_classifier._get_llm")
    def test_punishment_query(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({
                "intent": "punishment",
                "secondary_intents": [],
                "confidence": 0.95,
                "reasoning": "Asking about punishment for murder"
            })
        )
        mock_get_llm.return_value = mock_llm

        result = classify_intent("What is the punishment for murder?")
        assert result.intent == LegalIntent.PUNISHMENT
        assert result.confidence == 0.95

    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.intent_classifier._get_llm")
    def test_mapping_query(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({
                "intent": "ipc_to_bns",
                "confidence": 0.9,
                "reasoning": "IPC to BNS mapping"
            })
        )
        mock_get_llm.return_value = mock_llm

        result = classify_intent("What is the BNS equivalent of IPC 302?")
        assert result.intent == LegalIntent.IPC_TO_BNS

    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.intent_classifier._get_llm")
    def test_llm_failure(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API Error")
        mock_get_llm.return_value = mock_llm

        result = classify_intent("test query")
        assert result.intent == LegalIntent.UNKNOWN
        assert result.confidence == 0.0
