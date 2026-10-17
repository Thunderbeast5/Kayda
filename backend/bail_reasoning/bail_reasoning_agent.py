"""
Bail Reasoning Agent for Anticipatory Bail Reasoning Engine.
Evaluates whether anticipatory bail should be granted or denied under Section 438 CrPC
by applying judicial bail reasoning principles to verified outputs from previous stages.
"""

import json
from typing import Any, Dict, Optional, Union
from langchain_core.messages import HumanMessage, SystemMessage

from lexigraphbe.config import extract_json_from_text, get_llm, MODEL_STAGE5
from lexigraphbe.prompts import STAGE5_BAIL_REASONING_SYSTEM_PROMPT, STAGE5_BAIL_REASONING_USER_PROMPT_TEMPLATE
from .schemas import BailReasoningObject, SideArgumentPackage


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
    }
}


class BailReasoningAgent:
    """
    Bail Reasoning Agent evaluating anticipatory bail under Sec 438 CrPC.
    Injects full statutory text and statutory factors of procedural bail provisions.
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
        case_context: Any,
        legal_query: Any,
        statutory_object: Any,
        side: Optional[str] = "BOTH",
        correction_feedback: Optional[str] = None,
    ) -> BailReasoningObject:
        """
        Runs Bail Reasoning on CaseContextObject, LegalQueryObject, and StatutoryVerificationObject.
        """
        if hasattr(case_context, "to_downstream_json"):
            cco_json_str = case_context.to_downstream_json()
            regime = getattr(case_context, "legal_regime", "IPC + CrPC")
        elif isinstance(case_context, dict):
            cco_json_str = json.dumps(case_context, indent=2)
            regime = case_context.get("legal_regime") or case_context.get("case_profile", {}).get("legal_regime") or "IPC + CrPC"
        else:
            cco_json_str = str(case_context)
            regime = "IPC + CrPC"

        if hasattr(legal_query, "to_downstream_json"):
            qo_json_str = legal_query.to_downstream_json()
        elif isinstance(legal_query, dict):
            qo_json_str = json.dumps(legal_query, indent=2)
        else:
            qo_json_str = str(legal_query)

        if hasattr(statutory_object, "to_downstream_json"):
            svo_json_str = statutory_object.to_downstream_json()
        elif isinstance(statutory_object, dict):
            svo_json_str = json.dumps(statutory_object, indent=2)
        else:
            svo_json_str = str(statutory_object)

        legal_regime_clean = "IPC + CrPC"
        bail_provision = "Section 438 CrPC"

        prov_record = PROCEDURAL_BAIL_PROVISIONS["Section 438 CrPC"]
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
        bail_obj = BailReasoningObject.model_validate(extracted_dict)

        target_side_clean = (side or "BOTH").strip().upper()
        bail_obj.target_side = target_side_clean
        bail_obj.bail_provision_applied = bail_provision
        bail_obj.legal_regime = legal_regime_clean

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

        return bail_obj
