# MootCourt Simulator: Project Architecture Context
## Goal
Build a multi-agent system simulating a real Indian courtroom for law students. It takes case files (FIRs/Evidence), extracts facts, performs dynamic GraphRAG retrieval to find IPC sections/precedents, initiates an adversarial debate between prosecutor/defense agents, and outputs a judicial verdict.
## Core Pattern
Hierarchical "Core Role – Meta-Role" decoupling (based on FMARLJP).
## Tech Stack
- **LangGraph**: State machine managing agent transitions.
- **OpenAI GPT-4o**: Main reasoning LLM via LangChain.
- **Neo4j**: Graph Database (IPC Sections, Crimes, Precedents).
- **Pinecone**: Vector Database for semantic similarity search.
- **MongoDB**: Document store for raw files and session logs.
- **Redis**: Short-term memory store for active session state.
- **FastAPI & WebSockets**: Real-time backend API.
- **React Flow & D3.js**: Frontend visualization.