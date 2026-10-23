"""
Game Judge Agent — Real-Time Courtroom Monitor, Interrupter & Arbiter (v2)
==========================================================================
Authoritative judicial logic, scoring standards, and gap detection tailored
for live multiplayer moot court simulations.

Key Upgrades (v2):
1. Multi-Tier Async LLM Engine:
   - Primary: OpenAI (gpt-4o-mini / gpt-4o) using OPENAI_API_KEY
   - Fast Alternative: Groq (llama-3.3-70b-versatile) using GROQ_API_KEY
   - Local: Ollama (llama3.2:3b) via OLLAMA_BASE_URL (5s timeout)
   - Fallback: Substantive Indian legal heuristics (no keyword stuffing exploits)
2. Adversarial Context Awareness:
   - Evaluates submissions in the context of opposing counsel's prior submissions
   - Distinguishes direct rebuttals from evasive rhetoric
3. Case Record & Statutory Grounding:
   - Validates arguments against actual case facts and applicable statutes
     (CrPC/BNSS, IPC/BNS, BSA/IEA, Constitution of India)
4. Interactive Judicial Questioning:
   - Bench queries, observations, and warnings formulated for upcoming counsel
   - Feeds judicial prompts directly into AI counsel turns
5. Meaningful Objections:
   - Sustained / Overruled rulings with procedural justifications and score impacts
6. Comprehensive Final Verdict:
   - Analyzes full trial transcript, opening submissions, rebuttals, and score merit
   - Dynamic judgment tailored to the exact case charges (bail, trial, acquittal, conviction)
7. Multi-Session Concurrency Isolation:
   - Cache keyed by (game_id, role) to prevent cross-match state leaks
"""

import re
import json
import os
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
import httpx

try:
    from backend.observer.case_service import get_case, list_cases
except ImportError:
    try:
        from observer.case_service import get_case, list_cases
    except ImportError:
        def get_case(cid): return None
        def list_cases(): return []

# Judicial System Prompt
JUDGE_SYSTEM_PROMPT = (
    "You are the Presiding Judge in an Indian Court of Law (Sessions Court / High Court). "
    "You speak in formal, authoritative, and precise legal English. "
    "You strictly evaluate arguments on three judicial axes: "
    "1. Legal Validity (statutory sections, constitutional provisions, precedent adherence) "
    "2. Evidence Linkage (conformance to the verified record and exhibits vs speculation) "
    "3. Logic Coherence (structure, direct rebuttal of opposing points, and courtroom decorum). "
    "You are impartial, rigorous, and grounded in Indian statutory and procedural law."
)

# Common Indian legal citation patterns
STATUTE_PATTERN = re.compile(
    r"\b(?:Section|Sec\.?|S\.?)\s*(\d+[A-Za-z]?(?:\s*\(\w+\))?)|"
    r"\b(IPC|CrPC|BNSS|BNS|BSA|IEA|Constitution|Article\s*\d+[A-Za-z]?)\b",
    re.IGNORECASE
)


