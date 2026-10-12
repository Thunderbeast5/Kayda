"""
Simple runner for the new Orchestrator-based Moot Court System

Usage:
    cd backend/prosecutor
    python run_moot_court.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Load .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from orchestrator_agent import OrchestratorAgent


def main():
    """Run the moot court session."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("Error: OPENAI_API_KEY not set!")
        sys.exit(1)
    
    orchestrator = OrchestratorAgent(api_key=api_key)
    orchestrator.run_moot_court_session()


if __name__ == "__main__":
    main()
