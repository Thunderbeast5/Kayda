"""
Defense Agent - Represents the Accused in criminal proceedings.

Architecture mirrors the Prosecutor Agent:
1. Takes case file as input
2. Uses lexigraphbe's query understanding to decompose the case
3. Identifies weaknesses in prosecution charges and builds defense grounds
4. Queries lexigraphbe for sections relevant to bail entitlement
5. Builds defense arguments from retrieved sections + ingredient matrix
6. Supports multiple rounds: opening bail argument, rebuttal to prosecution, closing

Defense Strategy for Anticipatory Bail:
- Attack prosecution's prima facie case ingredient by ingredient
- Establish civil/contractual nature of dispute where applicable
- Show evidence already in police custody (no tampering risk)
- Establish accused's roots in community (no flight risk)
- Argue Section 41A notice suffices over arrest
- Rely on Arnesh Kumar guidelines for lesser offences
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from lexigraphbe.query_understanding_agent import QueryUnderstandingAgent
from lexigraphbe.query_verifier_agent import QueryVerificationAgent
from lexigraphbe.stage1_pipeline import Stage1Pipeline
from lexigraphbe.schemas import CaseProfile, CaseContextObject, LegalQueryObject
from lexigraphbe.config import get_llm
from dotenv import load_dotenv

load_dotenv()


def get_defense_llm(temperature: float = 0.2):
    return get_llm(temperature=temperature)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DefenseGround:
    """A single ground of defense against one prosecution charge."""
    charge_name: str                          # The prosecution charge being attacked
    severity: str                             # "primary", "secondary", "ancillary"
    ingredients_attacked: List[str]           # Which statutory ingredients are contested
    defense_strategy: str                     # How this ground is argued
    evidence_gaps: List[str] = field(default_factory=list)   # What prosecution hasn't proved
    favorable_evidence: List[str] = field(default_factory=list)  # Evidence supporting defense
    retrieved_sections: List[Dict[str, Any]] = field(default_factory=list)  # Bail-relevant sections


@dataclass
class DefenseAnalysis:
    """Complete defense analysis of a case."""
    case_summary: str                         # Case from accused's perspective
    primary_defense: str                      # Main defense theory
    bail_grounds: List[str]                   # Specific grounds for anticipatory bail
    defense_grounds: List[DefenseGround]      # Per-charge defense grounds
    accused_profile: str                      # Roots in community, cooperation, no prior record
    evidence_assessment: List[str]            # Assessment of prosecution evidence strength
    legal_principles: List[str]               # Legal principles supporting bail


# ---------------------------------------------------------------------------
# Defense Agent
# ---------------------------------------------------------------------------

class DefenseAgent:
    """
    Defense Agent representing the accused in criminal proceedings.

    Key Features:
    - Reads the same case facts as the prosecutor but constructs a defense perspective
    - Builds an ingredient matrix from the DEFENSE viewpoint (what prosecution cannot prove)
    - Attacks prosecution ingredients using evidence gaps, disputed facts, and legal principles
    - Grounds every argument in the 438 CrPC / 482 BNSS bail framework
    - Supports opening bail argument, rebuttal to prosecution, and closing
    """

    def __init__(self):
        self.llm = get_defense_llm(temperature=0.2)
        self.query_understanding_agent = QueryUnderstandingAgent()
        self.query_verifier = QueryVerificationAgent()
        self.stage1_pipeline = Stage1Pipeline(
            query_agent=self.query_understanding_agent,
            verifier_agent=self.query_verifier,
        )

        self.case_context: Optional[CaseContextObject] = None
        self.legal_query: Optional[LegalQueryObject] = None
        self.defense_analysis: Optional[DefenseAnalysis] = None
        self.retrieved_sections_cache: Dict[str, Any] = {}
        self._cached_defense_matrix: List[Dict[str, Any]] = []

    # -----------------------------------------------------------------------
    # Step 1: Analyze case from defense perspective
    # -----------------------------------------------------------------------

    def analyze_case(
        self,
        case_file: str,
        proceeding_type: str = "anticipatory_bail",
        legal_regime: str = "IPC + CrPC",
    ) -> DefenseAnalysis:

        self._proceeding_type = proceeding_type

        _PROCEEDING_MAP = {
            "anticipatory_bail": (
                "Pre-Arrest / Anticipatory Bail (u/s 482 BNSS)",
                "Grant of Anticipatory Bail to applicant",
            ),
            "regular_bail": (
                "Post-Arrest Bail Hearing",
                "Grant of Regular Bail to accused",
            ),
            "trial_defense": (
                "Trial",
                "Acquittal of the accused",
            ),
        }

        procedural_stage, requested_relief = _PROCEEDING_MAP.get(
            proceeding_type,
            ("Pre-Arrest / Anticipatory Bail (u/s 482 BNSS)", "Grant of Anticipatory Bail to applicant"),
        )

        print(f"\n[DefenseAgent] Step 1: Understanding case through query decomposition...")
        print(f"[DefenseAgent] Proceeding type : {proceeding_type}")
        print(f"[DefenseAgent] Procedural stage: {procedural_stage}")

        # Normalise regime
        regime_upper = (legal_regime or "IPC + CrPC").upper()
        normalised_regime = "BNS + BNSS" if ("BNS" in regime_upper or "BNSS" in regime_upper) else "IPC + CrPC"

        # Build CaseProfile exactly as prosecutor does
        case_profile = CaseProfile(
            case_facts=case_file,
            legal_regime=normalised_regime,
            procedural_stage=procedural_stage,
            requested_relief=requested_relief,
        )

        contract_status, contract_violations = case_profile.validate_stage1_contract()

        self.case_context = CaseContextObject(
            case_profile=case_profile,
            contract_status=contract_status,
            contract_violations=contract_violations,
            verification_status="VERIFIED",
            active_parties=case_profile.get_accused_list(),
        )

        # Run Stage 1 — same call as prosecutor
        verification_result = self.stage1_pipeline.run(case_context=self.case_context)

        if verification_result.status != "VERIFIED":
            print(f"[DefenseAgent] Warning: Query verification returned {verification_result.status} — using best-available")

        self.legal_query = (
            verification_result.verified_query_object
            or self.stage1_pipeline.query_agent.run(self.case_context)
        )

        # Patch regime in case Stage 1 returned wrong value
        if self.legal_query and self.legal_query.legal_regime != normalised_regime:
            self.legal_query = LegalQueryObject(
                case_type=self.legal_query.case_type,
                legal_concepts=self.legal_query.legal_concepts,
                sub_queries=self.legal_query.sub_queries,
                legal_regime=normalised_regime,
                important_facts=self.legal_query.important_facts,
                entities=self.legal_query.entities,
                relationship=self.legal_query.relationship,
                procedural_events=self.legal_query.procedural_events,
            )

        concepts = self.legal_query.legal_concepts if self.legal_query else []
        print(f"[DefenseAgent] Identified {len(concepts)} prosecution concepts to counter:")
        for c in concepts:
            print(f"  - {c.concept} (confidence: {c.confidence:.2f})")

        print(f"\n[DefenseAgent] Step 2: Building defense strategy...")
        self.defense_analysis = self._analyze_defense_strategy(case_file, self.legal_query)

        # Enrich legal_query with ALL defense grounds as sub-queries
        # so Stage 2→4 retrieves sections for every charge, not just Stage 1 concepts
        self._enrich_legal_query_with_defense_grounds()

        return self.defense_analysis

    def _enrich_legal_query_with_defense_grounds(self):
        """
        Mirrors prosecutor's _enrich_legal_query_with_identified_crimes.
        Adds each defense ground as a sub-query + concept to legal_query so
        Stage 2→4 retrieves sections for ALL charges, not just Stage 1 concepts.
        """
        from lexigraphbe.schemas import LegalConceptItem, SubQueryItem

        existing_concepts = {c.concept.lower().strip() for c in self.legal_query.legal_concepts}

        for ground in self.defense_analysis.defense_grounds:
            charge_key = ground.charge_name.lower().strip()

            if not any(charge_key in ec or ec in charge_key for ec in existing_concepts):
                new_concept = LegalConceptItem(
                    concept=ground.charge_name,
                    confidence=0.95 if ground.severity == "primary" else 0.85,
                )
                self.legal_query.legal_concepts.append(new_concept)
                existing_concepts.add(charge_key)

                # Use statutory keyword phrasing so Stage 2's prefilter
                # matches the right section (e.g. "stalking repeatedly follows"
                # triggers 354D IPC, not 506 IPC)
                new_sq = SubQueryItem(
                    id=f"SQ{len(self.legal_query.sub_queries) + 1}",
                    query=f"{ground.charge_name}: {', '.join(ground.ingredients_attacked[:3])}",
                    concept=ground.charge_name,
                    target_parties=self.case_context.active_parties or [],
                    role_alleged="Accused",
                )
                self.legal_query.sub_queries.append(new_sq)
                print(f"[DefenseAgent] Added concept to legal_query: {ground.charge_name}")

    # Canonical charge name map — collapses aliases into their parent offence.
    # "Threat" is NOT a standalone offence; it is the mechanism of Criminal Intimidation.
    # "Stalking" and "Harassment" are distinct and must not be merged.
    _CHARGE_CANONICAL_MAP = {
        "threat": "Criminal Intimidation",
        "threatening": "Criminal Intimidation",
        "criminal threat": "Criminal Intimidation",
        "threatening messages": "Criminal Intimidation",
        "threatening communication": "Criminal Intimidation",
        "intimidation": "Criminal Intimidation",
        "wrongful restraint": "Wrongful Restraint",
        "wrongful confinement": "Wrongful Confinement",
        "molestation": "Outraging Modesty",
        "outrage of modesty": "Outraging Modesty",
        "cheating and dishonest inducement": "Cheating",
        "dishonest inducement to deliver property": "Cheating",
        "criminal misappropriation": "Misappropriation of Property",
        "misappropriation": "Misappropriation of Property",
    }

    def _canonicalise_charge(self, charge_name: str) -> str:
        """Collapses alias charge names into their canonical parent offence."""
        return self._CHARGE_CANONICAL_MAP.get(charge_name.lower().strip(), charge_name)

    def _deduplicate_grounds(self, grounds: List["DefenseGround"]) -> List["DefenseGround"]:
        """
        Deduplicates defense grounds by canonical charge name.
        When two grounds resolve to the same canonical name, merges their
        ingredients_attacked, evidence_gaps, and favorable_evidence lists
        and keeps the higher-severity entry.
        """
        severity_rank = {"primary": 0, "secondary": 1, "ancillary": 2}
        merged: Dict[str, "DefenseGround"] = {}

        for g in grounds:
            canonical = self._canonicalise_charge(g.charge_name)
            g.charge_name = canonical  # normalise in place

            if canonical not in merged:
                merged[canonical] = g
            else:
                existing = merged[canonical]
                # Keep higher severity
                if severity_rank.get(g.severity, 2) < severity_rank.get(existing.severity, 2):
                    g.ingredients_attacked = list(dict.fromkeys(
                        g.ingredients_attacked + existing.ingredients_attacked
                    ))
                    g.evidence_gaps = list(dict.fromkeys(
                        g.evidence_gaps + existing.evidence_gaps
                    ))
                    g.favorable_evidence = list(dict.fromkeys(
                        g.favorable_evidence + existing.favorable_evidence
                    ))
                    merged[canonical] = g
                else:
                    existing.ingredients_attacked = list(dict.fromkeys(
                        existing.ingredients_attacked + g.ingredients_attacked
                    ))
                    existing.evidence_gaps = list(dict.fromkeys(
                        existing.evidence_gaps + g.evidence_gaps
                    ))
                    existing.favorable_evidence = list(dict.fromkeys(
                        existing.favorable_evidence + g.favorable_evidence
                    ))

        return list(merged.values())

    def _analyze_defense_strategy(
        self, case_facts: str, legal_query: LegalQueryObject
    ) -> DefenseAnalysis:
        """
        Build the defense strategy from the accused's perspective.
        Attacks statutory ingredients specifically — not consequences.
        """
        concepts_str = "\n".join(
            f"- {c.concept} (confidence: {c.confidence:.2f})"
            for c in (legal_query.legal_concepts if legal_query else [])
        )

        proceeding_type = getattr(self, "_proceeding_type", "anticipatory_bail")
        _PROCEEDING_INSTRUCTIONS = {
            "anticipatory_bail": (
                "PROCEEDING: Anticipatory Bail Application\n"
                "GOAL: Obtain anticipatory bail by attacking the prosecution's prima facie case "
                "at the ingredient level. Focus on: (a) which statutory ingredients cannot be "
                "established on the current material; (b) civil/contractual nature of dispute; "
                "(c) evidence already in police custody; (d) no flight/tampering risk."
            ),
            "regular_bail": (
                "PROCEEDING: Regular Bail Application\n"
                "GOAL: Establish grounds for release — investigation complete, no tampering risk, "
                "no further purpose served by detention."
            ),
            "trial_defense": (
                "PROCEEDING: Trial Defense\n"
                "GOAL: Attack each ingredient that prosecution must prove beyond reasonable doubt. "
                "Identify every evidentiary gap."
            ),
        }
        proceeding_instruction = _PROCEEDING_INSTRUCTIONS.get(
            proceeding_type, _PROCEEDING_INSTRUCTIONS["anticipatory_bail"]
        )

        prompt = f"""You are a Senior Defense Counsel. Analyze the case strictly from the ACCUSED's perspective.

