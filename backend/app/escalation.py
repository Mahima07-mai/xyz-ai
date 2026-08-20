"""
Mock escalation service (Phase 3).

The project's anti-hallucination constraint is explicit: the assistant must
NEVER tell a user a teacher/management representative has been contacted
unless a mock service genuinely confirms it. A boolean isn't enough -- this
module gives every escalation request a real pending/confirmed/failed
lifecycle, persisted in `EscalationRequest` (model.py), so the status the
assistant reports is always read back from a row that was actually written,
never asserted by the LLM.

Any authenticated caller (regardless of role) may request escalation --
unlike attendance/marks data, "I want to talk to a person" is not
role-scoped. What IS enforced is that a caller can only ever create and
read back THEIR OWN escalation requests, scoped by requested_by_id, which
comes exclusively from auth.get_current_user()'s verified JWT (caller["id"]) 
-- never from anything typed in chat.
"""
import logging
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .model import EscalationRequest, EscalationStatus

logger = logging.getLogger("xyz_ai.escalation")

_MOCK_ENDPOINT_LATENCY_SECONDS = 0.15

# Reserved reason strings that force a specific outcome, purely so the
# security/functional test suite and demo can deterministically show the
# failed and pending paths. A real integration would replace
# `_call_mock_teacher_endpoint` with an actual HTTP call.
_FORCE_FAILED_SENTINEL = "__force_fail__"
_FORCE_PENDING_SENTINEL = "__force_pending__"


@dataclass
class EscalationOutcome:
    """Plain result object handed back to the tool layer -- deliberately
    NOT a raw boolean, so 'no answer yet' (pending) can never be silently
    collapsed into failure or success."""
    request_id: int
    status: EscalationStatus
    message: str


def _call_mock_teacher_endpoint(reason: str) -> EscalationStatus:
    time.sleep(_MOCK_ENDPOINT_LATENCY_SECONDS)
    normalized = reason.strip().lower()
    if _FORCE_FAILED_SENTINEL in normalized:
        return EscalationStatus.failed
    if _FORCE_PENDING_SENTINEL in normalized:
        return EscalationStatus.pending
    return EscalationStatus.confirmed


def request_escalation(db: Session, caller: dict, reason: str) -> EscalationOutcome:
    """Create an EscalationRequest row for the VERIFIED caller (caller["id"],
    caller["role"] -- from auth.get_current_user(), never from chat text),
    attempt the mock teacher/management call, and persist whatever it
    genuinely returned. tools.py is the only caller of this function and is
    responsible for confirming with the user BEFORE invoking it -- this
    function itself does not re-ask."""
    record = EscalationRequest(
        requested_by_id=str(caller["id"]),
        requested_by_role=caller["role"],
        reason=reason.strip() or "(no reason given)",
        status=EscalationStatus.pending.value,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    try:
        outcome_status = _call_mock_teacher_endpoint(reason)
    except Exception:
        logger.exception("Mock teacher endpoint call raised for escalation id=%s", record.id)
        outcome_status = EscalationStatus.failed

    record.status = outcome_status.value
    db.commit()

    logger.info(
        "escalation id=%s requested_by=%s role=%s status=%s reason=%r",
        record.id, caller["id"], caller["role"], outcome_status.value, reason,
    )

    messages = {
        EscalationStatus.confirmed: (
            "A teacher/management representative has been notified and the "
            "request is confirmed received."
        ),
        EscalationStatus.pending: (
            "The request was submitted, but confirmation from a teacher/"
            "management representative is still pending -- it has not yet "
            "been confirmed as received."
        ),
        EscalationStatus.failed: (
            "The request could not be delivered to a teacher/management "
            "representative right now. It was not confirmed as received."
        ),
    }
    return EscalationOutcome(
        request_id=record.id,
        status=outcome_status,
        message=messages[outcome_status],
    )


def list_own_escalations(db: Session, caller: dict, limit: int = 10) -> list[dict]:
    """Read-only history of the caller's OWN escalation requests, scoped by
    requested_by_id -- used by the /escalations/mine endpoint (main.py)."""
    rows = (
        db.query(EscalationRequest)
        .filter(EscalationRequest.requested_by_id == str(caller["id"]))
        .order_by(EscalationRequest.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
