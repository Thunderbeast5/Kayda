"""
BailJudgeAgent — Phase 1 + Phase 2
====================================
Anticipatory Bail Virtual Moot Court

Phase 1: Core scoring + findings
Phase 2: QuestionGenerator, CourtRoomStateMemory, answer ingestion

LLM: Ollama llama3.2:3b (dev) → OpenAI gpt-4o-mini (prod)
Switch: set LLM_PROVIDER=openai in judge_agents/.env
"""

import json
from datetime import datetime
from typing import Optional, TypedDict

from .llm_config import get_llm
from .courtroom_memory import CourtRoomStateMemory, get_memory, clear_memory
from .models.hearing_state import HearingState, HearingContext
from .models.question_model import JudgeQuestion, QuestionTarget
from .models.judicial_findings import JudicialFindings, QuestionRecord
from .prompts.system_prompt import JUDGE_SYSTEM_PROMPT
from .prompts.hearing_phase_prompts import SCORING_PROMPT, FINDINGS_PROMPT
from .services.argument_evaluator import ArgumentEvaluator
from .services.bail_factor_analyzer import BailFactorAnalyzer
from .services.findings_builder import FindingsBuilder
from .services.question_generator import QuestionGenerator
from .services.issue_detector import IssueDetector
from .dynamic_retrieval import DynamicRetrievalTrigger, RetrievalCallback

MAX_QUESTIONS_PER_HEARING = 5
MAX_DEBATE_ROUNDS         = 2


# ── BailJudgeAgent ─────────────────────────────────────────────────────────────

