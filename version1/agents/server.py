"""
API Server for the MootCourt Agent System
Provides REST endpoints for frontend integration.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from version1.agents.orchestrator import OrchestratorAgent

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend requests

# Initialize the orchestrator
orchestrator = OrchestratorAgent()


@app.route("/api/query", methods=["POST"])
def process_query():
    """
    Main endpoint that processes user queries through the orchestrator.
    
    Expected JSON:
    {
        "query": "user's question or statement"
    }
    
    Returns:
    {
        "success": true/false,
        "agent": "Agent name",
        "response": "Agent's response",
        "original_query": "original query"
    }
    """
    try:
        data = request.get_json()
        
        if not data or "query" not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'query' field in request"
            }), 400
        
        query = data["query"]
        result = orchestrator.analyze_and_route(query)
        
        return jsonify({
            "success": True,
            "agent": result["agent"],
            "response": result["response"],
            "original_query": result["original_query"]
        }), 200
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/health", methods=["GET"])
def health_check():
    """
    Health check endpoint.
    """
    return jsonify({
        "status": "healthy",
        "message": "MootCourt Agent API is running"
    }), 200


if __name__ == "__main__":
    # Run on port 5000
    app.run(debug=True, host="0.0.0.0", port=5001)
