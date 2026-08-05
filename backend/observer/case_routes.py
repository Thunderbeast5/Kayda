"""
Blueprint for observer-mode case bank endpoints.

Register this in your existing app.py:

    from case_routes import case_bp
    app.register_blueprint(case_bp)

Endpoints:
  GET  /api/cases              -> list of cases for the case picker
  GET  /api/cases/<case_id>    -> full case record + normalized caseData
  GET  /api/simulate/<case_id> -> SSE stream that replays simulation_conversation
                                   with pacing, in the same event shape your
                                   live /api/query flow already produces
"""

import json
import time

from flask import Blueprint, Response, jsonify, stream_with_context

from backend.observer.case_service import list_cases, get_case, normalize_case_data, build_events, _turn_delay

case_bp = Blueprint("case_bp", __name__)


@case_bp.route("/api/cases", methods=["GET"])
def api_list_cases():
    return jsonify(list_cases())


@case_bp.route("/api/cases/<case_id>", methods=["GET"])
def api_get_case(case_id):
    case = get_case(case_id)
    if case is None:
        return jsonify({"error": "Case not found"}), 404

    return jsonify({
        "caseData": normalize_case_data(case, case_id),
        "metadata": case.get("case_metadata", {}),
        "participants": case.get("participants", {}),
        "legal_principles": case.get("legal_principles_established", []),
    })


def _turn_delay(text: str) -> float:
    """
    Rough pacing so replay doesn't dump the whole transcript instantly.
    Scales with dialogue length, capped so long speeches don't stall the demo.
    """
    return min(0.5 + len(text) / 200, 2.5)


@case_bp.route("/api/simulate/<case_id>", methods=["GET"])
def api_simulate(case_id):
    events = build_events(case_id)
    if events is None:
        return jsonify({"error": "Case not found"}), 404

    @stream_with_context
    def event_stream():
        for evt in events:
            # "thinking" pause before the line lands, mirroring the setTimeout
            # pacing CourtroomInterface.jsx already uses for scripted turns
            time.sleep(_turn_delay(evt["full_text"]))
            yield f"data: {json.dumps(evt)}\n\n"

        yield f"data: {json.dumps({'type': 'verdict', 'message': 'Court stands adjourned.'})}\n\n"

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if you're behind one
        },
    )