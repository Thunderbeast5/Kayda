Production-Grade Legal Text-to-Cypher System Specification

Objective

Build a production-ready Text-to-Cypher system for a Legal GraphRAG
platform that converts natural language legal questions into valid Neo4j
Cypher queries with high accuracy (>95%). The system must avoid directly
asking an LLM to generate Cypher from scratch. Instead, use a
deterministic multi-stage pipeline.

------------------------------------------------------------------------

Existing Graph Schema

Node Labels: - Act - Chapter - LawSection - Crime - Punishment -
Keyword - LegalRule

Relationships: - HAS_CHAPTER - HAS_SECTION - DEFINED_BY -
HAS_PUNISHMENT - HAS_KEYWORD - REPLACED_BY - REPLACES -
MORE_SPECIFIC_THAN - OVERRIDES - ENHANCES - INCLUDES_ELEMENTS_OF -
CANNOT_COEXIST_WITH

Use Neo4j Fulltext indexes for: - crimeName - lawSectionText

Never perform case-sensitive matching.

------------------------------------------------------------------------

Architecture

User Query ↓ Intent Classifier ↓ Entity Extraction ↓ Entity Linking
(Neo4j Fulltext) ↓ Graph Expansion ↓ JSON Query Planner ↓ Deterministic
Cypher Builder ↓ Cypher Validator ↓ Neo4j Execution ↓ Result
Verification ↓ Natural Language Answer

------------------------------------------------------------------------

Required Modules

agents/ intent_classifier.py entity_extractor.py entity_linker.py
graph_expander.py planner.py cypher_builder.py cypher_validator.py
executor.py answer_generator.py prompts.py pipeline.py

utils/ neo4j_utils.py schema_loader.py query_cache.py

tests/ unit tests integration tests

------------------------------------------------------------------------

Intent Classifier

Classify questions into intents such as: - punishment - IPC→BNS
mapping - BNS→IPC mapping - section lookup - crime lookup - keyword
lookup - legal explanation - graph reasoning - related offences -
multiple crimes - comparison - hierarchy - punishment comparison

Output JSON only.

------------------------------------------------------------------------

Entity Extraction

Extract: - crimes - IPC sections - BNS sections - acts - chapters -
punishments - keywords - legal concepts

Return structured JSON.

Never generate Cypher here.

------------------------------------------------------------------------

Entity Linking

Resolve extracted entities using Neo4j Fulltext Search.

Return canonical graph nodes.

Example: “homicide” → Crime node

“kidnapping” → Crime node

Never rely on exact string equality.

------------------------------------------------------------------------

Graph Expansion

Expand entities using relationships:

MORE_SPECIFIC_THAN OVERRIDES ENHANCES INCLUDES_ELEMENTS_OF REPLACED_BY
REPLACES

Return expanded context.

------------------------------------------------------------------------

Planner

Planner receives:

Intent Entities Expanded graph context

Returns JSON like:

{ “intent”:“mapping”, “entities”:[“murder”], “needPunishment”:true,
“needReplacement”:true, “needKeywords”:false }

Never generate Cypher.

------------------------------------------------------------------------

Cypher Builder

Pure Python.

Reads planner JSON.

Generates deterministic Cypher templates.

No LLM.

Use parameterized queries.

------------------------------------------------------------------------

Validator

Validate: - labels - relationships - RETURN clause - parameters -
syntax - forbidden labels - empty MATCH

Reject invalid Cypher.

------------------------------------------------------------------------

Executor

Execute Cypher.

Retry on transient errors.

Return structured JSON.

------------------------------------------------------------------------

Answer Generator

Use LLM only after retrieval.

Explain: - offence - punishment - mapping - legal reasoning

Do not hallucinate.

------------------------------------------------------------------------

Multi-crime Handling

Input: “A child was kidnapped for ransom and murdered.”

Extract:

Kidnapping Ransom Murder

Generate one optimized query instead of multiple independent queries
whenever possible.

------------------------------------------------------------------------

Hybrid Retrieval

Combine:

-   Neo4j Fulltext
-   Graph traversal
-   Vector retrieval
-   Keyword retrieval

Merge results.

------------------------------------------------------------------------

Caching

Cache: - linked entities - planner output - generated Cypher

------------------------------------------------------------------------

Logging

Log every stage: - query - extracted entities - planner JSON - generated
Cypher - execution time - retries - final answer

------------------------------------------------------------------------

Performance Goals

Entity extraction accuracy >98%

Cypher validity >99%

Latency: <2 sec typical

------------------------------------------------------------------------

Recommended Tech Stack

Python 3.11+ Neo4j LangGraph LangChain Pydantic OpenAI / GPT-5.x Redis
Sentence Transformers Neo4j Python Driver

------------------------------------------------------------------------

Deliverables

Generate a complete production project containing:

-   Complete folder structure
-   Every Python module fully implemented
-   Type hints
-   Logging
-   Unit tests
-   Integration tests
-   Requirements.txt
-   Dockerfile
-   docker-compose.yml
-   README.md
-   Example queries
-   Example outputs
-   Configuration management
-   Environment variables
-   Prompt templates
-   JSON schemas
-   Retry logic
-   Error handling
-   Validation
-   Production-quality documentation

The code should be modular, maintainable, production-ready, and
compatible with the legal Neo4j schema described above.
