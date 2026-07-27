"""
evidence_ranking_service.py
===========================
Evidence Ranking Engine.

Ranks retrieved statutory and case-derived evidence types by:
1. Direct Query Semantic Triggers (40%)
2. Statutory Ingredient Fact Nexus (35%)
3. BSA 2023 Evidentiary Hierarchy Base Weight (25%)
"""

import re
from typing import Dict, Any, List


BASE_EVIDENCE_WEIGHTS = {
    "Dying Declaration": 5.0,
    "Postmortem Report": 5.0,
    "Medical Report": 4.5,
    "Statement under Section 164": 4.5,
    "FSL Report": 4.5,
    "DNA Report": 4.5,
    "CCTV Footage": 4.0,
    "Inquest Report": 4.0,
    "Witness Statement": 4.0,
    "Marriage Certificate": 3.5,
    "Call Detail Records (CDR)": 3.0,
    "WhatsApp Chats": 3.0,
    "Bank Transaction": 2.5,
    "Audio Recording": 2.5,
    "Birth Certificate": 2.0
}

QUERY_EVIDENCE_TRIGGERS = {
    "dying declaration": ["Dying Declaration"],
    "burned": ["Postmortem Report", "Medical Report", "Inquest Report"],
    "burns": ["Postmortem Report", "Medical Report", "Inquest Report"],
    "fire": ["Postmortem Report", "Inquest Report"],
    "death": ["Postmortem Report", "Inquest Report", "Dying Declaration"],
    "killed": ["Postmortem Report", "Inquest Report"],
    "hospital": ["Medical Report", "Dying Declaration"],
    "dowry": ["Witness Statement", "Marriage Certificate", "WhatsApp Chats", "Bank Transaction"],
    "harassed": ["Witness Statement"],
    "assault": ["Medical Report", "Witness Statement", "CCTV Footage"],
    "acid": ["Medical Report", "FSL Report", "CCTV Footage"],
    "rape": ["Medical Report", "FSL Report", "DNA Report", "Statement under Section 164"]
}


class EvidenceRankingService:
    """Ranks evidence types dynamically based on query triggers, fact nexus, and BSA weights."""

    def rank_evidence(self, evidence_list: List[str], query: str, facts: Dict[str, Any] = None, max_items: int = 6) -> List[str]:
        if not evidence_list:
            return []

        facts = facts or {}
        q_lower = query.lower()

        # Identify evidence items explicitly triggered by query
        triggered_items = set()
        for kw, ev_targets in QUERY_EVIDENCE_TRIGGERS.items():
            if kw in q_lower:
                for target in ev_targets:
                    triggered_items.add(target)

        scored_evidence = []
        for ev in set(evidence_list):
            base_w = BASE_EVIDENCE_WEIGHTS.get(ev, 3.0)
            
            # 1. Direct Query Mention Trigger Score (0.40 weight)
            trigger_score = 1.0 if (ev in triggered_items or ev.lower() in q_lower) else 0.20
            
            # 2. Fact Nexus Score (0.35 weight)
            nexus_score = 0.30
            if facts.get("death") and ev in ["Postmortem Report", "Inquest Report", "Dying Declaration", "Medical Report"]:
                nexus_score = 1.0
            elif facts.get("dowry_demand") and ev in ["Witness Statement", "Marriage Certificate", "WhatsApp Chats"]:
                nexus_score = 0.90
            elif facts.get("physical_force_or_assault") and ev in ["Medical Report", "Witness Statement", "CCTV Footage"]:
                nexus_score = 0.85
            elif facts.get("sexual_penetration") and ev in ["Medical Report", "FSL Report", "DNA Report", "Statement under Section 164"]:
                nexus_score = 1.0

            # 3. BSA Evidentiary Base Weight Score (0.25 weight)
            bsa_score = base_w / 5.0

            composite_score = (0.40 * trigger_score) + (0.35 * nexus_score) + (0.25 * bsa_score)
            scored_evidence.append((ev, round(composite_score, 4)))

        # Sort descending by composite relevance score
        scored_evidence.sort(key=lambda x: x[1], reverse=True)
        ranked_names = [item[0] for item in scored_evidence[:max_items]]

        return ranked_names