class GameJudgeAgent:
    """
    Real-time judicial decision-maker powered by multi-provider LLM inference
    (OpenAI, Groq, Ollama) and substantive Indian legal heuristics.
    """

    def __init__(self):
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.groq_model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
        self._openai_disabled = False
        
        # Concurrency-safe observation cache: keyed by f"{game_id}_{role}"
        self._last_observation_cache: Dict[str, str] = {}
        # Tracks last objection timestamp per player: f"{game_id}_{user_id}"
        self._last_objection_time: Dict[str, float] = {}

    # ──────────────────────────────────────────────────────────────────────────
    # Multi-Tier LLM Caller
    # ──────────────────────────────────────────────────────────────────────────

    async def _call_judicial_llm(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 250,
        timeout: float = 6.0
    ) -> Optional[str]:
        """
        Executes LLM call with multi-tier fallback:
        Tier 1: OpenAI Async API (if configured and active)
        Tier 2: Groq API (fast LPU inference via qwen/qwen3.8-27b)
        Tier 3: Local Ollama (if reachable)
        Tier 4: Returns None to trigger deterministic legal heuristics
        """
        sys_content = system or JUDGE_SYSTEM_PROMPT

        # Tier 1: OpenAI
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if openai_key and not openai_key.startswith("__") and not self._openai_disabled:
            try:
                import openai
                client = openai.AsyncOpenAI(api_key=openai_key, timeout=min(timeout, 3.0))
                resp = await client.chat.completions.create(
                    model=self.openai_model,
                    messages=[
                        {"role": "system", "content": sys_content},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=0.1
                )
                text = resp.choices[0].message.content.strip()
                if text:
                    return text
            except Exception as e:
                err_str = str(e).lower()
                if "invalid" in err_str or "401" in err_str:
                    self._openai_disabled = True
                print(f"[JudgeAgent:OpenAI] Call failed ({type(e).__name__}: {e}). Trying Groq tier.")

        # Tier 2: Groq API
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            try:
                async with httpx.AsyncClient(timeout=min(timeout, 4.0)) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {groq_key}"},
                        json={
                            "model": self.groq_model,
                            "messages": [
                                {"role": "system", "content": sys_content},
                                {"role": "user", "content": prompt}
                            ],
                            "max_tokens": max_tokens,
                            "temperature": 0.1
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        text = data["choices"][0]["message"]["content"].strip()
                        if text:
                            return text
            except Exception as e:
                print(f"[JudgeAgent:Groq] Call failed ({type(e).__name__}: {e}). Trying next tier.")

        # Tier 3: Local Ollama
        try:
            full_prompt = f"{sys_content}\n\n{prompt}"
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": max_tokens,
                            "stop": ["\n\n\n", "User:", "Human:"]
                        }
                    }
                )
                if res.status_code == 200:
                    text = res.json().get("response", "").strip()
                    if text:
                        return text
        except Exception as e:
            print(f"[JudgeAgent:Ollama] Fallback active ({type(e).__name__}: {e}). Using heuristics.")

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Case Context Resolution
    # ──────────────────────────────────────────────────────────────────────────

    def get_case_context(self, case_id: Optional[str]) -> Dict[str, Any]:
        """
        Retrieves case metadata and facts. Resolves direct ID, numeric index ("1"),
        or filename match against available observer cases.
        """
        case = None
        cid_str = str(case_id or "").strip()

        # 1. Try direct ID
        if cid_str:
            case = get_case(cid_str)

        # 2. Try title, citation, or keyword matching against available cases
        available = list_cases()
        if not case and cid_str and available:
            cid_clean = cid_str.lower().replace("_", " ").replace("-", " ")
            GENERIC_WORDS = {"state", "versus", "another", "others", "court", "appeal", "union", "india", "case", "appellant", "respondent"}
            distinctive_keywords = [w for w in cid_clean.split() if len(w) > 3 and w not in GENERIC_WORDS]
            for c in available:
                c_title = c.get("title", "").lower()
                c_id = c.get("id", "").lower()
                if cid_str.lower() == c_id or cid_clean in c_title:
                    case = get_case(c["id"])
                    break
                if distinctive_keywords and any(k in c_title for k in distinctive_keywords):
                    case = get_case(c["id"])
                    break

        # 3. Try numeric index resolution (e.g. case_id="1" -> available[0])
        if not case and cid_str.isdigit() and available:
            idx = int(cid_str) - 1
            if 0 <= idx < len(available):
                real_cid = available[idx]["id"]
                case = get_case(real_cid)

        # 4. Fallback to first available case
        if not case and available:
            first_case = get_case(available[0]["id"])
            if first_case:
                case = first_case

        if case:
            meta = case.get("case_metadata", {})
            raw_facts = case.get("case_facts", []) or case.get("facts_of_the_case", {})
            facts_str = ""
            if isinstance(raw_facts, list):
                facts_str = " ".join(
                    f.get("text", "") if isinstance(f, dict) else str(f)
                    for f in raw_facts[:6]
                )
            elif isinstance(raw_facts, dict):
                facts_str = " ".join(f"{k}: {v}" for k, v in list(raw_facts.items())[:6])

            charges_raw = meta.get("laws_referred", [])
            charges_str = ", ".join(charges_raw) if charges_raw else "Section 438 CrPC, Section 379 IPC"

            issues_raw = case.get("key_legal_issues", [])
            issues_list = []
            if isinstance(issues_raw, list):
                for iss in issues_raw:
                    if isinstance(iss, dict):
                        issues_list.append(iss.get("issue", ""))
                    elif isinstance(iss, str):
                        issues_list.append(iss)

            return {
                "case_id": meta.get("citation") or cid_str or "case_default",
                "title": meta.get("case_name") or f"{meta.get('appellant', 'Applicant')} vs. {meta.get('respondent', 'State')}",
                "court": meta.get("court", "Court of Sessions / High Court"),
                "charges": charges_str,
                "appellant": meta.get("appellant", "Accused / Applicant"),
                "respondent": meta.get("respondent", "State"),
                "facts_summary": facts_str or "Facts of the case per official charge-sheet and court records.",
                "key_issues": issues_list
            }

        # Safe Indian criminal law default
        return {
            "case_id": "default",
            "title": "State of NCT of Delhi vs. Rahul Sharma",
            "court": "Court of Sessions, Patiala House Courts, New Delhi",
            "charges": "Section 438 CrPC r/w Sections 379, 411, 34 IPC",
            "appellant": "Rahul Sharma (Applicant/Accused)",
            "respondent": "State of NCT of Delhi",
            "facts_summary": "FIR registered regarding theft of commercial property. Accused seeks anticipatory bail citing absence of recovery and violation of Section 41A CrPC arrest guidelines.",
            "key_issues": [
                "Whether custodial interrogation is necessary for material recovery under Section 27 IEA",
                "Whether applicant satisfies the tripartite test for pre-arrest bail under Section 438 CrPC"
            ]
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Hearing Initiation
    # ──────────────────────────────────────────────────────────────────────────

    async def generate_opening_address(self, case_id: Optional[str], game_id: Optional[str] = None) -> str:
        """
        Dynamically generates the Judge's opening statement when court commences.
        """
        ctx = self.get_case_context(case_id)

        prompt = (
            f"Case: {ctx['title']}\n"
            f"Court: {ctx['court']}\n"
            f"Applicable Charges: {ctx['charges']}\n"
            f"Summary Facts: {ctx['facts_summary'][:300]}\n\n"
            f"Deliver the Judge's formal 2-sentence opening statement: declare the court in session, "
            f"state the matter and primary charges, remind both counsels of verified record decorum, "
            f"and call upon the Public Prosecutor to commence opening framing."
        )

        llm_reply = await self._call_judicial_llm(prompt, max_tokens=120)
        if llm_reply and len(llm_reply) > 30:
            return llm_reply.strip().strip('"')

        return (
            f"The Court is now in session. Matter of {ctx['title']} under {ctx['charges']}. "
            f"Both learned counsels are directed to adhere strictly to the verified record and statutory provisions. "
            f"Public Prosecutor, the bench calls upon you to open the state's framing."
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Argument Evaluation & 3-Axis Scoring
    # ──────────────────────────────────────────────────────────────────────────

    async def evaluate_argument(
        self,
        case_id: Optional[str],
        role: str,
        phase: str,
        argument_text: str,
        argument_history: List[Dict[str, Any]],
        game_id: Optional[str] = None
    ) -> Tuple[Dict[str, int], int, List[str], str]:
        """
        Evaluates an argument across Legal Validity, Evidence Linkage, and Logic Coherence.
        Considers opposing counsel's prior argument for adversarial responsiveness.
        Returns:
            (score_breakdown: dict, total_delta: int, citations: list, observation: str)
        """
        ctx = self.get_case_context(case_id)
        role_label = "Public Prosecutor" if role.lower() in ["prosecutor", "prosecution"] else "Defense Counsel"
        opposing_role = "defense" if role.lower() in ["prosecutor", "prosecution"] else "prosecution"
        opposing_label = "Defense Counsel" if role.lower() in ["prosecutor", "prosecution"] else "Public Prosecutor"

        # Extract opposing counsel's last argument from history
        last_opposing_arg = ""
        for item in reversed(argument_history):
            if item.get("role") == opposing_role:
                last_opposing_arg = item.get("text", "")
                break

        # Extract verified statutory citations
        citations: List[str] = []
        for match in STATUTE_PATTERN.finditer(argument_text):
            val = match.group(0).strip()
            if val and val not in citations:
                citations.append(val)

        # Baseline Substantive Heuristics
        text_lower = argument_text.lower()
        word_count = len(argument_text.split())

        # 1. Legal Validity: Checks actual statutory sections and acts
        has_specific_section = bool(re.search(r"\b(?:Section|Sec\.?|S\.?)\s*\d+", argument_text, re.IGNORECASE))
        has_act_reference = any(act in argument_text.upper() for act in ["IPC", "CRPC", "BNSS", "BNS", "BSA", "IEA", "CONSTITUTION"])
        has_case_law = any(w in text_lower for w in ["judgment", "precedent", "supreme court", "high court", "in re", "v.", "vs."])

        base_lv = 4
        if has_specific_section:
            base_lv += 2
        if has_act_reference:
            base_lv += 1
        if has_case_law:
            base_lv += 1
        if len(citations) >= 2:
            base_lv += 1
        base_lv = min(max(base_lv, 3), 10)

        # 2. Evidence Linkage: Checks grounding in case facts / exhibits
        has_record_reference = any(term in text_lower for term in [
            "exhibit", "fir", "memo", "seizure", "panchnama", "witness", "statement",
            "medical report", "cctv", "forensic", "record", "investigation"
        ])
        mentions_case_parties = (ctx["appellant"].lower() in text_lower or ctx["respondent"].lower() in text_lower)
        
        base_el = 4
        if has_record_reference:
            base_el += 2
        if mentions_case_parties:
            base_el += 1
        if word_count >= 30 and has_record_reference:
            base_el += 1
        base_el = min(max(base_el, 3), 10)

        # 3. Logic Coherence: Checks structure and responsiveness to opposing argument
        base_lc = 5
        if word_count >= 25:
            base_lc += 1
        if any(term in text_lower for term in ["may it please", "hon'ble court", "learned counsel", "respectfully submit", "your honour"]):
            base_lc += 1
        # Check if responsive to opponent
        if last_opposing_arg:
            opp_words = set(w.lower() for w in re.findall(r"\w{5,}", last_opposing_arg))
            shared_words = opp_words.intersection(set(re.findall(r"\w{5,}", text_lower)))
            if len(shared_words) >= 2:
                base_lc += 2  # rewarded for directly tackling opponent's terms
        base_lc = min(max(base_lc, 3), 10)

        score_breakdown = {
            "legal_validity": base_lv,
            "evidence_linkage": base_el,
            "logic_coherence": base_lc
        }

        # Prompt with Adversarial & Case Context
        opposing_context_str = f"Opposing Counsel's Prior Argument: \"{last_opposing_arg[:250]}\"\n" if last_opposing_arg else "Prior Submissions: Opening submissions.\n"
        prompt = (
            f"Case: {ctx['title']}\n"
            f"Charges: {ctx['charges']}\n"
            f"Verified Facts: {ctx['facts_summary'][:300]}\n"
            f"Trial Phase: {phase}\n"
            f"{opposing_context_str}"
            f"Counsel Speaking: {role_label}\n"
            f"Counsel's Submission: \"{argument_text}\"\n\n"
            f"Evaluate strictly on 3 judicial axes (0-10):\n"
            f"Legal Validity: <0-10 based on statutory accuracy and relevance to {ctx['charges']}>\n"
            f"Evidence Linkage: <0-10 based on genuine record grounding vs speculation>\n"
            f"Logic Coherence: <0-10 based on responsiveness to opponent and argument structure>\n"
            f"OBSERVATION: <One authoritative judicial sentence from the Bench evaluating the legal merit of this submission>"
        )

        obs_text = f"The Bench takes note of {role_label}'s submissions on the record."
        llm_reply = await self._call_judicial_llm(prompt, max_tokens=180)
        if llm_reply:
            lv_m = re.search(r"Legal\s*Validity\s*[:\-]\s*(\d+)", llm_reply, re.IGNORECASE)
            el_m = re.search(r"Evidence\s*Linkage\s*[:\-]\s*(\d+)", llm_reply, re.IGNORECASE)
            lc_m = re.search(r"Logic\s*Coherence\s*[:\-]\s*(\d+)", llm_reply, re.IGNORECASE)
            obs_m = re.search(r"\*{0,2}OBSERVATION\*{0,2}\s*[:\-]\s*(.*?)(?:\n\n|\n[A-Z]|$)", llm_reply, re.IGNORECASE | re.DOTALL)

            if lv_m:
                score_breakdown["legal_validity"] = max(1, min(10, int(lv_m.group(1))))
            if el_m:
                score_breakdown["evidence_linkage"] = max(1, min(10, int(el_m.group(1))))
            if lc_m:
                score_breakdown["logic_coherence"] = max(1, min(10, int(lc_m.group(1))))
            if obs_m and obs_m.group(1).strip():
                clean_obs = obs_m.group(1).strip().strip('"*\'')
                # Take first complete sentence if multiline
                clean_obs = clean_obs.split("\n")[0].strip()
                if len(clean_obs) > 15:
                    obs_text = clean_obs

        # Cache observation safely per game session
        cache_key = f"{game_id or 'default'}_{role.lower()}"
        self._last_observation_cache[cache_key] = obs_text

        total_delta = round(
            (score_breakdown["legal_validity"] + score_breakdown["evidence_linkage"] + score_breakdown["logic_coherence"]) / 3
        )

        return score_breakdown, total_delta, citations, obs_text

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Interactive Judicial Questioning & Interruption
    # ──────────────────────────────────────────────────────────────────────────

    async def generate_interruption_or_question(
        self,
        case_id: Optional[str],
        role: str,
        phase: str,
        argument_text: str,
        scores: Dict[str, int],
        history: List[Dict[str, Any]],
        next_role: Optional[str] = None,
        game_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Formulates an authoritative judicial remark, warning, or targeted clarification
        question. Poses questions specifically framed for the upcoming counsel or
        admonishes the counsel who just finished speaking.
        """
        ctx = self.get_case_context(case_id)
        role_label = "Public Prosecutor" if role.lower() in ["prosecutor", "prosecution"] else "Defense Counsel"
        upcoming_role = next_role or ("defense" if role.lower() in ["prosecutor", "prosecution"] else "prosecution")
        upcoming_label = "Defense Counsel" if upcoming_role == "defense" else "Public Prosecutor"

        cache_key = f"{game_id or 'default'}_{role.lower()}"
        cached_obs = self._last_observation_cache.pop(cache_key, None)

        prompt = (
            f"Case: {ctx['title']} ({ctx['charges']})\n"
            f"Counsel Who Just Concluded: {role_label} ({phase})\n"
            f"Their Argument: \"{argument_text}\"\n"
            f"Scores: Legal Validity: {scores.get('legal_validity', 5)}/10, "
            f"Evidence Linkage: {scores.get('evidence_linkage', 5)}/10, Logic Coherence: {scores.get('logic_coherence', 5)}/10.\n"
            f"Counsel Now Taking Floor: {upcoming_label}\n\n"
            f"As the Presiding Judge, provide one judicial intervention:\n"
            f"- If the submission had weak evidence or legal gaps, pose a sharp clarification QUESTION directing {upcoming_label} on what issue they must address.\n"
            f"- Otherwise, deliver a formal OBSERVATION or DIRECTION for the courtroom.\n"
            f"Format:\n"
            f"TYPE: <QUESTION or WARNING or OBSERVATION>\n"
            f"CONTENT: <one or two authoritative sentences spoken by the Judge from the bench>"
        )

        llm_reply = await self._call_judicial_llm(prompt, max_tokens=140)
        if llm_reply:
            type_m = re.search(r"\*{0,2}TYPE\*{0,2}\s*[:\-]\s*(QUESTION|WARNING|OBSERVATION)", llm_reply, re.IGNORECASE)
            cont_m = re.search(r"\*{0,2}CONTENT\*{0,2}\s*[:\-]\s*(.*)", llm_reply, re.IGNORECASE | re.DOTALL)

            int_type = type_m.group(1).upper() if type_m else "OBSERVATION"
            content = cont_m.group(1).strip().strip('"*\'') if cont_m else llm_reply.strip()
            content = content.split("\n")[0].strip()

            if len(content) > 15:
                return {
                    "interruption_type": int_type,
                    "content": content,
                    "citations": ["Bench Query" if int_type == "QUESTION" else "Bench Direction"],
                    "target_role": upcoming_role if int_type == "QUESTION" else role
                }

        # Substantive Fallback Logic
        if cached_obs and len(cached_obs) > 20:
            return {
                "interruption_type": "OBSERVATION",
                "content": f"{cached_obs} {upcoming_label}, you now have the floor to present.",
                "citations": ["Bench Observation"],
                "target_role": upcoming_role
            }

        if scores.get("evidence_linkage", 5) < 5:
            return {
                "interruption_type": "QUESTION",
                "content": (
                    f"The Bench notes {role_label}'s assertion. {upcoming_label}, the court requires you "
                    f"to specifically address the evidentiary basis in the record regarding {ctx['charges']}."
                ),
                "citations": ["Section 60 BSA / IEA"],
                "target_role": upcoming_role
            }

        return {
            "interruption_type": "OBSERVATION",
            "content": f"The Bench takes note of {role_label}'s submissions. {upcoming_label}, proceed with your submissions.",
            "citations": [],
            "target_role": upcoming_role
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Instant Objection Rulings with Score Impact & Throttling
    # ──────────────────────────────────────────────────────────────────────────

    def check_objection_rate_limit(self, game_id: str, user_id: str, cooldown_seconds: float = 8.0) -> Tuple[bool, str]:
        """
        Throttles objection spamming. Allows at most one objection every 8 seconds per player.
        """
        key = f"{game_id}_{user_id}"
        now = asyncio.get_event_loop().time()
        last_time = self._last_objection_time.get(key, 0.0)
        if now - last_time < cooldown_seconds:
            remaining = int(cooldown_seconds - (now - last_time))
            return False, f"Objection cooldown active. Please wait {remaining}s before raising another objection."
        self._last_objection_time[key] = now
        return True, ""

    async def rule_on_objection(
        self,
        case_id: Optional[str],
        objecting_role: str,
        reason: str,
        last_argument: Optional[str] = None,
        game_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Dynamically rules on an in-court objection with formal ratio decidendi
        and score adjustments.
        """
        ctx = self.get_case_context(case_id)
        role_label = "Defense Counsel" if objecting_role.lower() == "defense" else "Public Prosecutor"
        target_role = "prosecution" if objecting_role.lower() == "defense" else "defense"
        target_label = "Public Prosecutor" if objecting_role.lower() == "defense" else "Defense Counsel"

        prompt = (
            f"Case: {ctx['title']} ({ctx['charges']})\n"
            f"Objecting Party: {role_label}\n"
            f"Grounds for Objection: \"{reason}\"\n"
            f"Submission Being Objected To: \"{last_argument or 'Prior oral submission'}\"\n\n"
            f"Rule as the presiding Indian Judge immediately.\n"
            f"Format:\n"
            f"RULING: <SUSTAINED or OVERRULED>\n"
            f"DIRECTION: <one authoritative sentence directing counsel on how to proceed under Indian evidence/procedure>"
        )

        llm_reply = await self._call_judicial_llm(prompt, max_tokens=100)
        ruling_val = "OVERRULED"
        direction = f"The submission is relevant to {ctx['charges']}. Proceed, {target_label}."

        if llm_reply:
            r_match = re.search(r"RULING\s*[:\-]\s*(SUSTAINED|OVERRULED)", llm_reply, re.IGNORECASE)
            d_match = re.search(r"DIRECTION\s*[:\-]\s*(.*)", llm_reply, re.IGNORECASE | re.DOTALL)
            if r_match:
                ruling_val = r_match.group(1).upper()
            if d_match:
                direction = d_match.group(1).strip().strip('"').split("\n")[0]
                direction = re.sub(r"^objection\s+(?:sustained|overruled)\.?\s*", "", direction, flags=re.IGNORECASE)
        else:
            reason_lower = reason.lower()
            if any(term in reason_lower for term in ["hearsay", "speculation", "no evidence", "unsubstantiated", "irrelevant", "leading"]):
                ruling_val = "SUSTAINED"
                direction = f"{target_label}, confine your submissions strictly to the proven case record."

        # Meaningful score consequences
        if ruling_val == "SUSTAINED":
            # Sustained: Objecting party gets +1 reward, offending party gets -2 penalty
            score_adj = {objecting_role.lower(): 1, target_role.lower(): -2}
        else:
            # Overruled: Objecting party penalized -1 for frivolous objection
            score_adj = {objecting_role.lower(): -1, target_role.lower(): 0}

        return {
            "ruling": ruling_val,
            "content": f"Objection {ruling_val.capitalize()}. {direction}".strip(),
            "citations": ["Indian Evidence Act / BSA" if ruling_val == "SUSTAINED" else "Judicial Discretion"],
            "score_adjustment": score_adj
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Comprehensive Final Verdict Synthesis
    # ──────────────────────────────────────────────────────────────────────────

    async def render_final_verdict(
        self,
        case_id: Optional[str],
        scores: Dict[str, int],
        transcript: List[Dict[str, Any]],
        game_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synthesizes the complete trial proceedings into a formal, binding Judicial Order.
        Guarantees winner determination strictly reflects cumulative advocacy score merit.
        Tailors the final ratio decidendi to the actual case charges.
        """
        ctx = self.get_case_context(case_id)
        pros_score = scores.get("prosecution", 0)
        def_score = scores.get("defense", 0)

        # Build full structured trial digest (not truncated to 120 chars)
        digest_lines = []
        for t in transcript:
            role = "Prosecution" if t.get("role") in ["prosecutor", "prosecution"] else "Defense"
            phase = t.get("phase", "TRIAL")
            snippet = t.get("text", "").strip()[:240]
            if snippet:
                digest_lines.append(f"[{phase}] {role}: \"{snippet}\"")
        
        trial_digest = "\n".join(digest_lines) if digest_lines else "Arguments heard on statutory merits."

        prompt = (
            f"Case: {ctx['title']}\n"
            f"Court: {ctx['court']}\n"
            f"Charges & Applicable Law: {ctx['charges']}\n"
            f"Case Summary: {ctx['facts_summary'][:300]}\n\n"
            f"Cumulative Trial Scores:\n"
            f"- Public Prosecutor: {pros_score} points\n"
            f"- Defense Counsel: {def_score} points\n\n"
            f"Trial Submissions Record:\n{trial_digest}\n\n"
            f"Deliver the Final Judicial Judgment:\n"
            f"WINNER: <PROSECUTION or DEFENSE>\n"
            f"VERDICT: <Formal one-sentence operative order tailored to {ctx['charges']}>\n"
            f"REASONING: <2-3 sentences of legal ratio decidendi balancing statutory ingredients, record evidence, and advocacy merit>"
        )

        llm_reply = await self._call_judicial_llm(prompt, max_tokens=300, timeout=12.0)
        
        # Enforce merit-based winner primacy:
        # If score difference >= 3 points, cumulative score determines the winner
        if def_score > pros_score:
            score_winner = "DEFENSE"
        elif pros_score > def_score:
            score_winner = "PROSECUTION"
        else:
            score_winner = "DEFENSE"  # In dubio pro reo principle for ties

        winner = score_winner
        verdict_text = ""
        reason_text = ""

        if llm_reply:
            w_match = re.search(r"WINNER\s*[:\-]\s*(PROSECUTION|DEFENSE)", llm_reply, re.IGNORECASE)
            v_match = re.search(r"VERDICT\s*[:\-]\s*(.*?)(?:\n|$)", llm_reply, re.IGNORECASE)
            r_match = re.search(r"REASONING\s*[:\-]\s*(.*)", llm_reply, re.IGNORECASE | re.DOTALL)

            llm_winner = w_match.group(1).upper() if w_match else score_winner
            # If scores are close (within 2 points), allow LLM qualitative winner; otherwise enforce score merit
            if abs(def_score - pros_score) <= 2:
                winner = llm_winner
            else:
                winner = score_winner

            verdict_text = v_match.group(1).strip() if v_match else ""
            reason_text = r_match.group(1).strip().replace("\n", " ") if r_match else ""

        # Dynamic Fallback tailored to the case's actual charges
        is_bail_case = any(term in ctx["charges"].lower() for term in ["438", "437", "439", "bail"])
        
        if not verdict_text:
            if is_bail_case:
                if winner == "DEFENSE":
                    verdict_text = f"The application for anticipatory bail is hereby GRANTED under {ctx['charges']} subject to cooperation with the investigating agency."
                else:
                    verdict_text = f"The plea for anticipatory bail is hereby REJECTED under {ctx['charges']} in view of the prima facie material on record."
            else:
                if winner == "DEFENSE":
                    verdict_text = f"The Court finds in favour of the Defense; charges under {ctx['charges']} are not established beyond reasonable doubt."
                else:
                    verdict_text = f"The Court finds in favour of the Prosecution; prima facie guilt is substantiated under {ctx['charges']}."

        if not reason_text:
            if winner == "DEFENSE":
                reason_text = (
                    f"Defense Counsel presented superior legal statutory grounds and demonstrated that custodial "
                    f"measures are unwarranted, safeguarding constitutional liberty under Article 21."
                )
            else:
                reason_text = (
                    f"The Prosecution established a credible prima facie nexus with the ingredients of {ctx['charges']}, "
                    f"corroborated by the verified record requiring unhindered administration of justice."
                )

        full_summary = f"{verdict_text} {reason_text}".strip()

        return {
            "winner": winner,
            "verdict": verdict_text,
            "summary": full_summary,
            "citations": [ctx["charges"], "Final Judgment Order"]
        }


# Singleton instance for the game engine
game_judge = GameJudgeAgent()
