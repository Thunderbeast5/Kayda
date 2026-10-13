import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Literal

backend_dir = Path(__file__).resolve().parent.parent
prosecutor_dir = Path(__file__).resolve().parent
for _p in [str(backend_dir), str(prosecutor_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from prosecutor.lexigraph_agent import LexiGraphAgent
except ImportError:
    from lexigraph_agent import LexiGraphAgent

try:
    from prosecutor.services.citation_formatter_service import get_citation_formatter
except ImportError:
    from services.citation_formatter_service import get_citation_formatter

try:
    from agents.config.llm_config import get_llm
except ModuleNotFoundError:
    from config.llm_config import get_llm


Phase = Literal["opening", "rebuttal", "closing"]

MAX_CORRECTION_ATTEMPTS = 2  # generation retries when verify_claims flags something


@dataclass
class ProsecutorTurnResult:
    phase: str
    theory_of_case: str
    statutory_basis: str
    precedent_support: str
    legal_principles: str
    application_to_facts: str
    prioritization: str
    spoken_argument: str
    verification: Dict[str, Any]
    production_output: Dict[str, Any] = field(default_factory=dict)
    # New: surfaces trust/quality info to the UI instead of hiding it.
    is_verified_clean: bool = True
    correction_attempts: int = 0
    auto_redacted: List[str] = field(default_factory=list)
    coaching_notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Shared rules that apply regardless of trial phase. Phase-specific guidance
# (opening / rebuttal / closing) is layered on top in _build_system_prompt so
# each phase gets behaviorally distinct instructions instead of one generic
# prompt reused for every turn of a multi-round moot court.
# ---------------------------------------------------------------------------
PROSECUTOR_CORE_RULES_TEMPLATE = """You are the Public Prosecutor in a High Court / Sessions Court opposing an application for ANTICIPATORY BAIL ({bail_provision}), in a live moot-court simulation against a law student.

YOUR MANDATE:
Argue forcefully against granting pre-arrest bail to the applicant using ONLY the verified statutory sections and precedents provided in the CONTEXT below. Never invent, guess, or recall a section number or case name from general knowledge — if it is not in the CONTEXT, do not cite it. If the context is thin on a point, argue from what IS present rather than filling the gap with an invented authority.

LEGAL CODE IN FORCE FOR THIS CASE: {regime_statement}
{code_restriction}

LEGAL & DOMAIN RULES:
1. Procedural Cross-Referencing: {cross_ref_rule}
2. For POCSO Cases (only if present in context/facts):
   - Cite relevant sections (e.g., Section 4, Section 6, Section 10 POCSO) as retrieved.
   - Emphasize Section 29 and Section 30 of POCSO regarding the Statutory Presumption of Guilt, if present in context.
   - Highlight the necessity of protecting the child victim and preventing witness tampering.
3. For Dowry Cases (only if present in context/facts):
   - Cite Dowry Death / Cruelty: Section 304B IPC / Section 80 BNS, Section 498A IPC / Section 85 BNS, Dowry Prohibition Act (Sections 3 & 4), as retrieved.
   - Emphasize Section 113B IEA / Section 118 BSA (Statutory Presumption as to Dowry Death), if present.
4. Precedents — argue from the actual holding, not just the name:
   - For any case in CONTEXT whose "Ratio/Holding" line is filled in (not marked NOT RECORDED), you MUST state what it actually held in your own words before relying on it, in the form: "In [Case Name], the [Court] held that [ratio, paraphrased from the CONTEXT] — which applies here because [specific link to this case's facts]." A bare mention of the case name with no stated holding ("the precedents cited do not directly support...") is not acceptable when a ratio was provided in CONTEXT; use it.
   - For any case whose "Ratio/Holding" line says NOT RECORDED, you may cite the name/citation as persuasive authority on the general point (e.g. that anticipatory bail was refused in a similar-fact scenario) but you MUST NOT invent or assert a specific holding for it — say only what CONTEXT actually supports (e.g. that the case shares the offence category), not what the case decided.
   - Cite ONLY case names appearing in the CONTEXT, formatted as [CASE: Case Name]. Do not cite a precedent from memory even if you believe it is real and relevant.
5. Custodial interrogation / recovery claims must be fact-specific, not generic: whenever you assert that custodial interrogation, custody, or further investigation is necessary, tie it explicitly to the concrete items in EXTRACTED CASE FACTS that make it necessary in THIS case (e.g. a specific amount to be traced, specific documents to be recovered, specific co-accused/conspirators to be identified, a specific money trail or account to be followed). A generic assertion of "custodial interrogation is necessary" with no case-specific reason attached is a weak, unusable argument for this teaching tool.
6. If the CONTEXT does not support a strong statutory or precedent basis for a point you'd like to make, say so honestly in APPLICATION_TO_FACTS rather than manufacturing support — a prosecutor who overclaims loses credibility with the bench, and this is a teaching tool where the citations must be checkable.
"""

OUTPUT_FORMAT_HEADER = """
OUTPUT FORMAT (You MUST use these exact headings, in this order):

###THEORY###
Prosecutorial theory (2-3 sentences) why pre-arrest bail must be denied in this case.

###STATUTORY_BASIS###
State all relevant substantive & procedural provisions (BNS/IPC, POCSO, Dowry Prohibition Act, BNSS/CrPC, BSA/IEA) present in context. Where CONTEXT gives a cross-code pairing (e.g. "BNS 318 ... corresponding to IPC 420"), state it in that same paired form. Where a section's CONTEXT entry lists "Statutory Ingredients," name the specific mandatory ingredients (e.g. "dishonest inducement," "entrustment of property") rather than describing the offence only in general terms — this is what makes the argument sound like a real prosecutor's submission instead of a generic summary.

###PRECEDENT_SUPPORT###
For each precedent you rely on, state its actual holding in your own words (see Rule 4) and connect it to why it defeats this bail application — do not merely list case names. Only assert a holding for a case whose Ratio/Holding was actually given in CONTEXT. CONTEXT is ordered with the most usable precedents first — cite 3-5 distinct cases when that many with real substance are available, rather than settling for a single case; do not pad with weak/NOT-RECORDED cases just to hit that count if fewer than 3 are genuinely usable.

###LEGAL_PRINCIPLES###
Key principles opposing anticipatory bail (Gravity of offence, Mandatory custodial interrogation for recovery, Statutory Presumption of Guilt, Protection of victims/witnesses) drawn from context.

###APPLICATION_TO_FACTS###
Apply the retrieved statutes, presumptions, and precedents directly to the specific facts of this case. Any claim that custodial interrogation/custody is necessary must name the specific fact(s) from EXTRACTED CASE FACTS that make it necessary here (see Rule 5) — not a generic statement of necessity.

###PRIORITIZATION###
Identify the 2 strongest points available from the context (e.g. statutory presumption of guilt + imperative need for custodial recovery).

###SPOKEN###
{spoken_instructions}
"""

PHASE_SPOKEN_INSTRUCTIONS: Dict[Phase, str] = {
    "opening": (
        "Deliver your OPENING courtroom argument in natural legal language (250-400 words):\n"
        "- Begin: \"May it please the Court, I strongly oppose this application for anticipatory bail...\"\n"
        "- Lay out statutory provisions (BNSS/CrPC and BNS/IPC/POCSO/DPA) and any statutory presumptions.\n"
        "- Detail why custodial interrogation and custody are indispensable.\n"
        "- Conclude with Prayer: \"In view of the gravity of the offence, statutory presumptions, and the "
        "necessity of custodial interrogation, the prosecution humbly prays that this Anticipatory Bail "
        "application be rejected.\""
    ),
    "rebuttal": (
        "Deliver a REBUTTAL (150-250 words) that directly engages the DEFENSE COUNSEL ARGUMENT TO REBUT given "
        "below, point by point:\n"
        "- Begin: \"May it please the Court, the submissions of my learned friend for the defense do not survive "
        "scrutiny...\"\n"
        "- Identify the specific claims or authorities the defense relied on and explain, using ONLY the verified "
        "CONTEXT, why they do not entitle the applicant to anticipatory bail. Name what you are rebutting rather "
        "than arguing in the abstract.\n"
        "- Name what you're rebutting in your OWN prosecutorial words, not by echoing the defense's phrasing back "
        "nearly verbatim (e.g. do not write \"The defense counsel's claim that X is unfounded\" using X copied "
        "almost word-for-word from their argument — recharacterize the claim yourself in a single clause, the way "
        "a real prosecutor summarizes an opponent's position before demolishing it, then attack it).\n"
        "- Vary your rebuttal structure between points instead of repeating the same sentence template "
        "(\"[claim] is unfounded/does not survive scrutiny because...\") for every point — use different "
        "constructions: concede-then-pivot, expose an internal contradiction, question a factual premise, or "
        "show a legal standard the defense ignored.\n"
        "- Do not simply repeat the opening argument; this must read as a direct response.\n"
        "- Close with a short renewed prayer for rejection of bail."
    ),
    "closing": (
        "Deliver a CLOSING argument (200-300 words):\n"
        "- Begin: \"May it please the Court, in conclusion...\"\n"
        "- Synthesize the strongest 2-3 points already established over the course of this hearing (draw on "
        "PRIORITIZATION above) — do NOT introduce a statute or precedent that was not already part of the "
        "CONTEXT for this case.\n"
        "- Directly address the single strongest point the defense has made across the hearing, if provided in "
        "DEFENSE COUNSEL ARGUMENT TO REBUT, and explain why it does not outweigh the case for custody.\n"
        "- Conclude with the formal Prayer: \"In view of the gravity of the offence, statutory presumptions, and "
        "the necessity of custodial interrogation, the prosecution humbly prays that this Anticipatory Bail "
        "application be rejected.\""
    ),
}

COACH_SYSTEM_PROMPT = """You are a moot-court coach for an Indian law student practicing as either Prosecutor or Defense Counsel on an anticipatory bail matter.

You will be given the VERIFIED LEGAL CONTEXT that was available for this case, and the STUDENT'S ARGUMENT they just delivered in their chosen role.

Give concise, constructive feedback (120-180 words) covering:
- One thing the student argued well (grounded in the actual context).
- One missed statutory provision, precedent, or principle that WAS available in the context but the student didn't use.
- One structural or advocacy point (e.g. didn't address the strongest opposing point, weak prayer, didn't engage presumptions).

Be specific and cite section/case names only if they appear in the provided context. Do not invent authorities. Keep the tone like a supportive but rigorous moot-court judge giving feedback after a round, not a courtroom voice.
"""

MARKER_NAMES = [
    "THEORY", "STATUTORY_BASIS", "PRECEDENT_SUPPORT",
    "LEGAL_PRINCIPLES", "APPLICATION_TO_FACTS", "PRIORITIZATION", "SPOKEN"
]

# Whitespace/case-tolerant marker matching. The exact-string version of this
# (`"###THEORY###"` via raw.find(...)) broke as soon as the LLM emitted
# "### THEORY ###" (extra spaces) instead of "###THEORY###" - no marker
# matched, every section came back empty, and the whole raw response fell
# through to the fallback path. This matches "###", optional whitespace,
# the name, optional whitespace, "###" - regardless of spacing or case.
MARKER_PATTERNS = [
    re.compile(rf"#{{2,3}}\s*{name}\s*#{{2,3}}", re.IGNORECASE) for name in MARKER_NAMES
]


class ProsecutorAgent:
    """
    ProsecutorAgent - Courtroom AI Agent specialized in opposing Anticipatory Bail.
    Handles standard criminal offences, POCSO, and Dowry cases.

    Designed for a real-time moot-court simulation: a law student picks a case
    and a role (prosecutor or defense); this agent plays whichever side the
    student did NOT pick. It keeps a running transcript so rebuttal/closing
    turns are contextually aware, and every turn is checked against
    LexiGraphAgent's retrieval before it's shown to the student - if the LLM
    cites something ungrounded, the agent asks it to correct itself, and as a
    last resort strips the ungrounded content rather than ever presenting it
    to a student as authoritative.
    """

    def __init__(self, lexigraph_agent: LexiGraphAgent, model: Optional[str] = None, temperature: float = 0.2):
        self.lexigraph = lexigraph_agent
        self.llm = get_llm(temperature=temperature, model_name=model)
        self.citation_formatter = get_citation_formatter()
        # Running record of the hearing so far, so later phases (rebuttal,
        # closing) have real continuity instead of relying on the caller to
        # thread everything through manually each turn.
        self.transcript: List[Dict[str, str]] = []
        self._retrieval_cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    def reset_session(self) -> None:
        """Start a fresh moot-court hearing (new case or new student session)."""
        self.transcript = []
        self._retrieval_cache.clear()

    def _record_turn(self, speaker: str, phase: str, text: str) -> None:
        self.transcript.append({"speaker": speaker, "phase": phase, "text": text})

    def _transcript_so_far(self) -> str:
        if not self.transcript:
            return ""
        lines = ["TRANSCRIPT OF HEARING SO FAR:"]
        for t in self.transcript:
            lines.append(f"\n[{t['phase'].upper()} - {t['speaker']}]\n{t['text']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LLM plumbing
    # ------------------------------------------------------------------
    def _call(self, messages: List[tuple]) -> str:
        return self.llm.invoke(messages).content

    def _build_system_prompt(self, phase: Phase, legal_regime: str = "IPC+CrPC") -> str:
        spoken_instructions = PHASE_SPOKEN_INSTRUCTIONS[phase]

        if legal_regime == "BNS+BNSS":
            bail_provision = "under Section 482 BNSS"
            regime_statement = (
                "This case was filed on or after 1 July 2024. The applicable substantive code is the "
                "BHARATIYA NYAYA SANHITA (BNS) and the applicable procedural code is the "
                "BHARATIYA NAGARIK SURAKSHA SANHITA (BNSS). "
                "Cite BNSS 482 (not CrPC 438), BNSS 187 (not CrPC 167), BSA 23 (not IEA 27), "
                "and BNS substantive sections."
            )
            code_restriction = (
                "DO NOT cite CrPC or IPC sections. If the CONTEXT provides an old-code equivalent in "
                "parentheses, you may mention it in brackets for the judge's reference (e.g. "
                "'BNSS 482 [equivalent of CrPC 438]') but frame the argument in the new code."
            )
            cross_ref_rule = (
                "State provisions under the NEW code only (BNS/BNSS/BSA). "
                "Where the CONTEXT supplies an old-code pairing (e.g. 'BNS 209 ... corresponding to IPC 174'), "
                "you may note the equivalence in brackets but lead with the BNS/BNSS/BSA citation."
            )
        else:
            bail_provision = "under Section 438 CrPC"
            regime_statement = (
                "This case was filed before 1 July 2024. The applicable substantive code is the "
                "INDIAN PENAL CODE (IPC) and the applicable procedural code is the "
                "CODE OF CRIMINAL PROCEDURE (CrPC). "
                "Cite Section 438 CrPC (not BNSS 482), Section 167 CrPC (not BNSS 187), "
                "Section 27 IEA (not BSA 23), and IPC substantive sections."
            )
            code_restriction = (
                "DO NOT cite BNSS or BNS sections as primary authority. If the CONTEXT provides a "
                "BNS/BNSS cross-reference in parentheses, you may note it in brackets for reference "
                "(e.g. 'IPC 174 [BNS 209]') but frame the argument in the old code."
            )
            cross_ref_rule = (
                "State provisions under the OLD code (IPC/CrPC/IEA). "
                "Where the CONTEXT supplies a cross-code pairing (e.g. 'IPC 420 ... corresponding to BNS 318'), "
                "carry that SAME pairing into your STATUTORY_BASIS in the form 'IPC 420 [BNS 318]' "
                "so the bench can see both."
            )

        core_rules = PROSECUTOR_CORE_RULES_TEMPLATE.format(
            bail_provision=bail_provision,
            regime_statement=regime_statement,
            code_restriction=code_restriction,
            cross_ref_rule=cross_ref_rule,
        )
        return core_rules + OUTPUT_FORMAT_HEADER.format(spoken_instructions=spoken_instructions)

    def _parse_sections(self, raw: str) -> Dict[str, str]:
        sections = {}
        # First find where each marker actually occurs (order-independent -
        # the LLM is asked to follow OUTPUT_FORMAT_HEADER's order, but this
        # no longer assumes it, since a reordered marker is more useful to
        # recover than to lose entirely).
        matches = []  # list of (name, match_start, content_start)
        for name, pattern in zip(MARKER_NAMES, MARKER_PATTERNS):
            m = pattern.search(raw)
            if m:
                matches.append((name, m.start(), m.end()))

        matches.sort(key=lambda t: t[1])  # order by position in the text

        for idx, (name, _match_start, content_start) in enumerate(matches):
            content_end = matches[idx + 1][1] if idx + 1 < len(matches) else len(raw)
            sections[name.lower()] = raw[content_start:content_end].strip()
        return sections

    # ------------------------------------------------------------------
    # Anti-hallucination: generate, verify, and self-correct before the
    # student ever sees the output.
    # ------------------------------------------------------------------
    def _correction_prompt(self, verification: Dict[str, Any]) -> str:
        problems = []
        if verification.get("hallucinated_sections"):
            problems.append(
                "These section citations do NOT correspond to any real provision and must be REMOVED entirely: "
                + ", ".join(verification["hallucinated_sections"])
            )
        if verification.get("real_but_ungrounded_sections"):
            problems.append(
                "These sections are real provisions but were NOT part of the verified context retrieved for THIS "
                "case, so they must be REMOVED (do not argue them even if plausible): "
                + ", ".join(verification["real_but_ungrounded_sections"])
            )
        if verification.get("unverified_cases"):
            problems.append(
                "These case names could not be matched to any precedent retrieved for THIS case and must be "
                "REMOVED (do not paraphrase-keep them either): "
                + ", ".join(verification["unverified_cases"])
            )
        return (
            "CORRECTION REQUIRED: your previous draft is not fully grounded in the verified CONTEXT.\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\n\nRewrite the FULL response from scratch, in the exact same ###HEADING### format, using ONLY "
            "citations that appear in the verified CONTEXT provided earlier. If removing an ungrounded citation "
            "weakens a point, argue that point more generally from principle instead, or drop it - do not "
            "substitute a different unverified citation."
        )

    def _sanitize(self, text: str, verification: Dict[str, Any]) -> (str, List[str]):
        """
        Last-resort cleanup if the model still won't self-correct after
        MAX_CORRECTION_ATTEMPTS: strip the specific ungrounded strings so
        nothing unverified reaches the student, and report what was removed.
        """
        redacted = []
        for bad in (
            verification.get("hallucinated_sections", [])
            + verification.get("real_but_ungrounded_sections", [])
            + verification.get("unverified_cases", [])
        ):
            # Guard: skip single characters and whitespace-only tokens
            # (they arise when a string field is iterated character-by-character)
            if not bad or not isinstance(bad, str) or len(bad.strip()) <= 1:
                continue
            if bad in text:
                text = text.replace(bad, "[citation removed - unverified]")
                redacted.append(bad)
        return text, redacted

    def _generate_verified(
        self,
        system_prompt: str,
        user_prompt: str,
        production_output: Dict[str, Any],
        canonical_case_file: Optional[str] = None,
    ) -> tuple:
        """Generate -> verify -> self-correct loop. Returns (raw_text, verification, attempts, redacted)."""
        from agents.orchestrator.case_file import format_cached_messages
        from langchain_core.messages import AIMessage, HumanMessage, BaseMessage

        if canonical_case_file:
            messages = format_cached_messages(canonical_case_file, system_prompt, user_prompt)
        else:
            messages = [("system", system_prompt), ("user", user_prompt)]
        raw = self._call(messages)
        parsed = self._parse_sections(raw)
        spoken = parsed.get("spoken", raw)
        spoken_formatted = self.citation_formatter.format_spoken_argument(spoken)
        verification = self.lexigraph.verify_claims(spoken_formatted, production_output)

        attempts = 0
        while not verification.get("is_clean", True) and attempts < MAX_CORRECTION_ATTEMPTS:
            attempts += 1
            if messages and isinstance(messages[0], BaseMessage):
                messages.append(AIMessage(content=raw))
                messages.append(HumanMessage(content=self._correction_prompt(verification)))
            else:
                messages.append(("assistant", raw))
                messages.append(("user", self._correction_prompt(verification)))
            raw = self._call(messages)
            parsed = self._parse_sections(raw)
            spoken = parsed.get("spoken", raw)
            spoken_formatted = self.citation_formatter.format_spoken_argument(spoken)
            verification = self.lexigraph.verify_claims(spoken_formatted, production_output)

        redacted: List[str] = []
        if not verification.get("is_clean", True):
            # Model didn't fully cooperate even after retries - never ship
            # ungrounded citations to a student. Strip them programmatically.
            # (raw and other parsed sections are left as-is; only the SPOKEN
            # text actually shown to the student is sanitized here.)
            spoken_formatted, redacted = self._sanitize(spoken_formatted, verification)
            parsed["spoken"] = spoken_formatted

        return raw, parsed, spoken_formatted, verification, attempts, redacted

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def generate_turn(
        self,
        case_facts: str,
        phase: Phase = "opening",
        opposing_argument: Optional[str] = None,
        include_coaching: bool = False,
        debug: bool = False,
        production_output: Optional[Dict[str, Any]] = None,
        canonical_case_file: Optional[str] = None,
    ) -> ProsecutorTurnResult:
        if phase not in PHASE_SPOKEN_INSTRUCTIONS:
            raise ValueError(f"Unknown phase '{phase}'. Expected one of {list(PHASE_SPOKEN_INSTRUCTIONS)}.")

        # 1. Query LexiGraphAgent for facts, statutes, cases & graph mappings (run once & cache)
        if production_output is None:
            cache_key = f"prosecutor:{case_facts.strip()}"
            if cache_key in self._retrieval_cache:
                production_output = self._retrieval_cache[cache_key]
            else:
                production_output = self.lexigraph.process_query(case_facts, debug=debug, role="prosecutor")
                self._retrieval_cache[cache_key] = production_output

        # 2. Render dynamic turn content (strictly at the END of prompt)
        turn_parts = []
        transcript_context = self._transcript_so_far()
        if transcript_context:
            turn_parts.append(transcript_context)

        if opposing_argument:
            turn_parts.append(f"DEFENSE COUNSEL ARGUMENT TO REBUT:\n{opposing_argument}")

        turn_parts.append("Deliver your structured courtroom argument opposing anticipatory bail now.")
        dynamic_turn_content = "\n\n".join(turn_parts)

        # 3. LLM Prosecutor Argument Generation, with verify + self-correct loop
        legal_regime = (production_output or {}).get("legal_regime", "IPC+CrPC")
        system_prompt = self._build_system_prompt(phase, legal_regime=legal_regime)

        raw_output, parsed, spoken_formatted, verification, attempts, redacted = self._generate_verified(
            system_prompt,
            dynamic_turn_content,
            production_output,
            canonical_case_file=canonical_case_file or case_facts,
        )

        # 4. Record this turn for continuity in later phases
        self._record_turn("Prosecutor (AI)", phase, spoken_formatted)
        if opposing_argument:
            self._record_turn("Defense (Student)", phase, opposing_argument)

        # 5. Optional coaching feedback on the student's argument
        coaching_notes = None
        if include_coaching and opposing_argument:
            coaching_notes = self._generate_coaching_notes(verified_context, opposing_argument)

        return ProsecutorTurnResult(
            phase=phase,
            theory_of_case=parsed.get("theory", ""),
            statutory_basis=parsed.get("statutory_basis", ""),
            precedent_support=parsed.get("precedent_support", ""),
            legal_principles=parsed.get("legal_principles", ""),
            application_to_facts=parsed.get("application_to_facts", ""),
            prioritization=parsed.get("prioritization", ""),
            spoken_argument=spoken_formatted,
            verification=verification,
            production_output=production_output,
            is_verified_clean=verification.get("is_clean", True),
            correction_attempts=attempts,
            auto_redacted=redacted,
            coaching_notes=coaching_notes,
        )

    # ------------------------------------------------------------------
    # Coaching (pedagogical layer, separate voice from the in-character
    # courtroom argument, since the goal is student learning, not just
    # simulating a trial).
    # ------------------------------------------------------------------
    def _generate_coaching_notes(self, verified_context: str, student_argument: str) -> str:
        user_prompt = (
            f"VERIFIED LEGAL CONTEXT AVAILABLE FOR THIS CASE:\n{verified_context}\n\n"
            f"STUDENT'S ARGUMENT:\n{student_argument}"
        )
        messages = [("system", COACH_SYSTEM_PROMPT), ("user", user_prompt)]
        return self._call(messages)


def _read_multiline(prompt: str) -> str:
    """Read free-form text from the terminal until the user enters a blank line."""
    print(prompt)
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "" and lines:
            break
        if line.strip() == "" and not lines:
            continue
        lines.append(line)
    return " ".join(lines).strip()


def _run_interactive_cli() -> None:
    """
    Live terminal moot-court session. No case facts, defense arguments, or
    outcomes are hardcoded anywhere below - everything is entered by the
    person running this script, turn by turn, exactly as a law student would
    supply it through the product UI.
    """
    lexigraph = LexiGraphAgent()
    prosecutor = ProsecutorAgent(lexigraph)

    print("\n==================================================")
    print("MOOT COURT SIMULATION - PROSECUTOR (AI) vs DEFENSE (YOU)")
    print("Opposing an application for Anticipatory Bail")
    print("==================================================")

    case_facts = _read_multiline(
        "\nEnter the CASE FACTS (paste from your dataset or type your own; blank line to submit):"
    )
    if not case_facts:
        print("No case facts entered. Exiting.")
        return

    prosecutor.reset_session()

    print("\n--- Generating OPENING argument for the prosecution ---")
    opening = prosecutor.generate_turn(case_facts, phase="opening")
    print("\n[THEORY OF CASE]\n" + opening.theory_of_case)
    print("\n[SPOKEN - OPENING]\n" + opening.spoken_argument)
    print(f"\n[VERIFICATION] clean={opening.is_verified_clean} corrections={opening.correction_attempts} redacted={opening.auto_redacted}")

    while True:
        print("\n" + "-" * 60)
        choice = input("Type your DEFENSE argument to get a prosecution REBUTTAL, "
                        "or type 'closing' for the prosecution's closing argument, "
                        "or 'quit' to end: ").strip()

        if choice.lower() in ("quit", "exit"):
            break

        if choice.lower() == "closing":
            closing = prosecutor.generate_turn(case_facts, phase="closing")
            print("\n[SPOKEN - CLOSING]\n" + closing.spoken_argument)
            print(f"\n[VERIFICATION] clean={closing.is_verified_clean} corrections={closing.correction_attempts} redacted={closing.auto_redacted}")
            break

        student_argument = choice if choice else _read_multiline(
            "Enter your DEFENSE argument (blank line to submit):"
        )
        if not student_argument:
            continue

        want_coaching = input("Include coaching feedback on your argument? (y/n): ").strip().lower().startswith("y")

        rebuttal = prosecutor.generate_turn(
            case_facts,
            phase="rebuttal",
            opposing_argument=student_argument,
            include_coaching=want_coaching,
        )
        print("\n[SPOKEN - REBUTTAL]\n" + rebuttal.spoken_argument)
        print(f"\n[VERIFICATION] clean={rebuttal.is_verified_clean} corrections={rebuttal.correction_attempts} redacted={rebuttal.auto_redacted}")
        if rebuttal.coaching_notes:
            print("\n[COACHING NOTES]\n" + rebuttal.coaching_notes)


if __name__ == "__main__":
    _run_interactive_cli()