class BailJudgeAgent:
    """
    Core Judge Agent — Phase 1 + Phase 2.

    Lifecycle per hearing
    ─────────────────────
    1. start_hearing(case_id)              → initialise state + memory
    2. score(case_id, ...)                 → Pass 1: score + generate questions
    3. ingest_answers(case_id, answers)    → Phase 2: record answers in memory
    4. form_findings(case_id, ...)         → Pass 2: final judicial findings
    5. end_hearing(case_id)                → cleanup memory
    """

    def __init__(self, retrieval_callback: Optional[RetrievalCallback] = None):
        self.llm                = get_llm(temperature=0.1)
        self._evaluator         = ArgumentEvaluator()
        self._bail_analyzer     = BailFactorAnalyzer()
        self._findings_builder  = FindingsBuilder()
        self._question_generator = QuestionGenerator()
        self._issue_detector    = IssueDetector()
        self._retrieval_trigger = DynamicRetrievalTrigger(
            retrieval_callback=retrieval_callback,
            max_retrievals=2,
        )
        self._contexts: dict[str, HearingContext] = {}
        # Tracks the latest merged context packages per case
        # (updated after each dynamic retrieval)
        self._live_legal_pkg:  dict[str, dict] = {}
        self._live_prec_ctx:   dict[str, dict] = {}

    # ── Session management ─────────────────────────────────────────────────────

    def start_hearing(self, case_id: str) -> CourtRoomStateMemory:
        if case_id in self._contexts:
            raise ValueError(f"Hearing '{case_id}' already started.")
        self._contexts[case_id] = HearingContext(session_id=case_id)
        self._live_legal_pkg[case_id] = {}
        self._live_prec_ctx[case_id]  = {}
        memory = get_memory(case_id)
        memory.add_turn("System", "finding", f"Hearing started for case: {case_id}", round=0)
        return memory

    def _get_context(self, case_id: str) -> HearingContext:
        if case_id not in self._contexts:
            self._contexts[case_id] = HearingContext(session_id=case_id)
        return self._contexts[case_id]

    def _transition(self, case_id: str, new_state: HearingState) -> None:
        self._get_context(case_id).transition(new_state)
        print(f"[BailJudge] [{case_id}] → {new_state.value}")

    def end_hearing(self, case_id: str) -> None:
        self._contexts.pop(case_id, None)
        self._live_legal_pkg.pop(case_id, None)
        self._live_prec_ctx.pop(case_id, None)
        clear_memory(case_id)

    def update_context(
        self,
        case_id: str,
        legal_context_package: dict,
        precedent_context: dict | list,
    ) -> None:
        """
        Phase 3: Store the latest merged context packages for a hearing.
        Called automatically after dynamic retrieval.
        Can also be called externally by the Orchestrator (Phase 4).
        """
        self._live_legal_pkg[case_id] = dict(legal_context_package)
        self._live_prec_ctx[case_id]  = (
            dict(precedent_context)
            if isinstance(precedent_context, dict)
            else {"similar_cases": list(precedent_context)}
        )

    def get_live_context(self, case_id: str) -> tuple[dict, dict]:
        """Return the latest legal and precedent context for a hearing."""
        return (
            self._live_legal_pkg.get(case_id, {}),
            self._live_prec_ctx.get(case_id, {}),
        )

    # ── LLM call ───────────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> str:
        return self.llm.invoke(prompt).content

    # ── Pass 1: Score ──────────────────────────────────────────────────────────

    def score(
        self,
        case_id: str,
        structured_case_context: dict,
        evidence_context: dict,
        legal_context_package: dict,
        precedent_context: dict | list,
        bail_assessment_report: dict,
        defence_arguments: str,
        prosecution_arguments: str,
        investigation_report: str,
        courtroom_state_memory: list[dict] | str = "",
    ) -> tuple[dict, list[JudgeQuestion], list[str]]:
        """
        Scoring pass: evaluate arguments, use QuestionGenerator for gap-based
        questions, and write everything to CourtRoomStateMemory.

        Returns
        -------
        evaluation_dict : {defence_score, prosecution_score}
        questions       : list[JudgeQuestion] (empty if sufficient)
        new_issues      : list[str] for dynamic retrieval
        """
        ctx    = self._get_context(case_id)
        memory = get_memory(case_id)

        # ── One-time opening transitions ──
        if ctx.current_state == HearingState.IDLE:
            self._transition(case_id, HearingState.RECEIVING_INPUTS)
            self._transition(case_id, HearingState.COMPREHENDING_CASE)
            self._transition(case_id, HearingState.HEARING_OPEN)

        if ctx.current_state in (
            HearingState.HEARING_OPEN,
            HearingState.AWAITING_ANSWERS,
            HearingState.AWAITING_RETRIEVAL,
        ):
            self._transition(case_id, HearingState.EVALUATING_ARGUMENTS)

        ctx.debate_round += 1

        # ── Write arguments to memory ──
        memory.add_turn("Defence",     "argument", defence_arguments,    round=ctx.debate_round)
        memory.add_turn("Prosecution", "argument", prosecution_arguments, round=ctx.debate_round)
        memory.add_turn("IO Agent",    "argument", investigation_report,  round=ctx.debate_round)

        # ── Build memory context string for prompt ──
        memory_str = (
            memory.to_summary_string()
            if not courtroom_state_memory
            else (
                json.dumps(courtroom_state_memory, indent=2)
                if isinstance(courtroom_state_memory, list)
                else str(courtroom_state_memory)
            )
        )

        # ── LLM scoring call ──
        prompt = SCORING_PROMPT.format(
            system_prompt           = JUDGE_SYSTEM_PROMPT,
            structured_case_context = json.dumps(structured_case_context, indent=2),
            evidence_context        = json.dumps(evidence_context, indent=2),
            legal_context_package   = json.dumps(legal_context_package, indent=2),
            precedent_context       = json.dumps(precedent_context, indent=2),
            bail_assessment_report  = json.dumps(bail_assessment_report, indent=2),
            defence_arguments       = defence_arguments,
            prosecution_arguments   = prosecution_arguments,
            investigation_report    = investigation_report,
            courtroom_state_memory  = memory_str,
        )
        raw_output = self._call_llm(prompt)
        evaluation, is_sufficient, raw_questions, new_issues = self._evaluator.parse(raw_output)

        # ── Phase 3: IssueDetector ──────────────────────────────────────────
        # Scan all argument texts for sections/articles/precedents not in context
        detection = self._issue_detector.detect(
            texts={
                "Defence":     defence_arguments,
                "Prosecution": prosecution_arguments,
                "IO Agent":    investigation_report,
            },
            legal_context_package=legal_context_package,
            precedent_context=precedent_context,
        )

        # Merge LLM-detected new issues with deterministic detection
        all_new_issues = list(new_issues) + [i.reference for i in detection.new_issues]
        # Deduplicate
        seen_issues: set[str] = set()
        deduped_issues: list[str] = []
        for issue in all_new_issues:
            if issue not in seen_issues:
                seen_issues.add(issue)
                deduped_issues.append(issue)
        new_issues = deduped_issues

        # ── Phase 3: DynamicRetrievalTrigger ──────────────────────────────
        retrieval_result = None
        if detection.retrieval_required and ctx.can_trigger_retrieval():
            retrieval_result = self._retrieval_trigger.trigger(
                detection_result      = detection,
                legal_context_package = legal_context_package,
                precedent_context     = precedent_context,
                memory                = memory,
                case_id               = case_id,
                debate_round          = ctx.debate_round,
            )
            # Update live context with merged packages
            if retrieval_result.triggered:
                ctx.dynamic_retrieval_count += 1
                self.update_context(
                    case_id,
                    retrieval_result.updated_legal_context_package,
                    retrieval_result.updated_precedent_context,
                )
                legal_context_package = retrieval_result.updated_legal_context_package
                precedent_context     = retrieval_result.updated_precedent_context

        # ── Phase 2: QuestionGenerator ──
        # Use QuestionGenerator (deterministic gap detection + LLM wording)
        # when the LLM scoring pass returns insufficient OR we detect gaps
        # independently. QuestionGenerator enforces the budget guard.
        questions: list[JudgeQuestion] = []

        if not is_sufficient:
            # Try QuestionGenerator first (deterministic gaps → precise LLM wording)
            questions = self._question_generator.generate(
                context               = ctx,
                evidence_context      = evidence_context,
                legal_context_package = legal_context_package,
                defence_arguments     = defence_arguments,
                prosecution_arguments = prosecution_arguments,
                investigation_report  = investigation_report,
                bail_assessment_report= bail_assessment_report,
                debate_round          = ctx.debate_round,
            )

            # Fallback: if QuestionGenerator found no gaps but LLM found questions,
            # use the LLM-sourced questions (budget still enforced)
            if not questions and raw_questions and ctx.can_ask_question(MAX_QUESTIONS_PER_HEARING):
                slots = MAX_QUESTIONS_PER_HEARING - ctx.questions_asked_count
                for rq in raw_questions[:slots]:
                    t = rq.get("target", "").lower()
                    if "defence" in t or "defense" in t:
                        target = QuestionTarget.DEFENCE
                    elif "prosecution" in t:
                        target = QuestionTarget.PROSECUTION
                    else:
                        target = QuestionTarget.IO_AGENT
                    questions.append(JudgeQuestion(
                        target=target,
                        issue=rq.get("issue", "Unspecified gap"),
                        question=rq.get("question", ""),
                        round=ctx.debate_round,
                    ))
                ctx.questions_asked_count += len(questions)

        # ── Write questions to memory ──
        for q in questions:
            memory.record_question(q.question, q.target.value, q.issue, ctx.debate_round)

        # ── State transitions ──
        if questions:
            self._transition(case_id, HearingState.QUESTIONING)
            self._transition(case_id, HearingState.AWAITING_ANSWERS)
        elif retrieval_result and retrieval_result.triggered:
            # Retrieval already done — resume evaluation with updated context
            self._transition(case_id, HearingState.DETECTING_NEW_ISSUES)
            self._transition(case_id, HearingState.AWAITING_RETRIEVAL)
        elif new_issues and ctx.can_trigger_retrieval():
            # LLM detected issues but IssueDetector didn't trigger retrieval
            ctx.dynamic_retrieval_count += 1
            self._transition(case_id, HearingState.DETECTING_NEW_ISSUES)
            self._transition(case_id, HearingState.AWAITING_RETRIEVAL)
        else:
            self._transition(case_id, HearingState.DETECTING_NEW_ISSUES)
            self._transition(case_id, HearingState.HEARING_FINAL_SUBS)

        p = evaluation.prosecution_score
        d = evaluation.defence_score
        print(
            f"[BailJudge] Round {ctx.debate_round} — "
            f"Prosecution: {p.total}/30 | Defence: {d.total}/30 | "
            f"Sufficient: {is_sufficient} | Questions: {len(questions)} | "
            f"New issues: {len(new_issues)}"
        )
        return evaluation.model_dump(), questions, new_issues

    # ── Phase 2: Answer ingestion ──────────────────────────────────────────────

    def ingest_answers(
        self,
        case_id: str,
        answers: list[dict],
    ) -> list[JudgeQuestion]:
        """
        Record answers to Judge questions in CourtRoomStateMemory.

        Parameters
        ----------
        answers : list of dicts, each with keys:
            {
              "question_index": int,   — 0-based index in judge_questions list
              "respondent": str,       — "Defence" / "Prosecution" / "IO Agent"
              "answer": str,           — the answer text
              "round": int             — debate round
            }

        Returns
        -------
        Updated list of JudgeQuestion objects with .answer filled.
        """
        memory = get_memory(case_id)
        ctx    = self._get_context(case_id)

        # Transition from AWAITING_ANSWERS → EVALUATING_ARGUMENTS
        if ctx.current_state == HearingState.AWAITING_ANSWERS:
            self._transition(case_id, HearingState.EVALUATING_ARGUMENTS)

        updated_questions: list[JudgeQuestion] = []
        for item in answers:
            idx        = item.get("question_index", 0)
            respondent = item.get("respondent", "Unknown")
            answer_txt = item.get("answer", "")
            round_num  = item.get("round", ctx.debate_round)

            memory.record_answer(answer_txt, respondent, idx, round_num)

            # Reconstruct the question from memory
            if idx < len(memory._questions):
                q_turn = memory._questions[idx]
                target_str = str(q_turn.metadata.get("target", "")).lower()
                if "defence" in target_str or "defense" in target_str:
                    target = QuestionTarget.DEFENCE
                elif "prosecution" in target_str:
                    target = QuestionTarget.PROSECUTION
                else:
                    target = QuestionTarget.IO_AGENT

                updated_questions.append(JudgeQuestion(
                    target=target,
                    issue=q_turn.metadata.get("issue", ""),
                    question=q_turn.content,
                    answer=answer_txt,
                    round=round_num,
                ))

        print(f"[BailJudge] Ingested {len(answers)} answer(s) for case '{case_id}'.")
        return updated_questions

    # ── Pass 2: Form findings ──────────────────────────────────────────────────

    def form_findings(
        self,
        case_id: str,
        structured_case_context: dict,
        evidence_context: dict,
        legal_context_package: dict,
        precedent_context: dict | list,
        bail_assessment_report: dict,
        defence_arguments: str,
        prosecution_arguments: str,
        investigation_report: str,
        argument_evaluation: dict,
        questions_and_answers: list[JudgeQuestion],
        new_issues: list[str],
        defence_final_submission: str = "",
        prosecution_final_submission: str = "",
    ) -> JudicialFindings:
        """
        Findings pass — uses full CourtRoomStateMemory as context.
        """
        ctx    = self._get_context(case_id)
        memory = get_memory(case_id)

        # Write final submissions to memory
        if defence_final_submission:
            memory.add_turn("Defence", "submission", defence_final_submission, round=ctx.debate_round)
        if prosecution_final_submission:
            memory.add_turn("Prosecution", "submission", prosecution_final_submission, round=ctx.debate_round)

        if ctx.current_state in (
            HearingState.AWAITING_ANSWERS,
            HearingState.AWAITING_RETRIEVAL,
            HearingState.DETECTING_NEW_ISSUES,
            HearingState.EVALUATING_ARGUMENTS,
        ):
            self._transition(case_id, HearingState.HEARING_FINAL_SUBS)

        self._transition(case_id, HearingState.FORMING_FINDINGS)

        # Use CourtRoomStateMemory Q&A if no explicit questions passed
        if not questions_and_answers:
            answered = memory.get_answered_questions()
            for q_turn, a_turn in answered:
                target_str = str(q_turn.metadata.get("target", "")).lower()
                if "defence" in target_str or "defense" in target_str:
                    t = QuestionTarget.DEFENCE
                elif "prosecution" in target_str:
                    t = QuestionTarget.PROSECUTION
                else:
                    t = QuestionTarget.IO_AGENT
                questions_and_answers.append(JudgeQuestion(
                    target=t,
                    issue=q_turn.metadata.get("issue", ""),
                    question=q_turn.content,
                    answer=a_turn.content if a_turn else None,
                    round=q_turn.round,
                ))

        qa_lines = "\n".join(
            f"Q ({q.target.value}): {q.question}\nA: {q.answer or '(no answer received)'}"
            for q in questions_and_answers
        ) or "No clarification questions were asked."

        def_scores = argument_evaluation.get("defence_score", {})
        pro_scores = argument_evaluation.get("prosecution_score", {})
        who        = structured_case_context.get("who", {})
        incident   = structured_case_context.get("incident", {})
        case_id_str = structured_case_context.get("session_id") or case_id
        applicant   = (who.get("accused") or ["Unknown"])[0] if who.get("accused") else "Unknown"
        place       = str(incident.get("place") or "Unknown")
        respondent  = f"State of {place.split(',')[-1].strip()}" if "," in place else f"State of {place}"

        questions_asked_json    = json.dumps([q.to_dict() for q in questions_and_answers], indent=2)
        new_issues_json         = json.dumps(new_issues, indent=2)
        dynamic_triggered_json  = "true" if ctx.dynamic_retrieval_count > 0 else "false"

        prompt = FINDINGS_PROMPT.format(
            system_prompt                = JUDGE_SYSTEM_PROMPT,
            structured_case_context      = json.dumps(structured_case_context, indent=2),
            evidence_context             = json.dumps(evidence_context, indent=2),
            legal_context_package        = json.dumps(legal_context_package, indent=2),
            precedent_context            = json.dumps(precedent_context, indent=2),
            bail_assessment_report       = json.dumps(bail_assessment_report, indent=2),
            defence_arguments            = defence_arguments,
            prosecution_arguments        = prosecution_arguments,
            investigation_report         = investigation_report,
            questions_and_answers        = qa_lines,
            defence_final_submission     = defence_final_submission or "(not provided)",
            prosecution_final_submission = prosecution_final_submission or "(not provided)",
            def_lv    = def_scores.get("legal_validity", 0),
            def_el    = def_scores.get("evidence_linkage", 0),
            def_lc    = def_scores.get("logic_coherence", 0),
            def_total = def_scores.get("total", 0),
            pro_lv    = pro_scores.get("legal_validity", 0),
            pro_el    = pro_scores.get("evidence_linkage", 0),
            pro_lc    = pro_scores.get("logic_coherence", 0),
            pro_total = pro_scores.get("total", 0),
            case_id                     = case_id_str,
            hearing_date                = datetime.now().strftime("%d/%m/%Y"),
            applicant                   = applicant,
            respondent                  = respondent,
            questions_asked_json        = questions_asked_json,
            dynamic_retrieval_triggered = dynamic_triggered_json,
            new_issues_json             = new_issues_json,
        )

        raw_output = self._call_llm(prompt)
        findings   = self._findings_builder.build(
            llm_output            = raw_output,
            legal_context_package = legal_context_package,
            precedent_context     = precedent_context,
            state_history         = list(ctx.state_history),
        )

        # Write finding summary to memory
        memory.add_turn(
            "Judge", "finding",
            f"Preliminary finding: {findings.preliminary_finding} "
            f"(confidence {findings.confidence}%)",
            round=ctx.debate_round,
        )

        self._transition(case_id, HearingState.FINDINGS_COMPLETE)
        print(f"[BailJudge] Findings: {findings.preliminary_finding} ({findings.confidence}%)")
        return findings