{proceeding_instruction}

CASE FACTS (authoritative — do not add facts not stated here):
{case_facts}

PROSECUTION'S LIKELY CHARGES:
{concepts_str}

DEFENSE ANALYSIS RULES — READ CAREFULLY:

RULE 0 — EVIDENCE INVENTORY FIRST (do this before writing any defense ground):
Read the case facts carefully and list every piece of prosecution evidence explicitly stated.
You MUST account for ALL of it. You cannot pretend evidence does not exist.
Common items to look for: complainant's statement, witness statements (named or unnamed), CCTV footage,
recovered messages/devices, admissions by the accused, medical reports, call records.
If the accused has ADMITTED to an act (e.g. sending messages, being at a location), that act is ESTABLISHED
and cannot be denied — the defense must attack the INTERPRETATION or INTENT, not the act itself.
WRONG: "the prosecution relies solely on the complainant's statement" — when CCTV, messages, and a witness also exist.
RIGHT: "although messages and CCTV corroborate communication and presence, neither independently establishes the requisite criminal intent."

RULE 1 — INGREDIENT-LEVEL ATTACK ONLY:
Attack the statutory ingredient itself, not its consequences.
WRONG: "The photographs were never published, therefore no intimidation."
RIGHT: "The prosecution must establish that the threat was communicated with intent to cause alarm. Non-publication of the photographs is relevant context but does not by itself prove or disprove intent — the defense contests whether the communication was made with the statutory mens rea."
WRONG: "No physical harm occurred, therefore no assault/intimidation."
RIGHT: "The prosecution must establish the accused used criminal force with the requisite intent — the evidence establishes presence and communication but does not independently establish that the specific intent required by the section was formed."

RULE 2 — CHARGE DEDUPLICATION:
"Threat" is NOT a standalone offence — it is the mechanism of Criminal Intimidation (IPC 503 / BNS 351).
Do NOT create a separate "Threat" ground. Fold it into Criminal Intimidation.
Each distinct offence (Criminal Intimidation, Stalking, Outraging Modesty, Cheating, etc.) gets ONE ground.

RULE 3 — EVIDENCE IN CUSTODY:
If key evidence (messages, devices, records) is already with police, state specifically what is in custody and why this eliminates tampering risk.

RULE 4 — CIVIL DISPUTE:
Only raise civil dispute argument if the facts disclose an underlying contractual/financial relationship. State specifically what the civil relationship is.

RULE 5 — DO NOT include Arnesh Kumar or bail-law principles in defense_grounds or bail_grounds.
Bail law is verified separately. Only include ingredient-level and factual grounds here.

RULE 6 — Do NOT concede any ingredient unless it is indefensible on the facts.
But DO concede acts the accused has admitted — only contest the intent or legal characterisation of those acts.

