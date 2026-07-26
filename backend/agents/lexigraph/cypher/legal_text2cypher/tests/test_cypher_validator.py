"""
Unit tests for the Cypher Validator.
"""

import pytest

from backend.agents.lexigraph.cypher.legal_text2cypher.schemas.models import CypherQuery
from backend.agents.lexigraph.cypher.legal_text2cypher.agents.cypher_validator import (
    CypherValidationError,
    validate_cypher,
    validate_all,
    _extract_labels,
    _extract_rel_types,
)


class TestExtractLabels:
    def test_simple_label(self):
        labels = _extract_labels("MATCH (n:LawSection {id: $id})")
        assert "LawSection" in labels

    def test_multiple_labels(self):
        labels = _extract_labels(
            "MATCH (c:Crime)-[:DEFINED_BY]->(l:LawSection)"
        )
        assert "Crime" in labels
        assert "LawSection" in labels


class TestExtractRelTypes:
    def test_simple_rel(self):
        types = _extract_rel_types("MATCH ()-[r:DEFINED_BY]->()")
        assert "DEFINED_BY" in types

    def test_multiple_rels(self):
        types = _extract_rel_types(
            "MATCH ()-[r:MORE_SPECIFIC_THAN|OVERRIDES|ENHANCES]->()"
        )
        assert "MORE_SPECIFIC_THAN" in types
        assert "OVERRIDES" in types
        assert "ENHANCES" in types

    def test_anonymous_rel(self):
        types = _extract_rel_types("MATCH ()-[:HAS_PUNISHMENT]->()")
        assert "HAS_PUNISHMENT" in types


class TestValidateCypher:
    def test_valid_query(self):
        q = CypherQuery(
            cypher="MATCH (l:LawSection {id: $id}) RETURN l.title",
            parameters={"id": "IPC_302"},
        )
        result = validate_cypher(q)
        assert result == q

    def test_missing_return(self):
        q = CypherQuery(
            cypher="MATCH (l:LawSection {id: $id})",
            parameters={"id": "IPC_302"},
        )
        with pytest.raises(CypherValidationError) as exc_info:
            validate_cypher(q)
        assert any("RETURN" in e for e in exc_info.value.errors)

    def test_forbidden_delete(self):
        q = CypherQuery(
            cypher="MATCH (n) DELETE n RETURN count(n)",
            parameters={},
        )
        with pytest.raises(CypherValidationError) as exc_info:
            validate_cypher(q)
        assert any("DELETE" in e for e in exc_info.value.errors)

    def test_forbidden_drop(self):
        q = CypherQuery(
            cypher="DROP INDEX myIndex RETURN 1",
            parameters={},
        )
        with pytest.raises(CypherValidationError) as exc_info:
            validate_cypher(q)
        assert any("DROP" in e for e in exc_info.value.errors)

    def test_forbidden_create(self):
        q = CypherQuery(
            cypher="CREATE (n:Fake {name: 'bad'}) RETURN n",
            parameters={},
        )
        with pytest.raises(CypherValidationError) as exc_info:
            validate_cypher(q)
        assert any("CREATE" in e for e in exc_info.value.errors)

    def test_missing_parameters(self):
        q = CypherQuery(
            cypher="MATCH (l:LawSection {id: $id}) RETURN l.title",
            parameters={},  # Missing $id
        )
        with pytest.raises(CypherValidationError) as exc_info:
            validate_cypher(q)
        assert any("Missing parameter" in e for e in exc_info.value.errors)

    def test_unbalanced_parens(self):
        q = CypherQuery(
            cypher="MATCH (l:LawSection {id: $id} RETURN l.title",
            parameters={"id": "test"},
        )
        with pytest.raises(CypherValidationError) as exc_info:
            validate_cypher(q)
        assert any("parentheses" in e.lower() for e in exc_info.value.errors)


class TestValidateAll:
    def test_filters_invalid(self):
        queries = [
            CypherQuery(
                cypher="MATCH (l:LawSection {id: $id}) RETURN l",
                parameters={"id": "IPC_302"},
            ),
            CypherQuery(
                cypher="MATCH (n) DELETE n RETURN count(n)",
                parameters={},
            ),
        ]
        valid = validate_all(queries)
        assert len(valid) == 1
        assert valid[0].parameters["id"] == "IPC_302"
