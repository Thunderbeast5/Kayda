"""
Orchestrator Agent - Central brain of the MootCourt application.

Architecture:
1. Receives initial user input (case info, evidence files, witness info)
2. Stores session state using Firestore memory
3. Sends raw files to Evidence Agent → receives structured facts + timeline + graph
4. Optionally runs LexiGraphBE pipelines (Stage 1-6) for legal research
5. Passes extracted case facts to Prosecutor Agent (from backend/prosecutor/prosecutor.py)
6. Passes extracted case facts to Defense Agent (from backend/prosecutor/defense.py)
7. Collects both arguments
8. [Future] Sends arguments to Judge Agent
9. [Future] Pushes final verdict to frontend via WebSocket

LexiGraphBE Integration:
- Stage 0: Case Intake (optional - if not using evidence agent)
- Stage 1: Query Understanding (legal concept decomposition)
- Stage 2: Sub-Query to Chapter Mapping
- Stage 3: Chapter Identification
- Stage 4: Statutory Verification & Ingredient Matching
- Stage 5: Bail Reasoning (if anticipatory bail case)
- Stage 6: Precedent Retrieval

State Management:
- Uses Firestore for persistent session storage
- Tracks conversation flow and agent outputs
- Maintains context for multi-turn interactions
"""

import sys
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Add lexigraphbe directory to path
lexigraphbe_dir = backend_dir / "lexigraphbe"
if str(lexigraphbe_dir) not in sys.path:
    sys.path.insert(0, str(lexigraphbe_dir))

# Add prosecutor directory to path
prosecutor_dir = backend_dir / "prosecutor"
if str(prosecutor_dir) not in sys.path:
    sys.path.insert(0, str(prosecutor_dir))

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# Add evidence directory directly to path
evidence_dir = backend_dir / "agents" / "evidence"
if str(evidence_dir) not in sys.path:
    sys.path.insert(0, str(evidence_dir))

# Add agents directory to path
agents_dir = backend_dir / "agents"
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

# Import from evidence.py (the only evidence module — evidence_analyzer.py does not exist)
from evidence import (
    extract_facts,
    extract_timeline,
    build_case_graph,
    build_session_id,
    analyze_evidence_with_context,
    _get_firestore_client,
)

# Import lexigraphbe pipelines
from lexigraphbe.stage1_pipeline import Stage1Pipeline
from lexigraphbe.stage2_pipeline import Stage2Pipeline
from lexigraphbe.stage3_pipeline import Stage3Pipeline
from lexigraphbe.stage4_pipeline import Stage4Pipeline
from lexigraphbe.stage5_pipeline import Stage5Pipeline
from lexigraphbe.stage6_pipeline import Stage6Pipeline
from lexigraphbe.schemas import CaseProfile, CaseContextObject

# Import prosecutor and defense agents from correct location
sys.path.insert(0, str(backend_dir / "prosecutor"))
from prosecutor import ProsecutorAgent
from defense import DefenseAgent

load_dotenv(backend_dir / ".env")


# ============================================================================
# Enums and Data Classes
# ============================================================================

class SessionPhase(Enum):
    """Tracks the current phase of the moot court session"""
    INITIALIZED = "initialized"
    EVIDENCE_ANALYSIS = "evidence_analysis"
    LEGAL_RESEARCH_STAGE1 = "legal_research_stage1"  # Query understanding
    LEGAL_RESEARCH_STAGE2 = "legal_research_stage2"  # Chapter mapping
    LEGAL_RESEARCH_STAGE3 = "legal_research_stage3"  # Chapter identification
    LEGAL_RESEARCH_STAGE4 = "legal_research_stage4"  # Statutory verification
    LEGAL_RESEARCH_STAGE5 = "legal_research_stage5"  # Bail reasoning
    LEGAL_RESEARCH_STAGE6 = "legal_research_stage6"  # Precedent retrieval
    PROSECUTION_ANALYSIS = "prosecution_analysis"
    DEFENSE_ANALYSIS = "defense_analysis"
    PROSECUTION_OPENING = "prosecution_opening"
    DEFENSE_OPENING = "defense_opening"
    PROSECUTION_REBUTTAL = "prosecution_rebuttal"
    DEFENSE_REBUTTAL = "defense_rebuttal"
    JUDGE_DELIBERATION = "judge_deliberation"
    VERDICT = "verdict"
    COMPLETED = "completed"
    ERROR = "error"


