# Kayda Agents Backend

This folder contains the Python backend for the Kayda AI agent system. The system consists of three agents:

- **Orchestrator Agent**: Main controller that routes queries to appropriate agents
- **Prosecutor Agent**: Handles prosecution-related logic and responses
- **Accused Agent**: Handles defense/accused perspective responses

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

