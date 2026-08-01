"""
Test script to verify LexiGraph Explorer endpoint is working correctly
"""
import requests
import json

# Test query
test_query = "A woman alleged that a man induced her into a sexual relationship by falsely promising marriage despite already being married and having no intention of marrying her."

# API URL
api_url = "http://localhost:5001/api/lexigraph/analyze"

print("=" * 80)
print("TESTING LEXIGRAPH EXPLORER ENDPOINT")
print("=" * 80)
print(f"\nEndpoint: {api_url}")
print(f"Query: {test_query[:100]}...")
print("\nSending request...")

try:
    response = requests.post(
        api_url,
        json={"query": test_query},
        timeout=120
    )
    
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("\n✅ SUCCESS! Backend is connected and working.")
        print("\nResponse structure:")
        print(json.dumps({
            "success": data.get("success"),
            "agent": data.get("agent"),
            "data_keys": list(data.get("data", {}).keys()),
            "pipeline_confidence": data.get("data", {}).get("pipeline_confidence"),
            "recommended_sections_count": len(data.get("data", {}).get("recommended_sections", [])),
            "supporting_cases_count": len(data.get("data", {}).get("supporting_cases", [])),
        }, indent=2))
        
        print("\nFirst recommended section:")
        recommended = data.get("data", {}).get("recommended_sections", [])
        if recommended:
            sec = recommended[0]
            print(json.dumps({
                "act": sec.get("act"),
                "section": sec.get("section"),
                "title": sec.get("title"),
                "confidence": sec.get("confidence"),
            }, indent=2))
        else:
            print("No sections recommended")
            
    else:
        print(f"\n❌ ERROR: Status {response.status_code}")
        print(response.text)
        
except requests.exceptions.ConnectionError:
    print("\n❌ CONNECTION ERROR: Cannot connect to backend at port 5001")
    print("\nMake sure backend is running:")
    print("  cd backend")
    print("  uvicorn app:app --host 0.0.0.0 --port 5001 --reload")
    
except requests.exceptions.Timeout:
    print("\n⏱️ TIMEOUT: Request took longer than 120 seconds")
    print("The LexiGraph pipeline can take time. Query is still processing.")
    
except Exception as e:
    print(f"\n❌ UNEXPECTED ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
