"""
Regression test suite verifying ground-truth statutory metadata against the First Schedule of CrPC / BNSS and Special Acts.
Guarantees that section punishments, cognizability, and bailability match ground truth before deployment.
"""

import pytest
from lexigraphbe.statute_repository import StatuteRepository
from lexigraphbe.classifier_prefilter import STATUTE_KNOWLEDGE_BASE


# Ground Truth Matrix from First Schedule of CrPC / BNSS
GROUND_TRUTH_MATRIX = [
    {
        "section": "498A",
        "statute": "IPC",
        "cognizable": True,
        "bailable": False,  # Non-bailable under CrPC First Schedule
        "punishment_maximum": "3 Years",
        "chapter_number": "XXA",
    },
    {
        "section": "304B",
        "statute": "IPC",
        "cognizable": True,
        "bailable": False,  # Non-bailable
        "punishment_minimum": "7 Years",
        "punishment_maximum": "Life Imprisonment",
        "chapter_number": "XVI",
    },
    {
        "section": "302",
        "statute": "IPC",
        "cognizable": True,
        "bailable": False,  # Non-bailable
        "punishment_minimum": "Life Imprisonment",
        "punishment_maximum": "Death",
    },
    {
        "section": "307",
        "statute": "IPC",
        "cognizable": True,
        "bailable": False,  # Non-bailable
        "punishment_maximum": "10 Years",
    },
    {
        "section": "376",
        "statute": "IPC",
        "cognizable": True,
        "bailable": False,  # Non-bailable
        "punishment_minimum": "10 Years",
        "punishment_maximum": "Life Imprisonment",
    },
    {
        "section": "406",
        "statute": "IPC",
        "cognizable": True,
        "bailable": False,  # Non-bailable under CrPC First Schedule
        "punishment_maximum": "3 Years",
    },
    {
        "section": "506",
        "statute": "IPC",
        "cognizable": False,  # Simple intimidation is Non-cognizable under standard CrPC
        "bailable": True,    # Bailable under standard CrPC First Schedule
        "punishment_maximum": "2 Years",
    },
    {
        "section": "323",
        "statute": "IPC",
        "cognizable": False,  # Voluntarily causing hurt is Non-cognizable
        "bailable": True,    # Bailable
        "punishment_maximum": "1 Year",
    },
    {
        "section": "Section 4",
        "statute": "Dowry Prohibition Act",
        "cognizable": True,  # Cognizable as per S.8 DP Act
        "bailable": True,    # Bailable as per S.8 DP Act
        "punishment_minimum": "6 Months",
        "punishment_maximum": "2 Years",
    },
    # --- Serious offences: Cognizable, Non-bailable, 7 Years ---
    {
        "section": "420",
        "statute": "IPC",
        "cognizable": True,   # Cognizable
        "bailable": False,    # Non-bailable (First Schedule IPC)
        "punishment_maximum": "7 Years",
    },
    {
        "section": "468",
        "statute": "IPC",
        "cognizable": True,   # Cognizable
        "bailable": False,    # Non-bailable (First Schedule IPC)
        "punishment_maximum": "7 Years",
    },
    # --- Minor offences: Non-cognizable, Bailable, 2 Years ---
    {
        "section": "465",
        "statute": "IPC",
        "cognizable": False,  # Non-cognizable (First Schedule IPC)
        "bailable": True,     # Bailable (First Schedule IPC)
        "punishment_maximum": "2 Years",
    },
    {
        "section": "423",
        "statute": "IPC",
        "cognizable": False,  # Non-cognizable (First Schedule IPC)
        "bailable": True,     # Bailable (First Schedule IPC)
        "punishment_maximum": "2 Years",
    },
    {
        "section": "403",
        "statute": "IPC",
        "cognizable": False,  # Non-cognizable (First Schedule IPC)
        "bailable": True,     # Bailable (First Schedule IPC)
        "punishment_maximum": "2 Years",
    },
]


def test_first_schedule_repository_ground_truth():
    """
    Verifies StatuteRepository.get_first_schedule_metadata against ground-truth values.
    """
    repo = StatuteRepository.get_instance()

    for item in GROUND_TRUTH_MATRIX:
        sec = item["section"]
        meta = repo.get_first_schedule_metadata(sec, item["statute"])
        assert meta is not None, f"Metadata missing for section {sec}"
        assert meta["cognizable"] == item["cognizable"], f"Cognizability mismatch for {sec}: expected {item['cognizable']}, got {meta['cognizable']}"
        assert meta["bailable"] == item["bailable"], f"Bailability mismatch for {sec}: expected {item['bailable']}, got {meta['bailable']}"
        assert meta["punishment_maximum"] == item["punishment_maximum"], f"Punishment max mismatch for {sec}: expected {item['punishment_maximum']}, got {meta['punishment_maximum']}"
        if "punishment_minimum" in item:
            assert meta["punishment_minimum"] == item["punishment_minimum"], f"Punishment min mismatch for {sec}: expected {item['punishment_minimum']}, got {meta['punishment_minimum']}"


def test_statute_knowledge_base_ground_truth_compliance():
    """
    Verifies that all SectionRules in STATUTE_KNOWLEDGE_BASE strictly comply with First Schedule values.
    """
    for rule in STATUTE_KNOWLEDGE_BASE:
        matching_gt = next((g for g in GROUND_TRUTH_MATRIX if g["section"].upper() in rule.section.upper() or rule.section.upper() in g["section"].upper()), None)
        if matching_gt:
            assert rule.cognizable == matching_gt["cognizable"], f"Knowledge base rule {rule.section} cognizable mismatch"
            assert rule.bailable == matching_gt["bailable"], f"Knowledge base rule {rule.section} bailable mismatch"
            assert rule.punishment_maximum == matching_gt["punishment_maximum"], f"Knowledge base rule {rule.section} punishment max mismatch"
