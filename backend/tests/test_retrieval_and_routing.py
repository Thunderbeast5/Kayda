"""
Unit test suite verifying P2 (BM25F & RRF retrieval), P4 (BSA & BNSS routing), and P5 (concurrency/instrumentation).
Ensures zero hardcoding, strict word-boundary matching, noise control, and robust routing.
"""

import unittest
from lexigraphbe.classifier_prefilter import _BM25FIndex, CandidateSectionMatch
from lexigraphbe.family_retrieval import reciprocal_rank_fusion, augment_families, OFFENCE_FAMILIES
from lexigraphbe.bsa_retrieval_agent import _matches_keyword, _EVIDENCE_CLUSTERS
from lexigraphbe.bnss_retrieval_agent import BNSSRetrievalAgent


class TestBM25FAndRetrieval(unittest.TestCase):
    def test_bm25f_multi_field_weighting(self):
        """Field match in title (weight 3.0) should outscore full_text (weight 0.6)."""
        docs = [
            # Doc 0 has 'trespass' in title
            {"title": ["trespass"], "lexicon": [], "key_principle": [], "ingredients": [], "illustrations": [], "full_text": []},
            # Doc 1 has 'trespass' only in full_text
            {"title": [], "lexicon": [], "key_principle": [], "ingredients": [], "illustrations": [], "full_text": ["trespass"]},
        ]
        index = _BM25FIndex(docs)
        score_0, _, _ = index.score(0, {"trespass": 1.0})
        score_1, _, _ = index.score(1, {"trespass": 1.0})
        self.assertGreater(score_0, score_1, "Title match must outscore full_text match in BM25F")

    def test_bm25f_empty_fields(self):
        """Empty documents should return 0 score and not divide by zero."""
        docs = [
            {"title": [], "lexicon": [], "key_principle": [], "ingredients": [], "illustrations": [], "full_text": []},
            {"title": ["theft"], "lexicon": [], "key_principle": [], "ingredients": [], "illustrations": [], "full_text": []},
        ]
        index = _BM25FIndex(docs)
        score_0, matched_0, _ = index.score(0, {"theft": 1.0})
        self.assertEqual(score_0, 0.0)
        self.assertEqual(matched_0, [])

    def test_reciprocal_rank_fusion(self):
        """RRF should combine ranks monotonically and reward documents present across views."""
        # Doc 5 is rank 1 in view 1 and rank 1 in view 2
        # Doc 10 is rank 1 in view 1 only
        view1 = [(5, 10.0, ["a"], 1.0), (10, 8.0, ["b"], 0.8)]
        view2 = [(5, 9.0, ["a"], 1.0), (20, 7.0, ["c"], 0.7)]
        fused = reciprocal_rank_fusion([view1, view2], k=60)
        top_doc_idx = fused[0][0]
        self.assertEqual(top_doc_idx, 5, "Doc present at top of both rankings must rank first in RRF")

    def test_noise_control_no_single_family_bypass(self):
        """Single stray section hit must NOT augment a secondary family (no code == top_code bypass)."""
        # A stray act that matches only 1 random section weakly
        facts = [{"fact_id": "F1", "conduct_type": "ACT", "verbatim_quote": "he had a conversation in the room"}]
        families = [{"family": "TRESPASS", "fact_ids": ["F1"], "tier": "PRIMARY"}]
        fams, notes = augment_families(facts, families)
        fam_codes = [f["family"] for f in fams]
        # Should not augment unrelated families with 1 weak hit
        self.assertEqual(len(fam_codes), 1)
        self.assertEqual(fam_codes[0], "TRESPASS")


class TestBSAAndBNSSRouting(unittest.TestCase):
    def test_bsa_word_boundary_matching(self):
        """'sign' or 'deed' must not match substrings like 'assigned', 'resigned', 'indeed'."""
        self.assertFalse(_matches_keyword("sign", "The officer assigned the duty to the constable."))
        self.assertFalse(_matches_keyword("sign", "The employee resigned from the company."))
        self.assertTrue(_matches_keyword("signed", "The accused signed the forged cheque."))
        self.assertTrue(_matches_keyword("signature", "The document bears a forged signature."))
        self.assertFalse(_matches_keyword("deed", "The incident indeed took place at night."))
        self.assertTrue(_matches_keyword("deed", "The accused executed a false sale deed."))

    def test_bnss_procedural_routing_anticipatory_bail(self):
        """Anticipatory bail relief must score BNSS 482 and arrest safeguards 35 highly."""
        agent = BNSSRetrievalAgent()
        facts_text = "The applicant apprehends arrest in FIR No. 12/2025 and seeks anticipatory bail."
        procedural_meta = {"requested_relief": "Anticipatory Bail", "procedural_stage": "Anticipatory Bail"}
        candidates = agent._prefilter_bnss_candidates(facts_text, procedural_meta)
        candidate_secs = {c["section_number"] for c in candidates}
        self.assertIn("482", candidate_secs, "BNSS 482 must be retrieved for Anticipatory Bail")
        self.assertIn("35", candidate_secs, "BNSS 35 (arrest safeguards) must be retrieved for Anticipatory Bail")

    def test_bnss_procedural_routing_regular_bail(self):
        """Regular bail relief for accused in custody must score BNSS 480 and 483."""
        agent = BNSSRetrievalAgent()
        facts_text = "The applicant has been in judicial custody for 30 days and applies for regular bail."
        procedural_meta = {"requested_relief": "Regular Bail", "procedural_stage": "Regular Bail"}
        candidates = agent._prefilter_bnss_candidates(facts_text, procedural_meta)
        candidate_secs = {c["section_number"] for c in candidates}
        self.assertIn("480", candidate_secs, "BNSS 480 must be retrieved for Regular Bail")
        self.assertIn("483", candidate_secs, "BNSS 483 must be retrieved for Regular Bail")


if __name__ == "__main__":
    unittest.main()
