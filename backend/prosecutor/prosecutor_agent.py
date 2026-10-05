"""
Prosecutor Agent
================
Stateful AI prosecutor for anticipatory bail moot court hearings.

Flow:
  start_session()
    1. Load case text
    2. Orchestrator.run() — lexigraphbe runs untouched, returns verified sections
    3. Prosecutor LLM extraction — reads case text + retrieved sections together
       → understands facts
       → builds SectionUsagePlan: per section, which pillar, when to deploy, which fact it anchors to
    4. Session file created

  opening_argument()
    → Uses sections marked deploy_when="opening" in SectionUsagePlan
    → Argues all 4 pillars

  rebuttal(defense_argument)
    → Compresses defense argument
    → LLM decides:
        Decision A: can I counter with sections already retrieved? → use them
        Decision B: defense raised a specific fact with no section in session?
                    → extract that fact + surrounding context from case text
                    → orchestrator.query_for_fact(fact, context, existing_sections)
                    → new sections stored in session
    → Generates rebuttal — non-repetitive, specific, cites sections by number

Non-repetition enforced by:
  - prosecutor_positions[] tracked in session
  - pillars_argued[] tracked in session
  - sections_cited_so_far[] tracked in session
  - Hard system prompt instruction every turn: "never restate these positions"
"""

from __future__ import annotations
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

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

console = Console()

ALL_PILLARS = [
    "P1:Gravity",
    "P2:PrimaFacie",
    "P3:CustodialInterrogation",
    "P4:FlightRisk",
]

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

SESSIONS_DIR = Path("mootcourt_sessions")


# ─────────────────────────────────────────────────────────────
# File I/O
# ─────────────────────────────────────────────────────────────