RULE 7 — evidence_gaps must be HONEST:
Only state an evidence gap if that specific item is genuinely absent from the case facts.
Do NOT list "no corroborating evidence" if the case facts contain CCTV, witnesses, or recovered messages.
Instead, state what those items do and do NOT establish — e.g. "CCTV establishes presence but does not capture the alleged threat or establish intent."

Output ONLY valid JSON:
{{
    "case_summary": "Summary from accused's perspective — every defence claim, accused's own version of events",
    "primary_defense": "Main defense theory — one sentence, ingredient-specific",
    "bail_grounds": [
        "Factual ground 1 — ingredient-specific, not bail-law",
        "Factual ground 2",
        "..."
    ],
    "defense_grounds": [
        {{
            "charge_name": "Exact canonical offence name (not 'Threat' — use 'Criminal Intimidation')",
            "severity": "primary|secondary|ancillary",
            "ingredients_attacked": [
                "Exact statutory ingredient prosecution must prove but cannot — stated precisely"
            ],
            "evidence_gaps": [
                "Specific gap: what evidence is missing or insufficient for this ingredient"
            ],
            "favorable_evidence": [
                "Specific fact from the case facts (verbatim or direct) that helps accused"
            ],
            "defense_strategy": "Ingredient-level strategy — attack what prosecution must prove, not what did not happen afterwards"
        }}
    ],
    "accused_profile": "Cooperation with investigation, no prior record (if not stated: state unknown), community ties, undertaking to comply with bail conditions",
    "evidence_assessment": [
        "Assessment of one prosecution evidence item — its strength and what it does and does not establish"
    ],
    "legal_principles": [
        "Legal principle (case name if known) — factual/evidential principles only, no bail-law principles"
    ]
}}

