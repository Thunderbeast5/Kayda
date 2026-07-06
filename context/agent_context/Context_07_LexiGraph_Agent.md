# Agent: LexiGraph (GraphRAG Legal Researcher)
## Role
Central legal library using Neo4j and Pinecone for precise GraphRAG retrieval.
## Dependencies
- `neo4j` Python driver
- `pinecone-client`, `langchain`
- `spaCy` (NER)
## Workflow
1. Receive query (crime type + facts) from Prosecutor/Defense.
2. **Entity Extraction (NER)**: Use `spaCy` to extract legal terms, crime names, IPC section numbers.
3. **Graph Traversal (Neo4j)**: Run Cypher query:
4. **Amendment Tracking**: Follow `[:AMENDED_TO]` edges in Neo4j to ensure we track the latest version of the law.
5. **Vector Semantic Match**: Query Pinecone vector DB to find similar laws based on the user's fact description.
6. **Rank & Join**: Combine graph results and vector results, rank them by relevance.
7. Return `list[Laws, Precedents, Relationship Context]` back to the calling agent.