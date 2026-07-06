# Database Schemas & Indexes

## 1. MongoDB (Sessions and Raw Data)
### Collection: `sessions`
{
  "_id": ObjectId,
  "session_id": "uuid",
  "user_id": "str",
  "timeline": ["Upload", "Debate", "Verdict"],
  "final_verdict": "dict"
}
### Collection: `evidence_logs`
{
  "session_id": "uuid",
  "raw_file_path": "str",
  "extracted_facts": { "who": "...", "what": "...", "when": "...", "where": "..." }
}

## 2. Neo4j Graph DB (Law Structure)
### Nodes:
- `Law:IPC` (section: str, description: str, punishment: str)
- `Crime` (name: str, classification: str)
- `Precedent` (case_name: str, citation: str, court: str, year: int)
### Relationships:
- `(:Crime)-[:DEFINED_BY]->(:Law)`
- `(:Law)-[:AMENDED_TO]->(:Law)`
- `(:Precedent)-[:APPLIES_TO]->(:Law)`
### Cypher Indexes:
- `CREATE INDEX ipc_section_idx FOR (l:Law) ON (l.section)`

## 3. Pinecone (Vector DB)
### Index: `legal_embeddings`
- Dimension: 1536 (OpenAI text-embedding-3-small)
- Metric: Cosine Similarity
- Metadata: section_number, legal_domain (e.g., "Theft", "Fraud"), description.