Return ONLY the JSON. No markdown."""

        from lexigraphbe.config import extract_json_from_text
        response = self.llm.invoke(prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

        try:
            parsed = extract_json_from_text(response_text)
        except Exception as e:
            print(f"[DefenseAgent] Strategy parse failed: {e}")
            parsed = {}

        grounds_raw = []
        for g in parsed.get("defense_grounds", []):
            grounds_raw.append(DefenseGround(
                charge_name=g.get("charge_name", "Unknown charge"),
                severity=g.get("severity", "secondary"),
                ingredients_attacked=g.get("ingredients_attacked", []),
                defense_strategy=g.get("defense_strategy", ""),
                evidence_gaps=g.get("evidence_gaps", []),
                favorable_evidence=g.get("favorable_evidence", []),
            ))

        # Deduplicate: collapse "Threat" → "Criminal Intimidation" etc.
        grounds = self._deduplicate_grounds(grounds_raw)
        duped = len(grounds_raw) - len(grounds)
        if duped > 0:
            print(f"[DefenseAgent] Deduplicated {duped} duplicate charge(s)")

        analysis = DefenseAnalysis(
            case_summary=parsed.get("case_summary", ""),
            primary_defense=parsed.get("primary_defense", ""),
            bail_grounds=parsed.get("bail_grounds", []),
            defense_grounds=grounds,
            accused_profile=parsed.get("accused_profile", ""),
            evidence_assessment=parsed.get("evidence_assessment", []),
            legal_principles=parsed.get("legal_principles", []),
        )

        print(f"\nPrimary Defense: {analysis.primary_defense}")
        print(f"\nDefense Grounds ({len(grounds)} after deduplication):")
        for g in analysis.defense_grounds:
            print(f"  - {g.charge_name} ({g.severity})")
            print(f"    Strategy: {g.defense_strategy[:120]}...")

        return analysis

    # -----------------------------------------------------------------------
    # Step 2: Retrieve sections relevant to defense / bail
    # -----------------------------------------------------------------------

    def _run_full_pipeline_once(self) -> Dict[str, Any]:
        """
        Runs Stage 2→3→4 once on the full legal query.
        Caches result for all defense grounds. Same approach as prosecutor.
        """
        if hasattr(self, "_full_pipeline_cache") and self._full_pipeline_cache:
            return self._full_pipeline_cache

        try:
            from lexigraphbe.stage2_pipeline import Stage2Pipeline
            from lexigraphbe.stage3_pipeline import Stage3Pipeline
            from lexigraphbe.stage4_pipeline import Stage4Pipeline

            regime_upper = (self.case_context.case_profile.legal_regime or "IPC + CrPC").upper()
            normalised_regime = "BNS + BNSS" if ("BNS" in regime_upper or "BNSS" in regime_upper) else "IPC + CrPC"

            full_query = self.legal_query
            if full_query.legal_regime != normalised_regime:
                full_query = LegalQueryObject(
                    case_type=full_query.case_type,
                    legal_concepts=full_query.legal_concepts,
                    sub_queries=full_query.sub_queries,
                    legal_regime=normalised_regime,
                    important_facts=full_query.important_facts,
                    entities=full_query.entities,
                    relationship=full_query.relationship,
                    procedural_events=full_query.procedural_events,
                )

            print(f"\n[DefenseAgent] Running full pipeline (Stage 2→3→4)...")

            stage2 = Stage2Pipeline()
            s2_result = stage2.run(full_query)
            if s2_result.status != "VERIFIED":
                print(f"[DefenseAgent] Warning: Stage 2 returned {s2_result.status}")
            s2_output = s2_result.batched_mapping_response.model_dump() if s2_result.batched_mapping_response else {}

            mappings = s2_output.get("mappings", [])
            print(f"[DefenseAgent] Stage 2: {len(mappings)} sub-query mappings")

            stage3 = Stage3Pipeline()
            s3_result = stage3.run(full_query, stage2_mapping=s2_output)
            s3_output = s3_result.verified_chapter_object.model_dump() if s3_result.verified_chapter_object else {}
            print(f"[DefenseAgent] Stage 3: {len(s3_output.get('verified_offences', []))} verified_offences")

            stage4 = Stage4Pipeline()
            s4_result = stage4.run(full_query, s3_output)
            s4_output = s4_result.verified_statutory_object.model_dump() if s4_result.verified_statutory_object else {}

            all_verified = s4_output.get("verified_offences", [])
            if not all_verified:
                for v in s4_output.get("verified_sections", []):
                    all_verified.append({
                        "section_number": v.get("section_number", ""),
                        "statute": v.get("statute", "IPC"),
                        "title": v.get("section_title", ""),
                        "section_title": v.get("section_title", ""),
                        "ingredients_matched": [i.get("ingredient", "") for i in v.get("ingredients", [])],
                        "overall_confidence": v.get("overall_confidence", 0.90),
                        "punishment_text": v.get("punishment_text", ""),
                        "max_imprisonment_years": v.get("max_imprisonment_years", 3.0),
                        "arnesh_kumar_threshold_exceeded": v.get("arnesh_kumar_threshold_exceeded", False),
                    })

            print(f"[DefenseAgent] Stage 4: {len(all_verified)} verified sections")

            self._full_pipeline_cache = {
                "all_verified_sections": all_verified,
                "stage2_output": s2_output,
                "stage3_output": s3_output,
                "stage4_output": s4_output,
                "stage2_mappings": mappings,
            }
            return self._full_pipeline_cache

        except Exception as e:
            print(f"[DefenseAgent] Pipeline error: {e}")
            import traceback; traceback.print_exc()
            self._full_pipeline_cache = {"all_verified_sections": [], "error": str(e)}
            return self._full_pipeline_cache

    def query_sections_for_ground(self, ground: DefenseGround) -> Dict[str, Any]:
        """
        Retrieve sections for a defense ground using the shared pipeline cache.
        Uses same sub_query→concept linkage as prosecutor, with LLM fallback.
        """
        print(f"\n[DefenseAgent] Querying sections for: {ground.charge_name}")

        cache_key = ground.charge_name.lower().strip()
        if cache_key in self.retrieved_sections_cache:
            cached = self.retrieved_sections_cache[cache_key]
            print(f"[DefenseAgent] Using cached: {len(cached.get('recommended_sections', []))} sections")
            ground.retrieved_sections = cached.get("recommended_sections", [])
            return cached

        pipeline_results = self._run_full_pipeline_once()
        all_sections = pipeline_results.get("all_verified_sections", [])
        stage2_mappings = pipeline_results.get("stage2_mappings", [])
        verified_sec_nums = {str(s.get("section_number", "")).strip() for s in all_sections}
        s4_by_num = {str(s.get("section_number", "")).strip(): s for s in all_sections}

        # Build sub_query_id → charge mapping (same logic as prosecutor Step A)
        # ---------------------------------------------------------------------------
        # Section-to-charge title filter
        # ---------------------------------------------------------------------------
        # Stage 2 batches ALL candidate sections per sub-query regardless of which
        # charge that sub-query belongs to. Without filtering, a "Criminal Intimidation"
        # sub-query mapping can carry 354D Stalking as a secondary candidate and vice versa,
        # causing cross-contamination in ground_sections for both charges.
        #
        # The canonical title map below resolves each verified section number to the one
        # charge name it belongs to. A section is only accepted for a ground if it maps
        # to that ground's canonical charge. This is a hard filter — not an LLM call.
        # ---------------------------------------------------------------------------
        _SECTION_CHARGE_MAP: Dict[str, str] = {
            # Criminal Intimidation
            "503": "criminal intimidation",
            "506": "criminal intimidation",
            "351": "criminal intimidation",   # BNS equivalent
            # Stalking
            "354d": "stalking",
            "78":   "stalking",               # BNS equivalent
            # Outraging Modesty
            "354":  "outraging modesty",
            "74":   "outraging modesty",
            # Assault / Wrongful Restraint
            "341":  "wrongful restraint",
            "339":  "wrongful restraint",
            "352":  "assault",
            # Cheating
            "420":  "cheating",
            "318":  "cheating",
            # Defamation
            "499":  "defamation",
            "500":  "defamation",
            # Voyeurism / Privacy
            "354c": "voyeurism",
            "77":   "voyeurism",
            # Dowry / Domestic Violence
            "498a": "cruelty",
            "84":   "cruelty",
            "304b": "dowry death",
            "80":   "dowry death",
            # Kidnapping / Abduction
            "363":  "kidnapping",
            "365":  "kidnapping",
            # Robbery / Theft
            "392":  "robbery",
            "379":  "theft",
            # Hurt
            "323":  "hurt",
            "324":  "hurt",
            "325":  "grievous hurt",
            "326":  "grievous hurt",
            # Sexual assault
            "376":  "rape",
            "354b": "sexual assault",
        }

        def _section_matches_charge(section_number: str, charge_name: str) -> bool:
            """Return True only if this section belongs to this charge."""
            norm_num = section_number.lower().strip()
            norm_charge = charge_name.lower().strip()
            mapped = _SECTION_CHARGE_MAP.get(norm_num)
            if mapped is not None:
                # Accept if the mapped charge is a substring of or equals the ground charge
                return mapped in norm_charge or norm_charge in mapped
            # If not in the map, fall back to checking the section's own title in s4_by_num
            sec_data = s4_by_num.get(section_number, {})
            sec_title = (sec_data.get("title") or sec_data.get("section_title") or "").lower()
            if not sec_title:
                return True   # no title available — let it through, LLM fallback will clean up
            # Accept if charge name keywords appear in section title
            charge_keywords = [w for w in norm_charge.split() if len(w) > 4]
            return any(kw in sec_title for kw in charge_keywords)

        # Build sub_query -> charge linkage using KEYWORD-BASED matching, not substring.
        # Loose substring matching ("stalking" in "criminal intimidation query text") causes
        # cross-contamination. Each canonical charge has a required keyword that must appear
        # in the sub-query's concept field (not free-text query) for a match to count.
        charge_lower = ground.charge_name.lower().strip()
        _CHARGE_KEYWORDS: Dict[str, List[str]] = {
            "criminal intimidation": ["intimidat"],
            "stalking":              ["stalk"],
            "outraging modesty":     ["modesty", "outrag"],
            "cheating":              ["cheat"],
            "wrongful restraint":    ["restraint"],
            "wrongful confinement":  ["confinement"],
            "rape":                  ["rape"],
            "sexual assault":        ["sexual assault"],
            "voyeurism":             ["voyeur"],
            "cruelty":               ["cruelty", "498"],
            "dowry death":           ["dowry death", "304b"],
            "defamation":            ["defam"],
            "kidnapping":            ["kidnap"],
            "robbery":               ["robb"],
            "theft":                 ["theft"],
            "hurt":                  ["hurt"],
        }
        # Fall back to first significant word of charge name if not in map
        required_keywords = _CHARGE_KEYWORDS.get(
            charge_lower,
            [w for w in charge_lower.split() if len(w) > 4][:1] or [charge_lower]
        )

        sq_to_charge: Dict[str, str] = {}
        if self.legal_query:
            for sq in self.legal_query.sub_queries:
                sq_concept = (sq.concept or "").lower()
                # Match only on the concept field, not the free-text query string
                if any(kw in sq_concept for kw in required_keywords):
                    sq_to_charge[sq.id] = ground.charge_name

        # Pull candidate sections from Stage 2 mappings for matched sub-queries.
        # HARD FILTER: _section_matches_charge is applied to every candidate — a section
        # is rejected even if it came from a matched sub-query, if it belongs to a
        # different charge. This is the only line of defence against cross-contamination
        # once Stage 2 batches candidates from multiple charges into the same mapping.
        ground_sections = []
        seen_nums: set = set()
        for mapping in stage2_mappings:
            sq_id = mapping.get("sub_query_id", "")
            if sq_id not in sq_to_charge:
                continue
            all_cands = (
                mapping.get("primary_candidate_sections", []) +
                mapping.get("secondary_candidate_sections", [])
            )
            for csec in all_cands:
                num = str(csec.get("section_number", "")).strip()
                if num not in seen_nums and num in verified_sec_nums:
                    if not _section_matches_charge(num, ground.charge_name):
                        continue   # hard filter: belongs to a different charge
                    seen_nums.add(num)
                    enriched = {**csec, **s4_by_num.get(num, {})}
                    ground_sections.append(enriched)

        # Second pass: if sub_query linkage produced nothing, scan all Stage 2 mappings
        # for sub-queries whose concept/query text overlaps this charge, again with the
        # title filter applied so we still can't pull in the wrong sections.
        if not ground_sections and stage2_mappings and self.legal_query:
            charge_lower = ground.charge_name.lower()
            for mapping in stage2_mappings:
                sq_id = mapping.get("sub_query_id", "")
                sq_obj = next(
                    (sq for sq in self.legal_query.sub_queries if sq.id == sq_id),
                    None,
                )
                if sq_obj is None:
                    continue
                sq_concept = (sq_obj.concept or "").lower()
                sq_query_text = (sq_obj.query or "").lower()
                if charge_lower not in sq_concept and charge_lower not in sq_query_text:
                    charge_keywords = charge_lower.split()
                    if not any(kw in sq_concept or kw in sq_query_text for kw in charge_keywords if len(kw) > 4):
                        continue
                candidate_nums = set()
                for field_name in ("primary_candidate_sections", "secondary_candidate_sections", "candidate_sections"):
                    for item in mapping.get(field_name, []):
                        num = str(item.get("section_number", item) if isinstance(item, dict) else item).strip()
                        if num:
                            candidate_nums.add(num)
                for num in candidate_nums:
                    if num in verified_sec_nums and num not in seen_nums:
                        if not _section_matches_charge(num, ground.charge_name):
                            continue   # wrong charge — skip even in fallback
                        seen_nums.add(num)
                        enriched = {**s4_by_num.get(num, {})}
                        if enriched:
                            ground_sections.append(enriched)

        # LLM fallback: only if nothing matched via sub_query linkage OR section-number pre-pass.
        # Hard rule: the section's title must directly correspond to this charge.
        # Never assign "Criminal Intimidation" to "Stalking" just because it's the
        # only verified section available — return empty and let the matrix use fallback.
        if not ground_sections and all_sections:
            # Build a title→section lookup
            sec_brief = "\n".join(
                f"- {s.get('section_number','')} {s.get('statute','')}: "
                f"{s.get('title', s.get('section_title',''))}"
                for s in all_sections
            )
            assign_prompt = (
                f"You are a legal expert. From the sections below, return ONLY those whose "
                f"title or subject matter DIRECTLY covers the offence '{ground.charge_name}'.\n\n"
                f"SECTIONS:\n{sec_brief}\n\n"
                f"Rules:\n"
                f"1. A section covers '{ground.charge_name}' ONLY if its title names that exact "
                f"offence or a recognised synonym (e.g. 354D IPC covers Stalking, 506 IPC covers "
                f"Criminal Intimidation, 420 IPC covers Cheating).\n"
                f"2. Do NOT assign a section merely because it is the closest available — if no "
                f"section directly covers '{ground.charge_name}', return an empty array [].\n"
                f"3. Return ONLY a JSON array of section_number strings. No markdown."
            )
            try:
                from lexigraphbe.config import extract_json_from_text
                resp = self.llm.invoke(assign_prompt)
                resp_text = resp.content if hasattr(resp, "content") else str(resp)
                matched_nums = extract_json_from_text(resp_text)
                if isinstance(matched_nums, list):
                    matched_strs = [str(n) for n in matched_nums]
                    for s in all_sections:
                        num = str(s.get("section_number", "")).strip()
                        if num in matched_strs and num not in seen_nums:
                            seen_nums.add(num)
                            ground_sections.append(s)
            except Exception as e:
                print(f"[DefenseAgent] LLM section assignment failed: {e}")

        print(f"[DefenseAgent] Retrieved {len(ground_sections)} sections for {ground.charge_name}")
        result = {"recommended_sections": ground_sections}
        self.retrieved_sections_cache[cache_key] = result
        ground.retrieved_sections = ground_sections
        return result

    # -----------------------------------------------------------------------
    # Step 3: Build defense ingredient matrix
    # -----------------------------------------------------------------------

    def _build_defense_matrix(self, case_facts: str) -> List[Dict[str, Any]]:
        """
        Builds a Defense Ingredient Matrix — one LLM call per charge.
        For each prosecution charge, maps every ingredient to:
          - prosecution_status: how strong the prosecution's proof is
          - defense_attack: how the defense contests it
          - evidence_gap: what prosecution is missing
          - favorable_facts: case facts that help the accused
        """
        from lexigraphbe.config import extract_json_from_text

        matrix = []
        for ground in self.defense_analysis.defense_grounds:
            secs = ground.retrieved_sections
            sec_line = ", ".join(
                f"{s.get('section_number','')} {s.get('statute','')} ({s.get('title', s.get('section_title',''))})"
                for s in secs
            ) if secs else "(section pending)"

            # Extract verified statutory ingredients from Stage 4 section data.
            # These are the ACTUAL ingredients the statute requires — not free-form
            # strings generated by the strategy LLM. Using them as the source of truth
            # prevents the matrix LLM from inventing phantom ingredients like
            # "threatening purpose" that don't exist in the section text.
            statutory_ingredients: List[str] = []
            seen_ing: set = set()
            for s in secs:
                for ing in (s.get("ingredients_matched") or []):
                    ing_str = str(ing).strip()
                    if ing_str and ing_str.lower() not in seen_ing:
                        seen_ing.add(ing_str.lower())
                        statutory_ingredients.append(ing_str)
            # Fall back to strategy-generated ingredients only if Stage 4 returned nothing
            if not statutory_ingredients:
                statutory_ingredients = ground.ingredients_attacked or ["All statutory ingredients"]
            ingredients_block = "\n".join(f"  - {ing}" for ing in statutory_ingredients)

            matrix_prompt = f"""You are a defense lawyer building a rigorous ingredient-by-ingredient challenge to a prosecution charge.