def read_pdf(path: Union[str, Path]) -> str:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    parts: List[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


def load_case_text(source: Union[str, Path]) -> str:
    s = str(source)
    if s.lower().endswith(".pdf"):
        console.print(f"[dim]Reading PDF: {s}[/dim]")
        return read_pdf(s)
    if s.lower().endswith(".txt") and Path(s).exists():
        return Path(s).read_text(encoding="utf-8")
    return s


def _session_path(session_id: str) -> Path:
    SESSIONS_DIR.mkdir(exist_ok=True)
    return SESSIONS_DIR / f"session_{session_id}.json"


def _save_session(session: SessionState) -> None:
    _session_path(session.session_id).write_text(
        session.model_dump_json(indent=2), encoding="utf-8"
    )


# ─────────────────────────────────────────────────────────────
# LLM helpers
# ─────────────────────────────────────────────────────────────

def _call_llm(client: OpenAI, system: str, user: str,
              model: str = "gpt-4o-mini", temperature: float = 0.1) -> str:
    resp = client.chat.completions.create(
        model=model, temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return resp.choices[0].message.content.strip()


def _parse_json(raw: str) -> Dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$",          "", cleaned, flags=re.MULTILINE)
    return json.loads(cleaned.strip())


# ─────────────────────────────────────────────────────────────
# Context window helper — find surrounding sentences for a fact
# ─────────────────────────────────────────────────────────────

def _extract_fact_context(case_text: str, fact_text: str, window: int = 3) -> str:
    """
    Given a specific fact (a sentence or phrase), find it in the case text
    and return it together with `window` surrounding sentences on each side.
    This gives Stage 0 enough context to build a proper CaseContextObject.
    """
    sentences = re.split(r'(?<=[.!?])\s+', case_text)
    # Find the sentence(s) most relevant to the fact
    fact_lower = fact_text.lower()
    best_idx = 0
    best_overlap = 0.0
    fact_tokens = set(fact_lower.split())
    for i, sent in enumerate(sentences):
        sent_tokens = set(sent.lower().split())
        overlap = len(fact_tokens & sent_tokens) / max(len(fact_tokens), 1)
        if overlap > best_overlap:
            best_overlap = overlap
            best_idx = i
    start = max(0, best_idx - window)
    end   = min(len(sentences), best_idx + window + 1)
    return " ".join(sentences[start:end])


# ─────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────

def _extraction_system(sections_text: str) -> str:
    return f"""You are a Senior Public Prosecutor preparing for an ANTICIPATORY BAIL hearing.
You have already received the verified IPC sections that apply to this case (retrieved by a statutory analysis pipeline).

VERIFIED SECTIONS RETRIEVED:
{sections_text}

Your task: read the case facts carefully and produce a structured JSON analysis.

RULES:
1. Every inferred fact MUST be backed by a VERBATIM quote from the case text.
   Copy the quote exactly as written. If no direct quote exists, omit the fact.
2. Extract only what is EXPLICITLY stated. No speculation.
3. Your sub_queries are for YOUR OWN argument planning — they are NOT sent back to the pipeline.
4. Rank sub_queries by bail-rejection importance (priority 1 = most critical).
5. Respond ONLY with valid JSON. No preamble, no markdown.

OUTPUT SCHEMA:
{{
  "case_summary": "<one paragraph, prosecutor perspective, referencing retrieved sections>",
  "victim": ["<name or description>"],
  "accused": ["<name or description>"],
  "relationship": "<relationship>",
  "legal_concepts": ["<concept1>"],
  "sub_queries": [
    {{
      "id": "PSQ1",
      "query": "<factual allegation>",
      "legal_concept": "<concept>",
      "bail_relevance": "<why this supports bail rejection>",
      "priority": 1,
      "supporting_facts": [
        {{
          "fact_label": "<short label>",
          "inferred_meaning": "<legal meaning, referencing specific section if applicable>",
          "verbatim_quote": "<EXACT text from case>"
        }}
      ]
    }}
  ],
  "bail_rejection_summary": "<consolidated argument citing retrieved sections>"
}}"""


EXTRACTION_REFLECTION = """You are a Senior Public Prosecutor.
Your previous JSON had citation errors — some verbatim quotes were NOT found in the case text.
Re-read the case and fix ONLY the flagged quotes. Return the COMPLETE corrected JSON. No preamble."""


def _usage_plan_system(sections_text: str, case_summary: str) -> str:
    return f"""You are a Senior Public Prosecutor building your argument strategy for an anticipatory bail hearing.

CASE SUMMARY:
{case_summary}

VERIFIED IPC SECTIONS (from statutory analysis — these are the ONLY sections you may use):
{sections_text}

THE 4 PILLARS you must cover across your arguments:
  P1:Gravity               — Gravity of offence: nature, severity, societal impact
  P2:PrimaFacie            — Prima facie strength: ingredients satisfied, evidence
  P3:CustodialInterrogation — Why custody is needed: evidence tampering, investigation needs
  P4:FlightRisk             — Flight risk, witness tampering, roots in society

YOUR TASK: For each retrieved section, decide:
  1. Which pillar does it primarily support?
  2. When should it be deployed?
     - "opening"     : cite in opening argument
     - "rebuttal"    : keep for rebuttal (stronger impact when defense has spoken)
     - "conditional" : only deploy if defense specifically raises this line of argument
  3. Which specific fact from the case does it anchor to?
  4. What prosecution argument does it enable (one sentence)?

Only include sections where overall_status is "Prima Facie Attracted" or "Partially Attracted".
Do NOT plan to use sections marked "Not Attracted".

Return ONLY valid JSON, no preamble:
{{
  "sections": [
    {{
      "section_number": "...",
      "statute": "IPC",
      "title": "...",
      "pillar": "P1:Gravity",
      "deploy_when": "opening",
      "anchored_fact": "<specific case fact this section applies to>",
      "argument_enabled": "<one sentence: what prosecution argument this unlocks>",
      "prima_facie_strength": "Strong",
      "overall_status": "Prima Facie Attracted"
    }}
  ]
}}"""


def _opening_system(
    sections_text: str,
    case_summary: str,
    usage_plan: SectionUsagePlan,
) -> str:
    opening_sections = usage_plan.for_opening()
    if opening_sections:
        opening_plan = "\n".join(
            f"  § {s.section_number} ({s.statute}) — Pillar {s.pillar}\n"
            f"    Anchored fact: {s.anchored_fact}\n"
            f"    Argument: {s.argument_enabled}"
            for s in opening_sections
        )
    else:
        # fallback: use all available sections
        opening_plan = sections_text

    return f"""You are a Senior Public Prosecutor making your OPENING ARGUMENT in an anticipatory bail hearing.
Objective: persuade the court to REJECT anticipatory bail.

CASE SUMMARY:
{case_summary}

YOUR SECTION DEPLOYMENT PLAN FOR THIS OPENING:
{opening_plan}

ALL VERIFIED SECTIONS AVAILABLE (for reference):
{sections_text}

THE 4 PILLARS — you MUST cover all four in this opening:
  P1:Gravity               — Gravity of the offence
  P2:PrimaFacie            — Prima facie strength of the case
  P3:CustodialInterrogation — Why custodial interrogation is essential
  P4:FlightRisk             — Flight risk and witness tampering risk

Return ONLY valid JSON, no preamble:
{{
  "needs_new_sections": false,
  "unaddressed_fact": "",
  "new_concepts": [],
  "pillars_to_address": ["P1:Gravity","P2:PrimaFacie","P3:CustodialInterrogation","P4:FlightRisk"],
  "countering": [],
  "new_ground": ["<opening ground>"],
  "sections_to_cite": ["<section numbers you will cite>"],
  "argument": "<full courtroom argument — formal, specific, cites sections by number e.g. 'Under Section 468 IPC...'>",
  "summary_bullets": ["<bullet 1>","<bullet 2>","<bullet 3>"],
  "positions_asserted": ["<short declarative claim 1>","<short declarative claim 2>"]
}}

RULES:
- Cite ONLY sections from your deployment plan. Do not fabricate sections.
- Be specific to THIS case. No generic boilerplate.
- Formal courtroom language throughout.
- Each pillar must be grounded in the actual case facts and retrieved sections."""


def _rebuttal_system(
    sections_text: str,
    case_summary: str,
    usage_plan: SectionUsagePlan,
    prosecutor_positions: List[str],
    pillars_argued: List[str],
    sections_cited_so_far: List[str],
    defense_summary: str,
    prior_turns_context: str,
) -> str:
    remaining_pillars = [p for p in ALL_PILLARS if p not in pillars_argued]
    remaining_desc = (
        "\n".join(f"  {p}: {PILLAR_DESCRIPTIONS[p]}" for p in remaining_pillars)
        if remaining_pillars
        else "  All 4 pillars argued. Focus on countering defense directly."
    )

    argued_str = (
        "\n".join(f"  - {p}" for p in prosecutor_positions)
        if prosecutor_positions else "  None yet."
    )

    uncited = [
        s for s in usage_plan.sections
        if s.section_number not in sections_cited_so_far
        and s.overall_status in ("Prima Facie Attracted", "Partially Attracted")
    ]
    uncited_desc = (
        "\n".join(
            f"  § {s.section_number} — {s.argument_enabled} [deploy_when={s.deploy_when}]"
            for s in uncited
        )
        if uncited else "  All planned sections already cited."
    )

    return f"""You are a Senior Public Prosecutor making a REBUTTAL in an anticipatory bail hearing.
Objective: counter the defense and reinforce the case for REJECTING bail.

CASE SUMMARY:
{case_summary}

ALL VERIFIED SECTIONS AVAILABLE:
{sections_text}

SECTIONS NOT YET CITED (available to deploy now):
{uncited_desc}

POSITIONS ALREADY ARGUED — DO NOT REPEAT:
{argued_str}

REMAINING PILLARS NOT YET FULLY ARGUED:
{remaining_desc}

PRIOR TURN CONTEXT (compressed):
{prior_turns_context}

DEFENSE'S LATEST ARGUMENT:
{defense_summary}

DECISION FRAMEWORK — reason through this before writing:

1. Can I counter the defense using sections already retrieved?
   → If yes, set needs_new_sections=false. Use them.

2. Did the defense raise a specific FACT (not just a legal argument) for which
   NO retrieved section covers it?
   → If yes, set needs_new_sections=true.
   → In unaddressed_fact: state the SPECIFIC FACT from the defense argument
     (not a concept, not a legal principle — a concrete factual claim).
   → The orchestrator will query lexigraphbe specifically for that fact.

3. Which remaining pillars can I advance this turn?

4. Which specific defense claims am I directly countering — and how?

Return ONLY valid JSON, no preamble:
{{
  "needs_new_sections": <true|false>,
  "unaddressed_fact": "<specific factual claim from defense that has no section — empty string if not needed>",
  "new_concepts": ["<concept if new>"],
  "pillars_to_address": ["<pillar codes>"],
  "countering": ["<defense claim being countered>"],
  "new_ground": ["<new prosecution point>"],
  "sections_to_cite": ["<section numbers>"],
  "argument": "<full courtroom rebuttal — formal, specific, non-repetitive, cites sections by number>",
  "summary_bullets": ["<bullet 1>","<bullet 2>","<bullet 3>"],
  "positions_asserted": ["<new declarative claim 1>"]
}}

RULES:
- NEVER restate a position from POSITIONS ALREADY ARGUED.
- Only cite sections that are actually retrieved and relevant.
- Do NOT fabricate sections.
- Be specific to THIS case. No boilerplate."""


# ─────────────────────────────────────────────────────────────
# Formatting helpers for prompts
# ─────────────────────────────────────────────────────────────

def _format_sections_for_prompt(sections: Dict[str, RetrievedSection]) -> str:
    if not sections:
        return "  No sections retrieved yet."
    lines = []
    for sec in sections.values():
        lines.append(
            f"  § {sec.section_number} {sec.statute} — {sec.title}\n"
            f"    Status    : {sec.overall_status}\n"
            f"    Strength  : {sec.overall_prima_facie_strength}\n"
            f"    Punishment: {sec.punishment_text}\n"
            f"    Reasoning : {sec.legal_reasoning}"
        )
    return "\n\n".join(lines)


def _format_prior_turns(turns: List[TurnRecord], last_n: int = 6) -> str:
    if not turns:
        return "  No prior turns."
    recent = turns[-last_n:]
    lines = []
    for t in recent:
        bullets = "\n".join(f"    • {b}" for b in t.summary_bullets)
        lines.append(f"  Turn {t.turn_number} [{t.speaker.upper()}]:\n{bullets}")
    return "\n\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Rich display
# ─────────────────────────────────────────────────────────────

def _rule(title: str = "") -> None:
    console.rule(f"[bold cyan]{title}[/bold cyan]" if title else "")


def _display_extraction(output: ProsecutorOutput) -> None:
    console.print()
    console.print(Panel(
        f"[bold white]{output.case_summary}[/bold white]",
        title="[bold red]⚖  PROSECUTOR — CASE UNDERSTANDING[/bold red]",
        border_style="red", padding=(1, 2),
    ))
    _rule("PARTIES")
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column("Role", style="bold yellow")
    t.add_column("",     style="white")
    t.add_row("Victim(s)",    ", ".join(output.victim)  or "N/A")
    t.add_row("Accused",      ", ".join(output.accused) or "N/A")
    t.add_row("Relationship", output.relationship       or "N/A")
    console.print(t)

    _rule("CITED FACTS  (by bail-rejection priority)")
    for sq in output.sub_queries:
        console.print()
        console.print(Panel(
            f"[bold white]{sq.query}[/bold white]",
            title=f"[yellow]{sq.id}  |  Priority {sq.priority}  |  {sq.legal_concept}[/yellow]",
            border_style="yellow", padding=(0, 2),
        ))
        console.print(f"  [bold red]Bail Relevance:[/bold red] {sq.bail_relevance}")
        for cf in sq.supporting_facts:
            console.print(f"\n    [bold green]► {cf.fact_label}[/bold green]")
            console.print(f"      Inference  : {cf.inferred_meaning}")
            span = ""
            if cf.char_start is not None and cf.char_start >= 0:
                span = f" [dim](chars {cf.char_start}–{cf.char_end})[/dim]"
            console.print(
                f"      Source Text: [italic yellow]\"{cf.verbatim_quote}\"[/italic yellow]{span}"
            )
    gs = output.verification_status
    color = "green" if gs == "VERIFIED" else "red"
    console.print()
    console.print(f"[{color}]{format_guardrail_report(output)}[/{color}]")


def _display_usage_plan(plan: SectionUsagePlan) -> None:
    _rule("SECTION USAGE PLAN")
    t = Table(box=box.SIMPLE, show_header=True,
              header_style="bold white", padding=(0, 1))
    t.add_column("§",           style="bold yellow", width=6)
    t.add_column("Pillar",      style="magenta",     width=24)
    t.add_column("Deploy",      style="cyan",        width=12)
    t.add_column("Anchored Fact", style="white",     width=40)
    for s in plan.sections:
        t.add_row(
            s.section_number, s.pillar, s.deploy_when,
            s.anchored_fact[:38] + ("…" if len(s.anchored_fact) > 38 else ""),
        )
    console.print(t)
    console.print()


def _display_argument(turn: TurnRecord) -> None:
    console.print()
    console.print(Panel(
        f"[bold white]{turn.full_argument}[/bold white]",
        title=f"[bold red]⚖  PROSECUTOR — Turn {turn.turn_number}[/bold red]",
        border_style="red", padding=(1, 2),
    ))
    _rule("PILLARS COVERED THIS TURN")
    for p in turn.pillars_covered:
        console.print(f"  [magenta]•[/magenta] {p}: {PILLAR_DESCRIPTIONS.get(p,'')}")
    if turn.sections_cited:
        _rule("SECTIONS CITED")
        for s in turn.sections_cited:
            console.print(f"  [yellow]§{s}[/yellow]")
    _rule("POSITIONS ASSERTED")
    for pos in turn.positions_asserted:
        console.print(f"  [cyan]→[/cyan] {pos}")
    console.print()


# ─────────────────────────────────────────────────────────────
# ProsecutorAgent
# ─────────────────────────────────────────────────────────────

class ProsecutorAgent:

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

    def _generate_verified(self, system_prompt: str, user_prompt: str, production_output: Dict[str, Any]) -> tuple:
        """Generate -> verify -> self-correct loop. Returns (raw_text, verification, attempts, redacted)."""
        messages = [("system", system_prompt), ("user", user_prompt)]
        raw = self._call(messages)
        parsed = self._parse_sections(raw)
        spoken = parsed.get("spoken", raw)
        spoken_formatted = self.citation_formatter.format_spoken_argument(spoken)
        verification = self.lexigraph.verify_claims(spoken_formatted, production_output)

        attempts = 0
        while not verification.get("is_clean", True) and attempts < MAX_CORRECTION_ATTEMPTS:
            attempts += 1
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

    def _extract_case(
        self,
        case_text: str,
        retrieved_sections: Dict[str, RetrievedSection],
    ) -> ProsecutorOutput:
        """
        LLM extraction pass AFTER sections are retrieved.
        The LLM sees both case text and retrieved sections,
        so its understanding is grounded in the actual law.
        """
        _rule("PROSECUTOR — CASE EXTRACTION")
        sections_text = _format_sections_for_prompt(retrieved_sections)
        system = _extraction_system(sections_text)

        user_prompt = f"CASE FACTS:\n{case_facts}\n\n{verified_context}"

        transcript_context = self._transcript_so_far()
        if transcript_context:
            user_prompt += f"\n\n{transcript_context}"

        if opposing_argument:
            user_prompt += f"\n\nDEFENSE COUNSEL ARGUMENT TO REBUT:\n{opposing_argument}"

        # 3. LLM Prosecutor Argument Generation, with verify + self-correct loop
        legal_regime = (production_output or {}).get("legal_regime", "IPC+CrPC")
        system_prompt = self._build_system_prompt(phase, legal_regime=legal_regime)
        raw_output, parsed, spoken_formatted, verification, attempts, redacted = self._generate_verified(
            system_prompt, user_prompt, production_output
        )

        output: Optional[ProsecutorOutput] = None
        for attempt in range(1, self.max_retries + 2):
            s = system if attempt == 1 else EXTRACTION_REFLECTION
            if attempt > 1:
                flags = "\n".join(output.hallucination_flags)  # type: ignore
                user  = (
                    f"CASE TEXT:\n\"\"\"\n{case_text}\n\"\"\"\n\n"
                    f"FLAGGED CITATION ERRORS:\n{flags}\n\nReturn corrected JSON."
                )
            console.print(f"[dim]→ Extraction LLM call (attempt {attempt})…[/dim]")
            raw = _call_llm(self.client, s, user, self.model)

            try:
                data = _parse_json(raw)
            except json.JSONDecodeError as e:
                console.print(f"[red]JSON parse error: {e}[/red]")
                if attempt > self.max_retries:
                    raise
                continue

            sqs: List[ProsecutionSubQuery] = []
            for sq_raw in data.get("sub_queries", []):
                facts = [
                    CitedFact(
                        fact_label=f.get("fact_label", ""),
                        inferred_meaning=f.get("inferred_meaning", ""),
                        verbatim_quote=f.get("verbatim_quote", ""),
                    )
                    for f in sq_raw.get("supporting_facts", [])
                ]
                sqs.append(ProsecutionSubQuery(
                    id=sq_raw.get("id", "PSQ?"),
                    query=sq_raw.get("query", ""),
                    legal_concept=sq_raw.get("legal_concept", ""),
                    bail_relevance=sq_raw.get("bail_relevance", ""),
                    priority=int(sq_raw.get("priority", 99)),
                    supporting_facts=facts,
                ))
            sqs.sort(key=lambda x: x.priority)

            output = ProsecutorOutput(
                case_summary=data.get("case_summary", ""),
                victim=data.get("victim", []),
                accused=data.get("accused", []),
                relationship=data.get("relationship", ""),
                legal_concepts=data.get("legal_concepts", []),
                sub_queries=sqs,
                bail_rejection_summary=data.get("bail_rejection_summary", ""),
            )
            output = self.guardrail.verify(output, case_text)

            if output.verification_status == "VERIFIED":
                console.print(f"[green]✓ Citation Guardrail PASSED (attempt {attempt})[/green]")
                break
            if attempt <= self.max_retries:
                console.print(
                    f"[yellow]⚠ Guardrail flagged {len(output.hallucination_flags)} issue(s) — retrying…[/yellow]"
                )
                output.hallucination_flags = []
            else:
                console.print("[red]⚠ Guardrail issues remain — proceeding with flags.[/red]")

        assert output is not None
        _display_extraction(output)
        return output

    # ── Section Usage Plan ───────────────────────────────────

    def _build_usage_plan(
        self,
        case_summary: str,
        retrieved_sections: Dict[str, RetrievedSection],
    ) -> SectionUsagePlan:
        """
        Ask the LLM to assign each retrieved section to a pillar,
        a deployment timing, and a specific case fact.
        """
        _rule("PROSECUTOR — BUILDING SECTION USAGE PLAN")
        sections_text = _format_sections_for_prompt(retrieved_sections)
        system = _usage_plan_system(sections_text, case_summary)
        console.print("[dim]→ Section usage plan LLM call…[/dim]")
        raw = _call_llm(self.client, system,
                        "Build the section usage plan.", self.model)
        try:
            data = _parse_json(raw)
        except json.JSONDecodeError:
            console.print("[yellow]⚠ Usage plan parse failed — using default plan.[/yellow]")
            # Fallback: assign all attracted sections to opening, P2
            data = {"sections": []}

        sections: List[SectionUsage] = []
        for s in data.get("sections", []):
            sections.append(SectionUsage(
                section_number=str(s.get("section_number", "")),
                statute=str(s.get("statute", "IPC")),
                title=str(s.get("title", "")),
                pillar=str(s.get("pillar", "P2:PrimaFacie")),
                deploy_when=str(s.get("deploy_when", "opening")),
                anchored_fact=str(s.get("anchored_fact", "")),
                argument_enabled=str(s.get("argument_enabled", "")),
                prima_facie_strength=str(s.get("prima_facie_strength", "")),
                overall_status=str(s.get("overall_status", "")),
            ))

        plan = SectionUsagePlan(sections=sections)
        _display_usage_plan(plan)
        return plan

    # ── Argument generation ──────────────────────────────────

    def _generate_argument(self, system_prompt: str, label: str) -> ArgumentDecision:
        console.print(f"[dim]→ {label}…[/dim]")
        raw = _call_llm(self.client, system_prompt,
                        "Generate your courtroom argument now.", self.model)
        try:
            data = _parse_json(raw)
        except json.JSONDecodeError:
            console.print("[yellow]⚠ JSON parse failed — using raw text.[/yellow]")
            data = {
                "needs_new_sections": False,
                "unaddressed_fact": "",
                "new_concepts": [],
                "pillars_to_address": [],
                "countering": [],
                "new_ground": [],
                "sections_to_cite": [],
                "argument": raw,
                "summary_bullets": [raw[:200]],
                "positions_asserted": [],
            }
        # Ensure unaddressed_fact key exists
        if "unaddressed_fact" not in data:
            data["unaddressed_fact"] = ""
        return ArgumentDecision(**data)

    # ── Public API ───────────────────────────────────────────

    def start_session(
        self,
        source: Union[str, Path],
        student_role: str,
        case_id: Optional[str] = None,
    ) -> SessionState:
        from .orchestrator_agent import OrchestratorAgent

        case_text  = load_case_text(source)
        case_id    = case_id or (
            Path(str(source)).stem
            if str(source).endswith((".pdf", ".txt"))
            else datetime.now().strftime("%Y%m%d%H%M%S")
        )
        session_id = str(uuid.uuid4())[:8]

        console.print()
        console.print(Panel(
            f"[bold white]VIRTUAL MOOT COURT — ANTICIPATORY BAIL HEARING\n"
            f"[dim]Case: {case_id}  |  Student role: {student_role.upper()}[/dim]",
            border_style="blue", padding=(1, 4),
        ))

        # Step 1 — Lexigraphbe runs first, untouched
        _rule("ORCHESTRATOR — RUNNING LEXIGRAPHBE PIPELINE")
        orchestrator = OrchestratorAgent(api_key=self.client.api_key, model=self.model)
        orch_result  = orchestrator.run(OrchestratorInput(case_text=case_text))

        # Step 2 — Store sections
        retrieved: Dict[str, RetrievedSection] = {}
        for vs in orch_result.verified_sections:
            retrieved[vs.section_number] = RetrievedSection(
                section_number=vs.section_number,
                statute=vs.statute,
                title=vs.title,
                classification=vs.classification,
                overall_status=vs.overall_status,
                overall_prima_facie_strength=vs.overall_prima_facie_strength,
                punishment_text=vs.punishment_text,
                ingredient_evaluation=vs.ingredient_evaluation,
                legal_reasoning=vs.legal_reasoning,
                missing_supporting_facts=vs.missing_supporting_facts,
                investigation_requirements=vs.investigation_requirements,
                retrieved_at_turn=0,
            )
        console.print(
            f"[green]✓ Sections retrieved: {list(retrieved.keys())}[/green]\n"
        )

        # Step 3 — Prosecutor extraction (sees case + sections)
        p_output = self._extract_case(case_text, retrieved)

        # Step 4 — Build section usage plan
        usage_plan = self._build_usage_plan(p_output.case_summary, retrieved)

        session = SessionState(
            session_id=session_id,
            case_id=case_id,
            case_text=case_text,
            student_role=student_role,
            prosecutor_output=p_output,
            section_usage_plan=usage_plan,
            retrieved_sections=retrieved,
            argued_concepts=list(p_output.legal_concepts),
        )
        _save_session(session)
        console.print(f"[green]✓ Session created: {_session_path(session_id)}[/green]\n")
        return session

    def opening_argument(self, session: SessionState) -> SessionState:
        _rule("PROSECUTOR — OPENING ARGUMENT")
        sections_text = _format_sections_for_prompt(session.retrieved_sections)
        case_summary  = session.prosecutor_output.case_summary if session.prosecutor_output else ""
        usage_plan    = session.section_usage_plan or SectionUsagePlan()

        system   = _opening_system(sections_text, case_summary, usage_plan)
        decision = self._generate_argument(system, "Opening Argument LLM call")

        session.current_turn += 1
        turn = TurnRecord(
            turn_number=session.current_turn,
            speaker="prosecutor",
            full_argument=decision.argument,
            summary_bullets=decision.summary_bullets,
            concepts_used=decision.pillars_to_address,
            positions_asserted=decision.positions_asserted,
            pillars_covered=decision.pillars_to_address,
            sections_cited=decision.sections_to_cite,
        )
        session.turns.append(turn)
        for p in decision.pillars_to_address:
            if p not in session.pillars_argued:
                session.pillars_argued.append(p)
        for pos in decision.positions_asserted:
            if pos not in session.prosecutor_positions:
                session.prosecutor_positions.append(pos)
        for sec in decision.sections_to_cite:
            if sec not in session.sections_cited_so_far:
                session.sections_cited_so_far.append(sec)

        _display_argument(turn)
        _save_session(session)
        return session

    def rebuttal(self, session: SessionState, defense_argument: str) -> SessionState:
        from .orchestrator_agent import OrchestratorAgent

        # ── Record defense turn ──
        session.current_turn += 1
        console.print("[dim]→ Compressing defense argument…[/dim]")
        compress_raw = _call_llm(
            self.client,
            ('Compress the defense argument into 3–5 bullet points. '
             'Extract key positions as short phrases. '
             'Return ONLY JSON: {"bullets": [...], "positions": [...]}'),
            f"Defense argument:\n{defense_argument}",
            self.model,
        )
        try:
            cd = _parse_json(compress_raw)
            defense_bullets   = cd.get("bullets",    [defense_argument[:200]])
            defense_positions = cd.get("positions",  [])
        except Exception:
            defense_bullets   = [defense_argument[:300]]
            defense_positions = []

        defense_turn = TurnRecord(
            turn_number=session.current_turn,
            speaker="defense",
            full_argument=defense_argument,
            summary_bullets=defense_bullets,
            concepts_used=[],
            positions_asserted=defense_positions,
        )
        session.turns.append(defense_turn)
        for p in defense_positions:
            if p not in session.defense_positions:
                session.defense_positions.append(p)
        _save_session(session)

        # ── Generate rebuttal decision ──
        _rule(f"PROSECUTOR — REBUTTAL (Turn {session.current_turn + 1})")
        sections_text   = _format_sections_for_prompt(session.retrieved_sections)
        case_summary    = session.prosecutor_output.case_summary if session.prosecutor_output else ""
        usage_plan      = session.section_usage_plan or SectionUsagePlan()
        prior_context   = _format_prior_turns(session.turns)
        defense_summary = "\n".join(f"• {b}" for b in defense_bullets)

        system   = _rebuttal_system(
            sections_text=sections_text,
            case_summary=case_summary,
            usage_plan=usage_plan,
            prosecutor_positions=session.prosecutor_positions,
            pillars_argued=session.pillars_argued,
            sections_cited_so_far=session.sections_cited_so_far,
            defense_summary=defense_summary,
            prior_turns_context=prior_context,
        )
        decision = self._generate_argument(system, "Rebuttal LLM call")

        # ── Mid-session orchestrator call if needed ──
        if decision.needs_new_sections and decision.unaddressed_fact.strip():
            fact_text = decision.unaddressed_fact.strip()
            console.print(
                f"[yellow]→ Unaddressed fact: \"{fact_text}\"[/yellow]\n"
                f"[dim]→ Extracting context from case text…[/dim]"
            )
            context_text = _extract_fact_context(session.case_text, fact_text, window=3)
            console.print(f"[dim]  Context: {context_text[:120]}…[/dim]")

            orchestrator = OrchestratorAgent(
                api_key=self.client.api_key, model=self.model
            )
            new_result = orchestrator.query_for_fact(
                fact_text=fact_text,
                context_text=context_text,
                existing_section_numbers=list(session.retrieved_sections.keys()),
            )

            # Merge new sections — never overwrite existing
            for vs in new_result.verified_sections:
                if vs.section_number not in session.retrieved_sections:
                    session.retrieved_sections[vs.section_number] = RetrievedSection(
                        section_number=vs.section_number,
                        statute=vs.statute,
                        title=vs.title,
                        classification=vs.classification,
                        overall_status=vs.overall_status,
                        overall_prima_facie_strength=vs.overall_prima_facie_strength,
                        punishment_text=vs.punishment_text,
                        ingredient_evaluation=vs.ingredient_evaluation,
                        legal_reasoning=vs.legal_reasoning,
                        missing_supporting_facts=vs.missing_supporting_facts,
                        investigation_requirements=vs.investigation_requirements,
                        retrieved_at_turn=session.current_turn,
                    )
                    console.print(
                        f"[green]  + New section: §{vs.section_number} {vs.title}[/green]"
                    )
                    # Also add to usage plan
                    if session.section_usage_plan:
                        session.section_usage_plan.sections.append(SectionUsage(
                            section_number=vs.section_number,
                            statute=vs.statute,
                            title=vs.title,
                            pillar="P2:PrimaFacie",
                            deploy_when="rebuttal",
                            anchored_fact=fact_text,
                            argument_enabled=vs.legal_reasoning[:120],
                            prima_facie_strength=vs.overall_prima_facie_strength,
                            overall_status=vs.overall_status,
                        ))

            for c in decision.new_concepts:
                if c not in session.argued_concepts:
                    session.argued_concepts.append(c)

        # ── Record prosecutor rebuttal ──
        session.current_turn += 1
        rebuttal_turn = TurnRecord(
            turn_number=session.current_turn,
            speaker="prosecutor",
            full_argument=decision.argument,
            summary_bullets=decision.summary_bullets,
            concepts_used=list(session.retrieved_sections.keys()),
            positions_asserted=decision.positions_asserted,
            pillars_covered=decision.pillars_to_address,
            sections_cited=decision.sections_to_cite,
        )
        session.turns.append(rebuttal_turn)
        for p in decision.pillars_to_address:
            if p not in session.pillars_argued:
                session.pillars_argued.append(p)
        for pos in decision.positions_asserted:
            if pos not in session.prosecutor_positions:
                session.prosecutor_positions.append(pos)
        for sec in decision.sections_to_cite:
            if sec not in session.sections_cited_so_far:
                session.sections_cited_so_far.append(sec)

        _display_argument(rebuttal_turn)
        _save_session(session)
        return session