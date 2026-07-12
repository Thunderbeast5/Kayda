import json
import time
from prosecutor import ProsecutorAgent
from defense import DefenseAgent
from judge import JudgeAgent

def run_evaluation():
    print("==================================================")
    print("          MOOT COURT EVALUATION RUNNER            ")
    print("==================================================")

    # 1. Initialize Agents
    print("[System] Initializing agents...")
    prosecutor = ProsecutorAgent()
    defense = DefenseAgent()
    judge = JudgeAgent()

    # 2. Define Test Cases (Factual Scenarios + Verified LexiGraph results)
    test_cases = [
        {
            "name": "Case 1: Motorcycle Theft (IPC 379)",
            "facts": {
                "who": {
                    "complainant": "Amit Sharma",
                    "accused": ["Rahul Verma"],
                    "victims": ["Amit Sharma"]
                },
                "incident": {
                    "summary": "Rahul Verma was seen on CCTV breaking the lock of Amit's motorcycle in the Pune Metro parking lot and riding away with it without consent.",
                    "date": "05/07/2026",
                    "time": "14:30",
                    "place": "Pune Metro Parking Lot"
                },
                "property": {
                    "vehicles": [
                        {
                            "type": "Motorcycle",
                            "make_model": "Hero Splendor",
                            "registration_no": "MH-12-AB-1234"
                        }
                    ]
                },
                "sections": ["IPC 379"]
            },
            "lexigraph": {
                "ipc_sections": [
                    {
                        "section": "379",
                        "description": "Punishment for theft. Whoever commits theft shall be punished with imprisonment of either description for a term which may extend to three years, or with fine, or with both.",
                        "punishment": "Imprisonment up to 3 years, or fine, or both.",
                        "offense": "Theft",
                        "source": "neo4j",
                        "score": 1.0
                    }
                ],
                "keywords": ["theft"],
                "neo4j_count": 1,
                "pinecone_count": 0,
                "rewritten": False
            }
        },
        {
            "name": "Case 2: Corporate Cheating/Fraud (IPC 420)",
            "facts": {
                "who": {
                    "complainant": "TechCorp Solutions",
                    "accused": ["Suresh Patel"],
                    "victims": ["TechCorp Solutions"]
                },
                "incident": {
                    "summary": "Suresh Patel presented forged educational credentials and a fake previous employment certificate to secure a senior manager position and a signing bonus of 5,00,000 INR.",
                    "date": "10/06/2026",
                    "time": "10:00",
                    "place": "Mumbai Office"
                },
                "property": {
                    "cash": "5,00,000 INR",
                    "documents": ["Fake degree certificate", "Fake experience letter"]
                },
                "sections": ["IPC 420"]
            },
            "lexigraph": {
                "ipc_sections": [
                    {
                        "section": "420",
                        "description": "Cheating and dishonestly inducing delivery of property. Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person... shall be punished with imprisonment... which may extend to seven years, and shall also be liable to fine.",
                        "punishment": "Imprisonment up to 7 years + fine.",
                        "offense": "Cheating",
                        "source": "neo4j",
                        "score": 1.0
                    }
                ],
                "keywords": ["cheating"],
                "neo4j_count": 1,
                "pinecone_count": 0,
                "rewritten": False
            }
        }
    ]

    total_prosecution_score = 0
    total_cases = len(test_cases)
    
    for idx, case in enumerate(test_cases, 1):
        print(f"\nEvaluating Case {idx}: {case['name']}")
        print("-" * 50)
        
        # A. Run Prosecution Agent
        print("[Prosecutor] Generating arguments...")
        try:
            p_args = prosecutor.generate(case["facts"], case["lexigraph"])
        except Exception as e:
            print(f"[Error] Prosecutor failed: {e}")
            continue

        # B. Run Defense Agent
        print("[Defense] Generating arguments...")
        try:
            d_args = defense.generate(case["facts"], case["lexigraph"], p_args)
        except Exception as e:
            print(f"[Error] Defense failed: {e}")
            continue

        # C. Run Judge Agent to Score Both
        print("[Judge] Scoring arguments...")
        try:
            scores, question = judge.score(case["facts"], p_args, d_args)
        except Exception as e:
            print(f"[Error] Judge failed: {e}")
            continue

        # D. Display Case Results
        p_score = scores.get("prosecution", {})
        d_score = scores.get("defense", {})
        
        p_total = p_score.get("total", 0)
        d_total = d_score.get("total", 0)
        total_prosecution_score += p_total

        print(f"\nResult for Case {idx}:")
        print(f"  Prosecution Score: {p_total}/30")
        print(f"    - Legal Validity: {p_score.get('legal_validity', 0)}/10")
        print(f"    - Evidence Linkage: {p_score.get('evidence_linkage', 0)}/10")
        print(f"    - Logic Coherence: {p_score.get('logic_coherence', 0)}/10")
        
        print(f"  Defense Score: {d_total}/30")
        print(f"    - Legal Validity: {d_score.get('legal_validity', 0)}/10")
        print(f"    - Evidence Linkage: {d_score.get('evidence_linkage', 0)}/10")
        print(f"    - Logic Coherence: {d_score.get('logic_coherence', 0)}/10")
        
        if question:
            print(f"  Judge Question for Accused: '{question}'")
        else:
            print("  Evidence sufficient for immediate verdict.")

    # 3. Calculate Global Prosecutor Accuracy Percentage
    avg_score = total_prosecution_score / total_cases
    accuracy_percentage = (avg_score / 30) * 100

    print("\n" + "=" * 50)
    print("             FINAL EVALUATION REPORT             ")
    print("=" * 50)
    print(f"Total Cases Tested          : {total_cases}")
    print(f"Average Prosecution Score   : {avg_score:.2f} / 30")
    print(f"Prosecutor Accuracy Score   : {accuracy_percentage:.1f}%")
    print("=" * 50)

if __name__ == "__main__":
    run_evaluation()
