"""
Bail Reasoning Agent for Stage 5: Anticipatory Bail Reasoning Engine.
Evaluates whether anticipatory bail should be granted or denied under Section 438 CrPC / Section 482 BNSS
by applying judicial bail reasoning principles to verified outputs from previous stages.
Statically injects exact statutory text and factors of Section 438 CrPC / Section 482 BNSS based on regime.
Model: gpt-4.1-mini (MODEL_STAGE5) — deep judicial reasoning.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from .config import extract_json_from_text, get_llm, MODEL_STAGE5
from .prompts import STAGE5_BAIL_REASONING_SYSTEM_PROMPT, STAGE5_BAIL_REASONING_USER_PROMPT_TEMPLATE
from .schemas import BailReasoningObject, CaseContextObject, LegalQueryObject, SideArgumentPackage, StatutoryVerificationObject


PROCEDURAL_BAIL_PROVISIONS: Dict[str, Dict[str, Any]] = {
    "Section 438 CrPC": {
        "provision_name": "Section 438, Code of Criminal Procedure, 1973",
        "title": "Direction for grant of bail to person apprehending arrest",
        "legal_regime": "IPC + CrPC",
        "full_statutory_text": "When any person has reason to believe that he may be arrested on an accusation of having committed a non-bailable offence, he may apply to the High Court or the Court of Session for a direction under this section; and that Court may, if it thinks fit, direct that in the event of such arrest, he shall be released on bail.",
        "statutory_factors": [
            "(i) the nature and gravity of the accusation;",
            "(ii) the antecedents of the applicant including the fact as to whether he has previously undergone imprisonment on conviction in respect of any cognizable offence;",
            "(iii) the possibility of the applicant to flee from justice; and",
            "(iv) where the accusation has been made with the object of injuring or humiliating the applicant by having him so arrested."
        ]
    },
    "Section 482 BNSS": {
        "provision_name": "Section 482, Bharatiya Nagarik Suraksha Sanhita, 2023",
        "title": "Direction for grant of bail to person apprehending arrest",
        "legal_regime": "BNS + BNSS",
        "full_statutory_text": "When any person has reason to believe that he may be arrested on an accusation of having committed a non-bailable offence, he may apply to the High Court or the Court of Session for a direction under this section that in the event of such arrest he shall be released on bail; and that Court may, after taking into consideration, inter alia, the statutory factors: (i) nature and gravity of accusation; (ii) antecedents of applicant; (iii) flight risk; (iv) object of accusation to humiliate applicant.",
        "statutory_factors": [
            "(i) the nature and gravity of the accusation;",
            "(ii) the antecedents of the applicant including previous imprisonment on conviction;",
            "(iii) the possibility of the applicant to flee from justice; and",
            "(iv) whether accusation is made with object of injuring or humiliating applicant."
        ]
    }
}


class BailReasoningAgent:
    """
    Stage 5 Bail Reasoning Agent evaluating anticipatory bail under Sec 438 CrPC / Sec 482 BNSS.
    Injects full statutory text and statutory factors of procedural bail provisions.
    Model: gpt-4.1-mini (MODEL_STAGE5) — deep judicial reasoning.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        min_confidence_threshold: float = 0.70,
    ):
        self._llm = llm
        self.min_confidence_threshold = min_confidence_threshold

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.1, model_name=MODEL_STAGE5)
        return self._llm

    def run(
        self,
        case_context: Union[CaseContextObject, Dict[str, Any], str],
        legal_query: Union[LegalQueryObject, Dict[str, Any], str],
        statutory_object: Union[StatutoryVerificationObject, Dict[str, Any], str],
        side: Optional[str] = "BOTH",
        correction_feedback: Optional[str] = None,
    ) -> BailReasoningObject:
        """
        Runs Stage 5 Bail Reasoning on CaseContextObject, LegalQueryObject, and StatutoryVerificationObject.

        Args:
            case_context: Verified CaseContextObject from Stage 0.
            legal_query: Verified LegalQueryObject from Stage 1.
            statutory_object: Verified StatutoryVerificationObject from Stage 4.
            side: Target role side ('PROSECUTION', 'DEFENSE', or 'BOTH').
            correction_feedback: Feedback from BailReasoningVerifierAgent if retrying.

        Returns:
            BailReasoningObject instance containing side-specific argument packages.
        """
        # Standardize inputs
        if isinstance(case_context, CaseContextObject):
            cco_json_str = case_context.to_downstream_json()
            regime = getattr(case_context, "legal_regime", "IPC + CrPC")
        elif isinstance(case_context, dict):
            cco_json_str = json.dumps(case_context, indent=2)
            regime = case_context.get("legal_regime") or case_context.get("case_profile", {}).get("legal_regime") or "IPC + CrPC"
        else:
            cco_json_str = str(case_context)
            try:
                parsed = json.loads(str(case_context))
                regime = parsed.get("legal_regime") or parsed.get("case_profile", {}).get("legal_regime") or "IPC + CrPC"
            except Exception:
                regime = "IPC + CrPC"

        if isinstance(legal_query, LegalQueryObject):
            qo_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            qo_json_str = json.dumps(legal_query, indent=2)
        else:
            qo_json_str = str(legal_query)

        if isinstance(statutory_object, StatutoryVerificationObject):
            svo_json_str = statutory_object.to_downstream_json()
        elif isinstance(statutory_object, dict):
            svo_json_str = json.dumps(statutory_object, indent=2)
        else:
            svo_json_str = str(statutory_object)

        # Determine statutory bail provision
        legal_regime_clean = regime or "IPC + CrPC"
        if "UNKNOWN" in legal_regime_clean.upper():
            bail_provision = "Section 438 CrPC / Section 482 BNSS"
        elif "BNS" in legal_regime_clean.upper():
            bail_provision = "Section 482 BNSS"
        else:
            bail_provision = "Section 438 CrPC"

        # Retrieve full statutory text & factors for procedural bail provision
        if bail_provision == "Section 438 CrPC / Section 482 BNSS":
            p1 = PROCEDURAL_BAIL_PROVISIONS["Section 438 CrPC"]
            p2 = PROCEDURAL_BAIL_PROVISIONS["Section 482 BNSS"]
            statutory_text_fmt = (
                f"DUAL REGIME BAIL PROVISIONS (Regime Unresolved):\n"
                f"1. {p1['provision_name']}: {p1['full_statutory_text']}\n"
                f"2. {p2['provision_name']}: {p2['full_statutory_text']}\n"
                f"Statutory Factors: " + "; ".join(p1["statutory_factors"])
            )
        else:
            prov_record = PROCEDURAL_BAIL_PROVISIONS.get(bail_provision, PROCEDURAL_BAIL_PROVISIONS["Section 438 CrPC"])
            statutory_text_fmt = f"Provision: {prov_record['provision_name']}\nTitle: {prov_record['title']}\nStatutory Text: {prov_record['full_statutory_text']}\nStatutory Factors: " + "; ".join(prov_record["statutory_factors"])

        feedback_section = ""
        if correction_feedback:
            feedback_section = f"\nATTENTION - PREVIOUS BAIL REASONING VERIFICATION FEEDBACK:\n{correction_feedback}\n"

        user_prompt = STAGE5_BAIL_REASONING_USER_PROMPT_TEMPLATE.format(
            case_context_json=cco_json_str,
            legal_query_json=qo_json_str,
            statutory_object_json=svo_json_str,
            bail_provision=bail_provision,
            legal_regime=legal_regime_clean,
            bail_provision_statutory_text=statutory_text_fmt,
            correction_feedback_section=feedback_section,
        )

        messages = [
            SystemMessage(content=STAGE5_BAIL_REASONING_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        extracted_dict = extract_json_from_text(response_text)

        # Validate with BailReasoningObject Pydantic schema
        bail_obj = BailReasoningObject.model_validate(extracted_dict)

        # Enforce exact passthrough fields
        target_side_clean = (side or "BOTH").strip().upper()
        bail_obj.target_side = target_side_clean
        bail_obj.bail_provision_applied = bail_provision
        bail_obj.legal_regime = legal_regime_clean

        if "UNKNOWN" in legal_regime_clean.upper():
            note = f"UNKNOWN legal regime: defaulted to dual provision '{bail_provision}'; verify offence date to determine whether CrPC S.438 or BNSS S.482 applies."
            if note not in bail_obj.manual_review:
                bail_obj.manual_review.append(note)

        # Ensure SideArgumentPackage for Prosecution (advocating BAIL REJECTION)
        if not bail_obj.prosecution_arguments:
            pros_factors = []
            pros_points = []
            if bail_obj.bail_evaluation.gravity_of_offence.value in ["High", "Severe", "Required"]:
                pros_factors.append("Gravity of Offence")
                pros_points.append(f"Gravity of offence is severe: {bail_obj.bail_evaluation.gravity_of_offence.reason or 'Serious allegation.'}")
            if bail_obj.bail_evaluation.custodial_interrogation.value in ["Required", "High"]:
                pros_factors.append("Custodial Interrogation")
                pros_points.append(f"Custodial interrogation is necessary for investigation and recovery: {bail_obj.bail_evaluation.custodial_interrogation.reason or 'Recovery required.'}")
            if bail_obj.bail_evaluation.witness_tampering.value in ["High", "Medium"]:
                pros_factors.append("Witness Tampering Risk")
                pros_points.append(f"Apprehension of witness intimidation or tampering with evidence: {bail_obj.bail_evaluation.witness_tampering.reason or 'High tampering risk.'}")
            if not pros_points:
                pros_points = [
                    "Offence is non-bailable and serious in nature.",
                    "Custodial interrogation is essential for effective investigation and recovery of property.",
                    "Apprehension of influencing witnesses or tampering with evidence."
                ]

            bail_obj.prosecution_arguments = SideArgumentPackage(
                target_side="PROSECUTION",
                primary_objective="REJECT_BAIL",
                key_factors_highlighted=pros_factors or ["Gravity of Accusation", "Custodial Interrogation Requirement", "Witness Tampering Risk"],
                argument_points=pros_points,
                suggested_conditions_or_objections=[
                    "Anticipatory bail should be denied in view of the gravity of allegations.",
                    "Interrogation in custody is required to complete investigation."
                ]
            )

        # Ensure SideArgumentPackage for Defense (advocating BAIL GRANT)
        if not bail_obj.defense_arguments:
            def_factors = []
            def_points = []
            if bail_obj.bail_evaluation.custodial_interrogation.value in ["Not Required", "Low", "None"]:
                def_factors.append("No Custodial Interrogation Needed")
                def_points.append(f"Custodial interrogation is unnecessary: {bail_obj.bail_evaluation.custodial_interrogation.reason or 'Accused is willing to cooperate.'}")
            if bail_obj.bail_evaluation.cooperation.value in ["Cooperative", "High", "Good"]:
                def_factors.append("Cooperation with Investigation")
                def_points.append(f"Accused has undertaken to fully cooperate with investigation: {bail_obj.bail_evaluation.cooperation.reason or 'Cooperative.'}")
            if bail_obj.bail_evaluation.flight_risk.value in ["Low", "None"]:
                def_factors.append("No Flight Risk / Local Roots")
                def_points.append("Accused has permanent residence and deep roots in society with zero flight risk.")
            if not def_points:
                def_points = [
                    "Custodial interrogation is not required and applicant undertakes to cooperate with investigation.",
                    "Applicant has deep roots in society and no risk of absconding.",
                    "Applicant complies with statutory guidelines under Arnesh Kumar / Section 41A CrPC."
                ]

            bail_obj.defense_arguments = SideArgumentPackage(
                target_side="DEFENSE",
                primary_objective="GRANT_BAIL",
                key_factors_highlighted=def_factors or ["Absence of Custodial Interrogation Need", "Cooperation Undertaking", "Roots in Society"],
                argument_points=def_points,
                suggested_conditions_or_objections=[
                    "Applicant shall surrender passport if required by court.",
                    "Applicant shall report to police station as and when directed."
                ]
            )

        # Check confidence cutoff (< 0.70 threshold)
        if bail_obj.overall_recommendation.confidence < self.min_confidence_threshold:
            note = f"Overall bail recommendation confidence {bail_obj.overall_recommendation.confidence:.2f} < cutoff {self.min_confidence_threshold}."
            if note not in bail_obj.manual_review:
                bail_obj.manual_review.append(note)

        return bail_obj