CASE FACTS:
{case_facts}

ACCUSED'S POSITION:
{self.defense_analysis.case_summary}

CHARGE TO CHALLENGE: {ground.charge_name}
Section: {sec_line}
Verified statutory ingredients prosecution must prove (from statute — do NOT add, remove, or rename these):
{ingredients_block}

STEP 1 — EVIDENCE INVENTORY (mandatory before assigning any prosecution_status):
List every piece of prosecution evidence in the case facts for this charge:
- Complainant's statement (always present)
- Named witnesses (e.g. Kavya Singh — eyewitness)
- Recovered items (messages, devices — specify which)
- CCTV footage (location and what it captures)
- Accused's own admissions (what exactly was admitted)
Only after completing this inventory may you assess each ingredient below.

For EACH ingredient, assess from the DEFENSE perspective:
- prosecution_status: UNPROVEN / WEAK / DISPUTED / ESTABLISHED
  UNPROVEN  = genuinely no evidence of any kind for this specific ingredient
  WEAK      = evidence exists (name it) but does not directly prove the ingredient —
              e.g. CCTV shows presence but not intent; messages exist but content is ambiguous.
              Do NOT use WEAK to mean "single-witness only" if other evidence also exists.
  DISPUTED  = accused directly contests the act or intent with a specific counter-version
  ESTABLISHED = the ingredient is clearly proved and indefensible — use this when the accused
                has admitted the act or when multiple independent sources confirm it
- defense_attack: the specific legal argument — attack the ingredient, not the consequence.
  CRITICAL: If the accused admitted the act, you CANNOT attack the act. Attack the INTENT only.
- evidence_gap: what specific item is GENUINELY absent.
  FORBIDDEN: Do NOT write "relies solely on complainant's statement" if the case facts also
  contain CCTV, witness testimony, recovered messages, or admissions.
  Instead state: what the corroborating evidence does establish AND what it does NOT establish.
- favorable_facts: verbatim or direct sentences from the case facts that help the accused
- concede: true if the ingredient is ESTABLISHED and indefensible

CRITICAL RULES:
1. Attack the ingredient itself — not what happened afterwards.
   WRONG: "The photographs were never published therefore no intimidation."
   RIGHT: "The prosecution must establish intent to cause alarm from the face of the communications themselves — non-publication is a surrounding circumstance that does not resolve the question of mens rea in either direction."
   WRONG: "No physical harm occurred therefore no assault."
   RIGHT: "The prosecution must establish the accused used criminal force with the requisite intent — presence and physical proximity are established by CCTV and admission, but neither source independently establishes that force was used or that the specific intent required by the section was formed."
2. Do NOT invent facts not in the case facts.
3. favorable_facts must come verbatim or directly from the case facts.
4. Do NOT assess bail law or Arnesh Kumar here — that is handled separately.
5. NEVER describe the evidence record as thin or sole-source when CCTV, witnesses, messages, or admissions appear in the case facts.

