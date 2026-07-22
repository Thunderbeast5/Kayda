# Kayda

An advanced platform for practicing legal arguments with AI agents playing the roles of prosecutor and accused. Features a sophisticated agent-based backend that analyzes user queries and routes them to appropriate legal agents.

## Project Structure

```
MootCourt/
├── src/                   # Frontend (React)
│   ├── components/        # React components
│   ├── styles/            # Styling system
│   └── App.jsx            # Main app component
├── agents/                # Backend (Python)
│   ├── orchestrator.py    # Main agent controller
│   ├── prosecutor.py      # Prosecutor agent
│   ├── accused.py         # Accused/Defense agent
│   ├── server.py          # Flask API server
│   └── requirements.txt   # Python dependencies
├── public/                # Static assets
└── package.json           # Frontend dependencies
```

## Quick Start

### Frontend Setup

1. Install Node.js dependencies:
```bash
npm install
```

2. Start the development server (in a new terminal):
```bash
npm run dev
```

The frontend will run on `http://localhost:5173`

### Backend Setup

1. Navigate to the agents folder:
```bash
cd agents
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Start the Flask API server (in a new terminal):
```bash
python server.py
```

The backend will run on `http://localhost:5001`

## Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
VITE_API_URL=http://localhost:5000
```

For reference, see `.env.example` file. The frontend will use this URL to make API calls to the backend.

**For Production:**
```env
VITE_API_URL=https://your-api-domain.com
```

## Features

- **Orchestrator Agent**: Intelligently routes user queries based on content analysis
- **Prosecutor Agent**: Presents prosecution perspective with evidence-based arguments
- **Accused Agent**: Provides defense perspective with innocence assertions
- **Real-time Chat Interface**: Sophisticated courtroom UI with trial phase tracking
- **Agent-to-Agent Communication**: Agents respond to user queries through API integration

## How It Works

1. User enters a query in the courtroom interface
2. Frontend sends the query to the backend API (`/api/query`)
3. Orchestrator Agent analyzes keywords to determine which agent should respond
4. Selected agent (Prosecutor or Accused) generates a response
5. Response is displayed in the chat panel with appropriate styling

## Agent Keywords

### Prosecutor Keywords
prosecution, prosecutor, charge, accuse, guilty, evidence, crime, criminal, prosecute

### Accused Keywords
defense, defendant, accused, innocent, alibi, case, charges against me, defend

## API Documentation

See [agents/README.md](agents/README.md) for detailed API documentation and agent implementation detail

## Available Scripts

### Frontend
- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint

### Backend
- `python server.py` - Start Flask API server
- `python -m agents.orchestrator` - Test orchestrator directly (future)

## Technology Stack

**Frontend:**
- React
- Vite
- Tailwind CSS
- Lucide React (icons)

**Backend:**
- Python 3.x
- Flask
- Flask-CORS

## Future Enhancements

- [ ] Advanced NLP for better query routing
- [ ] Integration with legal knowledge bases
- [ ] Conversation memory and context management
- [ ] Multi-turn dialogue support
- [ ] Evidence linking and citation system
- [ ] Judge agent implementation
- [ ] Case law research integration
- [ ] Performance analytics and user feedback

## Contributing

Instructions for contributing will be added soon.

## License

All rights reserved.