# ── LangGraph TypedDict ────────────────────────────────────────────────────────

class BailHearingState(TypedDict, total=False):
    session_id:               str
    structured_case_context:  dict
    evidence_context:         dict
    legal_context_package:    dict
    precedent_context:        dict
    bail_assessment_report:   dict
    defence_arguments:        str
    prosecution_arguments:    str
    investigation_report:     str
    courtroom_state_memory:   list   # list[dict] — serialised HearingTurn objects
    defence_final_submission: str
    prosecution_final_submission: str
    judge_evaluation:         dict
    judge_questions:          list
    judge_new_issues:         list
    judge_debate_round:       int
    judge_findings:           dict


# ── Singleton ──────────────────────────────────────────────────────────────────

_judge_instance: Optional[BailJudgeAgent] = None


def _get_judge() -> BailJudgeAgent:
    global _judge_instance
    if _judge_instance is None:
        _judge_instance = BailJudgeAgent()
    return _judge_instance


# ── LangGraph node functions ───────────────────────────────────────────────────

def bail_judge_score_node(state: dict) -> dict:
    judge   = _get_judge()
    case_id = state.get("session_id", "unknown")
    if case_id not in judge._contexts:
        judge.start_hearing(case_id)

    evaluation, questions, new_issues = judge.score(
        case_id                  = case_id,
        structured_case_context  = state.get("structured_case_context", {}),
        evidence_context         = state.get("evidence_context", {}),
        legal_context_package    = state.get("legal_context_package", {}),
        precedent_context        = state.get("precedent_context", {}),
        bail_assessment_report   = state.get("bail_assessment_report", {}),
        defence_arguments        = state.get("defence_arguments", ""),
        prosecution_arguments    = state.get("prosecution_arguments", ""),
        investigation_report     = state.get("investigation_report", ""),
        courtroom_state_memory   = state.get("courtroom_state_memory", []),
    )
    memory = get_memory(case_id)
    return {
        **state,
        "judge_evaluation":   evaluation,
        "judge_questions":    [q.model_dump() for q in questions],
        "judge_new_issues":   new_issues,
        "judge_debate_round": state.get("judge_debate_round", 0) + 1,
        "courtroom_state_memory": memory.to_list(),
    }


