"""
Clarification question generation prompt.

Used by QuestionGenerator service when the scoring pass
returns SUFFICIENCY: NO.
"""

QUESTION_GENERATION_PROMPT = """\
{system_prompt}

You identified the following gaps during argument evaluation:

GAPS DETECTED:
{gaps}

EXISTING ARGUMENTS:
Defence: {defence_arguments}
Prosecution: {prosecution_arguments}
IO Report: {investigation_report}

Generate up to {max_questions} targeted clarification questions.
Each question must address a SPECIFIC factual or legal gap.
Direct each question to the correct party.

Respond in EXACTLY this format (one question per line):
TARGET: <Defence / Prosecution / IO Agent> | ISSUE: <gap in one phrase> | QUESTION: <precise one-sentence question>

Rules:
- Do NOT ask about facts already stated in the arguments or investigation report.
- Do NOT ask generic questions — be specific to this case.
- Do NOT ask more than {max_questions} questions.
- If no clarification is needed, respond with: NO QUESTIONS NEEDED
"""