class AgentStatus(Enum):
    """Status of individual agent execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentExecution:
    """Tracks execution of a single agent"""
    agent_name: str
    status: AgentStatus
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


@dataclass
class SessionState:
    """Complete state of an orchestrator session"""
    session_id: str
    case_title: str
    current_phase: SessionPhase
    created_at: str
    updated_at: str
    
    # Evidence analysis outputs
    evidence_session_id: Optional[str] = None
    raw_evidence_text: Optional[str] = None
    structured_facts: Optional[Dict[str, Any]] = None
    timeline: Optional[List[Dict[str, Any]]] = None
    case_graph: Optional[Dict[str, Any]] = None
    
    # LexiGraphBE pipeline outputs (Stages 1-6)
    lexigraphbe_stage1_output: Optional[Dict[str, Any]] = None  # LegalQueryObject
    lexigraphbe_stage2_output: Optional[Dict[str, Any]] = None  # BatchedMappingResponse
    lexigraphbe_stage3_output: Optional[Dict[str, Any]] = None  # ChapterIdentificationObject
    lexigraphbe_stage4_output: Optional[Dict[str, Any]] = None  # StatutoryVerificationObject
    lexigraphbe_stage5_output: Optional[Dict[str, Any]] = None  # BailReasoningObject
    lexigraphbe_stage6_output: Optional[Dict[str, Any]] = None  # PrecedentRetrievalObject
    
    # Prosecutor outputs
    prosecutor_analysis: Optional[Dict[str, Any]] = None
    prosecutor_opening: Optional[Dict[str, Any]] = None
    prosecutor_rebuttal: Optional[Dict[str, Any]] = None
    
    # Defense outputs
    defense_analysis: Optional[Dict[str, Any]] = None
    defense_opening: Optional[Dict[str, Any]] = None
    defense_rebuttal: Optional[Dict[str, Any]] = None
    
    # Judge outputs (future)
    judge_analysis: Optional[Dict[str, Any]] = None
    verdict: Optional[Dict[str, Any]] = None
    
    # Execution tracking
    agent_executions: List[AgentExecution] = None
    
    # Additional metadata
    proceeding_type: str = "anticipatory_bail_opposition"
    legal_regime: str = "IPC + CrPC"
    
    def __post_init__(self):
        if self.agent_executions is None:
            self.agent_executions = []


# ============================================================================
# Orchestrator Agent
# ============================================================================

class OrchestratorAgent:
    """
    Central orchestrator that manages the complete moot court simulation workflow.
    
    Key Features:
    - State management via Firestore
    - Sequential agent execution with dependency tracking
    - LexiGraphBE 6-stage pipeline integration
    - Prosecutor and Defense agent coordination
    - Error handling and recovery
    - Progress tracking and logging
    """
    
    def __init__(self):
        """Initialize the orchestrator with Firestore connection"""
        try:
            self.db = _get_firestore_client()
            self.use_firestore = True
            print("[Orchestrator] Firestore enabled")
        except Exception as e:
            print(f"[Orchestrator] Warning: Firestore not available ({e})")
            print("[Orchestrator] Running in memory-only mode")
            self.db = None
            self.use_firestore = False
            self._memory_sessions = {}  # In-memory fallback
        
        self.collection_name = "orchestrator_sessions"
        
        # Initialize pipelines (lazy loading)
        self._stage1_pipeline = None
        self._stage2_pipeline = None
        self._stage3_pipeline = None
        self._stage4_pipeline = None
        self._stage5_pipeline = None
        self._stage6_pipeline = None
        self._prosecutor_agent = None
        self._defense_agent = None
        
        print("[Orchestrator] Initialized")
    
    # ========================================================================
    # Session Management
    # ========================================================================
    
    def create_session(
        self,
        case_title: str,
        proceeding_type: str = "anticipatory_bail_opposition",
        legal_regime: str = "IPC + CrPC"
    ) -> SessionState:
        """
        Create a new orchestrator session.
        
        Args:
            case_title: Human-readable case title
            proceeding_type: Type of proceeding
            legal_regime: Legal regime to use
        
        Returns:
            SessionState object
        """
        session_id = f"orch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        now = datetime.now(timezone.utc).isoformat()
        
        session = SessionState(
            session_id=session_id,
            case_title=case_title,
            current_phase=SessionPhase.INITIALIZED,
            created_at=now,
            updated_at=now,
            proceeding_type=proceeding_type,
            legal_regime=legal_regime,
            agent_executions=[]
        )
        
        self._save_session(session)
        print(f"[Orchestrator] Created session: {session_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Retrieve a session from Firestore or memory"""
        # Memory fallback
        if not self.use_firestore:
            return self._memory_sessions.get(session_id)
        
        # Firestore
        doc_ref = self.db.collection(self.collection_name).document(session_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return None
        
        data = doc.to_dict()
        
        # Reconstruct AgentExecution objects
        agent_executions = []
        for exec_dict in data.get("agent_executions", []):
            agent_executions.append(AgentExecution(
                agent_name=exec_dict["agent_name"],
                status=AgentStatus(exec_dict["status"]),
                started_at=exec_dict.get("started_at"),
                completed_at=exec_dict.get("completed_at"),
                input_data=exec_dict.get("input_data"),
                output_data=exec_dict.get("output_data"),
                error_message=exec_dict.get("error_message"),
            ))
        
        data["agent_executions"] = agent_executions
        data["current_phase"] = SessionPhase(data["current_phase"])
        
        return SessionState(**data)
    
    def _save_session(self, session: SessionState):
        """Save session state to Firestore or memory"""
        # Memory fallback
        if not self.use_firestore:
            self._memory_sessions[session.session_id] = session
            return
        
        # Firestore
        data = asdict(session)
        
        # Convert enums to strings
        data["current_phase"] = session.current_phase.value
        
        # Convert AgentExecution objects
        agent_execs_serialized = []
        for exec_obj in session.agent_executions:
            exec_dict = asdict(exec_obj)
            exec_dict["status"] = exec_obj.status.value
            agent_execs_serialized.append(exec_dict)
        data["agent_executions"] = agent_execs_serialized
        
        doc_ref = self.db.collection(self.collection_name).document(session.session_id)
        doc_ref.set(data)
    
    def _update_phase(self, session: SessionState, new_phase: SessionPhase):
        """Update session phase and save"""
        session.current_phase = new_phase
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_session(session)
        print(f"[Orchestrator] Phase: {new_phase.value}")
    
    def _record_agent_execution(
        self,
        session: SessionState,
        agent_name: str,
        status: AgentStatus,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ):
        """Record agent execution in session state"""
        existing = next(
            (e for e in session.agent_executions if e.agent_name == agent_name),
            None
        )
        
        if existing:
            existing.status = status
            if status == AgentStatus.RUNNING and not existing.started_at:
                existing.started_at = datetime.now(timezone.utc).isoformat()
            if status in (AgentStatus.COMPLETED, AgentStatus.FAILED):
                existing.completed_at = datetime.now(timezone.utc).isoformat()
            if input_data:
                existing.input_data = input_data
            if output_data:
                existing.output_data = output_data
            if error_message:
                existing.error_message = error_message
        else:
            execution = AgentExecution(
                agent_name=agent_name,
                status=status,
                started_at=datetime.now(timezone.utc).isoformat() if status == AgentStatus.RUNNING else None,
                completed_at=datetime.now(timezone.utc).isoformat() if status in (AgentStatus.COMPLETED, AgentStatus.FAILED) else None,
                input_data=input_data,
                output_data=output_data,
                error_message=error_message,
            )
            session.agent_executions.append(execution)
        
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_session(session)
    
    # ========================================================================
    # Step 1: Evidence Analysis
    # ========================================================================
    
    def process_evidence(
        self,
        session_id: str,
        evidence_file_path: str
    ) -> Dict[str, Any]:
        """
        Step 1: Process evidence file and extract structured facts + timeline + graph.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        print(f"\n{'='*80}")
        print(f"[Orchestrator] STEP 1: Evidence Analysis")
        print(f"{'='*80}")
        
        self._update_phase(session, SessionPhase.EVIDENCE_ANALYSIS)
        self._record_agent_execution(
            session, "evidence_agent", AgentStatus.RUNNING,
            input_data={"file_path": evidence_file_path}
        )
        
        try:
            evidence_session_id = build_session_id(evidence_file_path)
            result = analyze_evidence_with_context(evidence_session_id, evidence_file_path)
            
            session.evidence_session_id = evidence_session_id
            session.raw_evidence_text = result.get("rawText", "")
            session.structured_facts = result.get("facts", {})
            session.timeline = result.get("timeline", [])
            session.case_graph = result.get("graph", {})
            
            self._record_agent_execution(
                session, "evidence_agent", AgentStatus.COMPLETED,
                output_data={
                    "evidence_session_id": evidence_session_id,
                    "timeline_events": len(session.timeline),
                    "graph_nodes": len(session.case_graph.get("nodes", [])),
                }
            )
            
            print(f"[Orchestrator] ✓ Evidence analyzed successfully")
            print(f"  - Evidence Session ID: {evidence_session_id}")
            print(f"  - Timeline Events: {len(session.timeline)}")
            
            return {
                "success": True,
                "evidence_session_id": evidence_session_id,
                "structured_facts": session.structured_facts,
                "timeline": session.timeline,
                "graph": session.case_graph
            }
            
        except Exception as e:
            error_msg = f"Evidence analysis failed: {str(e)}"
            print(f"[Orchestrator] ✗ {error_msg}")
            
            self._record_agent_execution(
                session, "evidence_agent", AgentStatus.FAILED,
                error_message=error_msg
            )
            self._update_phase(session, SessionPhase.ERROR)
            
            return {"success": False, "error": error_msg}
    
    # ========================================================================
    # Step 2: LexiGraphBE Stage 1 - Query Understanding
    # ========================================================================
    
    def run_lexigraphbe_stage1(self, session_id: str) -> Dict[str, Any]:
        """
        Step 2a: Run LexiGraphBE Stage 1 - Query Understanding and Legal Decomposition.
        Transforms case facts into LegalQueryObject with concepts and sub-queries.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if not session.structured_facts:
            return {"success": False, "error": "No structured facts available. Run evidence analysis first."}
        
        print(f"\n{'='*80}")
        print(f"[Orchestrator] STEP 2a: LexiGraphBE Stage 1 - Query Understanding")
        print(f"{'='*80}")
        
        self._update_phase(session, SessionPhase.LEGAL_RESEARCH_STAGE1)
        self._record_agent_execution(session, "lexigraphbe_stage1", AgentStatus.RUNNING)
        
        try:
            # Build case context from evidence
            case_facts = self._build_case_facts_text(session)
            
            case_profile = CaseProfile(
                case_facts=case_facts,
                legal_regime=session.legal_regime,
                procedural_stage="Pre-Arrest / Anticipatory Bail" if "bail" in session.proceeding_type else "Trial",
                requested_relief="Opposition to grant of Anticipatory Bail" if "bail" in session.proceeding_type else "Conviction",
            )
            
            contract_status, contract_violations = case_profile.validate_stage1_contract()
            
            case_context = CaseContextObject(
                case_profile=case_profile,
                contract_status=contract_status,
                contract_violations=contract_violations,
                verification_status="VERIFIED",
                active_parties=case_profile.get_accused_list()
            )
            
            # Run Stage 1 pipeline
            if not self._stage1_pipeline:
                self._stage1_pipeline = Stage1Pipeline()
            
            result = self._stage1_pipeline.run(case_context)
            
            # Store result
            session.lexigraphbe_stage1_output = {
                "status": result.status,
                "legal_query": result.verified_query_object.model_dump() if result.verified_query_object else None,
                "feedback": result.feedback,
            }
            
            self._record_agent_execution(
                session, "lexigraphbe_stage1", AgentStatus.COMPLETED,
                output_data={
                    "status": result.status,
                    "concepts_identified": len(result.verified_query_object.legal_concepts) if result.verified_query_object else 0,
                }
            )
            
            print(f"[Orchestrator] ✓ Stage 1 completed - Status: {result.status}")
            
            return {"success": True, "result": session.lexigraphbe_stage1_output}
            
        except Exception as e:
            error_msg = f"LexiGraphBE Stage 1 failed: {str(e)}"
            print(f"[Orchestrator] ✗ {error_msg}")
            self._record_agent_execution(session, "lexigraphbe_stage1", AgentStatus.FAILED, error_message=error_msg)
            return {"success": False, "error": error_msg}
    
    # ========================================================================
    # LexiGraphBE Stages 2-6 (helper methods follow similar pattern)
    # ========================================================================
    
    def run_lexigraphbe_stage2(self, session_id: str) -> Dict[str, Any]:
        """Stage 2: Sub-Query to Chapter Mapping"""
        session = self.get_session(session_id)
        if not session or not session.lexigraphbe_stage1_output:
            return {"success": False, "error": "Stage 1 must be completed first"}
        
        print(f"\n[Orchestrator] STEP 2b: LexiGraphBE Stage 2 - Chapter Mapping")
        self._update_phase(session, SessionPhase.LEGAL_RESEARCH_STAGE2)
        self._record_agent_execution(session, "lexigraphbe_stage2", AgentStatus.RUNNING)
        
        try:
            if not self._stage2_pipeline:
                self._stage2_pipeline = Stage2Pipeline()
            
            legal_query = session.lexigraphbe_stage1_output["legal_query"]
            result = self._stage2_pipeline.run(legal_query)
            
            session.lexigraphbe_stage2_output = {
                "status": result.status,
                "mapping_response": result.batched_mapping_response.model_dump() if result.batched_mapping_response else None,
            }
            
            self._record_agent_execution(session, "lexigraphbe_stage2", AgentStatus.COMPLETED)
            print(f"[Orchestrator] ✓ Stage 2 completed - Status: {result.status}")
            
            return {"success": True, "result": session.lexigraphbe_stage2_output}
            
        except Exception as e:
            error_msg = f"Stage 2 failed: {str(e)}"
            self._record_agent_execution(session, "lexigraphbe_stage2", AgentStatus.FAILED, error_message=error_msg)
            return {"success": False, "error": error_msg}
    
    def run_lexigraphbe_stage3(self, session_id: str) -> Dict[str, Any]:
        """Stage 3: Chapter Identification"""
        session = self.get_session(session_id)
        if not session or not session.lexigraphbe_stage2_output:
            return {"success": False, "error": "Stage 2 must be completed first"}
        
        print(f"\n[Orchestrator] STEP 2c: LexiGraphBE Stage 3 - Chapter Identification")
        self._update_phase(session, SessionPhase.LEGAL_RESEARCH_STAGE3)
        self._record_agent_execution(session, "lexigraphbe_stage3", AgentStatus.RUNNING)
        
        try:
            if not self._stage3_pipeline:
                self._stage3_pipeline = Stage3Pipeline()
            
            legal_query = session.lexigraphbe_stage1_output["legal_query"]
            stage2_mapping = session.lexigraphbe_stage2_output["mapping_response"]
            
            result = self._stage3_pipeline.run(legal_query, stage2_mapping)
            
            session.lexigraphbe_stage3_output = {
                "status": result.status,
                "chapter_object": result.verified_chapter_object.model_dump() if result.verified_chapter_object else None,
            }
            
            self._record_agent_execution(session, "lexigraphbe_stage3", AgentStatus.COMPLETED)
            print(f"[Orchestrator] ✓ Stage 3 completed - Status: {result.status}")
            
            return {"success": True, "result": session.lexigraphbe_stage3_output}
            
        except Exception as e:
            error_msg = f"Stage 3 failed: {str(e)}"
            self._record_agent_execution(session, "lexigraphbe_stage3", AgentStatus.FAILED, error_message=error_msg)
            return {"success": False, "error": error_msg}
    
    def run_lexigraphbe_stage4(self, session_id: str) -> Dict[str, Any]:
        """Stage 4: Statutory Verification & Ingredient Matching"""
        session = self.get_session(session_id)
        if not session or not session.lexigraphbe_stage3_output:
            return {"success": False, "error": "Stage 3 must be completed first"}
        
        print(f"\n[Orchestrator] STEP 2d: LexiGraphBE Stage 4 - Statutory Verification")
        self._update_phase(session, SessionPhase.LEGAL_RESEARCH_STAGE4)
        self._record_agent_execution(session, "lexigraphbe_stage4", AgentStatus.RUNNING)
        
        try:
            if not self._stage4_pipeline:
                self._stage4_pipeline = Stage4Pipeline()
            
            legal_query = session.lexigraphbe_stage1_output["legal_query"]
            chapter_object = session.lexigraphbe_stage3_output["chapter_object"]
            
            result = self._stage4_pipeline.run(legal_query, chapter_object)
            
            session.lexigraphbe_stage4_output = {
                "status": result.status,
                "statutory_object": result.verified_statutory_object.model_dump() if result.verified_statutory_object else None,
            }
            
            self._record_agent_execution(session, "lexigraphbe_stage4", AgentStatus.COMPLETED)
            print(f"[Orchestrator] ✓ Stage 4 completed - Status: {result.status}")
            
            return {"success": True, "result": session.lexigraphbe_stage4_output}
            
        except Exception as e:
            error_msg = f"Stage 4 failed: {str(e)}"
            self._record_agent_execution(session, "lexigraphbe_stage4", AgentStatus.FAILED, error_message=error_msg)
            return {"success": False, "error": error_msg}
    
    def run_lexigraphbe_full_pipeline(self, session_id: str, include_bail: bool = True) -> Dict[str, Any]:
        """
        Run complete LexiGraphBE pipeline (Stages 1-4, optionally 5-6).
        """
        print(f"\n{'='*80}")
        print(f"[Orchestrator] Running Full LexiGraphBE Pipeline")
        print(f"{'='*80}")
        
        # Stage 1
        result1 = self.run_lexigraphbe_stage1(session_id)
        if not result1["success"]:
            return result1
        
        # Stage 2
        result2 = self.run_lexigraphbe_stage2(session_id)
        if not result2["success"]:
            return result2
        
        # Stage 3
        result3 = self.run_lexigraphbe_stage3(session_id)
        if not result3["success"]:
            return result3
        
        # Stage 4
        result4 = self.run_lexigraphbe_stage4(session_id)
        if not result4["success"]:
            return result4
        
        print(f"[Orchestrator] ✓ LexiGraphBE Stages 1-4 completed successfully")
        
        return {
            "success": True,
            "stages_completed": [1, 2, 3, 4],
            "final_result": result4["result"]
        }
    
    # ========================================================================
    # Step 3: Prosecutor Analysis
    # ========================================================================
    
    def run_prosecutor_analysis(self, session_id: str) -> Dict[str, Any]:
        """
        Step 3: Analyze case from prosecutor's perspective.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if not session.structured_facts:
            return {"success": False, "error": "No structured facts available. Run evidence analysis first."}
        
        print(f"\n{'='*80}")
        print(f"[Orchestrator] STEP 3: Prosecutor Analysis")
        print(f"{'='*80}")
        
        self._update_phase(session, SessionPhase.PROSECUTION_ANALYSIS)
        case_facts = self._build_case_facts_text(session)
        
        self._record_agent_execution(session, "prosecutor_agent", AgentStatus.RUNNING)
        
        try:
            if not self._prosecutor_agent:
                self._prosecutor_agent = ProsecutorAgent()
            
            analysis = self._prosecutor_agent.analyze_case(
                case_file=case_facts,
                proceeding_type=session.proceeding_type,
                legal_regime=session.legal_regime
            )
            
            session.prosecutor_analysis = {
                "case_summary": analysis.case_summary,
                "primary_crime": analysis.primary_crime,
                "prosecution_theory": analysis.prosecution_theory,
                "identified_crimes": [
                    {
                        "crime_name": crime.crime_name,
                        "severity": crime.severity,
                        "legal_elements": crime.legal_elements,
                        "prosecution_strategy": crime.prosecution_strategy,
                    }
                    for crime in analysis.identified_crimes
                ],
            }
            
            self._record_agent_execution(session, "prosecutor_agent", AgentStatus.COMPLETED,
                output_data={"primary_crime": analysis.primary_crime}
            )
            
            print(f"[Orchestrator] ✓ Prosecutor analysis completed")
            print(f"  - Primary Crime: {analysis.primary_crime}")
            
            return {"success": True, "analysis": session.prosecutor_analysis}
            
        except Exception as e:
            error_msg = f"Prosecutor analysis failed: {str(e)}"
            print(f"[Orchestrator] ✗ {error_msg}")
            self._record_agent_execution(session, "prosecutor_agent", AgentStatus.FAILED, error_message=error_msg)
            self._update_phase(session, SessionPhase.ERROR)
            return {"success": False, "error": error_msg}
    
    # ========================================================================
    # Step 4: Defense Analysis
    # ========================================================================
    
    def run_defense_analysis(self, session_id: str) -> Dict[str, Any]:
        """
        Step 4: Analyze case from defense perspective.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if not session.structured_facts:
            return {"success": False, "error": "No structured facts available."}
        
        print(f"\n{'='*80}")
        print(f"[Orchestrator] STEP 4: Defense Analysis")
        print(f"{'='*80}")
        
        self._update_phase(session, SessionPhase.DEFENSE_ANALYSIS)
        case_facts = self._build_case_facts_text(session)
        
        self._record_agent_execution(session, "defense_agent", AgentStatus.RUNNING)
        
        try:
            if not self._defense_agent:
                self._defense_agent = DefenseAgent()
            
            defense_proceeding = {
                "anticipatory_bail_opposition": "anticipatory_bail",
                "bail_opposition": "regular_bail",
                "trial_prosecution": "trial_defense",
            }.get(session.proceeding_type, "anticipatory_bail")
            
            analysis = self._defense_agent.analyze_case(
                case_file=case_facts,
                proceeding_type=defense_proceeding,
                legal_regime=session.legal_regime
            )
            
            session.defense_analysis = {
                "case_summary": analysis.case_summary,
                "primary_defense": analysis.primary_defense,
                "bail_grounds": analysis.bail_grounds,
                "defense_grounds": [
                    {
                        "charge_name": ground.charge_name,
                        "severity": ground.severity,
                        "ingredients_attacked": ground.ingredients_attacked,
                        "defense_strategy": ground.defense_strategy,
                    }
                    for ground in analysis.defense_grounds
                ],
            }
            
            self._record_agent_execution(session, "defense_agent", AgentStatus.COMPLETED,
                output_data={"primary_defense": analysis.primary_defense}
            )
            
            print(f"[Orchestrator] ✓ Defense analysis completed")
            print(f"  - Primary Defense: {analysis.primary_defense}")
            
            return {"success": True, "analysis": session.defense_analysis}
            
        except Exception as e:
            error_msg = f"Defense analysis failed: {str(e)}"
            print(f"[Orchestrator] ✗ {error_msg}")
            self._record_agent_execution(session, "defense_agent", AgentStatus.FAILED, error_message=error_msg)
            self._update_phase(session, SessionPhase.ERROR)
            return {"success": False, "error": error_msg}
    
    # ========================================================================
    # Step 5 & 6: Opening Arguments
    # ========================================================================
    
    def build_prosecutor_opening(self, session_id: str) -> Dict[str, Any]:
        """Build prosecutor's opening argument"""
        session = self.get_session(session_id)
        if not session or not session.prosecutor_analysis:
            return {"success": False, "error": "Prosecutor analysis not available"}
        
        print(f"\n[Orchestrator] STEP 5: Prosecutor Opening Argument")
        self._update_phase(session, SessionPhase.PROSECUTION_OPENING)
        self._record_agent_execution(session, "prosecutor_opening", AgentStatus.RUNNING)
        
        try:
            if not self._prosecutor_agent:
                return {"success": False, "error": "Prosecutor agent not initialized"}
            
            opening = self._prosecutor_agent.build_opening_argument()
            session.prosecutor_opening = opening
            
            self._record_agent_execution(session, "prosecutor_opening", AgentStatus.COMPLETED)
            print(f"[Orchestrator] ✓ Prosecutor opening built")
            
            return {"success": True, "opening": opening}
            
        except Exception as e:
            error_msg = f"Prosecutor opening failed: {str(e)}"
            self._record_agent_execution(session, "prosecutor_opening", AgentStatus.FAILED, error_message=error_msg)
            return {"success": False, "error": error_msg}
    
    def build_defense_opening(
        self, session_id: str, prosecution_argument: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build defense's opening argument.

        Always runs the full pipeline first (Stage 2→4 section retrieval +
        ingredient matrix) via build_opening_argument(), which populates
        _cached_defense_matrix and _cached_bail_law on the agent.

        If prosecution_argument is supplied (real-time courtroom mode), the
        defence then calls handle_rebuttal() so its response is grounded in
        the retrieved sections AND addresses what the prosecutor just said.

        Without prosecution_argument (AI-goes-first mode), the opening
        argument built by the pipeline is returned directly.
        """
        session = self.get_session(session_id)
        if not session or not session.defense_analysis:
            return {"success": False, "error": "Defense analysis not available"}
        
        print(f"\n[Orchestrator] STEP 6: Defense Opening Argument")
        self._update_phase(session, SessionPhase.DEFENSE_OPENING)
        self._record_agent_execution(session, "defense_opening", AgentStatus.RUNNING)
        
        try:
            if not self._defense_agent:
                return {"success": False, "error": "Defense agent not initialized"}

            # ----------------------------------------------------------------
            # ALWAYS run the full pipeline first.
            # build_opening_argument() triggers Stage 2→4 (section retrieval),
            # builds the defense ingredient matrix, and retrieves bail law.
            # handle_rebuttal() REQUIRES _cached_defense_matrix to be
            # populated — if we skip this step the rebuttal has no matrix
            # and degrades to a generic LLM text response.
            # ----------------------------------------------------------------
            print("[Orchestrator] Running full defense pipeline (Stage 2→4 section retrieval + ingredient matrix)...")
            full_opening = self._defense_agent.build_opening_argument()
            # _cached_defense_matrix and _cached_bail_law are now populated.

            if prosecution_argument:
                # Real-time mode: pipeline has built the matrix; now rebut
                # specifically what the prosecutor argued at the podium.
                print("[Orchestrator] Grounding defense response in retrieved sections + prosecution argument...")
                rebuttal_result = self._defense_agent.handle_rebuttal(prosecution_argument)
                opening_text = rebuttal_result.get("defense_response", {}).get("rebuttal", "")
                opening = {
                    "phase": "opening_response",
                    "opening_statement": opening_text,
                    "responded_to": prosecution_argument[:300],
                    # Carry matrix metadata for downstream use (rebuttals, closing)
                    "defense_matrix": full_opening.get("defense_matrix", []),
                    "defense_grounds": full_opening.get("defense_grounds", []),
                    "bail_grounds": full_opening.get("bail_grounds", []),
                }
            else:
                # AI-goes-first mode: use the pipeline opening directly.
                opening = full_opening

            session.defense_opening = opening
            
            self._record_agent_execution(session, "defense_opening", AgentStatus.COMPLETED)
            print(f"[Orchestrator] ✓ Defense opening built")
            
            return {"success": True, "opening": opening}
            
        except Exception as e:
            error_msg = f"Defense opening failed: {str(e)}"
            self._record_agent_execution(session, "defense_opening", AgentStatus.FAILED, error_message=error_msg)
            return {"success": False, "error": error_msg}
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def _build_case_facts_text(self, session: SessionState) -> str:
        """Build comprehensive case facts text from structured evidence"""
        facts = session.structured_facts or {}
        timeline = session.timeline or []
        
        parts = []
        parts.append(f"CASE: {session.case_title}")
        parts.append(f"PROCEEDING TYPE: {session.proceeding_type}")
        parts.append(f"LEGAL REGIME: {session.legal_regime}")
        parts.append("")
        
        who = facts.get("who", {})
        if who.get("complainant"):
            parts.append(f"COMPLAINANT: {who['complainant']}")
        if who.get("accused"):
            parts.append(f"ACCUSED: {', '.join(who['accused'])}")
        if who.get("victims"):
            parts.append(f"VICTIMS: {', '.join(who['victims'])}")
        if who.get("witnesses"):
            parts.append(f"WITNESSES: {', '.join(who['witnesses'])}")
        parts.append("")
        
        incident = facts.get("incident", {})
        parts.append("INCIDENT DETAILS:")
        if incident.get("date"):
            parts.append(f"Date: {incident['date']}")
        if incident.get("time"):
            parts.append(f"Time: {incident['time']}")
        if incident.get("place"):
            parts.append(f"Place: {incident['place']}")
        if incident.get("summary"):
            parts.append(f"Summary: {incident['summary']}")
        parts.append("")
        
        sections = facts.get("sections", [])
        if sections:
            parts.append(f"SECTIONS INVOKED: {', '.join(sections)}")
            parts.append("")

        # Evidence items — critical for agent reasoning
        evidence_items = facts.get("evidence", [])
        if evidence_items:
            parts.append("EVIDENCE:")
            for item in evidence_items:
                parts.append(f"  - {item}")
            parts.append("")

        # Accused's own admissions — constrain what defense can deny
        admissions = facts.get("accused_admissions", [])
        if admissions:
            parts.append("ACCUSED ADMISSIONS (acts the accused has admitted):")
            for a in admissions:
                parts.append(f"  - {a}")
            parts.append("")

        # Accused's stated defence version
        accused_defence = facts.get("accused_defence")
        if accused_defence:
            parts.append(f"ACCUSED'S VERSION: {accused_defence}")
            parts.append("")

        # Relief sought
        relief = facts.get("relief_sought")
        if relief:
            parts.append(f"RELIEF SOUGHT: {relief}")
            parts.append("")
        
        if timeline:
            parts.append("CHRONOLOGICAL TIMELINE OF EVENTS:")
            for event in timeline[:20]:
                event_str = f"[{event.get('date', 'Date unknown')}]"
                if event.get("time"):
                    event_str += f" {event['time']}"
                event_str += f" - {event.get('description', 'No description')}"
                parts.append(event_str)
            parts.append("")
        
        if session.raw_evidence_text:
            parts.append("EVIDENCE TEXT EXCERPT:")
            parts.append(session.raw_evidence_text[:1000])
            if len(session.raw_evidence_text) > 1000:
                parts.append("... (truncated)")
            parts.append("")
        
        return "\n".join(parts)
    
    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Get human-readable session summary"""
        session = self.get_session(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}
        
        return {
            "session_id": session.session_id,
            "case_title": session.case_title,
            "current_phase": session.current_phase.value,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "proceeding_type": session.proceeding_type,
            "legal_regime": session.legal_regime,
            "evidence_analyzed": session.evidence_session_id is not None,
            "lexigraphbe_stage1_done": session.lexigraphbe_stage1_output is not None,
            "lexigraphbe_stage2_done": session.lexigraphbe_stage2_output is not None,
            "lexigraphbe_stage3_done": session.lexigraphbe_stage3_output is not None,
            "lexigraphbe_stage4_done": session.lexigraphbe_stage4_output is not None,
            "prosecutor_analysis_done": session.prosecutor_analysis is not None,
            "defense_analysis_done": session.defense_analysis is not None,
            "prosecutor_opening_done": session.prosecutor_opening is not None,
            "defense_opening_done": session.defense_opening is not None,
            "agent_executions": [
                {
                    "agent": e.agent_name,
                    "status": e.status.value,
                    "started": e.started_at,
                    "completed": e.completed_at,
                }
                for e in session.agent_executions
            ]
        }


# ============================================================================
# CLI Interface
# ============================================================================

def _read_multiline(prompt_header: str, instructions: str = "") -> str:
    """
    Read a multiline argument from stdin.
    The user types freely across as many lines as they need.
    Two consecutive blank lines (or a single Ctrl-D / EOF) signals end of input.
    Returns the full text as a single string.
    """
    if instructions:
        print(instructions)
    print(f"\n{prompt_header}")
    print("(Press ENTER twice when you have finished typing)\n")

    lines: list = []
    consecutive_blanks = 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "":
            consecutive_blanks += 1
            if consecutive_blanks >= 2 and lines:
                break
            # Keep a single blank line so paragraph structure is preserved
            if lines:
                lines.append("")
        else:
            consecutive_blanks = 0
            lines.append(line)

    # Strip any trailing blank lines that were accumulated
    while lines and lines[-1].strip() == "":
        lines.pop()

    return "\n".join(lines).strip()


def main():
    """Interactive CLI for testing the orchestrator"""
    print("=" * 80)
    print("ORCHESTRATOR AGENT - MootCourt Central Manager")
    print("=" * 80)

    orchestrator = OrchestratorAgent()

    # Select role
    print("\n📋 Select your role:")
    print("1. Prosecutor (State/Complainant)")
    print("2. Defense (Accused)")
    role_choice = input("Choice (1-2): ").strip() or "1"
    user_role = "prosecutor" if role_choice == "1" else "defense"
    print(f"\n✓ You are playing: {'Prosecutor' if user_role == 'prosecutor' else 'Defense'}")

    # Create session
    print("\n📋 Enter case title:")
    case_title = input().strip() or "Test Case"

    session = orchestrator.create_session(case_title)
    print(f"\n✓ Session created: {session.session_id}")

    # Evidence analysis - choose mode
    print("\n📋 Evidence Input Mode:")
    print("1. Upload evidence file (PDF or image)")
    print("2. Use case facts as text (skip file upload)")
    mode_choice = input("Choice (1-2): ").strip() or "2"

    if mode_choice == "1":
        print("\n📋 Enter path to evidence file (PDF or image):")
        evidence_path = input().strip()

        if not evidence_path or not Path(evidence_path).exists():
            print("❌ File not found. Exiting...")
            return

        result = orchestrator.process_evidence(session.session_id, evidence_path)
        if not result["success"]:
            print(f"❌ Evidence analysis failed: {result['error']}")
            return
    else:
        # Text mode
        print("\n📋 Running Evidence Analyzer on case text...")
        print(f"\n{'='*80}")
        print(f"[Orchestrator] STEP 1: Evidence Analysis (Text Mode)")
        print(f"{'='*80}")

        session = orchestrator.get_session(session.session_id)
        orchestrator._update_phase(session, SessionPhase.EVIDENCE_ANALYSIS)
        orchestrator._record_agent_execution(
            session, "evidence_analyzer_text", AgentStatus.RUNNING,
            input_data={"text_length": len(case_title)}
        )

        try:
            print("[Evidence Analyzer] Extracting structured facts from case text...")
            structured_facts = extract_facts(case_title)

            print("[Evidence Analyzer] Building chronological timeline...")
            timeline = extract_timeline(case_title)

            print("[Evidence Analyzer] Generating relationship graph...")
            case_graph = build_case_graph(session.session_id, structured_facts, timeline)

            session.structured_facts = structured_facts
            session.timeline = timeline
            session.case_graph = case_graph
            session.raw_evidence_text = case_title

            orchestrator._record_agent_execution(
                session, "evidence_analyzer_text", AgentStatus.COMPLETED,
                output_data={
                    "facts_extracted": True,
                    "timeline_events": len(timeline),
                    "graph_nodes": len(case_graph.get("nodes", [])),
                    "graph_edges": len(case_graph.get("edges", []))
                }
            )
            orchestrator._save_session(session)

            print(f"\n[Evidence Analyzer] ✓ Analysis completed")
            print(f"  - Complainant: {structured_facts.get('who', {}).get('complainant', 'N/A')}")
            print(f"  - Accused: {', '.join(structured_facts.get('who', {}).get('accused', []))}")
            print(f"  - Victims: {', '.join(structured_facts.get('who', {}).get('victims', []))}")
            print(f"  - Sections: {', '.join(structured_facts.get('sections', []))}")
            print(f"  - Timeline Events: {len(timeline)}")

        except Exception as e:
            error_msg = f"Evidence analysis failed: {str(e)}"
            print(f"[Orchestrator] ✗ {error_msg}")
            orchestrator._record_agent_execution(
                session, "evidence_analyzer_text", AgentStatus.FAILED,
                error_message=error_msg
            )
            print("❌ Cannot proceed without evidence analysis")
            return

    # LexiGraphBE pipeline (optional)
    print("\n📋 Run LexiGraphBE pipeline for legal research? (y/n):")
    if input().strip().lower() == "y":
        orchestrator.run_lexigraphbe_full_pipeline(session.session_id)

    # ---------------------------------------------------------------------------
    # Pre-court preparation — AI studies the brief privately (silent)
    # ---------------------------------------------------------------------------
    if user_role == "prosecutor":
        print("\n⏳ Defense AI is reviewing the case file privately (pre-court preparation)...")
        import io, contextlib
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            d_result = orchestrator.run_defense_analysis(session.session_id)
        if not d_result.get("success"):
            print(f"❌ Defense AI preparation failed: {d_result.get('error')}")
            return
        print("✓ Defense AI briefed. Court is now in session.\n")
    else:
        print("\n⏳ Prosecutor AI is reviewing the case file privately (pre-court preparation)...")
        import io, contextlib
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            p_result = orchestrator.run_prosecutor_analysis(session.session_id)
        if not p_result.get("success"):
            print(f"❌ Prosecutor AI preparation failed: {p_result.get('error')}")
            return
        print("✓ Prosecutor AI briefed. Court is now in session.\n")

    # ========================================================================
    # Interactive Courtroom Debate
    # ========================================================================
    print("\n" + "=" * 80)
    print("🏛️  COURTROOM PROCEEDINGS - INTERACTIVE DEBATE")
    print("=" * 80)

    debate_log: list = []   # Full record of every submission

    # ------------------------------------------------------------------
    # Helper — extract all prosecution text seen so far in the debate
    # ------------------------------------------------------------------
    def _prosecution_context(focus_label: str, focus_text: str) -> str:
        prior = "\n\n".join(
            f"[{log['type'].upper()}]\n{log['content']}"
            for log in debate_log
            if "Prosecutor" in log["speaker"]
        )
        return (
            f"PROSECUTION SUBMISSIONS SO FAR:\n\n{prior}\n\n"
            f"MOST RECENT PROSECUTION SUBMISSION ({focus_label} — focus primarily on this):\n{focus_text}"
        ) if prior else (
            f"PROSECUTION SUBMISSION ({focus_label}):\n{focus_text}"
        )

    # ------------------------------------------------------------------
    # Helper — extract all defense text seen so far in the debate
    # ------------------------------------------------------------------
    def _defense_context(focus_label: str, focus_text: str) -> str:
        prior = "\n\n".join(
            f"[{log['type'].upper()}]\n{log['content']}"
            for log in debate_log
            if "Defense" in log["speaker"]
        )
        return (
            f"DEFENSE SUBMISSIONS SO FAR:\n\n{prior}\n\n"
            f"MOST RECENT DEFENSE SUBMISSION ({focus_label} — focus primarily on this):\n{focus_text}"
        ) if prior else (
            f"DEFENSE SUBMISSION ({focus_label}):\n{focus_text}"
        )

    # ==================================================================
    # PROSECUTOR (YOU) MODE
    # ==================================================================
    if user_role == "prosecutor":

        # ----- Your opening -----
        print("\n" + "=" * 80)
        print("📝 YOUR TURN: Opening Argument (Prosecutor)")
        print("=" * 80)
        your_opening = _read_multiline(
            "[Your Opening Argument]",
            "Present your opening. Build the case, cite sections, explain why bail should be denied."
        )
        if not your_opening:
            print("❌ No opening argument provided. Cannot proceed.")
            return
        debate_log.append({"speaker": "Prosecutor (You)", "type": "opening", "content": your_opening})
        session = orchestrator.get_session(session.session_id)
        session.prosecutor_opening = {"opening_statement": your_opening, "user_written": True}
        orchestrator._save_session(session)
        print("\n✓ Your opening argument recorded.")

        # ----- Defense AI responds to your opening -----
        print("\n" + "=" * 80)
        print("🤖 DEFENSE AI: Opening Response")
        print("=" * 80)
        print("\n[Defense AI is reviewing your argument and building a grounded response...]\n")
        d_opening = orchestrator.build_defense_opening(
            session.session_id,
            prosecution_argument=your_opening
        )
        if not d_opening.get("success"):
            print("❌ Defense AI failed to respond")
            return
        defense_opening_text = d_opening["opening"].get("opening_statement", "")
        print(defense_opening_text)
        debate_log.append({"speaker": "Defense (AI)", "type": "opening_response", "content": defense_opening_text})

        # ----- Rebuttal rounds -----
        max_rebuttals = 2
        for round_num in range(1, max_rebuttals + 1):

            # Your rebuttal
            print("\n" + "=" * 80)
            print(f"📝 YOUR TURN: Rebuttal Round {round_num} (Prosecutor)")
            print("=" * 80)
            print("\n[Defense's last submission]:")
            last_defense = debate_log[-1]["content"]
            print(last_defense[:600] + ("..." if len(last_defense) > 600 else ""))
            print()
            your_rebuttal = _read_multiline(
                f"[Your Rebuttal {round_num}]",
                "Counter the defense's points. Address every live argument. Cite specific evidence."
            )
            if not your_rebuttal:
                print("⏭️  Skipping rebuttal. Moving to closing.")
                break
            debate_log.append({"speaker": "Prosecutor (You)", "type": f"rebuttal_{round_num}", "content": your_rebuttal})
            print("\n✓ Your rebuttal recorded.")

            # Defense AI rebuts — reads your rebuttal AND all prior prosecution submissions
            print("\n" + "=" * 80)
            print(f"🤖 DEFENSE AI: Rebuttal Round {round_num}")
            print("=" * 80)
            print("\n[Defense AI is reviewing all prosecution submissions and preparing a grounded counter...]\n")
            rebuttal_context = _prosecution_context(f"rebuttal {round_num}", your_rebuttal)
            try:
                rebuttal_result = orchestrator._defense_agent.handle_rebuttal(rebuttal_context)
                defense_rebuttal_text = rebuttal_result.get("defense_response", {}).get("rebuttal", "")
                if not defense_rebuttal_text:
                    raise ValueError("empty rebuttal")
            except Exception as _e:
                defense_rebuttal_text = (
                    "Your Honor, the prosecution's submissions do not displace the fundamental "
                    "deficiency in the prima facie case. The statutory ingredients remain unestablished "
                    "on the material before this Court and anticipatory bail ought to be granted."
                )
            print(defense_rebuttal_text)
            debate_log.append({"speaker": "Defense (AI)", "type": f"rebuttal_{round_num}", "content": defense_rebuttal_text})

        # ----- Your closing -----
        print("\n" + "=" * 80)
        print("📝 YOUR TURN: Closing Argument (Prosecutor)")
        print("=" * 80)
        your_closing = _read_multiline(
            "[Your Closing Argument]",
            "Final statement. Reinforce your strongest points and make your prayer to deny bail."
        )
        if your_closing:
            debate_log.append({"speaker": "Prosecutor (You)", "type": "closing", "content": your_closing})
            print("\n✓ Your closing recorded.")

        # ----- Defense AI closing — reads every prosecution submission -----
        print("\n" + "=" * 80)
        print("🤖 DEFENSE AI: Closing Argument")
        print("=" * 80)
        print("\n[Defense AI is reviewing the full proceedings before delivering its closing...]\n")
        closing_context = _prosecution_context(
            "closing — respond with a complete closing argument that addresses the entire proceedings",
            your_closing or "(no closing submitted by prosecution)"
        )
        try:
            closing_result = orchestrator._defense_agent.handle_rebuttal(closing_context)
            defense_closing = closing_result.get("defense_response", {}).get("rebuttal", "")
            if not defense_closing:
                raise ValueError("empty closing")
        except Exception:
            defense_closing = (
                "Your Honor, across these proceedings the prosecution has not established any "
                "statutory ingredient at the prima facie threshold required for anticipatory bail "
                "to be refused. The accused has co-operated fully and no custodial purpose has "
                "been shown. We respectfully pray that anticipatory bail be granted."
            )
        print(defense_closing)
        debate_log.append({"speaker": "Defense (AI)", "type": "closing", "content": defense_closing})

    # ==================================================================
    # DEFENSE (YOU) MODE
    # ==================================================================
    else:

        # ----- Prosecutor AI opens -----
        print("\n" + "=" * 80)
        print("🤖 PROSECUTOR AI: Opening Argument")
        print("=" * 80)
        print("\n[Prosecutor AI is preparing its opening based on the case file...]\n")
        p_opening = orchestrator.build_prosecutor_opening(session.session_id)
        if not p_opening.get("success"):
            print("❌ Prosecutor AI failed to present opening")
            return
        prosecutor_opening_text = p_opening["opening"].get("opening_statement", "")
        print(prosecutor_opening_text)
        debate_log.append({"speaker": "Prosecutor (AI)", "type": "opening", "content": prosecutor_opening_text})

        # ----- You respond -----
        print("\n" + "=" * 80)
        print("📝 YOUR TURN: Opening Response (Defense)")
        print("=" * 80)
        print("\n[Prosecution's opening]:")
        print(prosecutor_opening_text[:600] + ("..." if len(prosecutor_opening_text) > 600 else ""))
        print()
        your_opening = _read_multiline(
            "[Your Opening Response]",
            "Respond to the prosecution's opening. Present your defense, attack the ingredients, argue for bail."
        )
        if not your_opening:
            print("❌ No response provided. Cannot proceed.")
            return
        debate_log.append({"speaker": "Defense (You)", "type": "opening_response", "content": your_opening})
        session = orchestrator.get_session(session.session_id)
        session.defense_opening = {"opening_statement": your_opening, "user_written": True}
        orchestrator._save_session(session)
        print("\n✓ Your response recorded.")

        # ----- Rebuttal rounds -----
        max_rebuttals = 2
        for round_num in range(1, max_rebuttals + 1):

            # Prosecutor AI rebuts — reads your submission AND all prior defense submissions
            print("\n" + "=" * 80)
            print(f"🤖 PROSECUTOR AI: Rebuttal Round {round_num}")
            print("=" * 80)
            print("\n[Prosecutor AI is reviewing all defense submissions and preparing a grounded rebuttal...]\n")
            defense_context_for_p = _defense_context(f"rebuttal {round_num}", debate_log[-1]["content"])
            try:
                p_rebuttal_result = orchestrator._prosecutor_agent.handle_rebuttal(defense_context_for_p)
                prosecution_rebuttal_text = "\n".join(
                    p_rebuttal_result.get("prosecution_response", {}).get("counter_arguments", [])
                )
                if not prosecution_rebuttal_text.strip():
                    raise ValueError("empty prosecution rebuttal")
            except Exception as _pe:
                prosecution_rebuttal_text = (
                    "Your Honor, the defense's submissions do not displace the prima facie case "
                    "established by the prosecution. The statutory ingredients are made out on the "
                    "material on record and the prayer for anticipatory bail ought to be refused."
                )
            print(prosecution_rebuttal_text)
            debate_log.append({"speaker": "Prosecutor (AI)", "type": f"rebuttal_{round_num}", "content": prosecution_rebuttal_text})

            # You rebut
            print("\n" + "=" * 80)
            print(f"📝 YOUR TURN: Rebuttal Round {round_num} (Defense)")
            print("=" * 80)
            print("\n[Prosecution's last submission]:")
            last_p = debate_log[-1]["content"]
            print(last_p[:600] + ("..." if len(last_p) > 600 else ""))
            print()
            your_rebuttal = _read_multiline(
                f"[Your Rebuttal {round_num}]",
                "Counter the prosecution's new points. Address every live argument."
            )
            if not your_rebuttal:
                print("⏭️  Skipping rebuttal. Moving to closing.")
                break
            debate_log.append({"speaker": "Defense (You)", "type": f"rebuttal_{round_num}", "content": your_rebuttal})
            print("\n✓ Your rebuttal recorded.")

        # ----- Prosecutor AI closing — reads every defense submission -----
        print("\n" + "=" * 80)
        print("🤖 PROSECUTOR AI: Closing Argument")
        print("=" * 80)
        print("\n[Prosecutor AI is reviewing the full proceedings before delivering its closing...]\n")
        all_defense_context = _defense_context(
            "closing — respond with a complete closing argument addressing the entire proceedings",
            debate_log[-1]["content"] if debate_log and "Defense" in debate_log[-1]["speaker"] else "(no further defense submissions)"
        )
        try:
            p_close_result = orchestrator._prosecutor_agent.handle_rebuttal(all_defense_context)
            prosecutor_closing_text = "\n".join(
                p_close_result.get("prosecution_response", {}).get("counter_arguments", [])
            )
            if not prosecutor_closing_text.strip():
                raise ValueError("empty")
        except Exception:
            prosecutor_closing_text = (
                "Your Honor, the defense has not successfully displaced the prima facie case "
                "established in these proceedings. The evidence on record amply justifies refusing "
                "anticipatory bail and we respectfully pray that the application be dismissed."
            )
        print(prosecutor_closing_text)
        debate_log.append({"speaker": "Prosecutor (AI)", "type": "closing", "content": prosecutor_closing_text})

        # ----- Your closing -----
        print("\n" + "=" * 80)
        print("📝 YOUR TURN: Closing Argument (Defense)")
        print("=" * 80)
        your_closing = _read_multiline(
            "[Your Closing Argument]",
            "Final statement. Reinforce your strongest grounds and make your final prayer for bail."
        )
        if your_closing:
            debate_log.append({"speaker": "Defense (You)", "type": "closing", "content": your_closing})
            print("\n✓ Your closing recorded.")

    # ========================================================================
    # Save debate log and print summary
    # ========================================================================
    session = orchestrator.get_session(session.session_id)
    session.prosecutor_rebuttal = {"debate_log": [log for log in debate_log if "Prosecutor" in log["speaker"]]}
    session.defense_rebuttal = {"debate_log": [log for log in debate_log if "Defense" in log["speaker"]]}
    orchestrator._save_session(session)

    print("\n" + "=" * 80)
    print("📋 DEBATE SUMMARY")
    print("=" * 80)
    for i, log in enumerate(debate_log, 1):
        preview = log["content"][:200] + ("..." if len(log["content"]) > 200 else "")
        print(f"\n{i}. {log['speaker']} — {log['type'].upper()}")
        print(f"   {preview}")

    print(f"\n✓ Total exchanges : {len(debate_log)}")
    print(f"✓ Your submissions: {len([l for l in debate_log if 'You' in l['speaker']])}")
    print(f"✓ AI submissions  : {len([l for l in debate_log if 'AI' in l['speaker']])}")

    print("\n" + "=" * 80)
    print("SESSION SUMMARY:")
    print("=" * 80)
    summary = orchestrator.get_session_summary(session.session_id)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()