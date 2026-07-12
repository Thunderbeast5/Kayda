"""
Manual test harness — run any agent with custom data without editing source files.

Usage
-----
    # Test Judge + Accused loop
    ..\venv\Scripts\python.exe test_manual.py judge

    # Test Defense
    ..\venv\Scripts\python.exe test_manual.py defense

    # Test LexiGraph
    ..\venv\Scripts\python.exe test_manual.py lexigraph

Edit the CUSTOM_FACTS / CUSTOM_PROSECUTION / CUSTOM_DEFENSE blocks below
to use your own case details.
"""

import sys

# ── Your custom test data — edit these ───────────────────────────────────────

CUSTOM_FACTS = {
    "who": {
        "complainant": "Suresh Patil",
        "accused":     ["Vikram Desai"],
        "victims":     ["Suresh Patil"],
    },
    "incident": {
        "summary": "Vikram Desai allegedly entered Suresh Patil's house at night and stole gold jewellery worth ₹2,00,000.",
        "date":    "10/07/2026",
        "time":    "02:15",
        "place":   "Mumbai, Maharashtra",
    },
    "property": {
        "gold":           "Two gold necklaces, total 40g",
        "estimated_loss": "₹2,00,000",
    },
    "sections": ["IPC 380", "IPC 457"],
}

CUSTOM_PROSECUTION = """
1. The accused was found near the victim's house at 2 AM with no valid reason.
2. Gold jewellery matching the stolen items was recovered from the accused's bag.
3. IPC Section 380 — theft in a dwelling house — clearly applies.
4. IPC Section 457 — lurking house-trespass at night — is established by the time of entry.
5. The accused had no prior relationship with the complainant.
"""

CUSTOM_DEFENSE = """
1. No eyewitness places the accused inside the house — only near it.
2. The recovered jewellery has not been conclusively identified as the stolen items.
3. The accused was returning from a night shift and was merely passing by.
4. Chain of custody for the recovered items has not been established.
5. Mens rea for trespass (IPC 457) requires proof of intent to commit an offence — not proven.
"""

# ─────────────────────────────────────────────────────────────────────────────

def test_judge():
    from judge import JudgeAgent
    judge = JudgeAgent()

    print("\n" + "=" * 70)
    print("STEP 1 — SCORING PASS")
    print("=" * 70)
    scores, question = judge.score(CUSTOM_FACTS, CUSTOM_PROSECUTION, CUSTOM_DEFENSE)

    p = scores["prosecution"]
    d = scores["defense"]
    print(f"\nProsecution  →  Legal: {p['legal_validity']}  Evidence: {p['evidence_linkage']}  Logic: {p['logic_coherence']}  Total: {p['total']}/30")
    print(f"Defense      →  Legal: {d['legal_validity']}  Evidence: {d['evidence_linkage']}  Logic: {d['logic_coherence']}  Total: {d['total']}/30")

    accused_history = []
    if question:
        print(f"\n⚖️  Judge asks Accused: \"{question}\"")

        from accused import AccusedAgent
        accused = AccusedAgent()
        testimony = accused.respond(
            session_id       = "manual_test_001",
            question         = question,
            structured_facts = CUSTOM_FACTS,
            prior_history    = [],
        )
        print(f"\n🧑 Accused responds:\n{testimony}")
        accused_history = [testimony]
    else:
        print("\n✅  Evidence sufficient — no question needed.")

    print("\n" + "=" * 70)
    print("STEP 2 — VERDICT")
    print("=" * 70)
    verdict = judge.verdict(
        CUSTOM_FACTS, CUSTOM_PROSECUTION, CUSTOM_DEFENSE, accused_history, scores
    )

    print(f"\n{'GUILTY' if verdict['decision'] == 'Guilty' else 'NOT GUILTY':^70}")
    print(f"\nConfidence : {verdict['confidence']}%")
    print(f"Laws cited : IPC {', IPC '.join(verdict['laws_applied'])}")
    print(f"\n{'-'*70}\nExplanation:\n{verdict['explanation']}")


def test_defense():
    from defense import DefenseAgent
    from lexigraph import retrieve, format_for_prompt

    print("\n[test] Running LexiGraph retrieval first…")
    query  = CUSTOM_FACTS["incident"]["summary"]
    result = retrieve(query)

    agent  = DefenseAgent()
    output = agent.generate(
        structured_facts      = CUSTOM_FACTS,
        lexigraph_result      = result,
        prosecution_arguments = CUSTOM_PROSECUTION,
    )
    print("\n" + "=" * 70)
    print("DEFENSE ARGUMENTS")
    print("=" * 70)
    print(output)


def test_lexigraph():
    from lexigraph import retrieve, _print_results
    query  = CUSTOM_FACTS["incident"]["summary"]
    result = retrieve(query)
    _print_results(query, result)


if __name__ == "__main__":
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "judge"

    if mode == "judge":
        test_judge()
    elif mode == "defense":
        test_defense()
    elif mode == "lexigraph":
        test_lexigraph()
    else:
        print(f"Unknown mode '{mode}'. Use: judge | defense | lexigraph")