def bail_judge_verdict_node(state: dict) -> dict:
    judge   = _get_judge()
    case_id = state.get("session_id", "unknown")
    raw_qs  = state.get("judge_questions", [])
    questions = _deserialise_questions(raw_qs)

    findings = judge.form_findings(
        case_id                      = case_id,
        structured_case_context      = state.get("structured_case_context", {}),
        evidence_context             = state.get("evidence_context", {}),
        legal_context_package        = state.get("legal_context_package", {}),
        precedent_context            = state.get("precedent_context", {}),
        bail_assessment_report       = state.get("bail_assessment_report", {}),
        defence_arguments            = state.get("defence_arguments", ""),
        prosecution_arguments        = state.get("prosecution_arguments", ""),
        investigation_report         = state.get("investigation_report", ""),
        argument_evaluation          = state.get("judge_evaluation", {}),
        questions_and_answers        = questions,
        new_issues                   = state.get("judge_new_issues", []),
        defence_final_submission     = state.get("defence_final_submission", ""),
        prosecution_final_submission = state.get("prosecution_final_submission", ""),
    )
    memory = get_memory(case_id)
    return {
        **state,
        "judge_findings": findings.to_dict(),
        "courtroom_state_memory": memory.to_list(),
    }


def should_proceed_to_verdict(state: dict) -> str:
    questions    = state.get("judge_questions", [])
    new_issues   = state.get("judge_new_issues", [])
    debate_round = state.get("judge_debate_round", 0)
    if new_issues and debate_round <= MAX_DEBATE_ROUNDS:
        return "needs_retrieval"
    if questions and debate_round <= MAX_DEBATE_ROUNDS:
        return "needs_questions"
    return "verdict"


def _deserialise_questions(raw_qs: list[dict]) -> list[JudgeQuestion]:
    questions: list[JudgeQuestion] = []
    for q in raw_qs:
        t_str = str(q.get("target") or "").lower()
        if "defence" in t_str or "defense" in t_str:
            t = QuestionTarget.DEFENCE
        elif "prosecution" in t_str:
            t = QuestionTarget.PROSECUTION
        else:
            t = QuestionTarget.IO_AGENT
        questions.append(JudgeQuestion(
            target=t, issue=q.get("issue", ""),
            question=q.get("question", ""), answer=q.get("answer"),
            round=q.get("round", 1),
        ))
    return questions
