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


import argparse

def main():
    """Run the moot court session."""
    parser = argparse.ArgumentParser(description="Run Virtual Moot Court Session (AI vs Human)")
    parser.add_argument(
        "--role",
        choices=["prosecution", "defense", "prosecutor", "defence"],
        default=None,
        help="Choose role for human counsel ('prosecution'/'prosecutor' or 'defense'/'defence').",
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
    orchestrator = OrchestratorAgent(api_key=api_key)
    orchestrator.run_moot_court_session(role=args.role)


if __name__ == "__main__":
    main()

