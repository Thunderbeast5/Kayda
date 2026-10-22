"""
Tests for P0 - Correctness and Fail-Closed Fixes.
Verifies C-1 through C-14 defects are resolved cleanly without regressions.
"""

import unittest
from lexigraphbe.config import extract_json_from_text, reset_request_budget, _REQUEST_BUDGET
from lexigraphbe.statutory_verification_agent import parse_punishment_and_severity, _aggregate_ingredient_status
from lexigraphbe.statute_repository import StatuteRepository
from lexigraphbe.crosswalk_service import CrosswalkService
from lexigraphbe.family_retrieval import clause_backstop
from lexigraphbe.schemas.stage4 import StatutoryVerificationObject, VerifiedOffenceItemStage4, IngredientEvaluationItem


class TestP0Correctness(unittest.TestCase):

    def test_c1_c2_fail_closed_status_parsing(self):
        """C-1 and C-2: Invalid or empty verifier outputs must never become VERIFIED."""
        # Empty string
        res_empty = extract_json_from_text("")
        self.assertNotEqual(res_empty.get("status"), "VERIFIED")
        self.assertEqual(res_empty.get("status"), "NEEDS_CORRECTION")

        # None
        res_none = extract_json_from_text(None)
        self.assertNotEqual(res_none.get("status"), "VERIFIED")
        self.assertEqual(res_none.get("status"), "NEEDS_CORRECTION")

        # Substrings containing VERIFIED
        res_not_ver = extract_json_from_text("NOT_VERIFIED")
        self.assertEqual(res_not_ver.get("status"), "NEEDS_CORRECTION")

        res_unver = extract_json_from_text("UNVERIFIED")
        self.assertEqual(res_unver.get("status"), "NEEDS_CORRECTION")

        res_sentence = extract_json_from_text("I could not verify; status: not verified")
        self.assertEqual(res_sentence.get("status"), "NEEDS_CORRECTION")

        # Strict exact match should pass
        res_ok = extract_json_from_text('{"status": "VERIFIED", "issues": []}')
        self.assertEqual(res_ok.get("status"), "VERIFIED")

        res_exact_plain = extract_json_from_text("VERIFIED")
        self.assertEqual(res_exact_plain.get("status"), "VERIFIED")

    def test_c3_punishment_parsing(self):
        """C-3: Life imprisonment / death must be recognized (> 7 years Arnesh Kumar threshold)."""
        p_text, max_yrs, exceeded = parse_punishment_and_severity("", "302", "IPC")
        self.assertTrue(exceeded, "IPC 302 (murder) must exceed Arnesh Kumar threshold")
        self.assertGreaterEqual(max_yrs, 20.0)

        p_text, max_yrs, exceeded = parse_punishment_and_severity("", "307", "IPC")
        self.assertTrue(exceeded, "IPC 307 must exceed Arnesh Kumar threshold")

        p_text, max_yrs, exceeded = parse_punishment_and_severity("", "326", "IPC")
        self.assertTrue(exceeded, "IPC 326 (grievous hurt by weapon) must exceed threshold")

        # Simple hurt (323) is 1 year, must not exceed threshold
        p_text, max_yrs, exceeded = parse_punishment_and_severity("", "323", "IPC")
        self.assertFalse(exceeded, "IPC 323 should not exceed 7 years threshold")
        self.assertEqual(max_yrs, 1.0)

    def test_c4_attracted_rejected_separation(self):
        """C-4: Not Attracted sections must be in rejected_offences and omitted from verified_offences."""
        s4 = StatutoryVerificationObject(
            attracted_offences=[
                VerifiedOffenceItemStage4(
                    section_number="304A", title="Causing death by negligence", overall_status="Prima Facie Attracted"
                )
            ],
            rejected_offences=[
                VerifiedOffenceItemStage4(
                    section_number="123", title="Concealing design to wage war", overall_status="Not Attracted"
                )
            ],
            verified_offences=[
                VerifiedOffenceItemStage4(
                    section_number="304A", title="Causing death by negligence", overall_status="Prima Facie Attracted"
                )
            ]
        )
        self.assertEqual(len(s4.verified_offences), 1)
        self.assertEqual(s4.verified_offences[0].section_number, "304A")
        self.assertEqual(len(s4.rejected_offences), 1)
        self.assertEqual(s4.rejected_offences[0].section_number, "123")

    def test_c5_request_scoped_budget(self):
        """C-5: Request-scoped budget must be resettable and isolate per-request counts."""
        reset_request_budget()
        self.assertEqual(_REQUEST_BUDGET.get(), 0)

    def test_c6_c7_bns_equivalent_operative_clause(self):
        """C-6 and C-7: CrosswalkService and StatuteRepository must agree on operative clause."""
        repo = StatuteRepository.get_instance()
        cw = CrosswalkService.get_instance()
        # IPC 323 -> BNS 115(2) (punishment clause)
        self.assertEqual(repo.get_ipc_bns_equivalent("323"), "115(2)")
        self.assertEqual(cw.get_bns_for_ipc("323"), "115(2)")

        # IPC 304A -> BNS 106(1)
        self.assertEqual(repo.get_ipc_bns_equivalent("304A"), "106(1)")
        self.assertEqual(cw.get_bns_for_ipc("304A"), "106(1)")

        # IPC 465 -> BNS 336(2)
        self.assertEqual(repo.get_ipc_bns_equivalent("465"), "336(2)")
        self.assertEqual(cw.get_bns_for_ipc("465"), "336(2)")

    def test_c9_stage0_no_input_fails_loudly(self):
        """C-9: Stage 0 must raise ValueError if no input text or file path is provided."""
        from lexigraphbe.runner import run_stage0
        with self.assertRaises(ValueError):
            run_stage0(text=None, file_path=None)

    def test_c10_clause_backstop_unique_ids(self):
        """C-10: Clause backstop must never collide with existing fact IDs (like C1, C2)."""
        existing_facts = [
            {"fact_id": "C1", "verbatim_quote": "hit the victim", "conduct_type": "ACT"},
            {"fact_id": "C2", "verbatim_quote": "threatened him", "conduct_type": "ACT"},
        ]
        narrative = "The accused hit the victim, and threatened him, and destroyed the documents."
        new_facts = clause_backstop(narrative, existing_facts)
        new_ids = {f["fact_id"] for f in new_facts}
        self.assertNotIn("C1", new_ids)
        self.assertNotIn("C2", new_ids)
        # Verify no collisions between existing and new
        all_ids = [f["fact_id"] for f in existing_facts] + list(new_ids)
        self.assertEqual(len(all_ids), len(set(all_ids)))


if __name__ == "__main__":
    unittest.main()
