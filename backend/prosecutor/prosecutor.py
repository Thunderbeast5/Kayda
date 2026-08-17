"""
Prosecutor Agent - Defends the State/Complainant in criminal cases.

Architecture:
1. Takes case file as input
2. Uses lexigraphbe's query understanding to decompose the case
3. Identifies main offenses and required legal arguments
4. Queries lexigraphbe agent selectively for specific crimes
5. Builds prosecutorial arguments from retrieved sections
6. Can be queried multiple times during trial (opening, rebuttal, closing)
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

# Add backend directory to path for imports
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Import lexigraphbe components
from lexigraphbe.query_understanding_agent import QueryUnderstandingAgent
from lexigraphbe.query_verifier_agent import QueryVerificationAgent
from lexigraphbe.stage1_pipeline import Stage1Pipeline
from lexigraphbe.schemas import CaseProfile, CaseContextObject, LegalQueryObject

# Import LLM from lexigraphbe config (will use Groq based on .env)
from lexigraphbe.config import get_llm
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_prosecutor_llm(temperature: float = 0.2):
    """Get LLM instance using lexigraphbe config (respects LLM_PROVIDER in .env)"""
    return get_llm(temperature=temperature)


@dataclass
class CrimeAnalysis:
    """Analysis of a specific crime/offense in the case"""
    crime_name: str
    severity: str  # "primary", "secondary", "ancillary"
    legal_elements: List[str]
    prosecution_strategy: str
    required_sections: List[str] = field(default_factory=list)
    retrieved_sections: List[Dict[str, Any]] = field(default_factory=list)
    supporting_precedents: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ProsecutorAnalysis:
    """Complete prosecutorial analysis of a case"""
    case_summary: str
    identified_crimes: List[CrimeAnalysis]
    primary_crime: str
    prosecution_theory: str
    evidence_requirements: List[str]
    legal_principles: List[str]


class ProsecutorAgent:
    """
    Prosecutor Agent that defends the State/Complainant.
    
    Key Features:
    - Uses lexigraphbe's query understanding to decompose case
    - Identifies primary and ancillary offenses
    - Selectively queries lexigraphbe for specific crime-related sections
    - Builds prosecutorial arguments from retrieved legal framework
    - Supports multiple rounds of argumentation (opening, rebuttal, closing)
    """
    
    def __init__(self, lexigraphbe_pipeline=None):
        """
        Initialize Prosecutor Agent.
        
        Args:
            lexigraphbe_pipeline: Optional pre-configured lexigraphbe pipeline
        """
        # Use get_llm from lexigraphbe.config (respects LLM_PROVIDER in .env - now Groq)
        self.llm = get_prosecutor_llm(temperature=0.2)
        self.query_understanding_agent = QueryUnderstandingAgent()
        self.query_verifier = QueryVerificationAgent()
        self.stage1_pipeline = Stage1Pipeline(
            query_agent=self.query_understanding_agent,
            verifier_agent=self.query_verifier
        )
        
        # Store context for multi-turn interactions
        self.case_context: Optional[Dict[str, Any]] = None
        self.legal_query: Optional[LegalQueryObject] = None
        self.prosecutor_analysis: Optional[ProsecutorAnalysis] = None
        self.retrieved_sections_cache: Dict[str, Any] = {}
        
    def analyze_case(
        self,
        case_file: str,
        proceeding_type: str = "anticipatory_bail_opposition",
        legal_regime: str = "IPC + CrPC",  # Default to IPC until BNS database is fully populated
    ) -> ProsecutorAnalysis:
        """
        Main entry point: Analyze case file and prepare prosecutorial strategy.

        Args:
            case_file: Raw case text/facts.
            proceeding_type: Nature of the proceeding — drives how Stage 1 frames
                legal concepts and how the strategy LLM selects the primary crime.
                Supported values:
                  "anticipatory_bail_opposition"  (default)
                  "bail_opposition"
                  "trial_prosecution"
                  "civil_injunction"
                  "consumer_dispute"
                  "cheque_dishonour"        # NI Act
                  "motor_accident_claim"    # MACT
            legal_regime: Applicable statutory regime ("BNS_2023", "IPC_1860", etc.)

        Returns:
            ProsecutorAnalysis with identified crimes and strategy.
        """
        self._proceeding_type = proceeding_type  # store for downstream prompts

        # Map proceeding_type → (procedural_stage, requested_relief) for CaseProfile
        _PROCEEDING_MAP = {
            "anticipatory_bail_opposition": (
                "Pre-Arrest / Anticipatory Bail (u/s 482 BNSS)",
                "Opposition to grant of Anticipatory Bail",
            ),
            "bail_opposition": (
                "Post-Arrest Bail Hearing",
                "Opposition to grant of Regular Bail",
            ),
            "trial_prosecution": (
                "Trial",
                "Conviction of the accused",
            ),
            "civil_injunction": (
                "Civil Suit / Injunction Application",
                "Grant of interim / permanent injunction",
            ),
            "consumer_dispute": (
                "Consumer Forum Complaint",
                "Compensation and relief under Consumer Protection Act",
            ),
            "cheque_dishonour": (
                "Summary Trial (NI Act s.138)",
                "Conviction and compensation for dishonoured cheque",
            ),
            "motor_accident_claim": (
                "MACT Claim Petition",
                "Compensation award under Motor Vehicles Act",
            ),
        }

        procedural_stage, requested_relief = _PROCEEDING_MAP.get(
            proceeding_type,
            ("Pre-Arrest / Anticipatory Bail (u/s 482 BNSS)", "Opposition to grant of Anticipatory Bail"),
        )

        print("\n[ProsecutorAgent] Step 1: Understanding case through query decomposition...")
        print(f"[ProsecutorAgent] Proceeding type : {proceeding_type}")
        print(f"[ProsecutorAgent] Procedural stage: {procedural_stage}")

        # Create case profile with required fields
        case_profile = CaseProfile(
            case_facts=case_file,
            legal_regime=legal_regime,
            procedural_stage=procedural_stage,
            requested_relief=requested_relief,
        )
        
        # Validate contract
        contract_status, contract_violations = case_profile.validate_stage1_contract()
        
        # Create case context object with all required fields
        self.case_context = CaseContextObject(
            case_profile=case_profile,
            contract_status=contract_status,
            contract_violations=contract_violations,
            verification_status="VERIFIED",  # Assume verified for direct prosecutor use
            active_parties=case_profile.get_accused_list()
        )
        
        # Run lexigraphbe Stage 1 pipeline for query understanding
        verification_result = self.stage1_pipeline.run(case_context=self.case_context)

        if verification_result.status != "VERIFIED":
            print(f"[ProsecutorAgent] Warning: Query verification returned {verification_result.status} — "
                  f"using best-available query object from understanding agent")

        # verified_query_object is None on RETRY; fall back to the understanding agent's
        # raw output which is always populated regardless of verification outcome.
        self.legal_query = (
            verification_result.verified_query_object
            or self.stage1_pipeline.query_agent.run(self.case_context)
        )

        print(f"[ProsecutorAgent] Identified {len(self.legal_query.legal_concepts)} legal concepts:")
        for concept in self.legal_query.legal_concepts:
            print(f"  - {concept.concept} (confidence: {concept.confidence:.2f})")
        
        print(f"\n[ProsecutorAgent] Step 2: Analyzing crimes and prosecution strategy...")
        
        # Analyze which crimes to prosecute
        prosecutor_analysis = self._analyze_prosecution_strategy(case_file, self.legal_query)
        self.prosecutor_analysis = prosecutor_analysis
        
        # CRITICAL FIX: Update legal_query with prosecutor-identified crimes
        # Stage 1 might have identified "Criminal Intimidation" + "Theft" as separate concepts,
        # but the prosecutor correctly recognizes this as "Extortion" (threat + demand for property)
        # We need to add any missing crime concepts to legal_query before querying lexigraphbe
        self._enrich_legal_query_with_identified_crimes()
        
        return prosecutor_analysis
    
    def _enrich_legal_query_with_identified_crimes(self):
        """
        Enrich the legal_query with crimes identified by the prosecutor strategy LLM.
        Stage 1 identifies raw concepts, but the prosecutor refines them into specific crimes.
        This ensures lexigraphbe retrieves sections for ALL identified crimes, especially the primary one.
        """
        from lexigraphbe.schemas import LegalConceptItem, SubQueryItem
        
        existing_concepts = {c.concept.lower().strip() for c in self.legal_query.legal_concepts}
        
        for crime in self.prosecutor_analysis.identified_crimes:
            crime_key = crime.crime_name.lower().strip()
            
            # Check if this crime is already in legal_query concepts
            if not any(crime_key in ec or ec in crime_key for ec in existing_concepts):
                # Add missing crime as a new legal concept
                new_concept = LegalConceptItem(
                    concept=crime.crime_name,
                    confidence=0.95 if crime.severity == "primary" else 0.85
                )
                self.legal_query.legal_concepts.append(new_concept)
                
                # Also add a sub-query for this crime
                new_sub_query = SubQueryItem(
                    id=f"SQ{len(self.legal_query.sub_queries) + 1}",
                    query=f"{crime.crime_name}: {', '.join(crime.legal_elements)}",
                    concept=crime.crime_name,
                    target_parties=self.case_context.active_parties or [],
                    role_alleged="Accused"
                )
                self.legal_query.sub_queries.append(new_sub_query)
                
                print(f"[ProsecutorAgent] Added missing concept to legal_query: {crime.crime_name}")
    
    def _analyze_prosecution_strategy(self, case_facts: str, legal_query: LegalQueryObject) -> ProsecutorAnalysis:
        """
        Analyze the case and determine prosecution strategy.
        Identifies primary crime, supporting crimes, and strategy.
        """
        
        # Extract legal concepts from query
        concepts_str = "\n".join([
            f"- {lc.concept} (confidence: {lc.confidence:.2f})"
            for lc in legal_query.legal_concepts
        ])
        
        sub_queries_str = "\n".join([
            f"- {sq.query}"
            for sq in legal_query.sub_queries
        ])
        
        # Build proceeding-specific instruction block
        proceeding_type = getattr(self, "_proceeding_type", "anticipatory_bail_opposition")
        _PROCEEDING_INSTRUCTIONS = {
            "anticipatory_bail_opposition": (
                "PROCEEDING: Opposition to Anticipatory Bail\n"
                "GOAL: Identify the most serious, best-evidenced, cognisable and non-bailable "
                "offence from the facts to anchor the bail opposition. Prefer offences with "
                "direct physical or CCTV/documentary evidence over those requiring inference "
                "of intent. The primary_crime must be the offence that most strongly justifies "
                "REFUSING anticipatory bail — weigh statutory gravity AND evidence strength together."
            ),
            "bail_opposition": (
                "PROCEEDING: Opposition to Regular Bail\n"
                "GOAL: Select the primary offence that justifies continued custody — consider "
                "risk of flight, tampering with evidence, and gravity of the offence."
            ),
            "trial_prosecution": (
                "PROCEEDING: Trial on Merits\n"
                "GOAL: Select the offence that carries the highest probability of conviction "
                "given the evidence on record. Prefer charges where all legal elements are "
                "provable beyond reasonable doubt."
            ),
            "civil_injunction": (
                "PROCEEDING: Civil Injunction\n"
                "GOAL: Identify the primary cause of action that establishes a prima facie case, "
                "balance of convenience, and irreparable harm for the injunction prayer."
            ),
            "consumer_dispute": (
                "PROCEEDING: Consumer Forum Complaint\n"
                "GOAL: Identify the primary deficiency in service or unfair trade practice that "
                "anchors the complaint and supports the compensation prayer."
            ),
            "cheque_dishonour": (
                "PROCEEDING: NI Act Section 138 Summary Trial\n"
                "GOAL: The primary offence is always dishonour of cheque. Identify supporting "
                "elements: legally enforceable debt, proper notice, and failure to pay."
            ),
            "motor_accident_claim": (
                "PROCEEDING: MACT Claim Petition\n"
                "GOAL: Establish negligence, causation, and quantum of compensation as primary "
                "issues. Identify all heads of compensation available."
            ),
        }
        proceeding_instruction = _PROCEEDING_INSTRUCTIONS.get(
            proceeding_type,
            _PROCEEDING_INSTRUCTIONS["anticipatory_bail_opposition"],
        )

        prompt = f"""You are a Senior Public Prosecutor. Your task is STRICTLY LIMITED to the proceeding described below.