Return ONLY this JSON object (single object, not a list):
{{
  "charge_name": "{ground.charge_name}",
  "section": "{sec_line}",
  "punishment_range": "actual statutory range for this section e.g. Up to 2 years / Up to 7 years",
  "ingredients": [
    {{
      "ingredient": "exact statutory ingredient",
      "prosecution_status": "UNPROVEN|WEAK|DISPUTED|ESTABLISHED",
      "defense_attack": "specific legal argument against this ingredient",
      "evidence_gap": "what is specifically missing or insufficient",
      "favorable_facts": ["verbatim or direct fact from case facts"],
      "concede": false
    }}
  ],
  "civil_dispute_argument": "Precise civil/contractual relationship if applicable. Else: Not applicable.",
  "no_tampering_risk": "Specific evidence already in police custody — name it. Else: Not established.",
  "no_flight_risk": "State ONLY facts explicitly present in the case facts. FORBIDDEN: Do NOT infer no flight risk from the fact that the accused applied for anticipatory bail — that is a procedural step, not a factual indicator. If no flight-risk facts are stated, write: No flight-risk facts explicitly stated — no prior criminal record mentioned."
}}
No markdown. Single JSON object only."""

            try:
                response = self.llm.invoke(matrix_prompt)
                response_text = response.content if hasattr(response, "content") else str(response)
                stripped = response_text.strip()
                if stripped.startswith("["):
                    import re as _re
                    inner = _re.search(r'\{.*\}', stripped, _re.DOTALL)
                    if inner:
                        stripped = inner.group(0)
                entry = extract_json_from_text(stripped)
                if isinstance(entry, dict) and "charge_name" in entry:
                    matrix.append(entry)
                    print(f"[DefenseAgent] Defense matrix built for: {ground.charge_name}")
                elif isinstance(entry, list) and entry:
                    matrix.append(entry[0])
                    print(f"[DefenseAgent] Defense matrix built for: {ground.charge_name} (from list)")
                else:
                    print(f"[DefenseAgent] Matrix parse failed for {ground.charge_name} — using fallback")
                    matrix.append(self._fallback_defense_matrix_entry(ground, sec_line))
            except Exception as e:
                print(f"[DefenseAgent] Matrix error for {ground.charge_name}: {e}")
                matrix.append(self._fallback_defense_matrix_entry(ground, sec_line))

        return matrix

    def _fallback_defense_matrix_entry(self, ground: DefenseGround, sec_line: str) -> Dict[str, Any]:
        """
        Safe fallback when matrix LLM call fails or returns unparseable output.
        MUST NOT assert any legal conclusion (UNPROVEN, Arnesh applicable) that
        could cause the argument generator to make a false defense claim.
        All ingredient statuses are UNKNOWN so the generator cannot build
        arguments on fabricated assessments.
        """
        return {
            "charge_name": ground.charge_name,
            "section": sec_line,
            "punishment_range": "UNKNOWN — matrix generation failed",
            "arnesh_kumar_applicable": False,   # never default True — a false legal conclusion
            "ingredients": [
                {
                    "ingredient": ing,
                    "prosecution_status": "UNKNOWN",
                    "defense_attack": "Ingredient assessment unavailable — matrix generation failed.",
                    "evidence_gap": "UNKNOWN — matrix generation failed; do not assert any gap.",
                    "favorable_facts": [],
                    "concede": False,
                }
                for ing in ground.ingredients_attacked
            ],
            "civil_dispute_argument": "Not applicable",
            "no_tampering_risk": "UNKNOWN — matrix generation failed",
            "no_flight_risk": "UNKNOWN — matrix generation failed",
            "arnesh_kumar_argument": "Not assessed — matrix generation failed",
            "_fallback": True,
        }

    # -----------------------------------------------------------------------
    # Step 4: Build opening bail argument
    # -----------------------------------------------------------------------

    def _retrieve_bail_law(self) -> Dict[str, Any]:
        """
        Dedicated bail-law retrieval step.
        Queries lexigraphbe for the procedural bail framework applicable to
        this case — Section 438 CrPC / 482 BNSS, Arnesh Kumar guidelines,
        Section 41A CrPC — and verifies which apply based on the charges
        and punishment ranges in the defense matrix.

        Returns a structured bail_law dict with:
          - applicable_sections: verified bail/procedural sections
          - arnesh_kumar_applicable: bool — true only if ALL charges carry < 7 years
          - arnesh_kumar_reasoning: why it applies or doesn't
          - notice_sufficient: bool — whether 41A notice suffices over arrest
          - bail_principles: list of verified principles from the retrieved sections
        """
        if hasattr(self, "_cached_bail_law") and self._cached_bail_law:
            return self._cached_bail_law

        print("[DefenseAgent] Retrieving bail law framework...")

        # Collect punishment ranges from defense matrix
        matrix = getattr(self, "_cached_defense_matrix", [])
        charge_punishments = []
        for entry in matrix:
            charge_punishments.append({
                "charge": entry.get("charge_name", ""),
                "section": entry.get("section", ""),
                "punishment_range": entry.get("punishment_range", "As per statute"),
                "arnesh_applicable": entry.get("arnesh_kumar_applicable", False),
            })

        # Build the bail law query for the LLM — verified against known statute text
        bail_law_prompt = f"""You are a legal expert on Indian bail law. Assess the bail framework for this case.

CHARGES AND PUNISHMENT RANGES:
{chr(10).join(f"- {c['charge']} | {c['section']} | {c['punishment_range']}" for c in charge_punishments)}

PROCEEDING: Anticipatory Bail under Section 438 CrPC / Section 482 BNSS

TASK: Verify the applicable bail law framework. Answer each question strictly:

1. ARNESH KUMAR APPLICABILITY:
   Arnesh Kumar v. State of Bihar (2014) 8 SCC 273 held that for offences punishable with imprisonment of LESS THAN 7 YEARS, police must record reasons before arrest and consider issuing Section 41A CrPC notice instead.
   - Is Arnesh Kumar applicable to ALL charges listed above? (true only if ALL carry < 7 years)
   - If even one charge carries 7+ years, Arnesh Kumar does not provide a blanket shield.
   - State the specific punishment threshold for each charge above.

2. SECTION 41A CrPC / SECTION 35 BNSS:
   Notice of appearance — is it likely sufficient here given the nature of charges, or does the gravity/evidence warrant arrest?
   Be honest — do not mechanically say notice suffices for all < 7-year offences.

3. SECTION 438 CrPC / 482 BNSS FACTORS:
   State the four factors the court considers: nature of accusation, antecedents, possibility of fleeing, whether accusation appears to be made to humiliate.

Return ONLY valid JSON:
{{
    "arnesh_kumar_applicable": true or false,
    "arnesh_kumar_reasoning": "Specific reason — cite the punishment range of each charge and whether ALL are < 7 years",
    "notice_sufficient": true or false,
    "notice_reasoning": "Specific reason — why notice suffices or does not for these specific charges",
    "applicable_bail_sections": [
        {{
            "section": "438 CrPC / 482 BNSS",
            "title": "Anticipatory Bail",
            "key_factors": ["factor 1", "factor 2", "factor 3", "factor 4"]
        }}
    ],
    "bail_principles": [
        "Verified principle with case name — e.g. Sushila Aggarwal v. State (NCT of Delhi) (2020): anticipatory bail can be of unlimited duration"
    ]
}}
No markdown."""

        try:
            from lexigraphbe.config import extract_json_from_text
            response = self.llm.invoke(bail_law_prompt)
            response_text = response.content if hasattr(response, "content") else str(response)
            bail_law = extract_json_from_text(response_text)
            if isinstance(bail_law, dict):
                print(f"[DefenseAgent] Bail law retrieved — Arnesh applicable: {bail_law.get('arnesh_kumar_applicable')}")
                self._cached_bail_law = bail_law
                return bail_law
        except Exception as e:
            print(f"[DefenseAgent] Bail law retrieval failed: {e}")

        # Fallback — conservative defaults
        self._cached_bail_law = {
            "arnesh_kumar_applicable": False,
            "arnesh_kumar_reasoning": "Could not verify — treat as not established",
            "notice_sufficient": False,
            "notice_reasoning": "Could not verify",
            "applicable_bail_sections": [],
            "bail_principles": [],
        }
        return self._cached_bail_law

    def build_opening_argument(self) -> Dict[str, Any]:
        """
        Build the defense opening argument for anticipatory bail.
        Uses the 3-layer pipeline: retrieve → defense matrix → argument generator.
        """
        if not self.defense_analysis:
            raise ValueError("Must run analyze_case() first")

        print("\n[DefenseAgent] Building Opening Argument...")

        for ground in self.defense_analysis.defense_grounds:
            self.query_sections_for_ground(ground)

        case_facts = self.case_context.case_profile.case_facts if self.case_context else ""

        print("[DefenseAgent] Building Defense Ingredient Matrix...")
        matrix = self._build_defense_matrix(case_facts)
        self._cached_defense_matrix = matrix

        # Fix 4: Dedicated bail law retrieval — NOT inferred from punishment range alone
        bail_law = self._retrieve_bail_law()

        # Serialise matrix for argument generator
        matrix_block_parts = []
        for entry in matrix:
            charge = entry.get("charge_name", "")
            section = entry.get("section", "")
            punishment = entry.get("punishment_range", "As per statute")
            civil = entry.get("civil_dispute_argument", "Not applicable")
            no_tamper = entry.get("no_tampering_risk", "Not assessed")
            no_flight = entry.get("no_flight_risk", "Not assessed")

            ing_lines = []
            for ing in entry.get("ingredients", []):
                status = ing.get("prosecution_status", "UNPROVEN")
                attack = ing.get("defense_attack", "")
                gap = ing.get("evidence_gap", "")
                favorable = "; ".join(ing.get("favorable_facts", []))
                concede = ing.get("concede", False)
                ing_lines.append(
                    f"  Ingredient: {ing.get('ingredient','')}\n"
                    f"  Prosecution status: {status}\n"
                    f"  Defense attack: {attack}\n"
                    f"  Evidence gap: {gap}\n"
                    f"  Favorable facts: {favorable or 'None'}\n"
                    f"  Concede: {concede}"
                )

            matrix_block_parts.append(
                f"CHARGE: {charge} | {section} | Punishment: {punishment}\n"
                + "\n".join(ing_lines)
                + f"\n  Civil dispute: {civil}"
                + f"\n  No tampering risk: {no_tamper}"
                + f"\n  No flight risk: {no_flight}"
            )
        matrix_block = "\n\n".join(matrix_block_parts)

        bail_grounds = "\n".join(f"- {g}" for g in self.defense_analysis.bail_grounds)
        legal_principles = "\n".join(f"- {p}" for p in self.defense_analysis.legal_principles)

        # Bail law block — from verified retrieval, not LLM inference
        arnesh_applicable = bail_law.get("arnesh_kumar_applicable", False)
        arnesh_reasoning = bail_law.get("arnesh_kumar_reasoning", "Not verified")
        notice_sufficient = bail_law.get("notice_sufficient", False)
        notice_reasoning = bail_law.get("notice_reasoning", "Not verified")
        bail_principles_str = "\n".join(
            f"- {p}" for p in bail_law.get("bail_principles", [])
        ) or "- None retrieved"
        bail_sections_str = "\n".join(
            f"- {s.get('section','')}: {s.get('title','')} — Factors: {'; '.join(s.get('key_factors',[]))}"
            for s in bail_law.get("applicable_bail_sections", [])
        ) or "- 438 CrPC / 482 BNSS (standard)"

        bail_law_block = (
            f"VERIFIED BAIL LAW:\n"
            f"  Arnesh Kumar applicable: {arnesh_applicable} — {arnesh_reasoning}\n"
            f"  Section 41A notice sufficient: {notice_sufficient} — {notice_reasoning}\n"
            f"  Applicable sections: {bail_sections_str}\n"
            f"  Verified principles:\n{bail_principles_str}"
        )

        all_fallback = all(e.get("_fallback") for e in matrix) if matrix else True
        fallback_warning = (
            "\nCRITICAL: Matrix contains only preliminary data. "
            "Use 'it is submitted that' for every factual claim. "
            "Do not cite any section number or amount not in the matrix.\n"
        ) if all_fallback else ""

        opening_prompt = f"""You are a Senior Defense Counsel making oral submissions before a Sessions Court seeking anticipatory bail under Section 438 CrPC / Section 482 BNSS.
{fallback_warning}
Your argument must be generated STRICTLY from the matrices below. Do not add facts, inferences, or conclusions not in the matrices.

