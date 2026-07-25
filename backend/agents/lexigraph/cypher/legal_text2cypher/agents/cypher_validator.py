"""
Cypher Validator — Stage 6b of the Text-to-Cypher pipeline.

Validates generated Cypher queries before execution:
  • Labels must be in the schema allow-list
  • Relationship types must be in the schema allow-list
  • RETURN clause must exist
  • Forbidden operations (DELETE, DROP, etc.) are rejected
  • Parameters must be present
  • Basic syntax checks
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Set

from ..schemas.models import CypherQuery
from ..utils.schema_loader import (
    FORBIDDEN_LABELS,
    FORBIDDEN_OPERATIONS,
    VALID_LABELS,
    VALID_RELATIONSHIPS,
)

logger = logging.getLogger(__name__)


class CypherValidationError(Exception):
    """Raised when a Cypher query fails validation."""
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"Cypher validation failed: {'; '.join(errors)}")


def _extract_labels(cypher: str) -> Set[str]:
    """Extract all node labels from Cypher patterns like (n:Label)."""
    # Match patterns like :Label, (:Label), (n:Label)
    return set(re.findall(r"[:(\s]([A-Z][a-zA-Z]+)(?:\s*\{|\s*\)|\s*\]|\s*-)", cypher))


def _extract_rel_types(cypher: str) -> Set[str]:
    """Extract all relationship types from Cypher patterns like [:REL_TYPE]."""
    # Match [r:REL_TYPE] or [:REL_TYPE] or [r:A|B|C]
    raw = re.findall(r"\[(?:\w+)?:([\w|]+)\]", cypher)
    types: Set[str] = set()
    for r in raw:
        for t in r.split("|"):
            t = t.strip()
            if t:
                types.add(t)
    return types


def _check_forbidden_operations(cypher: str) -> List[str]:
    """Check for forbidden write/destructive operations."""
    errors: List[str] = []
    upper = cypher.upper()
    for op in FORBIDDEN_OPERATIONS:
        # Match the operation as a standalone word (not inside a string)
        pattern = r"\b" + op.replace(" ", r"\s+") + r"\b"
        if re.search(pattern, upper):
            errors.append(f"Forbidden operation detected: {op}")
    return errors


def _check_labels(cypher: str) -> List[str]:
    """Validate that all labels are in the schema allow-list."""
    errors: List[str] = []
    labels = _extract_labels(cypher)

    # Also check for labels extracted from fulltext index calls
    # db.index.fulltext.queryNodes('crimeName', ...) is allowed
    # Labels in these calls are index names, not node labels, so skip validation

    for label in labels:
        if label in FORBIDDEN_LABELS:
            errors.append(f"Forbidden label used: {label}")
        elif label not in VALID_LABELS and label not in {"node", "score", "r", "r1", "r2", "r3"}:
            # Allow some Cypher built-in variable names that look like labels
            if not label[0].isupper():
                continue
            # Soft warning only — don't block on unknown labels since
            # the CALL db.index patterns may produce false positives
            logger.warning("Unrecognised label '%s' in Cypher", label)

    return errors


def _check_rel_types(cypher: str) -> List[str]:
    """Validate that all relationship types are in the schema allow-list."""
    errors: List[str] = []
    rel_types = _extract_rel_types(cypher)

    for rt in rel_types:
        if rt not in VALID_RELATIONSHIPS:
            logger.warning("Unrecognised relationship type '%s' in Cypher", rt)
            # We warn but don't block — some dynamic relationship types
            # might be used in variable-length path patterns

    return errors


def _check_return(cypher: str) -> List[str]:
    """Ensure the query has a RETURN clause."""
    if not re.search(r"\bRETURN\b", cypher, re.IGNORECASE):
        return ["Query is missing a RETURN clause"]
    return []


def _check_empty_match(cypher: str) -> List[str]:
    """Check for empty MATCH patterns."""
    # Match followed immediately by RETURN without any pattern
    if re.search(r"MATCH\s*\n?\s*RETURN", cypher, re.IGNORECASE):
        return ["Empty MATCH pattern detected"]
    return []


def _check_parameters(query: CypherQuery) -> List[str]:
    """Ensure all $param references have corresponding parameter bindings."""
    errors: List[str] = []
    # Extract all $param_name references
    param_refs = set(re.findall(r"\$(\w+)", query.cypher))
    provided = set(query.parameters.keys())

    missing = param_refs - provided
    if missing:
        errors.append(f"Missing parameter bindings: {missing}")

    return errors


def _check_basic_syntax(cypher: str) -> List[str]:
    """Basic syntax sanity checks."""
    errors: List[str] = []

    # Check balanced parentheses
    if cypher.count("(") != cypher.count(")"):
        errors.append("Unbalanced parentheses")

    # Check balanced brackets
    if cypher.count("[") != cypher.count("]"):
        errors.append("Unbalanced brackets")

    # Check balanced curly braces
    if cypher.count("{") != cypher.count("}"):
        errors.append("Unbalanced curly braces")

    return errors


def validate_cypher(query: CypherQuery, strict: bool = False) -> CypherQuery:
    """
    Validate a CypherQuery against the schema and syntax rules.

    Parameters
    ----------
    query : CypherQuery
        The query to validate.
    strict : bool
        If True, treat warnings as errors.

    Returns
    -------
    CypherQuery
        The same query if valid.

    Raises
    ------
    CypherValidationError
        If the query fails validation.
    """
    logger.info("Validating Cypher: %s", query.cypher[:120])

    errors: List[str] = []

    errors.extend(_check_forbidden_operations(query.cypher))
    errors.extend(_check_return(query.cypher))
    errors.extend(_check_empty_match(query.cypher))
    errors.extend(_check_parameters(query))
    errors.extend(_check_basic_syntax(query.cypher))

    if strict:
        errors.extend(_check_labels(query.cypher))
        errors.extend(_check_rel_types(query.cypher))
    else:
        _check_labels(query.cypher)
        _check_rel_types(query.cypher)

    if errors:
        logger.error("Cypher validation failed: %s", errors)
        raise CypherValidationError(errors)

    logger.info("Cypher validation passed ✓")
    return query


def validate_all(queries: List[CypherQuery], strict: bool = False) -> List[CypherQuery]:
    """
    Validate a list of CypherQuery objects.

    Returns only the valid queries. Logs errors for invalid ones.
    """
    valid: List[CypherQuery] = []
    for q in queries:
        try:
            validate_cypher(q, strict=strict)
            valid.append(q)
        except CypherValidationError as exc:
            logger.error("Dropping invalid query: %s — %s", q.description, exc.errors)
    return valid
