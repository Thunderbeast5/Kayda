# Agent: Evidence Analyzer (The Data Processor)
## Role
Ingests messy real-world legal files and converts them into structured facts for the AI agents.
## Dependencies
- `pytesseract` (OCR), `PyPDF2`
- `langchain_text_splitters`, `openai` embeddings
## Workflow
1. Receive raw files (FIR.pdf, image evidence, witness docs).
2. **OCR & Text Extraction**: Use `pytesseract` and `PyPDF2` to convert to raw text.
3. **Text Chunking**: Split text into manageable chunks using LangChain `RecursiveCharacterTextSplitter`.
4. **LLM Fact Extraction**: Pass chunks to LLM with a specific prompt to extract:
   - Who: Accused name, Victims.
   - What: Crime description.
   - When: Date and time of incident.
   - Where: Location of crime.
   - Amount: Value of stolen goods or damages (if applicable).
5. **Store**: Save structured JSON in MongoDB (`document_store`), generate embeddings using `text-embedding-3-small` and save to Pinecone vector DB.
6. Return JSON `facts_object` to Orchestrator.