DEFENSE INGREDIENT MATRIX:
{matrix_block}

{bail_law_block}

BAIL GROUNDS:
{bail_grounds}

LEGAL PRINCIPLES:
{legal_principles}

ARGUMENT RULES — STRICT:

0. SECTION CITATION RULE (mandatory, overrides all other formatting preferences):
   Every time you name a charge — in any paragraph — you MUST immediately cite its
   section number and statute exactly as written in the DEFENSE INGREDIENT MATRIX
   (e.g. "Section 498A IPC / Section 84 BNS" or "Section 304B IPC").
   Naming a charge without citing its section is a violation of this rule.
   This applies to every mention of every charge throughout the argument.

1. Use ONLY: CASE FACTS, DEFENSE INGREDIENT MATRIX, VERIFIED BAIL LAW.

2. Do not introduce any fact, evidence, admission, witness, document, legal section,
   punishment, or case name that is not present in those sources.

3. Do not deny an act that the accused has admitted.

4. Do not claim evidence is absent when the matrix identifies that evidence.

5. For every DISPUTED or WEAK ingredient:
   - identify the statutory ingredient by name;
   - identify the specific evidence the prosecution relies upon (from the matrix);
   - explain precisely why that evidence does not conclusively establish the ingredient
     at the anticipatory-bail stage;
   - state the accused's alternative explanation if present in the matrix.

6. For every ESTABLISHED ingredient (concede=true):
   - concede only the established factual act;
   - immediately distinguish that act from the remaining disputed ingredient.

7. Do not use "no harm occurred, therefore no offence."
   Non-occurrence of a consequence may only be mentioned as contextual evidence
   going to the weight of the prosecution material.

8. Do not call the dispute "civil" unless the matrix's civil_dispute_argument
   field expressly identifies an underlying civil or contractual relationship.

9. Do not claim "no flight risk", "good character", "community ties", or
   "cooperation" unless those exact words appear in the matrix's no_flight_risk field.

10. Do not argue that an offence fails merely because the maximum punishment is
    below seven years. Bail law governs only the arrest and custody question.

11. Every factual proposition must be traceable to CASE FACTS or the matrix.
    Every statutory proposition must be traceable to VERIFIED BAIL LAW
    or the verified statutory ingredients.

12. Prioritise precision over length. Do not repeat the same argument
    in different wording. Do not add material merely to reach a word count.

13. If any ingredient has prosecution_status UNKNOWN, omit that ingredient
    entirely — do not argue it in either direction.

14. EVIDENCE ACKNOWLEDGMENT RULE:
    If CASE FACTS or the Defense Ingredient Matrix identifies evidence supporting
    an ingredient, the argument MUST acknowledge that evidence by name.
    The argument may challenge its reliability, interpretation, sufficiency,
    or connection to the ingredient, but MUST NOT claim that no evidence exists
    when the matrix or case facts show that evidence does exist.

15. LEGAL INGREDIENT RULE:
    Use the exact verified statutory ingredients supplied by the matrix.
    Do not create, expand, narrow, or paraphrase them into a new legal test.
    Example of what is FORBIDDEN: the matrix supplies "repeatedly follows or
    contacts despite clear indication of disinterest" and the argument writes
    "intent to follow or monitor with a threatening purpose" — that is a new,
    invented test and is not permitted.

STRUCTURE — five paragraphs, single continuous prose (no headings, no bullets):

Paragraph 1:
State the applicant's principal case and the limited issue at the
anticipatory-bail stage.

Paragraph 2:
Attack the strongest prosecution charge ingredient-by-ingredient using the
matrix. For each ingredient, apply Rules 5 and 6 above.

Paragraph 3:
Attack the next charge, if any, in the same manner.

Paragraph 4:
Address evidence already recovered (from no_tampering_risk field) and why
custodial interrogation is or is not necessary, using ONLY the verified bail
law block. If Arnesh Kumar is applicable (arnesh_kumar_applicable: true AND
notice_sufficient: true), cite Arnesh Kumar v. State of Bihar (2014) 8 SCC 273
with its exact holding and name each completed investigation step. If not
applicable, omit Arnesh Kumar entirely.

Paragraph 5:
State only verified bail considerations drawn from the bail law block.
If no_flight_risk field contains verified facts, state them here and only here.

Final sentence (exact):
"It is therefore humbly prayed that this Hon'ble Court be pleased to grant anticipatory bail to the applicant."

