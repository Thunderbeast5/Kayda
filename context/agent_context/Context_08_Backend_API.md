# Backend: FastAPI & WebSockets
## Goal
Expose the MootCourt Simulator to the React frontend.
## Dependencies
- `fastapi`, `uvicorn`, `websockets`
- `python-dotenv`
## Endpoints
1. `POST /api/upload_case`: Takes raw files. Returns `session_id`.
2. `POST /api/start_session`: Starts the `Orchestrator` state machine for a given `session_id`.
3. `WebSocket /ws/{session_id}`: Streams live debate logs and transcripts to the frontend.
4. `POST /api/chat`: Allows user to interact directly with the agents (optional interface for querying the Accused directly).