# Frontend: React Dashboard
## Goal
Provide a beautiful, interactive interface for students to simulate a courtroom.
## Dependencies
- `react`, `react-flow`, `d3`
- `react-dropzone` (for file uploads)
- `@mui/material` (for UI)
## Features
1. **Case File Uploader**: Drag and drop PDF/Image evidence.
2. **Courtroom Chat**: Real-time simulation log where students see the Prosecutor, Defense, and Judge speaking.
3. **Graph Visualization (React Flow)**: Visually display the Neo4j graph traversal results (showing the link between Crime -> IPC Section -> Precedent). This provides explainability.
4. **Evaluation Dashboard**: Display the final verdict with confidence score, logicality, and argument strength.