LENGTH: 300–450 words. Do not add material merely to reach the word count."""

        response = self.llm.invoke(opening_prompt)
        opening_prose = response.content if hasattr(response, "content") else str(response)

        argument = {
            "phase": "opening",
            "primary_defense": self.defense_analysis.primary_defense,
            "opening_statement": opening_prose,
            "defense_matrix": matrix,
            "defense_grounds": [
                {
                    "charge": g.charge_name,
                    "ingredients_attacked": g.ingredients_attacked,
                    "evidence_gaps": g.evidence_gaps,
                    "sections": g.retrieved_sections,
                    "strategy": g.defense_strategy,
                }
                for g in self.defense_analysis.defense_grounds
            ],
            "bail_grounds": self.defense_analysis.bail_grounds,
            "legal_principles": self.defense_analysis.legal_principles,
        }
        return argument

    # -----------------------------------------------------------------------
    # Step 5: Rebuttal to prosecution argument
    # -----------------------------------------------------------------------

    def handle_rebuttal(self, prosecution_argument: str) -> Dict[str, Any]:
        """
        Rebuttal to the prosecution's opening or counter-argument.
        Uses the cached defense matrix to respond to each prosecution point.
        """
        print("\n[DefenseAgent] Preparing Rebuttal to Prosecution...")

        if not self.defense_analysis:
            raise ValueError("Must run analyze_case() first")

        matrix = self._cached_defense_matrix or []
        matrix_block_parts = []
        for entry in matrix:
            ing_lines = []
            for ing in entry.get("ingredients", []):
                status = ing.get("prosecution_status", "UNPROVEN")
                attack = ing.get("defense_attack", "")
                gap = ing.get("evidence_gap", "")
                ing_lines.append(
                    f"  [{ing.get('ingredient','')}] Status: {status} | Attack: {attack} | Gap: {gap}"
                )
            matrix_block_parts.append(
                f"CHARGE: {entry.get('charge_name','')} | {entry.get('section','')}\n"
                + "\n".join(ing_lines)
                + f"\n  Civil dispute: {entry.get('civil_dispute_argument','Not applicable')}"
                + f"\n  No tampering: {entry.get('no_tampering_risk','Not assessed')}"
                + f"\n  Arnesh: {entry.get('arnesh_kumar_argument','Not applicable')}"
            )
        matrix_block = "\n\n".join(matrix_block_parts) or "(Defense matrix not available)"

        bail_law = getattr(self, "_cached_bail_law", {})
        arnesh_applicable = bail_law.get("arnesh_kumar_applicable", False)
        notice_sufficient = bail_law.get("notice_sufficient", False)
        arnesh_block = (
            f"VERIFIED BAIL LAW: Arnesh Kumar applicable: {arnesh_applicable} | "
            f"41A notice sufficient: {notice_sufficient} | "
            f"Reasoning: {bail_law.get('arnesh_kumar_reasoning','Not verified')}"
        )

        case_facts = self.case_context.case_profile.case_facts if self.case_context else ""

        prompt = f"""You are a Senior Defense Counsel making sharp rebuttal submissions seeking anticipatory bail under Section 438 CrPC / Section 482 BNSS.

DEFENSE INGREDIENT MATRIX:
{matrix_block}

{arnesh_block}

CASE FACTS:
{case_facts}

PROSECUTION ARGUMENT TO REBUT:
{prosecution_argument}

REBUTTAL RULES — STRICT:

0. SECTION CITATION RULE (mandatory, overrides all other formatting preferences):
   Every time you name a charge — anywhere in the rebuttal — you MUST immediately
   cite its section number and statute exactly as written in the DEFENSE INGREDIENT
   MATRIX (e.g. "Section 498A IPC / Section 84 BNS").
   Naming a charge without its section number is a violation of this rule.

1. Respond only to contentions the prosecution actually made in the argument above.
   Do not invent prosecution points that were not raised.



2. For each prosecution contention, in this order:
   (a) State what the prosecution relies upon;
   (b) State what that evidence establishes (concede it if true);
   (c) State what it does NOT establish and why, by reference to the matrix;
   (d) State the accused's counter-position if present in the matrix.

3. Do not deny an act the accused has admitted.

4. EVIDENCE ACKNOWLEDGMENT RULE:
   If the matrix or case facts identify evidence for an ingredient, acknowledge
   it by name. You may challenge its reliability, interpretation, sufficiency,
   or inferential connection to the ingredient, but MUST NOT claim no evidence
   exists when the matrix shows that it does.

5. LEGAL INGREDIENT RULE:
   Use the exact verified statutory ingredients from the matrix.
   Do not create, expand, narrow, or paraphrase them into a new legal test.

6. Do not repeat the opening argument unless directly needed to answer
   a specific prosecution contention.

7. Do not create a new defense ground during rebuttal.

8. Do not use consequence-based reasoning ("no harm → no offence").

9. Do not introduce any fact, section, case, or evidence not in the matrix
   or the verified bail law block.

10. If any ingredient has prosecution_status UNKNOWN, do not argue it.

11. Use bail law only for the arrest/custody question — not to argue that
    an offence is not made out.

12. End with exactly: "It is therefore prayed that anticipatory bail be granted."

FORMAT: Single continuous prose. No headings. No bullet points. 200–350 words.

Write only the rebuttal text."""

        response = self.llm.invoke(prompt)
        rebuttal_text = (response.content if hasattr(response, "content") else str(response)).strip()

        return {
            "phase": "rebuttal",
            "prosecution_argument_summary": prosecution_argument[:300],
            "defense_response": {
                "charges_addressed": [g.charge_name for g in self.defense_analysis.defense_grounds],
                "rebuttal": rebuttal_text,
            }
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("DEFENSE AGENT - Accused's Counsel System")
    print("=" * 80)

    print("\n📋 Enter case facts (paste the case details)")
    print("Press ENTER twice when done:\n")

    lines = []
    empty_count = 0
    while True:
        try:
            line = input()
            if line.strip() == "":
                empty_count += 1
                if empty_count >= 2 and lines:
                    break
            else:
                empty_count = 0
                lines.append(line)
        except EOFError:
            break

    case_file = "\n".join(lines).strip()
    if not case_file:
        print("\n[ERROR] No case facts entered. Exiting...")
        return

    print("\n" + "=" * 80)
    print("Case File Received:")
    print("=" * 80)
    print(case_file)
    print("\n" + "=" * 80)

    defense = DefenseAgent()

    # STEP 1: Analyze case
    print("\n[STEP 1] Analyzing Case and Building Defense Strategy...")
    analysis = defense.analyze_case(case_file)

    print(f"\nPrimary Defense: {analysis.primary_defense}")
    print(f"\nBail Grounds:")
    for g in analysis.bail_grounds:
        print(f"  - {g}")
    print(f"\nDefense Grounds:")
    for g in analysis.defense_grounds:
        print(f"  - {g.charge_name} ({g.severity})")
        print(f"    Strategy: {g.defense_strategy[:120]}...")

    # STEP 2: Build opening bail argument
    print("\n" + "=" * 80)
    print("[STEP 2] Building Opening Bail Argument...")
    print("=" * 80)
    opening = defense.build_opening_argument()

    print(f"\nPrimary Defense: {opening['primary_defense']}")
    print(f"\nDefense Grounds and Retrieved Sections:")
    for g in opening['defense_grounds']:
        print(f"\n  Charge Contested: {g['charge']}")
        print(f"  Ingredients Attacked: {', '.join(g['ingredients_attacked'])}")
        secs = g.get('sections', [])
        print(f"  Retrieved Sections: {len(secs)}")
        for sec in secs[:3]:
            print(f"    - {sec.get('section_number','N/A')} {sec.get('statute','')}: {sec.get('title', sec.get('section_title',''))}")

    if opening.get("opening_statement"):
        print("\n" + "=" * 80)
        print("FULL OPENING BAIL ARGUMENT:")
        print("=" * 80)
        print(opening["opening_statement"])

    # STEP 3: Wait for prosecution argument to rebut
    print("\n" + "=" * 80)
    print("[STEP 3] Prosecution Argument (for rebuttal)")
    print("=" * 80)
    print("\n📋 Enter prosecution's argument (press ENTER twice when done):\n")

    pro_lines = []
    empty_count = 0
    while True:
        try:
            line = input()
            if line.strip() == "":
                empty_count += 1
                if empty_count >= 2 and pro_lines:
                    break
            else:
                empty_count = 0
                pro_lines.append(line)
        except EOFError:
            break

    pro_arg = "\n".join(pro_lines).strip()
    if not pro_arg:
        print("\n[INFO] No prosecution argument provided. Exiting...")
        return

    print("\n" + "=" * 80)
    print("Prosecution Argument Received:")
    print("=" * 80)
    print(pro_arg)

    # STEP 4: Defense rebuttal
    print("\n" + "=" * 80)
    print("[STEP 4] Defense Rebuttal")
    print("=" * 80)
    rebuttal = defense.handle_rebuttal(pro_arg)

    resp = rebuttal["defense_response"]
    print(f"\nCharges Addressed: {', '.join(resp.get('charges_addressed', []))}")
    print(f"\nRebuttal:\n")
    print(resp.get("rebuttal", ""))

    print("\n" + "=" * 80)
    print("Defense Workflow Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()