# MootCourt.ai - Agent System Setup Complete 

## What Has Been Built

### 1. **Backend Agent System** (Python - `/agents` folder)

#### Three Intelligent Agents:

1. **Orchestrator Agent** (`orchestrator.py`)
   - Main controller that routes user queries to appropriate agents
   - Uses keyword-based analysis to determine routing
   - Coordinates between Prosecutor and Accused agents
   - Returns structured responses with agent identification

2. **Prosecutor Agent** (`prosecutor.py`)
   - Handles prosecution-related queries
   - Focuses on evidence, charges, and criminal case building
   - Keywords trigger: prosecution, prosecutor, charge, accuse, guilty, evidence, crime

3. **Accused Agent** (`accused.py`)
   - Represents the defense/accused perspective
   - Handles alibi and innocence assertions
   - Keywords trigger: defense, defendant, accused, innocent, alibi, case, defend

#### API Server (`server.py`)
- Flask REST API with CORS enabled
- Two endpoints:
  - `POST /api/query` - Process user queries and get agent responses
  - `GET /api/health` - Server health check
- Runs on `http://localhost:5000`

### 2. **Frontend Integration** (React - `src/App.jsx`)

#### Updated Features:
- Frontend now communicates with Python backend via API calls
- User queries are sent to the Orchestrator Agent
- Agent responses are displayed in the courtroom chat panel
- Visual feedback during processing ("PROCESSING QUERY" status)
- Error handling with user-friendly messages
- Agent responses properly mapped to UI roles (Prosecutor/Accused)

### 3. **Documentation & Setup Files**

- **README.md** - Main project documentation with setup instructions
- **agents/README.md** - Detailed agent system documentation
- **start.sh** - Bash startup script for macOS/Linux
- **start.bat** - Batch startup script for Windows

## System Architecture

```
User Input (Frontend)
        ↓
REST API Call to /api/query
        ↓
Orchestrator Agent
        ↓
    Keyword Analysis
    ↙       ↘
Prosecutor  Accused
  Agent      Agent
    ↘       ↙
Agent Response
        ↓
REST API Response
        ↓
Display in Chat Panel (Frontend)
```

## How to Get Started

### Option 1: Quick Start (macOS/Linux)
```bash
chmod +x start.sh
./start.sh
```

### Option 2: Quick Start (Windows)
```bash
start.bat
```

### Option 3: Manual Start

**Terminal 1 - Frontend:**
```bash
npm run dev
```
Opens at: `http://localhost:5173`

**Terminal 2 - Backend:**
```bash
cd agents
pip install -r requirements.txt
python server.py
```
Runs at: `http://localhost:5000`

## Testing the System

1. Open the MootCourt app in your browser
2. Select your role (Prosecutor, Defense, or Judge) in setup
3. Click "Begin Proceedings"
4. Enter a query in the input box at the bottom
5. Press "Submit to Record"
6. Watch as the Orchestrator routes your query to the appropriate agent
7. The agent's response appears in the chat transcript

### Example Queries to Try:

**For Prosecutor Agent Response:**
- "What evidence do you have against the defendant?"
- "Please present your charges under the criminal code"
- "How do you prove guilty intent?"

**For Accused Agent Response:**
- "I maintain my innocence of these charges"
- "My defense is based on alibi witnesses"
- "The accusations are completely false"

## API Usage Example

```javascript
// Frontend example (already implemented)
fetch("http://localhost:5000/api/query", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ query: "Your question here" })
})
.then(res => res.json())
.then(data => {
  console.log(data.agent);      // "Prosecutor" or "Accused"
  console.log(data.response);   // Agent's response text
});
```

## Current Features

✅ Keyword-based query routing
✅ Three independent agents with placeholder responses
✅ REST API with CORS support
✅ Frontend integration with backend
✅ Error handling and logging
✅ Health check endpoint
✅ Responsive chat interface
✅ Agent identification in responses

## Future Enhancement Opportunities

1. **Advanced NLP**: Replace keyword-based routing with ML models
2. **Conversation Memory**: Maintain context across multiple exchanges
3. **Response Templates**: Create more sophisticated response generation
4. **Legal Database Integration**: Pull real precedents and case law
5. **Judge Agent**: Implement the third agent role
6. **Multi-turn Dialogues**: Support longer legal arguments
7. **Evidence Linking**: Connect cases to cited legal references
8. **Analytics**: Track agent performance and user interactions

## File Structure

```
MootCourt/
├── agents/
│   ├── orchestrator.py      # Orchestrator Agent (234 lines)
│   ├── prosecutor.py        # Prosecutor Agent (29 lines)
│   ├── accused.py           # Accused Agent (29 lines)
│   ├── server.py            # Flask API Server (87 lines)
│   ├── requirements.txt      # Dependencies
│   └── README.md            # Backend documentation
├── src/
│   ├── App.jsx              # Updated with API calls
│   └── components/
│       └── ChatPanel.jsx    # Displays agent responses
├── README.md                # Main project documentation
├── start.sh                 # macOS/Linux startup script
├── start.bat                # Windows startup script
└── package.json             # Frontend dependencies
```

## Troubleshooting

**"Failed to connect to backend"**
- Ensure backend is running: `python server.py` in the agents folder
- Check that it's running on http://localhost:5000
- Verify Flask installation: `pip install flask flask-cors`

**"Module not found"**
- Make sure you're in the agents folder when running: `python server.py`
- Install requirements: `pip install -r requirements.txt`

**"Port already in use"**
- Backend (5000): `lsof -i :5000` (macOS/Linux) to find and kill
- Frontend (5173): Wait or change Vite config

## Next Steps

1. ✅ Test the system with sample queries
2. Enhance agent responses with actual legal logic
3. Add conversation memory for multi-turn dialogues
4. Integrate legal knowledge bases
5. Implement the Judge agent with ruling logic
6. Add advanced NLP for better routing
7. Deploy to production

---

**Setup complete!** 🎉 Your MootCourt.ai agent system is ready to use.
