"""
Per-phase LLM prompts for the BailJudgeAgent.

SCORING_PROMPT  — Phase 2: evaluate arguments, score, detect gaps
FINDINGS_PROMPT — Phase 7: form final judicial findings as JSON
"""

# ── Phase 2: Argument Scoring ─────────────────────────────────────────────────

SCORING_PROMPT = """\
{system_prompt}

═══════════════════════════════════════════════════════
ANTICIPATORY BAIL HEARING — ARGUMENT EVALUATION PHASE
═══════════════════════════════════════════════════════

CASE FACTS:
{structured_case_context}

EVIDENCE:
{evidence_context}

APPLICABLE LAW (sections and acts from LexiGraph — do NOT use any others):
{legal_context_package}

PRECEDENTS (from Precedent Retrieval Agent — do NOT cite any others):
{precedent_context}

BAIL ASSESSMENT REPORT:
{bail_assessment_report}

DEFENCE ARGUMENTS:
{defence_arguments}

PROSECUTION ARGUMENTS:
{prosecution_arguments}

INVESTIGATION REPORT:
{investigation_report}

COURTROOM HISTORY SO FAR:
{courtroom_state_memory}

═══════════════════════════════════════════════════════
YOUR TASK
═══════════════════════════════════════════════════════
Score BOTH arguments independently on three axes (each 0-10):
  • Legal Validity   — are the cited sections correctly applied to the facts?
  • Evidence Linkage — do the facts actually support the legal claim?
  • Logic Coherence  — is the argument internally consistent?

Then determine if the arguments are SUFFICIENT to form a preliminary finding,
or if you need clarification from any party.

Respond in EXACTLY this format (no extra text outside the format):

DEFENCE SCORES:
Legal Validity: <0-10>
Evidence Linkage: <0-10>
Logic Coherence: <0-10>

PROSECUTION SCORES:
Legal Validity: <0-10>
Evidence Linkage: <0-10>
Logic Coherence: <0-10>

SUFFICIENCY: <YES or NO>

QUESTIONS (only if SUFFICIENCY is NO — list up to 3, one per line):
TARGET: <Defence / Prosecution / IO Agent> | ISSUE: <gap> | QUESTION: <precise one-sentence question>

NEW LEGAL ISSUES DETECTED (list any sections/acts raised in arguments but NOT in APPLICABLE LAW above, one per line, or write NONE):
"""

# ── Phase 7: Final Judicial Findings ─────────────────────────────────────────

FINDINGS_PROMPT = """\
{system_prompt}

═══════════════════════════════════════════════════════
ANTICIPATORY BAIL HEARING — FINAL JUDICIAL FINDINGS
═══════════════════════════════════════════════════════

CASE FACTS:
{structured_case_context}

EVIDENCE:
{evidence_context}

APPLICABLE LAW (ONLY cite from this list):
{legal_context_package}

PRECEDENTS (ONLY cite from this list):
{precedent_context}

BAIL ASSESSMENT REPORT:
{bail_assessment_report}

DEFENCE ARGUMENTS:
{defence_arguments}

PROSECUTION ARGUMENTS:
{prosecution_arguments}

INVESTIGATION REPORT:
{investigation_report}

ANSWERS TO JUDGE'S QUESTIONS:
{questions_and_answers}

FINAL SUBMISSIONS:
Defence: {defence_final_submission}
Prosecution: {prosecution_final_submission}

ARGUMENT SCORES (from scoring pass):
Defence — Legal Validity: {def_lv}, Evidence Linkage: {def_el}, Logic Coherence: {def_lc}, Total: {def_total}/30
Prosecution — Legal Validity: {pro_lv}, Evidence Linkage: {pro_el}, Logic Coherence: {pro_lc}, Total: {pro_total}/30

═══════════════════════════════════════════════════════
YOUR TASK
═══════════════════════════════════════════════════════
Form the FINAL JUDICIAL FINDINGS in the JSON schema below.
Apply ALL nine bail factors. Apply the statutes and precedents listed above ONLY.
Balance liberty (Article 21) against the needs of investigation.
Write "judicial_analysis" as 3-5 formal paragraphs as a sitting Indian judge would.
List bail conditions if the preliminary finding is "Bail Likely Granted".

Return ONLY valid JSON — no markdown fences, no commentary outside the JSON.

{{
  "case_id": "{case_id}",
  "hearing_date": "{hearing_date}",
  "judge_name": "AI Judge",
  "applicant": "{applicant}",
  "respondent": "{respondent}",
  "sections_applied": ["<only from APPLICABLE LAW above>"],
  "constitutional_articles_applied": ["<e.g. Article 21>"],
  "precedents_applied": [
    {{
      "case_name": "<only from PRECEDENTS above>",
      "citation": "<citation>",
      "principle_applied": "<ratio decidendi applied>"
    }}
  ],
  "evidence_evaluation": {{
    "strength": "<High / Medium / Low>",
    "key_evidence": ["<item>"],
    "contradictions_noted": ["<item or empty list>"],
    "missing_evidence": ["<item or empty list>"]
  }},
  "bail_factor_analysis": {{
    "gravity_of_offence": "<High / Medium / Low>",
    "flight_risk": "<High / Medium / Low>",
    "custodial_need": "<Yes / No>",
    "witness_tampering_risk": "<High / Medium / Low>",
    "antecedents": "<None or description>",
    "mitigating_factors": ["<factor>"],
    "aggravating_factors": ["<factor>"]
  }},
  "argument_evaluation": {{
    "defence_score": {{
      "legal_validity": {def_lv},
      "evidence_linkage": {def_el},
      "logic_coherence": {def_lc},
      "total": {def_total}
    }},
    "prosecution_score": {{
      "legal_validity": {pro_lv},
      "evidence_linkage": {pro_el},
      "logic_coherence": {pro_lc},
      "total": {pro_total}
    }}
  }},
  "judicial_analysis": "<3-5 formal paragraphs>",
  "preliminary_finding": "<Bail Likely Granted / Bail Likely Rejected / Inconclusive>",
  "confidence": <0-100>,
  "conditions_if_granted": ["<condition if Bail Likely Granted, else empty list>"],
  "questions_asked": {questions_asked_json},
  "dynamic_retrieval_triggered": {dynamic_retrieval_triggered},
  "new_issues_identified": {new_issues_json}
}}
"""
