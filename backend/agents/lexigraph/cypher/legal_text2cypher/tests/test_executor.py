"""
Unit tests for the Executor.
"""

import pytest
from unittest.mock import patch

from backend.agents.lexigraph.cypher.legal_text2cypher.schemas.models import CypherQuery
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.executor import execute_query, execute_all


class TestExecuteQuery:
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.executor.run_cypher")
    def test_successful_execution(self, mock_run):
        mock_run.return_value = [{"id": "IPC_302", "title": "Murder"}]
        q = CypherQuery(
            cypher="MATCH (l:LawSection {id: $id}) RETURN l.title",
            parameters={"id": "IPC_302"},
            description="Test query",
        )
        result = execute_query(q)
        assert result.success is True
        assert len(result.records) == 1
        assert result.execution_time_ms > 0

    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.executor.run_cypher")
    def test_failed_execution(self, mock_run):
        mock_run.side_effect = RuntimeError("Connection failed")
        q = CypherQuery(
            cypher="MATCH (n) RETURN n",
            parameters={},
            description="Failing query",
        )
        result = execute_query(q)
        assert result.success is False
        assert "Connection failed" in result.error


class TestExecuteAll:
    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.executor.run_cypher")
    def test_multiple_queries(self, mock_run):
        mock_run.return_value = [{"count": 1}]
        queries = [
            CypherQuery(cypher="RETURN 1 AS n", parameters={}, description="Q1"),
            CypherQuery(cypher="RETURN 2 AS n", parameters={}, description="Q2"),
        ]
        results = execute_all(queries)
        assert len(results) == 2
        assert all(r.success for r in results)

    @patch("backend.agents.lexigraph.cypher.legal_text2cypher.agents.executor.run_cypher")
    def test_partial_failure(self, mock_run):
        mock_run.side_effect = [[{"a": 1}], RuntimeError("Fail")]
        queries = [
            CypherQuery(cypher="RETURN 1", parameters={}, description="OK"),
            CypherQuery(cypher="RETURN 2", parameters={}, description="FAIL"),
        ]
        results = execute_all(queries)
        assert results[0].success is True
        assert results[1].success is False
