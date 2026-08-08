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
        legal_regime: str = "BNS_2023",
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
        
        return prosecutor_analysis
    
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
VERIFIED LEGAL CONCEPTS — CLOSED SET (treat this as an exhaustive list):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{concepts_str}

SUB-QUERIES FOR THIS CASE:
{sub_queries_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HARD CONSTRAINTS — MANDATORY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Every crime_name in identified_crimes MUST map to one of the VERIFIED LEGAL CONCEPTS above.
   Do NOT introduce any offence that does not appear in the closed set.
2. Do NOT include any IPC/BNS section numbers in your output — name crimes by concept only.
3. If a concept from the closed set is not relevant to the proceeding goal, exclude it — do not
   force all concepts into identified_crimes.
4. The primary_crime must be the concept best suited to the PROCEEDING GOAL above, not merely
   the most morally serious offence in the abstract.

Output ONLY valid JSON matching this structure exactly:
{{
    "case_summary": "Brief summary from the prosecution's perspective for THIS proceeding",
    "primary_crime": "Name of the main offence (must be from closed set)",
    "prosecution_theory": "Theory tailored to the proceeding goal",
    "identified_crimes": [
        {{
            "crime_name": "Name of offence (from closed set)",
            "severity": "primary|secondary|ancillary",
            "legal_elements": ["element1", "element2"],
            "prosecution_strategy": "How this element is proved on these facts",
            "required_sections": ["Describe the type of BNS/BNSS section needed, NO section numbers"]
        }}
    ],
    "evidence_requirements": ["Evidence item grounded in the facts"],
    "legal_principles": ["Applicable legal principle"]
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
    
    def query_lexigraphbe_for_crime(self, crime: CrimeAnalysis) -> Dict[str, Any]:
        """
        Query lexigraphbe pipeline starting from Stage 2 (Section Mapping).
        The prosecutor already has Stage 1 output (legal concepts), so we skip stages 0-1.
        
        Args:
            crime: CrimeAnalysis object for the specific offense
            
        Returns:
            Retrieved sections from lexigraphbe pipeline
        """
        print(f"\n[ProsecutorAgent] Querying lexigraphbe for: {crime.crime_name}")
        
        # Check cache first
        cache_key = crime.crime_name.lower().strip()
        if cache_key in self.retrieved_sections_cache:
            print(f"[ProsecutorAgent] Using cached results")
            return self.retrieved_sections_cache[cache_key]
        
        # Build a minimal LegalQueryObject with just this crime's concept
        # We already have Stage 1 output from analyze_case, so we create a focused query
        try:
            from lexigraphbe.schemas import LegalQueryObject, LegalConceptItem, SubQueryItem
            from lexigraphbe.stage2_pipeline import Stage2Pipeline
            from lexigraphbe.stage3_pipeline import Stage3Pipeline
            from lexigraphbe.stage4_pipeline import Stage4Pipeline
            
            # Create a focused legal query for this specific crime
            # Find the matching concept from our original legal_query
            matching_concept = None
            for concept in self.legal_query.legal_concepts:
                if concept.concept.lower() in crime.crime_name.lower() or \
                   crime.crime_name.lower() in concept.concept.lower():
                    matching_concept = concept
                    break
            
            if not matching_concept:
                # Create a new concept for this crime
                matching_concept = LegalConceptItem(
                    concept=crime.crime_name,
                    confidence=0.90
                )
            
            # Build a focused query with just this concept
            focused_query = LegalQueryObject(
                case_type=self.case_context.case_profile.procedural_stage,
                legal_concepts=[matching_concept],
                sub_queries=[SubQueryItem(
                    id="SQ1",
                    query=f"{crime.crime_name}: {', '.join(crime.legal_elements)}",
                    concept=matching_concept.concept,
                    target_parties=self.case_context.active_parties or [],
                    role_alleged="Primary accused"
                )],
                legal_regime=self.case_context.case_profile.legal_regime,
                important_facts=self.legal_query.important_facts
            )
            
            print(f"[ProsecutorAgent] Running Stage 2: Section Mapping...")
            stage2_pipeline = Stage2Pipeline()
            stage2_result = stage2_pipeline.run(focused_query)
            
            if stage2_result.status != "VERIFIED":
                print(f"[ProsecutorAgent] Warning: Stage 2 returned {stage2_result.status}")
            
            stage2_output = stage2_result.batched_mapping_response.model_dump() if stage2_result.batched_mapping_response else {}
            
            print(f"[ProsecutorAgent] Running Stage 3: Chapter Identification...")
            stage3_pipeline = Stage3Pipeline()
            stage3_result = stage3_pipeline.run(focused_query, stage2_mapping=stage2_output)
            
            if stage3_result.status != "VERIFIED":
                print(f"[ProsecutorAgent] Warning: Stage 3 returned {stage3_result.status}")
            
            stage3_output = stage3_result.verified_chapter_object.model_dump() if stage3_result.verified_chapter_object else {}
            
            print(f"[ProsecutorAgent] Running Stage 4: Statutory Verification...")
            stage4_pipeline = Stage4Pipeline()
            stage4_result = stage4_pipeline.run(focused_query, stage3_output)
            
            if stage4_result.status != "VERIFIED":
                print(f"[ProsecutorAgent] Warning: Stage 4 returned {stage4_result.status}")
            
            stage4_output = stage4_result.verified_statutory_object.model_dump() if stage4_result.verified_statutory_object else {}
            
            # Extract verified offences from Stage 4
            verified_offences = stage4_output.get("verified_offences", [])
            
            # Format results for prosecutor use
            results = {
                "recommended_sections": verified_offences,
                "similar_cases": [],  # Not retrieved (would need Stage 6)
                "supporting_articles": [],
                "supporting_evidence": [],
                "stage2_output": stage2_output,
                "stage3_output": stage3_output,
                "stage4_output": stage4_output
            }
            
            # Cache the results
            self.retrieved_sections_cache[cache_key] = results
            
            # Update crime with retrieved sections
            crime.retrieved_sections = results.get("recommended_sections", [])
            crime.supporting_precedents = results.get("similar_cases", [])
            
            print(f"[ProsecutorAgent] Retrieved {len(crime.retrieved_sections)} statutory sections")
            
            return results
            
        except Exception as e:
            print(f"[ProsecutorAgent] Error running lexigraphbe pipeline: {e}")
            import traceback
            traceback.print_exc()
            print(f"[ProsecutorAgent] Returning placeholder results")
            return {
                "recommended_sections": [],
                "similar_cases": [],
                "error": str(e),
                "note": "lexigraphbe pipeline failed - check if all stages are properly configured"
            }
    
    def _build_crime_specific_query(self, crime: CrimeAnalysis) -> str:
        """
        Build a focused query for lexigraphbe based on specific crime.
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
    
    def build_opening_argument(self) -> Dict[str, Any]:
        """
        Build opening argument for the prosecution.
        Queries lexigraphbe for primary crime first.
        """
        if not self.prosecutor_analysis:
            raise ValueError("Must run analyze_case() first")
        
        print("\n[ProsecutorAgent] Building Opening Argument...")
        
        # Query lexigraphbe for primary crime
        primary_crimes = [c for c in self.prosecutor_analysis.identified_crimes if c.severity == "primary"]
        
        if not primary_crimes:
            print("[ProsecutorAgent] Warning: No primary crime identified, using first crime")
            primary_crimes = [self.prosecutor_analysis.identified_crimes[0]]
        
        # Retrieve sections for primary crime
        for crime in primary_crimes:
            self.query_lexigraphbe_for_crime(crime)
        
        # Build structured argument
        argument = {
            "phase": "opening",
            "prosecution_theory": self.prosecutor_analysis.prosecution_theory,
            "primary_charges": [
                {
                    "crime": crime.crime_name,
                    "elements": crime.legal_elements,
                    "sections": crime.retrieved_sections,
                    "strategy": crime.prosecution_strategy
                }
                for crime in primary_crimes
            ],
            "evidence_framework": self.prosecutor_analysis.evidence_requirements,
            "legal_principles": self.prosecutor_analysis.legal_principles
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
        Generate section-grounded counter-arguments against each specific defense claim.

        For each crime the defense attacks, the LLM receives:
          - The exact defense claim
          - The statutory elements of the offence (from retrieved sections)
          - The case evidence grounding each element

        This produces targeted rebuttals tied to actual statute text, not generic assertions.
        """
        # Build a structured brief of retrieved sections for the LLM
        sections_brief_parts = []
        for crime_name, sections in retrieved_sections.items():
            if not sections:
                sections_brief_parts.append(f"[{crime_name}] — No sections retrieved yet")
                continue
            sec_lines = []
            for sec in sections:
                sec_num = sec.get("section_number", sec.get("section", ""))
                statute = sec.get("statute", "BNS")
                title = sec.get("title", sec.get("section_title", ""))
                ingredients = sec.get("ingredients_matched", sec.get("legal_elements", []))
                ingredients_str = "; ".join(ingredients) if ingredients else "as per statute"
                sec_lines.append(f"    • {sec_num} {statute} ({title}): {ingredients_str}")
            sections_brief_parts.append(f"[{crime_name}]\n" + "\n".join(sec_lines))

        sections_brief = "\n\n".join(sections_brief_parts) if sections_brief_parts else "No sections retrieved."

        # Build the evidence map from case context
        case_facts = ""
        if self.case_context:
            case_facts = self.case_context.case_profile.case_facts

        evidence_items = "\n".join(
            f"- {e}" for e in self.prosecutor_analysis.evidence_requirements
        ) or "- See case facts above"

        prompt = f"""You are a Senior Public Prosecutor arguing AGAINST anticipatory bail.
The defense has raised specific challenges. Your job is to counter each one with
arguments grounded in the retrieved statutory provisions and case evidence below.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CASE FACTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{case_facts}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROSECUTION THEORY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{self.prosecutor_analysis.prosecution_theory}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RETRIEVED STATUTORY PROVISIONS (cite these in your arguments):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{sections_brief}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AVAILABLE EVIDENCE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{evidence_items}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEFENSE ARGUMENT TO REBUT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{defense_argument}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSTRUCTIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generate ONE counter-argument per distinct defense claim. Each counter-argument MUST:
1. Identify the specific defense claim it rebuts (quote or paraphrase it briefly).
2. Reference the specific statutory provision (section number + statute + title) that the
   defense claim conflicts with or that the prosecution relies on.
3. Map the statutory element to concrete evidence from the case facts
   (e.g. CCTV footage, medical examination, witness testimony, recovered phone).
4. Explain why the defense claim fails to defeat the statutory requirement.
5. End with why this strengthens the case for REFUSING anticipatory bail.

Do NOT make generic assertions like "the argument lacks merit."
Do NOT introduce facts not present in the case.
Be specific, legally precise, and forceful.

Return ONLY a JSON array of strings, one element per counter-argument.
Each string should be 3-5 sentences. No markdown, no numbering inside strings."""

        response = self.llm.invoke(prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

        try:
            from lexigraphbe.config import extract_json_from_text
            result = extract_json_from_text(response_text)
            if isinstance(result, list) and all(isinstance(a, str) for a in result):
                return result
        except Exception:
            pass

        # Fallback: try raw json.loads
        try:
            import json as _json
            result = _json.loads(response_text.strip())
            if isinstance(result, list):
                return result
        except Exception:
            pass

        # Last resort: return the raw text as a single argument
        return [response_text.strip()]

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
    print(f"\nPrimary Charges:")
    for charge in opening['primary_charges']:
        print(f"\n  Crime: {charge['crime']}")
        print(f"  Elements to Prove: {', '.join(charge['elements'])}")
        sections_count = len(charge.get('sections', []))
        print(f"  Retrieved Sections: {sections_count}")
        if sections_count > 0:
            for sec in charge['sections'][:3]:  # Show first 3 sections
                print(f"    - {sec.get('section_number', 'N/A')} {sec.get('statute', '')}: {sec.get('title', '')}")
        print(f"  Strategy: {charge['strategy'][:150]}...")
    
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
    print(f"\nCounter-Arguments:")
    for i, arg in enumerate(resp.get("counter_arguments", []), 1):
        print(f"\n  [{i}] {arg}")

    # Show retrieved sections per crime
    sections_per_crime = resp.get("retrieved_sections_per_crime", {})
    if sections_per_crime:
        print(f"\nStatutory Sections Retrieved During Rebuttal:")
        for crime_name, sections in sections_per_crime.items():
            print(f"  {crime_name}: {len(sections)} section(s)")
            for sec in sections[:3]:
                sec_num = sec.get("section_number", sec.get("section", "N/A"))
                statute = sec.get("statute", "")
                title = sec.get("title", sec.get("section_title", ""))
                print(f"    - {sec_num} {statute}: {title}")
    
    print("\n" + "=" * 80)
    print("Prosecution Workflow Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()