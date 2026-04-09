# MootCourt Agents Backend



This folder contains the Python backend for the MootCourt AI agent system. The system consists of three agents:

- **Orchestrator Agent**: Main controller that routes queries to appropriate agents
- **Prosecutor Agent**: Handles prosecution-related logic and responses
- **Accused Agent**: Handles defense/accused perspective responses

## Setup Instructions

### 1. Install Dependencies

Navigate to the agents folder and install Python dependencies:

```bash
cd agents
pip install -r requirements.txt
```

### 2. Run the Server

Start the Flask API server:

```bash
python server.py
```

The server will start on `http://localhost:5000` and will be accessible to the frontend.

## API Endpoints

### POST `/api/query`

Processes user queries through the agent system.

**Request Body:**
```json
{
  "query": "Your question or statement here"
}
```

**Response:**
```json
{
  "success": true,
  "agent": "Prosecutor or Accused",
  "response": "Agent's response text",
  "original_query": "Your original query"
}
```

### GET `/api/health`

Health check endpoint to verify the server is running.

**Response:**
```json
{
  "status": "healthy",
  "message": "MootCourt Agent API is running"
}
```

## Agent Routing

The Orchestrator Agent uses keyword-based routing to determine which agent should respond:

### Prosecutor Keywords
- prosecution, prosecutor, charge, accuse, guilty, evidence, crime, criminal, prosecute

### Accused Keywords
- defense, defendant, accused, innocent, alibi, case, charges against me, defend

If no clear keywords match, the query defaults to the Prosecutor Agent.

## Architecture

```
orchestrator.py   ← Main entry point, routes queries
├── prosecutor.py  ← Prosecutor Agent implementation
└── accused.py     ← Accused Agent implementation

server.py         ← Flask REST API server
requirements.txt  ← Python dependencies
```

## Next Steps

- Enhance the agent responses with more sophisticated logic
- Add natural language processing for better routing
- Integrate with legal knowledge bases
- Implement conversation history and context management
- Add logging and monitoring
