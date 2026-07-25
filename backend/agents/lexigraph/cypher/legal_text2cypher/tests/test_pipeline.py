"""
Integration test for the full pipeline.

Mocks only the LLM and Neo4j calls while testing the full
orchestration flow across all pipeline stages.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from backend.agents.lexigraph.cypher.legal_text2cypher.schemas.models import LegalIntent, FinalAnswer
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.pipeline import run_pipeline


class TestFullPipeline:
    """End-to-end pipeline tests with mocked externals."""

    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.answer_generator._get_llm")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.executor.run_cypher")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.graph_expander.run_cypher")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.find_section_by_number")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.fulltext_search_crimes")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.run_cypher")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.get_cached_entity_linking", return_value=None)
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_linker.cache_entity_linking")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.entity_extractor._get_llm")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.intent_classifier._get_llm")
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.planner.get_cached_planner_output", return_value=None)
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.planner.cache_planner_output")
    def test_murder_punishment_pipeline(
        self,
        mock_cache_plan,
        mock_get_plan_cache,
        mock_intent_llm,
        mock_entity_llm,
        mock_cache_put,
        mock_cache_get,
        mock_linker_run,
        mock_ft_crimes,
        mock_find_section,
        mock_expander_run,
        mock_executor_run,
        mock_answer_llm,
    ):
        """Test: 'What is the punishment for murder?'"""

        # Intent classifier mock
        intent_llm = MagicMock()
        intent_llm.invoke.return_value = MagicMock(
            content=json.dumps({
                "intent": "punishment",
                "secondary_intents": [],
                "confidence": 0.95,
                "reasoning": "User asks about punishment"
            })
        )
        mock_intent_llm.return_value = intent_llm

        # Entity extractor mock
        entity_llm = MagicMock()
        entity_llm.invoke.return_value = MagicMock(
            content=json.dumps({
                "crimes": ["murder"],
                "ipc_sections": [],
                "bns_sections": [],
                "acts": [],
                "chapters": [],
                "punishments": [],
                "keywords": [],
                "legal_concepts": []
            })
        )
        mock_entity_llm.return_value = entity_llm

        # Entity linker mocks
        mock_ft_crimes.return_value = [
            {"node_id": "crime_murder", "name": "Murder", "score": 0.95, "label": "Crime"}
        ]
        mock_find_section.return_value = None
        mock_linker_run.return_value = [
            {"node_id": "IPC_302", "act": "IPC", "section": "302",
             "title": "Murder", "description": "Punishment for murder",
             "punishment": "Death or life imprisonment", "label": "LawSection"}
        ]

        # Graph expander mock (empty expansion)
        mock_expander_run.return_value = []

        # Executor mock
        mock_executor_run.return_value = [
            {
                "id": "IPC_302", "act": "IPC", "section": "302",
                "title": "Murder", "description": "Punishment for murder",
                "punishment": "Death or life imprisonment",
                "crime_name": "Murder",
                "punishment_id": "p1",
                "punishment_text": "Death or life imprisonment and fine",
            }
        ]

        # Answer generator mock
        answer_llm = MagicMock()
        answer_llm.invoke.return_value = MagicMock(
            content="The punishment for murder under IPC Section 302 is death or life imprisonment and fine."
        )
        mock_answer_llm.return_value = answer_llm

        # Run pipeline
        result = run_pipeline("What is the punishment for murder?")

        # Assertions
        assert isinstance(result, FinalAnswer)
        assert result.intent == LegalIntent.PUNISHMENT
        assert result.total_time_ms > 0
        assert len(result.stages_log) >= 5
        assert "murder" in result.answer.lower() or "Murder" in result.answer
