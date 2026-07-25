# Legal Text-to-Cypher Pipeline

> Production-grade, deterministic Text-to-Cypher system for Indian Legal GraphRAG (IPC & BNS).

## Architecture

```
User Query
    ↓
Intent Classifier (LLM → JSON)
    ↓
Entity Extractor (LLM → JSON)
    ↓
Entity Linker (Neo4j Fulltext)
    ↓
Graph Expander (Neo4j traversal)
    ↓
Query Planner (deterministic + LLM fallback → JSON spec)
    ↓
Cypher Builder (PURE PYTHON — NO LLM)
    ↓
Cypher Validator (syntax, labels, relationships, forbidden ops)
    ↓
Neo4j Executor (retry with exponential backoff)
    ↓
Answer Generator (LLM — post-retrieval only)
    ↓
Natural Language Answer
```

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **No LLM for Cypher generation** | Cypher is built deterministically from parameterised templates. >99% validity. |
| **Fulltext indexes** | `crimeName` and `lawSectionText` indexes enable fuzzy, case-insensitive entity resolution. |
| **Parameterised queries** | All `$param` placeholders prevent injection and improve Neo4j plan cache hit rate. |
| **Deterministic planner fast-path** | Common intents (punishment, mapping, lookup) skip the LLM entirely. |
| **Multi-crime optimisation** | Single query for multiple crimes instead of N independent queries. |

## Graph Schema

| Node | Key Properties |
|---|---|
| `Act` | `code`, `name` |
| `Chapter` | `id`, `act`, `number`, `title` |
| `LawSection` | `id`, `act`, `section`, `title`, `description`, `punishment`, `mapping_status` |
| `Crime` | `id`, `name` |
| `Punishment` | `id`, `text` |
| `Keyword` | `id`, `name` |
| `LegalRule` | `id`, `relationship`, `condition`, `confidence` |

| Relationship | Direction |
|---|---|
| `HAS_CHAPTER` | `Act → Chapter` |
| `HAS_SECTION` | `Act/Chapter → LawSection` |
| `DEFINED_BY` | `Crime → LawSection` |
| `HAS_PUNISHMENT` | `LawSection → Punishment` |
| `HAS_KEYWORD` | `LawSection → Keyword` |
| `REPLACED_BY` | `LawSection[IPC] → LawSection[BNS]` |
| `REPLACES` | `LawSection[BNS] → LawSection[IPC]` |
| `MORE_SPECIFIC_THAN` | `LawSection → LawSection` |
| `OVERRIDES` | `LawSection → LawSection` |
| `ENHANCES` | `LawSection → LawSection` |
| `INCLUDES_ELEMENTS_OF` | `LawSection → LawSection` |
| `CANNOT_COEXIST_WITH` | `LawSection → LawSection` |

## Quick Start

### 1. Configure environment

Ensure your `.env` file exists in `backend/.env` or `legal_text2cypher/.env`.

### 2. Run the demo

```bash
# Option A: From inside legal_text2cypher directory:
cd backend/agents/lexigraph/cypher/legal_text2cypher
python run_demo.py "What is the BNS equivalent of IPC 302?"

# Option B: From MootCourt root:
PYTHONPATH=. python backend/agents/lexigraph/cypher/legal_text2cypher/run_demo.py
```

### 4. Run tests

```bash
PYTHONPATH=. python -m pytest legal_text2cypher/tests -v
```

### 5. Docker

```bash
cd legal_text2cypher
docker-compose up --build
```

## Example Queries & Expected Outputs

### Query: "What is the punishment for murder?"

```
Intent: punishment
Entities: ["murder"]
Cypher: CALL db.index.fulltext.queryNodes('crimeName', $term) YIELD node AS c, score
        WHERE score >= 0.3
        MATCH (c)-[:DEFINED_BY]->(l:LawSection)
        OPTIONAL MATCH (l)-[:HAS_PUNISHMENT]->(p:Punishment)
        RETURN c.name, l.act, l.section, l.title, p.text ...
Answer: Under IPC Section 302, murder is punishable with death or
        imprisonment for life, and shall also be liable to fine...
```

### Query: "What is the BNS equivalent of IPC Section 302?"

```
Intent: ipc_to_bns
Entities: ["302"]
Cypher: MATCH (ipc:LawSection {id: $nid, act: 'IPC'})
        OPTIONAL MATCH (ipc)-[r:REPLACED_BY]->(bns:LawSection {act: 'BNS'})
        ...
Answer: IPC Section 302 (Murder) has been replaced by BNS Section 103(1)
        (Punishment for murder) under the Bharatiya Nyaya Sanhita, 2023...
```

### Query: "A child was kidnapped for ransom and murdered."

```
Intent: multiple_crimes
Entities: ["kidnapping", "ransom", "murder"]
Cypher: (single optimised query for all crimes)
Answer: This scenario involves multiple offences:
        1. Kidnapping — IPC Section 363 / BNS Section 139...
        2. Kidnapping for Ransom — IPC Section 364A...
        3. Murder — IPC Section 302 / BNS Section 103...
```

## Project Structure

```
legal_text2cypher/
├── __init__.py
├── config/
│   ├── __init__.py
│   └── settings.py          # Pydantic Settings (env vars)
├── schemas/
│   ├── __init__.py
│   └── models.py            # Pydantic data models
├── utils/
│   ├── __init__.py
│   ├── neo4j_utils.py        # Neo4j driver + fulltext search
│   ├── schema_loader.py      # Static graph schema definition
│   └── query_cache.py        # LRU + TTL cache
├── agents/
│   ├── __init__.py
│   ├── prompts.py             # LLM prompt templates
│   ├── intent_classifier.py   # Stage 1
│   ├── entity_extractor.py    # Stage 2
│   ├── entity_linker.py       # Stage 3
│   ├── graph_expander.py      # Stage 4
│   ├── planner.py             # Stage 5
│   ├── cypher_builder.py      # Stage 6 (PURE PYTHON)
│   ├── cypher_validator.py    # Stage 6b
│   ├── executor.py            # Stage 7
│   ├── answer_generator.py   # Stage 8
│   └── pipeline.py           # Orchestrator
├── tests/
│   ├── __init__.py
│   ├── test_intent_classifier.py
│   ├── test_entity_extractor.py
│   ├── test_entity_linker.py
│   ├── test_graph_expander.py
│   ├── test_planner.py
│   ├── test_cypher_builder.py
│   ├── test_cypher_validator.py
│   ├── test_executor.py
│   ├── test_pipeline.py
│   └── test_query_cache.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── run_demo.py
└── README.md
```

## Performance Goals

| Metric | Target |
|---|---|
| Entity extraction accuracy | >98% |
| Cypher validity | >99% |
| Typical latency | <2 sec |

## Tech Stack

- Python 3.11+
- Neo4j 5.x (Aura or self-hosted)
- LangChain + Groq (LLM calls)
- Pydantic v2 (data validation)
- pytest (testing)
- Docker (deployment)
