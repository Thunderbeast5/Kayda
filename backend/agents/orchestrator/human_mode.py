"""
Human vs AI Moot Court Mode
============================
Allows law students to play as Prosecutor or Defense against AI opponent.

Flow:
1. Student selects role (Prosecutor / Defense)
2. Evidence & Lexigraph phases run normally
3. In courtroom phase:
   - If student is Prosecutor: student argues first, AI defense responds
   - If student is Defense: AI prosecution argues first, student responds
4. Judge evaluates both arguments with detailed feedback
5. Multi-round debate with AI adapting to student's arguments
"""

from typing import Dict, Any, List, Optional, Callable
import json
import re
from agents.orchestrator.formatting import (
    extract_citations_with_act,
    extract_evidence_references,
    format_argument_markdown,
    link_facts_to_text,
    parse_argument_structure,
)


class HumanArgumentValidator:
    """
    Validates human-submitted arguments for:
    - Grounding in case facts
    - Citation validity
    - Structural completeness
    - No hallucination detection
    """

    def __init__(self, case_facts: List[Any], lexigraph_output: Dict[str, Any], evidence_inventory: List[Any]):
        self.case_facts = case_facts
        self.lexigraph_output = lexigraph_output
        self.evidence_inventory = evidence_inventory
        self.allowed_sections = self._build_allowed_sections()

    def _build_allowed_sections(self) -> set:
        """Build set of allowed statute citations from lexigraph output"""
        allowed = set()
        
        # Add procedural sections (always allowed in anticipatory bail cases)
        procedural = {
            "438", "482", "437", "439", "480", "483",  # Bail
            "167", "187",  # Remand
            "161", "164", "180", "183",  # Statements
            "313", "351",  # Accused statement
            "70", "71", "72", "73",  # Warrants
            "82", "83", "84", "85",  # Proclamation
            "156", "173", "190", "200", "202", "204",  # Investigation
            "172", "174", "174a", "175",  # Absconding offences
            "206", "209", "210",  # BNS equivalents
        }
        
        for sec in procedural:
            allowed.add(sec)
            for act in ["IPC", "BNS", "CRPC", "BNSS", "IEA", "BSA"]:
                allowed.add(f"{act} {sec}".lower())
        
        # Add sections from lexigraph
        for sec in self.lexigraph_output.get("ipc_sections", []):
            if isinstance(sec, dict) and sec.get("section"):
                s = str(sec["section"]).lower().strip()
                allowed.add(s)
                allowed.add(f"ipc {s}")
                allowed.add(f"bns {s}")
        
        # Add sections from verified offences
        for vo in self.lexigraph_output.get("stage4_statutory_verification", {}).get("verified_offences", []):
            s = str(vo.get("section_number", "")).lower().strip()
            if s:
                allowed.add(s)
                act = vo.get("act", "IPC").upper()
                allowed.add(f"{act} {s}".lower())
        
        return allowed

    def validate_argument(
        self,
        argument_text: str,
        role: str  # "prosecutor" or "defense"
    ) -> Dict[str, Any]:
        """
        Validate human argument and return validation result with feedback.
        
        Returns:
        {
            "valid": bool,
            "feedback": str,  # What was good / what needs improvement
            "warnings": List[str],  # Non-fatal issues
            "errors": List[str],  # Fatal issues requiring correction
            "structured": Dict[str, Any]  # Parsed argument structure
        }
        """
        errors = []
        warnings = []
        feedback_parts = []

        # 1. Check minimum length
        if len(argument_text.strip()) < 100:
            errors.append("Argument is too brief. A courtroom submission should be at least 100 characters with specific legal reasoning.")

        # 2. Extract and validate citations
        cited = extract_citations_with_act(argument_text)
        invalid_citations = []
        
        for cit in cited:
            cit_lower = cit.lower().strip()
            # Check if citation is in allowed set
            found = False
            for allowed in self.allowed_sections:
                if cit_lower == allowed or cit_lower.endswith(f" {allowed}"):
                    found = True
                    break
            
            if not found:
                invalid_citations.append(cit)
        
        if invalid_citations:
            errors.append(
                f"The following citations are not grounded in the retrieved legal provisions: {', '.join(invalid_citations)}. "
                f"Only cite sections that appear in the case facts or lexigraph output."
            )
        
        if cited and not invalid_citations:
            feedback_parts.append(f"✓ Good use of legal citations: {', '.join(cited[:3])}")

        # 3. Check evidence references
        evidence_refs = extract_evidence_references(argument_text)
        
        if not evidence_refs:
            # Try to detect fact references in free text
            evidence_refs = link_facts_to_text(argument_text, self.case_facts)
        
        if not evidence_refs:
            warnings.append(
                "No specific evidence references found. "
                "Strong arguments reference specific facts (e.g., [fact_1], [fact_5]) from the case record."
            )
        else:
            feedback_parts.append(f"✓ Good evidence linkage: {len(evidence_refs)} fact references")

        # 4. Check for hallucination red flags
        hallucination_patterns = [
            (r'\b(?:recovered|seized)\s+(?:a|the)\s+\w+(?:\s+\w+){0,3}\s+(?:weapon|gun|knife|pistol)', 
             "weapon recovery"),
            (r'\bMLC\b|\bmedical\s+report\b|\binjury\s+report\b', 
             "medical documentation"),
            (r'\bCCTV\b|\bfootage\b|\bvideo\s+evidence\b', 
             "CCTV/video evidence"),
            (r'\b(?:witness|eyewitness)\s+(?:statement|testimony)\s+of\s+\w+', 
             "specific witness names"),
        ]
        
        for pattern, desc in hallucination_patterns:
            if re.search(pattern, argument_text, re.IGNORECASE):
                # Check if this is actually in the evidence inventory
                inv_text = " ".join([str(e.get("description", "") if isinstance(e, dict) else str(e)) 
                                    for e in self.evidence_inventory])
                
                if not re.search(pattern, inv_text, re.IGNORECASE):
                    warnings.append(
                        f"Potential hallucination: You mention {desc}, but this may not be present in the evidence inventory. "
                        f"If arguing absence, phrase as 'The record does not contain...' rather than asserting facts."
                    )

        # 5. Check role-appropriate arguments
        if role == "defense":
            # Defense should challenge, not assert prosecution facts
            assertive_patterns = [
                r'\bthe\s+accused\s+(?:committed|did|has)\b',
                r'\bguilt\s+is\s+(?:established|proven)\b',
            ]
            for pattern in assertive_patterns:
                if re.search(pattern, argument_text, re.IGNORECASE):
                    warnings.append(
                        "Defense role: Your submission appears to concede guilt. "
                        "Defense should challenge evidence, highlight gaps, and raise reasonable doubt."
                    )
        
        elif role == "prosecutor":
            # Prosecution should establish elements, not presume guilt
            if re.search(r'\bobviously\s+guilty\b|\bclearly\s+committed\b', argument_text, re.IGNORECASE):
                warnings.append(
                    "Prosecution role: Avoid conclusory language. "
                    "Methodically establish each element of the offense with evidence."
                )

        # 6. Check for key anticipatory bail arguments
        if role == "defense":
            defense_elements = {
                "no_prima_facie": r'\bprima\s+facie\b|\bingredients\s+not\s+(?:made\s+out|disclosed)\b',
                "no_custodial_need": r'\bcustodial\s+interrogation\b|\bphysical\s+custody\b|\bnot\s+required\b',
                "no_flight_risk": r'\b(?:not\s+)?(?:abscond|flee|evade)\b|\broots\s+in\s+community\b|\bfixed\s+residence\b',
                "article_21": r'\barticle\s+21\b|\bpersonal\s+liberty\b|\bconstitutional\s+right\b',
            }
            
            found_elements = [key for key, pattern in defense_elements.items() 
                            if re.search(pattern, argument_text, re.IGNORECASE)]
            
            if len(found_elements) >= 2:
                feedback_parts.append(f"✓ Strong defense framework covering: {', '.join(found_elements)}")
            elif len(found_elements) == 1:
                warnings.append(
                    "Consider strengthening your defense by addressing multiple grounds: "
                    "absence of prima facie case, no need for custodial interrogation, no flight risk, "
                    "and Article 21 protection of personal liberty."
                )
        
        elif role == "prosecutor":
            prosecution_elements = {
                "gravity": r'\b(?:gravity|severity|serious)\b.*\b(?:offense|crime)\b',
                "custodial_need": r'\bcustodial\s+(?:interrogation|questioning)\b.*\b(?:necessary|required|essential)\b',
                "flight_risk": r'\b(?:abscond|flee|evade|avoid)\b.*\b(?:summons|arrest|justice)\b',
                "tampering": r'\b(?:tamper|influence|threaten)\b.*\b(?:witness|evidence)\b',
                "investigation": r'\binvestigation\b.*\b(?:nascent|ongoing|incomplete|stage)\b',
            }
            
            found_elements = [key for key, pattern in prosecution_elements.items() 
                            if re.search(pattern, argument_text, re.IGNORECASE)]
            
            if len(found_elements) >= 2:
                feedback_parts.append(f"✓ Strong prosecution framework covering: {', '.join(found_elements)}")
            elif len(found_elements) == 1:
                warnings.append(
                    "Consider strengthening your prosecution by addressing: "
                    "gravity of offense, need for custodial interrogation, flight risk, "
                    "risk of tampering, and incomplete investigation."
                )

        # 7. Structure check
        try:
            # Try to parse as JSON if student used JSON format
            if argument_text.strip().startswith("{"):
                parsed = json.loads(argument_text)
                structured = {
                    "theory": parsed.get("theory", ""),
                    "arguments": parsed.get("arguments", []),
                    "evidence_refs": parsed.get("evidence_refs", evidence_refs),
                    "sections": parsed.get("sections", cited),
                }
                feedback_parts.append("✓ Well-structured JSON format")
            else:
                # Parse free text
                structured = {
                    "theory": argument_text.split('\n')[0][:200],  # First line as theory
                    "arguments": [arg.strip() for arg in argument_text.split('\n\n') if len(arg.strip()) > 50],
                    "evidence_refs": evidence_refs,
                    "sections": cited,
                }
        except json.JSONDecodeError:
            # Fallback: treat as free text
            structured = {
                "theory": argument_text.split('\n')[0][:200],
                "arguments": [argument_text],
                "evidence_refs": evidence_refs,
                "sections": cited,
            }

        # Final validation
        is_valid = len(errors) == 0

        # Compile feedback
        if feedback_parts:
            feedback = "\n".join(feedback_parts)
        else:
            feedback = "Your argument has been submitted."
        
        if warnings:
            feedback += "\n\n⚠️ Suggestions for improvement:\n" + "\n".join(f"• {w}" for w in warnings)
        
        if errors:
            feedback += "\n\n❌ Issues that must be corrected:\n" + "\n".join(f"• {e}" for e in errors)

        return {
            "valid": is_valid,
            "feedback": feedback,
            "warnings": warnings,
            "errors": errors,
            "structured": structured,
            "evidence_refs": evidence_refs,
            "citations": cited,
        }