{proceeding_instruction}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CASE FACTS (authoritative — do not embellish or add facts):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{case_facts}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRELIMINARY LEGAL CONCEPTS IDENTIFIED (use as a starting point, not a ceiling):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{concepts_str}

SUB-QUERIES FOR THIS CASE:
{sub_queries_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LEGAL ANALYSIS RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. You MAY add offences clearly supported by the case facts even if not in the preliminary list.
   The preliminary list is a starting point — exercise your legal judgment from the facts.
2. EXTORTION RULE: If the facts show a person was threatened to hand over money or property
   under threat of accusation/harm, that IS Extortion (BNS 308/309) — identify it as such
   even if the preliminary concepts call it "Dishonest Inducement" or "Criminal Intimidation".
   Extortion is ALWAYS more serious than bare Criminal Intimidation when a demand for property
   accompanies the threat — treat it as primary in anticipatory bail proceedings.
3. Do NOT include any IPC/BNS section numbers in your output — name crimes by concept only.
4. The primary_crime must be the concept best suited to the PROCEEDING GOAL, not merely
   the most morally serious offence in the abstract.
5. Every identified crime must be directly supported by specific facts stated above.

OFFENCE SEVERITY GUIDE FOR ANTICIPATORY BAIL:
- Extortion (threat + demand for property): HIGH — primary
- Theft (taking property without consent, with evidence): HIGH — primary or secondary
- Criminal Intimidation (threat alone, no property demand): MEDIUM — secondary
- Voluntarily Causing Hurt / Physical Assault: MEDIUM — secondary or ancillary

Output ONLY valid JSON matching this structure exactly:
{{
    "case_summary": "Detailed summary from the prosecution's perspective — cover all facts, evidence, and accused's defence claim",
    "primary_crime": "Name of the main offence",
    "prosecution_theory": "Comprehensive theory tailored to the proceeding goal — explain WHY bail must be refused",
    "identified_crimes": [
        {{
            "crime_name": "Name of offence",
            "severity": "primary|secondary|ancillary",
            "legal_elements": ["element1", "element2", "element3"],
            "prosecution_strategy": "Detailed strategy citing specific evidence from the facts",
            "required_sections": ["Describe the type of BNS/BNSS section needed, NO section numbers"]
        }}
    ],
    "evidence_requirements": ["Specific evidence item grounded in the facts"],
    "legal_principles": ["Applicable legal principle relevant to bail refusal"]
}}

Return ONLY the JSON, no markdown, no explanation."""
        
        response = self.llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Use enhanced JSON parser from lexigraphbe config
        from lexigraphbe.config import extract_json_from_text
        
        try:
            analysis_dict = extract_json_from_text(response_text)
        except ValueError as e:
            print(f"[ProsecutorAgent] JSON parsing failed: {e}")
            print(f"[ProsecutorAgent] Response text: {response_text[:500]}...")
            raise
        
        # Convert to ProsecutorAnalysis
        identified_crimes = []
        for crime_data in analysis_dict.get("identified_crimes", []):
            crime = CrimeAnalysis(
                crime_name=crime_data["crime_name"],
                severity=crime_data["severity"],
                legal_elements=crime_data.get("legal_elements", []),
                prosecution_strategy=crime_data.get("prosecution_strategy", ""),
                required_sections=crime_data.get("required_sections", [])
            )
            identified_crimes.append(crime)
        
        prosecutor_analysis = ProsecutorAnalysis(
            case_summary=analysis_dict.get("case_summary", ""),
            identified_crimes=identified_crimes,
            primary_crime=analysis_dict.get("primary_crime", ""),
            prosecution_theory=analysis_dict.get("prosecution_theory", ""),
            evidence_requirements=analysis_dict.get("evidence_requirements", []),
            legal_principles=analysis_dict.get("legal_principles", [])
        )
        
        return prosecutor_analysis
    
    def query_lexigraphbe_all_crimes(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Query lexigraphbe pipeline ONCE for ALL crimes using the full legal_query from Stage 1.
        This is the correct architecture — the pipeline was designed to handle multiple crimes together.
        The prefilter sees ALL concepts at once and can properly distinguish between them.
        
        Returns:
            Dict mapping crime names to their retrieved sections
        """
        # Check if we've already run the full pipeline
        if hasattr(self, '_all_crimes_sections_retrieved') and self._all_crimes_sections_retrieved:
            print(f"\n[ProsecutorAgent] Using previously retrieved sections for all crimes")
            return self.retrieved_sections_cache
        
        print(f"\n[ProsecutorAgent] Querying lexigraphbe for ALL crimes together...")
        
        try:
            from lexigraphbe.stage2_pipeline import Stage2Pipeline
            from lexigraphbe.stage3_pipeline import Stage3Pipeline
            from lexigraphbe.stage4_pipeline import Stage4Pipeline
            
            # Use the FULL legal_query from Stage 1 (contains all concepts together)
            # This prevents the prefilter from misclassifying crimes due to case facts bleed
            print(f"[ProsecutorAgent] Running Stage 2: Section Mapping for {len(self.legal_query.legal_concepts)} concepts...")
            stage2_pipeline = Stage2Pipeline()
            stage2_result = stage2_pipeline.run(self.legal_query)
            
            if stage2_result.status != "VERIFIED":
                print(f"[ProsecutorAgent] Warning: Stage 2 returned {stage2_result.status}")
            
            stage2_output = stage2_result.batched_mapping_response.model_dump() if stage2_result.batched_mapping_response else {}
            
            # Debug: Check what Stage 2 returned
            if stage2_output:
                mappings = stage2_output.get("mappings", [])
                print(f"[ProsecutorAgent] Stage 2 output: {len(mappings)} concept mappings")
                for mapping in mappings[:5]:  # Show first 5
                    sub_query_text = mapping.get("sub_query_text", "Unknown")
                    primary_secs = mapping.get("primary_candidate_sections", [])
                    if primary_secs:
                        sec = primary_secs[0]
                        print(f"  - {sub_query_text[:50]} → {sec.get('section_number', 'N/A')} {sec.get('statute', '')}")
            
            print(f"[ProsecutorAgent] Running Stage 3: Chapter Identification...")
            stage3_pipeline = Stage3Pipeline()
            stage3_result = stage3_pipeline.run(self.legal_query, stage2_mapping=stage2_output)
            
            if stage3_result.status != "VERIFIED":
                print(f"[ProsecutorAgent] Warning: Stage 3 returned {stage3_result.status}")
            
            stage3_output = stage3_result.verified_chapter_object.model_dump() if stage3_result.verified_chapter_object else {}
            
            # Debug: Check what Stage 3 returned
            if stage3_output:
                verified_offences_s3 = stage3_output.get("verified_offences", [])
                section_candidates_s3 = stage3_output.get("section_candidates", [])
                print(f"[ProsecutorAgent] Stage 3 output: {len(verified_offences_s3)} verified_offences, {len(section_candidates_s3)} section_candidates")
            
            print(f"[ProsecutorAgent] Running Stage 4: Statutory Verification...")
            stage4_pipeline = Stage4Pipeline()
            stage4_result = stage4_pipeline.run(self.legal_query, stage3_output)
            
            if stage4_result.status != "VERIFIED":
                print(f"[ProsecutorAgent] Warning: Stage 4 returned {stage4_result.status}")
            
            stage4_output = stage4_result.verified_statutory_object.model_dump() if stage4_result.verified_statutory_object else {}
            
            # Extract verified offences from Stage 4
            all_verified_offences = stage4_output.get("verified_offences", [])
            
            # Fallback to verified_sections if needed
            if not all_verified_offences:
                verified_sections = stage4_output.get("verified_sections", [])
                print(f"[ProsecutorAgent] verified_offences empty, using verified_sections fallback: {len(verified_sections)} sections")
                for v_sec in verified_sections:
                    all_verified_offences.append({
                        "section_number": v_sec.get("section_number", ""),
                        "statute": v_sec.get("statute", "IPC"),
                        "title": v_sec.get("section_title", ""),
                        "section_title": v_sec.get("section_title", ""),
                        "ingredients_matched": [ing.get("ingredient", "") for ing in v_sec.get("ingredients", [])],
                        "legal_elements": [ing.get("ingredient", "") for ing in v_sec.get("ingredients", [])],
                        "overall_confidence": v_sec.get("overall_confidence", 0.90),
                        "punishment_text": v_sec.get("punishment_text", ""),
                        "max_imprisonment_years": v_sec.get("max_imprisonment_years", 3.0),
                        "arnesh_kumar_threshold_exceeded": v_sec.get("arnesh_kumar_threshold_exceeded", False)
                    })
            
            print(f"\n[ProsecutorAgent] Total sections retrieved: {len(all_verified_offences)}")

            # --- Section-to-crime assignment ---
            # Strategy: use Stage 2's sub_query→concept linkage first (it already knows which
            # sub-query produced which sections). Then use one LLM call to assign any remaining
            # unassigned sections. No hardcoded keywords or section number maps.

            # Step A: Build sub_query_id → crime_name map from legal_query sub_queries.
            # Each sub-query was created with a concept field matching a crime name.
            sq_to_crime: Dict[str, str] = {}
            for sq in self.legal_query.sub_queries:
                sq_id = sq.id  # e.g. "SQ1", "SQ2"
                sq_concept = sq.concept  # matches crime.crime_name
                # Find the matching crime by concept similarity
                best_crime = None
                for crime in self.prosecutor_analysis.identified_crimes:
                    if (sq_concept.lower() in crime.crime_name.lower() or
                            crime.crime_name.lower() in sq_concept.lower()):
                        best_crime = crime.crime_name
                        break
                if not best_crime:
                    best_crime = sq_concept  # use concept as fallback label
                sq_to_crime[sq_id] = best_crime

            # Step B: Pull candidate sections per crime directly from Stage 2 mappings.
            # Stage 2 mappings[i] has sub_query_id and primary/secondary_candidate_sections.
            crime_sections_from_s2: Dict[str, List[Dict]] = {
                c.crime_name: [] for c in self.prosecutor_analysis.identified_crimes
            }
            stage2_mappings = stage2_output.get("mappings", [])
            for mapping in stage2_mappings:
                sq_id = mapping.get("sub_query_id", "")
                crime_name = sq_to_crime.get(sq_id)
                if not crime_name:
                    continue
                # Find the CrimeAnalysis object this maps to
                matched_crime_name = None
                for crime in self.prosecutor_analysis.identified_crimes:
                    if (crime_name.lower() in crime.crime_name.lower() or
                            crime.crime_name.lower() in crime_name.lower()):
                        matched_crime_name = crime.crime_name
                        break
                if not matched_crime_name:
                    continue
                all_secs = (
                    mapping.get("primary_candidate_sections", []) +
                    mapping.get("secondary_candidate_sections", [])
                )
                crime_sections_from_s2[matched_crime_name].extend(all_secs)

            # Step C: Cross-reference with Stage 4 verified sections for quality filtering.
            # A section from Stage 2 is "verified" if its section_number appears in Stage 4 output.
            verified_sec_nums = {
                str(s.get("section_number", "")).strip()
                for s in all_verified_offences
            }

            # Build a lookup of full section details from Stage 4 for enrichment
            s4_by_num: Dict[str, Dict] = {}
            for s in all_verified_offences:
                num = str(s.get("section_number", "")).strip()
                if num:
                    s4_by_num[num] = s

            # --- Dynamic KB Promotion ---
            # For every Stage 4 verified section, attempt to promote it into the
            # dynamic KB so future queries match it locally without an LLM call.
            # Also records which crime concept led to this section as a trigger.
            try:
                from lexigraphbe.classifier_prefilter import promote_from_llm_result
                for crime in self.prosecutor_analysis.identified_crimes:
                    for sq in self.legal_query.sub_queries:
                        if sq.concept and sq.concept.lower() in crime.crime_name.lower():
                            # Find any Stage 4 sections that will be assigned to this crime
                            sq_mapping = next(
                                (m for m in stage2_mappings if m.get("sub_query_id") == sq.id),
                                {}
                            )
                            candidate_secs = (
                                sq_mapping.get("primary_candidate_sections", []) +
                                sq_mapping.get("secondary_candidate_sections", [])
                            )
                            for csec in candidate_secs:
                                sec_num = str(csec.get("section_number", "")).strip()
                                if sec_num in verified_sec_nums:
                                    s4 = s4_by_num.get(sec_num, csec)
                                    promote_from_llm_result(
                                        section_number=sec_num,
                                        statute=s4.get("statute", csec.get("statute", "IPC")),
                                        title=s4.get("title", csec.get("section_title", "")),
                                        chapter=s4.get("chapter_title", ""),
                                        ingredients=s4.get("ingredients_matched", crime.legal_elements),
                                        matched_concept=crime.crime_name,
                                        bns_equivalent=s4.get("bns_equivalent", ""),
                                        cognizable=s4.get("cognizable", True),
                                        bailable=s4.get("bailable", False),
                                        punishment_maximum=s4.get("punishment_maximum"),
                                    )
            except Exception as promo_err:
                print(f"[ProsecutorAgent] Dynamic KB promotion error (non-fatal): {promo_err}")

            # Step D: For each crime, finalise its section list.
            # Use Stage 2 candidates that are also Stage 4 verified (best quality).
            # If none pass that filter, fall back to all Stage 2 candidates for that crime.
            all_assigned_nums: set = set()
            crime_final_sections: Dict[str, List[Dict]] = {}

            for crime in self.prosecutor_analysis.identified_crimes:
                s2_secs = crime_sections_from_s2.get(crime.crime_name, [])
                verified_for_crime = []
                unverified_for_crime = []
                for s in s2_secs:
                    num = str(s.get("section_number", "")).strip()
                    if num in verified_sec_nums:
                        enriched = {**s, **s4_by_num.get(num, {})}
                        verified_for_crime.append(enriched)
                    else:
                        unverified_for_crime.append(s)

                # Prefer verified; fall back to unverified if verified is empty
                final = verified_for_crime if verified_for_crime else unverified_for_crime

                # Deduplicate by section_number within this crime
                seen = set()
                deduped = []
                for s in final:
                    num = str(s.get("section_number", "")).strip()
                    if num not in seen:
                        seen.add(num)
                        deduped.append(s)
                        all_assigned_nums.add(num)

                crime_final_sections[crime.crime_name] = deduped

            # Step E: Two cases need LLM help:
            # (1) Stage 4 verified sections not yet assigned to any crime
            # (2) Crimes that ended up with 0 sections after Steps B-D
            crimes_with_zero = [
                c for c in self.prosecutor_analysis.identified_crimes
                if not crime_final_sections.get(c.crime_name)
            ]
            unassigned = [s for s in all_verified_offences
                          if str(s.get("section_number", "")).strip() not in all_assigned_nums]

            if unassigned or crimes_with_zero:
                crime_names_list = [c.crime_name for c in self.prosecutor_analysis.identified_crimes]

                unassigned_brief = "\n".join(
                    f"- {s.get('section_number','')} {s.get('statute','')}: "
                    f"{s.get('title', s.get('section_title',''))}"
                    for s in unassigned
                ) or "(none)"

                zero_crimes_brief = "\n".join(
                    f"- {c.crime_name}: {', '.join(c.legal_elements)}"
                    for c in crimes_with_zero
                ) or "(none)"

                case_facts_snippet = ""
                if self.case_context and self.case_context.case_profile.case_facts:
                    case_facts_snippet = self.case_context.case_profile.case_facts[:600]

                assignment_prompt = (
                    f"You are a legal expert. Two tasks:\n\n"
                    f"TASK 1: Assign each unassigned section to the most appropriate crime. "
                    f"If none, return empty dict for task1.\n"
                    f"TASK 2: For each crime with zero sections, identify the single best "
                    f"statutory section based on the crime name, elements, and case facts. "
                    f"Only return sections you are confident apply.\n\n"
                    f"CRIMES LIST: {crime_names_list}\n\n"
                    f"CASE FACTS: {case_facts_snippet}\n\n"
                    f"UNASSIGNED SECTIONS (TASK 1):\n{unassigned_brief}\n\n"
                    f"CRIMES WITH ZERO SECTIONS (TASK 2):\n{zero_crimes_brief}\n\n"
                    f'Return ONLY valid JSON: {{"task1": {{"<section_number>": "<crime_name>"}}, '
                    f'"task2": {{"<crime_name>": {{"section_number": "<num>", "statute": "<IPC or BNS>", "title": "<title>"}}}}}}\n'
                    f"No markdown."
                )
                try:
                    from lexigraphbe.config import extract_json_from_text
                    assign_response = self.llm.invoke(assignment_prompt)
                    assign_text = assign_response.content if hasattr(assign_response, "content") else str(assign_response)
                    assignment_map = extract_json_from_text(assign_text)
                    if isinstance(assignment_map, dict):
                        # Task 1: assign unassigned Stage 4 sections
                        task1 = assignment_map.get("task1", {})
                        if isinstance(task1, dict):
                            for sec in unassigned:
                                num = str(sec.get("section_number", "")).strip()
                                assigned_crime = task1.get(num)
                                if assigned_crime:
                                    for crime in self.prosecutor_analysis.identified_crimes:
                                        if crime.crime_name.lower() == assigned_crime.lower():
                                            crime_final_sections.setdefault(crime.crime_name, []).append(sec)
                                            all_assigned_nums.add(num)
                                            break
                        # Task 2: inject sections for zero-section crimes
                        task2 = assignment_map.get("task2", {})
                        if isinstance(task2, dict):
                            for crime_name_key, sec_info in task2.items():
                                if not isinstance(sec_info, dict):
                                    continue
                                for crime in self.prosecutor_analysis.identified_crimes:
                                    if crime.crime_name.lower() == crime_name_key.lower():
                                        if not crime_final_sections.get(crime.crime_name):
                                            crime_final_sections[crime.crime_name] = [{
                                                "section_number": sec_info.get("section_number", ""),
                                                "statute": sec_info.get("statute", "IPC"),
                                                "title": sec_info.get("title", ""),
                                                "section_title": sec_info.get("title", ""),
                                                "ingredients_matched": [],
                                                "legal_elements": crime.legal_elements,
                                                "overall_confidence": 0.80,
                                            }]
                                        break
                except Exception as assign_err:
                    print(f"[ProsecutorAgent] LLM section assignment failed: {assign_err}")

            # Step F: Commit final sections to each crime and cache
            for crime in self.prosecutor_analysis.identified_crimes:
                crime_key = crime.crime_name.lower().strip()
                final_secs = crime_final_sections.get(crime.crime_name, [])
                results = {
                    "recommended_sections": final_secs,
                    "similar_cases": [],
                    "supporting_articles": [],
                    "supporting_evidence": [],
                    "stage2_output": stage2_output,
                    "stage3_output": stage3_output,
                    "stage4_output": stage4_output,
                }
                self.retrieved_sections_cache[crime_key] = results
                crime.retrieved_sections = final_secs
                crime.supporting_precedents = []
                print(f"  → {crime.crime_name}: {len(final_secs)} sections"
                      + (f" ({[s.get('section_number') for s in final_secs]})" if final_secs else ""))
            
            # Mark complete
            self._all_crimes_sections_retrieved = True
            return self.retrieved_sections_cache
            
        except Exception as e:
            print(f"[ProsecutorAgent] Error running lexigraphbe pipeline: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def query_lexigraphbe_for_crime(self, crime: CrimeAnalysis) -> Dict[str, Any]:
        """
        Query lexigraphbe for a specific crime.
        Now uses the batch query approach (queries all crimes together) to avoid
        prefilter misclassification due to case facts bleeding across focused queries.
        
        Args:
            crime: CrimeAnalysis object for the specific offense
            
        Returns:
            Retrieved sections from lexigraphbe pipeline
        """
        print(f"\n[ProsecutorAgent] Querying lexigraphbe for: {crime.crime_name}")
        
        # Check cache first
        cache_key = crime.crime_name.lower().strip()
        if cache_key in self.retrieved_sections_cache:
            print(f"[ProsecutorAgent] Using cached results: {len(self.retrieved_sections_cache[cache_key].get('recommended_sections', []))} sections")
            return self.retrieved_sections_cache[cache_key]
        
        # Query all crimes together if not done yet (correct architecture)
        self.query_lexigraphbe_all_crimes()
        
        # Return the cached result for this specific crime
        result = self.retrieved_sections_cache.get(cache_key, {
            "recommended_sections": [],
            "similar_cases": [],
            "error": "Crime not found in batch query results"
        })
        
        print(f"[ProsecutorAgent] Retrieved {len(result.get('recommended_sections', []))} statutory sections")
        return result
    
    def _build_crime_specific_query(self, crime: CrimeAnalysis) -> str:
        """
        Build a focused query for lexigraphbe based on specific crime.
        (Kept for backward compatibility, but no longer used in the batch query approach)
        """
        # Include case facts context
        case_facts = self.case_context.case_profile.case_facts if self.case_context else ""
        
        query_parts = [
            f"Crime: {crime.crime_name}",
            f"Legal elements to prove: {', '.join(crime.legal_elements)}",
        ]
        
        if case_facts:
            query_parts.append(f"Case context: {case_facts[:500]}")  # Truncate for focused query
        
        return " | ".join(query_parts)
    
    def _build_ingredient_matrix(self, case_facts: str) -> List[Dict[str, Any]]:
        """
        Builds a structured Evidence-to-Ingredient Matrix.
        Calls LLM ONCE PER CRIME (not all crimes in one call) to prevent
        token overflow, JSON truncation, and 'Extra data' parse errors.
        """
        from lexigraphbe.config import extract_json_from_text

        defence_position = self.prosecutor_analysis.case_summary
        matrix = []

        for crime in self.prosecutor_analysis.identified_crimes:
            secs = crime.retrieved_sections
            sec_line = ", ".join(
                f"{s.get('section_number','')} {s.get('statute','')} ({s.get('title', s.get('section_title',''))})"
                for s in secs
            ) if secs else "(section pending)"

            matrix_prompt = f"""You are a legal analyst. Produce a structured ingredient matrix for ONE crime.

CASE FACTS:
{case_facts}

ACCUSED'S DEFENCE:
{defence_position}

CRIME: {crime.crime_name} [{crime.severity}]
Sections: {sec_line}
Ingredients to prove: {'; '.join(crime.legal_elements)}

For EACH ingredient, classify using ONE of: PRIMA_FACIE / ALLEGED / DISPUTED / NOT_ESTABLISHED
Rules:
- PRIMA_FACIE: at least one independent corroborating evidence item exists
- ALLEGED: complainant says so but no independent corroboration
- DISPUTED: accused directly contests with a specific counter-claim
- NOT_ESTABLISHED: no factual or evidentiary basis at all
- facts_supporting: copy verbatim sentences from CASE FACTS only
- intent can only be ALLEGED or PRIMA_FACIE inferred from conduct — never "established"
- defence_response: accused's specific counter-claim or "None raised"

Return ONLY this JSON object (not a list, not wrapped):
{{
  "crime_name": "{crime.crime_name}",
  "section": "{sec_line}",
  "cognizable": true,
  "bailable": false,
  "punishment_range": "state the actual range for this section",
  "ingredients": [
    {{
      "ingredient": "...",
      "status": "PRIMA_FACIE|ALLEGED|DISPUTED|NOT_ESTABLISHED",
      "facts_supporting": ["verbatim sentence from case facts"],
      "evidence": ["specific evidence item mentioned in facts"],
      "defence_response": "accused's counter-claim or None raised",
      "unproven": ["what is genuinely missing"]
    }}
  ],
  "specific_witnesses_at_risk": "name witnesses still reachable by accused, or None identified",
  "evidence_still_unrecovered": "specific evidence not in police custody, or None identified",
  "custodial_interrogation_necessity": "concrete reason — what ONLY the accused can tell investigators. If none, write: Not established from available facts",
  "arnesh_kumar_applicability": "why 41A notice is insufficient — name specific risk. Or: Notice may suffice on current facts"
}}
No markdown. No list wrapper. Single JSON object only."""

            try:
                response = self.llm.invoke(matrix_prompt)
                response_text = response.content if hasattr(response, "content") else str(response)
                # Strip any accidental list wrapper [ ... ]
                stripped = response_text.strip()
                if stripped.startswith("["):
                    # Try to extract the first object from the list
                    import re as _re
                    inner = _re.search(r'\{.*\}', stripped, _re.DOTALL)
                    if inner:
                        stripped = inner.group(0)
                entry = extract_json_from_text(stripped)
                if isinstance(entry, dict) and "crime_name" in entry:
                    matrix.append(entry)
                    print(f"[ProsecutorAgent] Matrix built for: {crime.crime_name}")
                elif isinstance(entry, list) and entry and isinstance(entry[0], dict):
                    matrix.append(entry[0])
                    print(f"[ProsecutorAgent] Matrix built for: {crime.crime_name} (from list)")
                else:
                    print(f"[ProsecutorAgent] Matrix parse failed for {crime.crime_name} — using fallback")
                    matrix.append(self._fallback_matrix_entry(crime, sec_line))
            except Exception as e:
                print(f"[ProsecutorAgent] Matrix error for {crime.crime_name}: {e}")
                matrix.append(self._fallback_matrix_entry(crime, sec_line))

        return matrix

    def _fallback_matrix_entry(self, crime, sec_line: str) -> Dict[str, Any]:
        """
        Produces a minimal matrix entry from structured crime data when the LLM
        matrix call fails. Prevents hallucination by grounding in crime.legal_elements
        and crime.prosecution_strategy only — no free-text generation.
        """
        return {
            "crime_name": crime.crime_name,
            "section": sec_line,
            "cognizable": True,
            "bailable": False,
            "punishment_range": "As per statute",
            "ingredients": [
                {
                    "ingredient": elem,
                    "status": "ALLEGED",
                    "facts_supporting": [],
                    "evidence": [],
                    "defence_response": "None raised",
                    "unproven": ["Full factual matrix not available — treat as alleged only"],
                }
                for elem in crime.legal_elements
            ],
            "specific_witnesses_at_risk": "None identified",
            "evidence_still_unrecovered": "None identified",
            "custodial_interrogation_necessity": "Not established from available facts",
            "arnesh_kumar_applicability": "Notice may suffice on current facts",
            "_fallback": True,
        }

    def build_opening_argument(self) -> Dict[str, Any]:
        """
        Build opening argument using a 3-layer pipeline:
        1. Retrieve sections (already done via query_lexigraphbe_all_crimes)
        2. Build Evidence-to-Ingredient Matrix (structured, calibrated)
        3. Generate argument from matrix (constrained input → constrained output)
        """
        if not self.prosecutor_analysis:
            raise ValueError("Must run analyze_case() first")

        print("\n[ProsecutorAgent] Building Opening Argument...")

        for crime in self.prosecutor_analysis.identified_crimes:
            self.query_lexigraphbe_for_crime(crime)

        case_facts = self.case_context.case_profile.case_facts if self.case_context else ""

        # Layer 2: Build ingredient matrix
        print("[ProsecutorAgent] Building Evidence-to-Ingredient Matrix...")
        matrix = self._build_ingredient_matrix(case_facts)
        self._cached_ingredient_matrix = matrix  # cache for rebuttal phase

        # Serialise matrix into a structured block for the argument generator
        matrix_block_parts = []
        for crime_entry in matrix:
            crime_name = crime_entry.get("crime_name", "")
            section = crime_entry.get("section", "")
            punishment = crime_entry.get("punishment_range", "As per statute")
            cognizable = "Cognizable" if crime_entry.get("cognizable", True) else "Non-cognizable"
            bailable = "Bailable" if crime_entry.get("bailable", False) else "Non-bailable"
            custodial = crime_entry.get("custodial_interrogation_necessity", "Not established from available facts")
            arnesh = crime_entry.get("arnesh_kumar_applicability", "Not assessed")
            witnesses = crime_entry.get("specific_witnesses_at_risk", "None identified")
            unrecovered = crime_entry.get("evidence_still_unrecovered", "None identified")
            ing_lines = []
            for ing in crime_entry.get("ingredients", []):
                status = ing.get("status", "ALLEGED")
                facts = "; ".join(ing.get("facts_supporting", []))
                evidence = "; ".join(ing.get("evidence", []))
                defence = ing.get("defence_response", "None raised")
                unproven = "; ".join(ing.get("unproven", []))
                ing_lines.append(
                    f"    Ingredient: {ing.get('ingredient','')}\n"
                    f"    Status: {status}\n"
                    f"    Facts: {facts or 'None'}\n"
                    f"    Evidence: {evidence or 'None'}\n"
                    f"    Defence counter: {defence}\n"
                    f"    Unproven: {unproven or 'None'}"
                )
            matrix_block_parts.append(
                f"OFFENCE: {crime_name} | {section} | {cognizable} | {bailable} | Punishment: {punishment}\n"
                + "\n".join(ing_lines)
                + f"\n  Custodial necessity: {custodial}"
                + f"\n  Arnesh Kumar / 41A: {arnesh}"
                + f"\n  Witnesses at risk: {witnesses}"
                + f"\n  Evidence still unrecovered: {unrecovered}"
            )
        matrix_block = "\n\n".join(matrix_block_parts)

        # Layer 3: Generate argument from constrained input
        # If matrix is all fallback entries, add an explicit guard
        all_fallback = all(e.get("_fallback") for e in matrix) if matrix else True
        fallback_warning = (
            "\nCRITICAL: The ingredient matrix above contains only ALLEGED-status entries "
            "because detailed analysis was unavailable. You MUST use 'it is alleged that' "
            "for every factual claim. Do NOT assert any fact as established or prima facie. "
            "Do NOT cite any section number, case name, or amount not present in the matrix above.\n"
        ) if all_fallback else ""
        opening_prompt = f"""You are a Senior Public Prosecutor making oral submissions before a Sessions Court opposing an anticipatory bail application under Section 482 BNSS / Section 438 CrPC.
{fallback_warning}
Your argument must be generated STRICTLY from the matrix below. Do not add facts, inferences, or conclusions not present in the matrix. Do not cite any section number, amount, name, or case not in the matrix.

EVIDENCE-TO-INGREDIENT MATRIX:
{matrix_block}

LANGUAGE RULES — NON-NEGOTIABLE:
  PRIMA_FACIE status  → "the material on record prima facie establishes..."
  ALLEGED status      → "it is alleged that..." / "the complainant states..."
  DISPUTED status     → "the accused's claim that [X] does not displace the prima facie case because..."
  NOT_ESTABLISHED     → do not argue this ingredient at all
  NEVER say: "proves", "it is clear", "strongly indicates", "establishes beyond doubt"
  NEVER convert ALLEGED or DISPUTED into established fact.
  NEVER assert intent is established — intent may only be prima facie inferred from conduct.

ARGUMENT STRUCTURE — follow this order, write as single continuous prose:

[438(1)(a) — Nature of offence]
State the offence, cite the section, state it is cognizable and non-bailable, give the punishment range from the matrix.

[438(1)(b) — Gravity]
State the gravity in one sentence grounded in the specific harm alleged (financial amount, nature of document fraud, use of force — whatever the matrix supports). Do not use generic gravity language.

[Prima facie case]
For each offence in order of severity: name the section, state which ingredients are PRIMA_FACIE supported, cite the specific evidence. One sentence per offence.

[438(1)(d) — Compliance risk / defence response]
Address each DISPUTED ingredient. Explain specifically why the accused's counter-claim does not displace the prima facie case — name the counter-claim, then the evidence that contradicts it.

[Custodial interrogation]
Use ONLY the custodial_interrogation_necessity and arnesh_kumar_applicability fields. If either says "Not established" or "Notice may suffice", say so plainly — do not manufacture a reason.

[438(1)(c) — Habitual behaviour]
Only include if the matrix contains prior conduct. If not, omit this entirely.

[Prayer]
End with a prayer to refuse bail that flows naturally from what has just been argued. Make it specific to the facts — not a generic formula.

FORMAT: Single continuous prose. No headings. No bullet points. No numbered paragraphs. Let the complexity of the arguments dictate the length — say what needs to be said, nothing more. Every sentence must carry a legal point tied to a specific fact or section from the matrix."""

        response = self.llm.invoke(opening_prompt)
        opening_prose = response.content if hasattr(response, "content") else str(response)

        argument = {
            "phase": "opening",
            "prosecution_theory": self.prosecutor_analysis.prosecution_theory,
            "opening_statement": opening_prose,
            "ingredient_matrix": matrix,
            "primary_charges": [
                {
                    "crime": crime.crime_name,
                    "elements": crime.legal_elements,
                    "sections": crime.retrieved_sections,
                    "strategy": crime.prosecution_strategy,
                }
                for crime in self.prosecutor_analysis.identified_crimes
            ],
            "evidence_framework": self.prosecutor_analysis.evidence_requirements,
            "legal_principles": self.prosecutor_analysis.legal_principles,
        }
        return argument
    
    def handle_rebuttal(self, defense_argument: str, specific_crime: Optional[str] = None) -> Dict[str, Any]:
        """
        Handle rebuttal to defense argument.
        Queries lexigraphbe for EVERY crime the defense attacks, then builds
        section-grounded counter-arguments against each specific defense claim.

        Args:
            defense_argument: The defense counsel's argument to rebut.
            specific_crime: Optional — force focus on a single crime name.

        Returns:
            Rebuttal dict with per-crime section-grounded counter-arguments.
        """
        print("\n[ProsecutorAgent] Preparing Rebuttal...")

        if not self.prosecutor_analysis:
            raise ValueError("Must run analyze_case() first")

        # Step 1: Identify ALL crimes the defense is attacking
        crimes_attacked = self._identify_crimes_from_defense(defense_argument, specific_crime)
        print(f"[ProsecutorAgent] Defense is attacking: {crimes_attacked}")

        # Step 2: Query lexigraphbe for every attacked crime not already cached
        all_retrieved_sections: Dict[str, List[Dict[str, Any]]] = {}
        for crime_name in crimes_attacked:
            cache_key = crime_name.lower().strip()
            if cache_key not in self.retrieved_sections_cache:
                matching_crime = next(
                    (c for c in self.prosecutor_analysis.identified_crimes
                     if c.crime_name.lower() == crime_name.lower()),
                    None
                )
                if matching_crime:
                    self.query_lexigraphbe_for_crime(matching_crime)
            all_retrieved_sections[crime_name] = self.retrieved_sections_cache.get(
                cache_key, {}
            ).get("recommended_sections", [])

        # Step 3: Build section-grounded counter-arguments
        counter_arguments = self._generate_counter_arguments(
            defense_argument, crimes_attacked, all_retrieved_sections
        )

        rebuttal = {
            "phase": "rebuttal",
            "defense_argument_summary": defense_argument[:300],
            "prosecution_response": {
                "crimes_addressed": crimes_attacked,
                "counter_arguments": counter_arguments,
                "retrieved_sections_per_crime": all_retrieved_sections,
            }
        }

        return rebuttal

    
    def _identify_crimes_from_defense(self, defense_argument: str, specific_crime: Optional[str]) -> List[str]:
        """
        Identify ALL crimes the defense is attacking, not just one.
        Uses the LLM to map defense claims to our identified crime list.
        Returns a list of crime names ordered by relevance to the defense argument.
        """
        if specific_crime:
            return [specific_crime]

        crime_names = [c.crime_name for c in self.prosecutor_analysis.identified_crimes]
        crimes_list = chr(10).join(f"- {name}" for name in crime_names)

        prompt = f"""You are a Senior Public Prosecutor reading the defense bail argument.

IDENTIFIED CRIMES IN THIS CASE:
{crimes_list}

DEFENSE ARGUMENT:
{defense_argument}

For each crime above, determine if the defense makes any claim that challenges,
disputes, or undermines that crime's elements or evidence.

Return ONLY a JSON array of crime names (exact spelling from the list above)
that the defense is attacking, ordered from most to least directly challenged.
Example: ["Physical Assault", "Unlawful Entry", "Threat"]
Return only the JSON array, nothing else."""

        response = self.llm.invoke(prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

        try:
            from lexigraphbe.config import extract_json_from_text
            result = extract_json_from_text(response_text)
            if isinstance(result, list):
                valid = [name for name in result if name in crime_names]
                if valid:
                    return valid
        except Exception:
            pass

        # Fallback: return all identified crimes so we query everything
        return crime_names
    
    def _generate_counter_arguments(
        self,
        defense_argument: str,
        crimes_attacked: List[str],
        retrieved_sections: Dict[str, List[Dict[str, Any]]],
    ) -> List[str]:
        """
        Generates a calibrated rebuttal using the ingredient matrix built during
        the opening argument phase. Each defense claim is addressed by referencing
        the specific ingredient status (PRIMA_FACIE / ALLEGED / DISPUTED) rather
        than making generic assertions.
        """
        # Pull the cached ingredient matrix if available
        cached_matrix = getattr(self, "_cached_ingredient_matrix", [])

        # Build matrix block for attacked crimes only
        matrix_parts = []
        for entry in cached_matrix:
            if entry.get("crime_name", "") in crimes_attacked:
                ing_lines = []
                for ing in entry.get("ingredients", []):
                    status = ing.get("status", "ALLEGED")
                    facts = "; ".join(ing.get("facts_supporting", []))
                    evidence = "; ".join(ing.get("evidence", []))
                    defence_counter = ing.get("defence_response", "None raised")
                    unproven = "; ".join(ing.get("unproven", []))
                    ing_lines.append(
                        f"  Ingredient: {ing.get('ingredient','')} [{status}]\n"
                        f"    Facts: {facts or 'None'}\n"
                        f"    Evidence: {evidence or 'None'}\n"
                        f"    Defence counter: {defence_counter}\n"
                        f"    Unproven: {unproven or 'None'}"
                    )
                matrix_parts.append(
                    f"OFFENCE: {entry.get('crime_name','')} | {entry.get('section','')}\n"
                    + "\n".join(ing_lines)
                )

        matrix_block = "\n\n".join(matrix_parts) if matrix_parts else "(Matrix not available — use sections below)"

        # Fallback sections brief if matrix is empty
        sections_brief_parts = []
        for crime_name, sections in retrieved_sections.items():
            if not sections:
                continue
            sec_lines = [
                f"  • {s.get('section_number','')} {s.get('statute','')} "
                f"({s.get('title', s.get('section_title',''))})"
                for s in sections
            ]
            sections_brief_parts.append(f"[{crime_name}]\n" + "\n".join(sec_lines))
        sections_brief = "\n\n".join(sections_brief_parts) or "No sections retrieved."

        case_facts = self.case_context.case_profile.case_facts if self.case_context else ""

        prompt = f"""You are a Senior Public Prosecutor making sharp rebuttal submissions before a Sessions Court opposing anticipatory bail under Section 438 CrPC / Section 482 BNSS.

INGREDIENT MATRIX:
{matrix_block}

STATUTORY SECTIONS:
{sections_brief}

CASE FACTS:
{case_facts}

DEFENCE ARGUMENT TO REBUT:
{defense_argument}

LANGUAGE RULES — NON-NEGOTIABLE:
  PRIMA_FACIE ingredient → "the material on record prima facie establishes..."
  ALLEGED ingredient     → "the allegation, though not yet conclusively proved, is corroborated by..."
  DISPUTED ingredient    → "the accused's claim that [X] does not displace the prima facie case because [specific evidence]..."
  NOT_ESTABLISHED        → do not use this ingredient at all
  NEVER say: "proves", "clearly shows", "establishes beyond doubt"

REBUTTAL STRATEGY — be aggressive but precise:
1. Each defence claim gets one sentence: name the claim in a few words, then immediately pivot to the specific statutory ingredient or evidence that defeats it. Do not acknowledge the claim more than necessary.
2. For evidential gap arguments (e.g. "report is only preliminary", "CCTV only shows presence"):
   — Acknowledge the limitation in three words maximum ("While preliminary,") then state why it still satisfies the prima facie threshold for bail purposes under Section 438.
3. For the "civil/contractual dispute" defence:
   — State the specific statutory element (e.g. dishonest intent, entrustment) that converts the civil act into a criminal one — do not just say "criminal liability is separate."
4. For the "evidence already in custody / cooperation undertaking" defence:
   — Cite the specific unrecovered evidence or unreached witness from the matrix's evidence_still_unrecovered / specific_witnesses_at_risk fields. If both say "None identified", concede this ground honestly.
5. For the "41A notice is sufficient" argument:
   — Use the arnesh_kumar_applicability field from the matrix. If it says "Notice may suffice", do not press this point.
6. End with a crisp final prayer that flows naturally from the argument — do not use a rigid canned phrase; phrase it in whatever way is most persuasive given what has just been argued.

FORMAT: Single continuous prose. No bullet points. No headings. Length is dictated by what the defense actually argued — address every live point, skip nothing, add nothing superfluous. Sharp and forensic.

Write only the rebuttal text."""

        response = self.llm.invoke(prompt)
        response_text = (response.content if hasattr(response, "content") else str(response)).strip()
        return [response_text]

    def build_closing_argument(self) -> Dict[str, Any]:
        """
        Build closing argument synthesizing all retrieved sections and arguments.
        """
        print("\n[ProsecutorAgent] Building Closing Argument...")
        
        if not self.prosecutor_analysis:
            raise ValueError("Must run analyze_case() first")
        
        # Ensure we have queried for all identified crimes
        for crime in self.prosecutor_analysis.identified_crimes:
            cache_key = crime.crime_name.lower().strip()
            if cache_key not in self.retrieved_sections_cache:
                self.query_lexigraphbe_for_crime(crime)
        
        closing = {
            "phase": "closing",
            "case_summary": self.prosecutor_analysis.case_summary,
            "prosecution_theory": self.prosecutor_analysis.prosecution_theory,
            "all_charges": [
                {
                    "crime": crime.crime_name,
                    "severity": crime.severity,
                    "sections": crime.retrieved_sections,
                    "precedents": crime.supporting_precedents
                }
                for crime in self.prosecutor_analysis.identified_crimes
            ],
            "consolidated_evidence": self.prosecutor_analysis.evidence_requirements,
            "final_prayer": "In light of the overwhelming evidence and applicable law, " +
                          f"we pray for conviction under {self.prosecutor_analysis.primary_crime}."
        }
        
        return closing
    
    def get_analysis_summary(self) -> Dict[str, Any]:
        """Get current state of prosecutorial analysis"""
        if not self.prosecutor_analysis:
            return {"error": "No analysis performed yet"}
        
        return {
            "case_summary": self.prosecutor_analysis.case_summary,
            "primary_crime": self.prosecutor_analysis.primary_crime,
            "prosecution_theory": self.prosecutor_analysis.prosecution_theory,
            "identified_crimes": [
                {
                    "name": crime.crime_name,
                    "severity": crime.severity,
                    "sections_retrieved": len(crime.retrieved_sections) > 0
                }
                for crime in self.prosecutor_analysis.identified_crimes
            ],
            "cached_queries": list(self.retrieved_sections_cache.keys())
        }


def main():
    """CLI interface for prosecutor agent - Interactive prosecution workflow"""
    print("=" * 80)
    print("PROSECUTOR AGENT - State/Complainant Defense System")
    print("=" * 80)
    
    # Interactive case input
    print("\n📋 Enter case facts (paste your case details)")
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
    
    # Initialize prosecutor
    prosecutor = ProsecutorAgent()
    
    # STEP 1: Analyze case and identify crimes
    print("\n[STEP 1] Analyzing Case and Identifying Crimes...")
    analysis = prosecutor.analyze_case(case_file)
    
    print(f"\nPrimary Crime: {analysis.primary_crime}")
    print(f"Prosecution Theory: {analysis.prosecution_theory}")
    print(f"\nIdentified Crimes:")
    for crime in analysis.identified_crimes:
        print(f"  - {crime.crime_name} ({crime.severity})")
        print(f"    Strategy: {crime.prosecution_strategy[:100]}...")
    
    # STEP 2: Build opening argument (queries lexigraphbe for primary crime)
    print("\n" + "=" * 80)
    print("[STEP 2] Building Opening Argument...")
    print("=" * 80)
    opening = prosecutor.build_opening_argument()
    
    print(f"\nOpening Argument Summary:")
    print(f"Prosecution Theory: {opening['prosecution_theory']}")

    # Print all charges with sections
    print(f"\nAll Charges and Retrieved Sections:")
    for charge in opening['primary_charges']:
        print(f"\n  Crime: {charge['crime']}")
        print(f"  Elements to Prove: {', '.join(charge['elements'])}")
        sections_count = len(charge.get('sections', []))
        print(f"  Retrieved Sections: {sections_count}")
        if sections_count > 0:
            for sec in charge['sections'][:5]:
                print(f"    - {sec.get('section_number', 'N/A')} {sec.get('statute', '')}: {sec.get('title', sec.get('section_title', ''))}")
        print(f"  Strategy: {charge['strategy'][:200]}...")

    # Print full opening argument prose
    if opening.get("opening_statement"):
        print("\n" + "=" * 80)
        print("FULL OPENING ARGUMENT:")
        print("=" * 80)
        print(opening["opening_statement"])
    
    # STEP 3: Wait for defense argument
    print("\n" + "=" * 80)
    print("[STEP 3] Defense Rebuttal")
    print("=" * 80)
    print("\n📋 Enter defense argument (press ENTER twice when done):\n")
    
    defense_lines = []
    empty_count = 0
    while True:
        try:
            line = input()
            if line.strip() == "":
                empty_count += 1
                if empty_count >= 2 and defense_lines:
                    break
            else:
                empty_count = 0
                defense_lines.append(line)
        except EOFError:
            break
    
    defense_arg = "\n".join(defense_lines).strip()
    
    if not defense_arg:
        print("\n[INFO] No defense argument provided. Exiting...")
        return
    
    print("\n" + "=" * 80)
    print("Defense Argument Received:")
    print("=" * 80)
    print(defense_arg)
    
    # STEP 4: Prepare prosecution rebuttal
    print("\n" + "=" * 80)
    print("[STEP 4] Prosecution Rebuttal")
    print("=" * 80)
    rebuttal = prosecutor.handle_rebuttal(defense_arg)
    
    resp = rebuttal["prosecution_response"]

    print(f"\nCrimes Addressed: {', '.join(resp.get('crimes_addressed', []))}")
    print(f"\nRebuttal:\n")
    for arg in resp.get("counter_arguments", []):
        print(arg)
    
    print("\n" + "=" * 80)
    print("Prosecution Workflow Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()