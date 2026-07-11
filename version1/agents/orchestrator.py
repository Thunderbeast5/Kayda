"""
Orchestrator Agent - Main Controller
Routes user queries to the appropriate agent based on content analysis.
"""

from version1.agents.prosecutor import ProsecutorAgent
from version1.agents.accused import AccusedAgent


class OrchestratorAgent:
    def __init__(self):
        self.prosecutor_agent = ProsecutorAgent()
        self.accused_agent = AccusedAgent()
    
    def analyze_and_route(self, query: str) -> dict:
        """
        Analyzes the user query and routes it to the appropriate agent.
        
        Args:
            query: User's input query
            
        Returns:
            dict with agent response and metadata
        """
        # Simple keyword-based routing logic
        query_lower = query.lower()
        
        # Keywords for prosecutor queries
        prosecutor_keywords = [
            "prosecution", "prosecutor", "charge", "accuse", "guilty",
            "evidence", "crime", "criminal", "prosecute"
        ]
        
        # Keywords for accused queries
        accused_keywords = [
            "defense", "defendant", "accused", "innocent", "alibi",
            "case", "charges against me", "defend"
        ]
        
        # Determine which agent should handle this query
        if any(keyword in query_lower for keyword in prosecutor_keywords):
            agent_name = "Prosecutor"
            response = self.prosecutor_agent.respond(query)
        elif any(keyword in query_lower for keyword in accused_keywords):
            agent_name = "Accused"
            response = self.accused_agent.respond(query)
        else:
            # Default to prosecutor if no clear match
            agent_name = "Prosecutor"
            response = self.prosecutor_agent.respond(query)
        
        return {
            "agent": agent_name,
            "response": response,
            "original_query": query
        }


# For standalone testing
if __name__ == "__main__":
    orchestrator = OrchestratorAgent()
    
    # Test queries
    test_queries = [
        "What evidence do you have against the defendant?",
        "I am innocent of these charges!",
        "The crime scene had no fingerprints"
    ]
    
    for query in test_queries:
        result = orchestrator.analyze_and_route(query)
        print(f"Query: {query}")
        print(f"Agent: {result['agent']}")
        print(f"Response: {result['response']}")
        print("---")