class HumanMootCourtOrchestrator:
    """
    Orchestrator for human vs AI moot court sessions.
    Manages turn-taking, validation, and AI opponent generation.
    """

    def __init__(
        self,
        student_role: str,  # "prosecutor" or "defense"
        case_facts: List[Any],
        evidence_inventory: List[Any],
        lexigraph_output: Dict[str, Any],
        max_rounds: int = 3,
        on_event: Optional[Callable] = None
    ):
        self.student_role = student_role.lower()
        self.ai_role = "defense" if self.student_role == "prosecutor" else "prosecutor"
        self.case_facts = case_facts
        self.evidence_inventory = evidence_inventory
        self.lexigraph_output = lexigraph_output
        self.max_rounds = max_rounds
        self.on_event = on_event or (lambda x: None)
        
        self.validator = HumanArgumentValidator(case_facts, lexigraph_output, evidence_inventory)
        self.current_round = 0
        self.transcript = []
        
        # Track arguments for AI to respond to
        self.student_arguments_history = []
        self.ai_arguments_history = []

    def emit(self, event_type: str, **kwargs):
        """Emit event to frontend"""
        self.on_event({"type": event_type, **kwargs})

    def start_round(self, round_no: int) -> Dict[str, Any]:
        """
        Start a new round and return instructions for the student.
        """
        self.current_round = round_no
        
        if round_no == 1:
            instruction = self._get_opening_instructions()
        else:
            instruction = self._get_rebuttal_instructions()
        
        self.emit("round_start", round=round_no, instruction=instruction)
        
        return {
            "round": round_no,
            "phase": "awaiting_student_argument",
            "instruction": instruction,
            "student_role": self.student_role,
            "ai_role": self.ai_role,
        }

    def _get_opening_instructions(self) -> str:
        """Get instructions for opening arguments"""
        if self.student_role == "prosecutor":
            return """**Opening Arguments - Prosecution**

You are the Public Prosecutor. Your objective is to oppose the anticipatory bail application by demonstrating:

1. **Gravity of the Offense**: Emphasize the severity and societal impact of the alleged crime
2. **Need for Custodial Interrogation**: Explain why physical custody is necessary for investigation (recovery, digital evidence, conspiracy investigation)
3. **Flight Risk**: Show that the accused may abscond, has been avoiding summons, or has no fixed residence
4. **Risk of Tampering**: Demonstrate potential for witness intimidation or evidence destruction
5. **Criminal Antecedents**: Highlight any past record or pending cases

**Requirements:**
- Cite specific sections from the verified legal provisions (e.g., "CrPC 438", "IPC 174")
- Reference case facts using [fact_1], [fact_2], etc.
- Do NOT invent facts not in the case record
- Build your argument methodically, establishing each element
- Use precedents from the retrieved holdings if applicable

**Format** (you may use prose or JSON):
```
Theory: [Your main legal theory in 1-2 sentences]

Submissions:
1. [First submission with fact references and legal basis]
2. [Second submission]
3. [Third submission]
...
```
"""
        else:  # defense
            return """**Opening Arguments - Defense**

You are the Defense Counsel for the accused seeking anticipatory bail. Your objective is to show:

1. **Absence of Prima Facie Case**: The FIR/complaint does not disclose essential ingredients of the alleged offense
2. **No Need for Custodial Interrogation**: Client is willing to cooperate, submit documents, and answer questions
3. **No Flight Risk**: Client has deep community roots, fixed residence, family responsibilities, and clean record
4. **No Threat to Evidence/Witnesses**: Client will not tamper with evidence or influence witnesses
5. **Protection of Personal Liberty**: Article 21 - unnecessary arrest causes irreparable harm to reputation and livelihood
6. **Malafide Prosecution** (if applicable): Political rivalry, personal grudge, or vexatious complaint

**Requirements:**
- Cite specific sections from the verified legal provisions (e.g., "CrPC 438", "IPC 324")
- Reference case facts using [fact_1], [fact_2], etc.
- Challenge gaps by stating "The record does not contain..." (not by inventing facts)
- Do NOT concede guilt - your role is to raise reasonable doubt
- Use precedents from the retrieved holdings if applicable

**Format** (you may use prose or JSON):
```
Theory: [Your main defense theory in 1-2 sentences]

Submissions:
1. [First submission with fact references and legal basis]
2. [Second submission]
3. [Third submission]
...
```
"""

    def _get_rebuttal_instructions(self) -> str:
        """Get instructions for rebuttal rounds"""
        last_ai_arg = self.ai_arguments_history[-1] if self.ai_arguments_history else ""
        
        return f"""**Round {self.current_round} - Rebuttal**

The opposing counsel has made the following arguments:

---
{last_ai_arg[:1000]}...
---

**Your Task:**
- Directly address and counter the opponent's key points
- Highlight weaknesses in their reasoning
- Introduce new legal grounds or precedents if applicable
- Maintain your core theory while adapting to their arguments
- Continue citing verified sections and case facts

**Remember:**
- Do NOT abandon your original position
- Focus on exposing gaps in their argument
- Use the case record to support your counter-arguments
"""

    def submit_student_argument(self, argument_text: str) -> Dict[str, Any]:
        """
        Process student's argument submission.
        Returns validation result and triggers AI response if valid.
        """
        # Validate argument
        validation = self.validator.validate_argument(argument_text, self.student_role)
        
        self.emit("student_argument_validated", 
                 round=self.current_round,
                 valid=validation["valid"],
                 feedback=validation["feedback"])
        
        if not validation["valid"]:
            return {
                "status": "rejected",
                "validation": validation,
                "message": "Please revise your argument based on the feedback below.",
            }
        
        # Store student argument
        self.student_arguments_history.append(argument_text)
        
        # Format for transcript
        formatted_arg = format_argument_markdown(
            theory=validation["structured"].get("theory", ""),
            arguments=validation["structured"].get("arguments", []),
            evidence_refs=validation["structured"].get("evidence_refs", []),
            sections=validation["structured"].get("citations", []),
            facts_lookup={},
        )
        
        self.transcript.append({
            "round": self.current_round,
            "role": self.student_role,
            "type": "human",
            "content": formatted_arg,
            "citations": validation["citations"],
            "evidence_refs": validation["evidence_refs"],
        })
        
        self.emit("argument_accepted",
                 round=self.current_round,
                 role=self.student_role,
                 content=formatted_arg)
        
        return {
            "status": "accepted",
            "validation": validation,
            "formatted_argument": formatted_arg,
            "next_phase": "ai_generating_response",
        }

    def generate_ai_response(self) -> Dict[str, Any]:
        """
        Generate AI opponent's response to student's argument.
        """
        from agents.defense.defense import DefenseAgent
        from agents.orchestrator.case_file import build_canonical_case_file
        
        self.emit("ai_thinking", role=self.ai_role, round=self.current_round)
        
        # Build context for AI
        canonical_case_file = build_canonical_case_file(
            case_facts=self.case_facts,
            evidence_inventory=self.evidence_inventory,
            lexigraph_output=self.lexigraph_output,
        )
        
        # Get opponent's argument history
        opponent_args = "\n\n---\n\n".join(self.student_arguments_history)
        
        try:
            if self.ai_role == "defense":
                agent = DefenseAgent()
                ai_argument = agent.generate(
                    structured_facts={},
                    lexigraph_result=self.lexigraph_output,
                    prosecution_arguments=opponent_args,
                    evidence_inventory=self.evidence_inventory,
                    case_facts=self.case_facts,
                    canonical_case_file=canonical_case_file,
                )
            else:  # prosecutor
                # Use the ProsecutorAgent from prosecutor module
                from prosecutor.prosecutor_agent import ProsecutorAgent as ProsAgent
                from agents.lexigraph.lexigraph_agent import LexiGraphAgent
                
                # Initialize prosecutor with lexigraph
                lexigraph_agent = LexiGraphAgent()
                pros_agent = ProsAgent(lexigraph_agent=lexigraph_agent)
                
                # Determine phase based on round
                phase = "opening" if self.current_round == 1 else "rebuttal"
                
                # Generate prosecutor turn
                result = pros_agent.generate_turn(
                    case_facts=canonical_case_file,
                    phase=phase,
                    opposing_argument=opponent_args if opponent_args else None,
                    production_output=self.lexigraph_output,
                    canonical_case_file=canonical_case_file,
                )
                
                ai_argument = result.spoken_argument
            
            self.ai_arguments_history.append(ai_argument)
            
            # Extract citations and evidence refs
            citations = extract_citations_with_act(ai_argument)
            evidence_refs = extract_evidence_references(ai_argument)
            
            self.transcript.append({
                "round": self.current_round,
                "role": self.ai_role,
                "type": "ai",
                "content": ai_argument,
                "citations": citations,
                "evidence_refs": evidence_refs,
            })
            
            self.emit("ai_argument_generated",
                     round=self.current_round,
                     role=self.ai_role,
                     content=ai_argument,
                     citations=citations)
            
            return {
                "status": "success",
                "argument": ai_argument,
                "citations": citations,
                "evidence_refs": evidence_refs,
            }
        
        except Exception as e:
            self.emit("error", message=f"AI generation failed: {str(e)}", recoverable=True)
            return {
                "status": "error",
                "message": str(e),
            }

    def get_judge_evaluation(self) -> Dict[str, Any]:
        """
        Get judge's evaluation of both arguments in current round.
        """
        from agents.judge.judge import JudgeAgent
        
        self.emit("judge_evaluating", round=self.current_round)
        
        student_arg = self.transcript[-2]["content"] if len(self.transcript) >= 2 else ""
        ai_arg = self.transcript[-1]["content"] if len(self.transcript) >= 1 else ""
        
        try:
            judge = JudgeAgent()
            
            # Evaluate both arguments
            evaluation = judge.evaluate_round(
                prosecutor_argument=student_arg if self.student_role == "prosecutor" else ai_arg,
                defense_argument=ai_arg if self.student_role == "prosecutor" else student_arg,
                case_facts=self.case_facts,
                lexigraph_output=self.lexigraph_output,
                round_no=self.current_round,
            )
            
            self.emit("judge_scores",
                     round=self.current_round,
                     student_scores=evaluation.get("student_scores", {}),
                     ai_scores=evaluation.get("ai_scores", {}),
                     feedback=evaluation.get("feedback", ""))
            
            return evaluation
        
        except Exception as e:
            self.emit("error", message=f"Judge evaluation failed: {str(e)}", recoverable=True)
            return {"status": "error", "message": str(e)}
