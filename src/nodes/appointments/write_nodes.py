"""Pure safety gates for appointment mutations.

These functions never call the appointment API. Phase 6 will consume an action
only after this module has staged, bound, and revalidated it.
"""

from copy import deepcopy
import re
import unicodedata
from uuid import uuid4

from langchain_core.messages import AIMessage

from src.models.appointments import (
    AppointmentBookingRequest,
    AppointmentCancellationRequest,
    AppointmentCancellationResponse,
    AppointmentRescheduleRequest,
    AppointmentSummary,
)
from src.services.appointments import AppointmentApiClient, AppointmentApiError
from src.state import AppointmentState, PendingAppointmentAction
from src.structured_outputs import AppointmentOperation, AppointmentPhase, ConfirmationStatus


def _clear(*, status: ConfirmationStatus = ConfirmationStatus.NOT_REQUESTED) -> dict:
    return {
        "pending_action": None,
        "confirmation_status": status,
        "confirmation_action_id": None,
    }


def _stage_error(code: str, message: str) -> dict:
    return {
        **_clear(),
        "phase": AppointmentPhase.COLLECTING,
        "error": {"code": code, "message": message, "retryable": False},
    }


def _matching_availability(state: AppointmentState) -> bool:
    evidence = state.get("availability_evidence") or {}
    return (
        evidence.get("available") is True
        and evidence.get("starts_at") == state.get("requested_start")
        and evidence.get("ends_at") == state.get("requested_end")
        and evidence.get("service_id") == state.get("service_id")
    )


def _confirmation_summary(action: PendingAppointmentAction) -> str:
    operation = action["operation"]
    if operation == AppointmentOperation.BOOK:
        return (
            "Please confirm booking an appointment from "
            f"{action['requested_start'].isoformat()} to {action['requested_end'].isoformat()}."
        )
    selected = action["selected_before"] or {}
    if operation == AppointmentOperation.RESCHEDULE:
        return (
            f"Please confirm moving appointment {action['appointment_id']} from "
            f"{selected.get('starts_at').isoformat()} to {action['requested_start'].isoformat()} "
            f"through {action['requested_end'].isoformat()}."
        )
    return (
        f"Please confirm cancelling appointment {action['appointment_id']} scheduled for "
        f"{selected.get('starts_at').isoformat()}."
    )


def stage_pending_action(state: AppointmentState) -> dict:
    """Create an immutable snapshot for one eligible appointment mutation."""
    operation = state.get("operation")
    business_id = state.get("business_id")
    customer_id = state.get("customer_id")
    starts_at = state.get("requested_start")
    ends_at = state.get("requested_end")
    selected = state.get("selected_appointment")

    if operation not in {
        AppointmentOperation.BOOK,
        AppointmentOperation.RESCHEDULE,
        AppointmentOperation.CANCEL,
    }:
        return _stage_error("unsupported_operation", "This appointment action cannot be confirmed.")
    if business_id is None or customer_id is None:
        return _stage_error("missing_identity", "The business or customer could not be identified.")
    if operation in {AppointmentOperation.BOOK, AppointmentOperation.RESCHEDULE}:
        if starts_at is None or ends_at is None or not _matching_availability(state):
            return _stage_error(
                "availability_required",
                "Please check availability for the exact appointment time first.",
            )
    if operation in {AppointmentOperation.RESCHEDULE, AppointmentOperation.CANCEL} and not selected:
        return _stage_error("selection_required", "Please select one appointment first.")

    action: PendingAppointmentAction = {
        "action_id": uuid4(),
        "operation": operation,
        "business_id": business_id,
        "customer_id": customer_id,
        "appointment_id": selected.get("id") if selected else None,
        "service_id": state.get("service_id"),
        "requested_start": starts_at,
        "requested_end": ends_at,
        "selected_before": deepcopy(selected) if selected else None,
        "cancellation_reason": state.get("cancellation_reason"),
    }
    return {
        "pending_action": action,
        "confirmation_status": ConfirmationStatus.PENDING,
        "confirmation_action_id": None,
        "phase": AppointmentPhase.AWAITING_CONFIRMATION,
        "error": None,
        "messages": [AIMessage(content=_confirmation_summary(action))],
    }


def _normalized_confirmation(text: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    normalized = re.sub(r"[^\w\s]", "", normalized)
    return re.sub(r"\s+", " ", normalized.strip().lower())


def classify_confirmation(text: str | None) -> str:
    """Classify only explicit whole-message approval or rejection phrases."""
    value = _normalized_confirmation(text)
    if value in {"yes", "confirm", "confirmed", "i confirm", "si", "si confirmo", "confirmo", "confirmar"}:
        return "approve"
    if value in {"no", "no confirmo", "cancel", "cancelar", "rechazo", "rechazar"}:
        return "reject"
    return "unclear"


def apply_confirmation(state: AppointmentState) -> dict:
    """Bind an explicit reply to the current pending action, or fail closed."""
    pending = state.get("pending_action")
    if (
        not pending
        or state.get("phase") != AppointmentPhase.AWAITING_CONFIRMATION
        or state.get("confirmation_status") != ConfirmationStatus.PENDING
    ):
        return _stage_error("confirmation_not_pending", "There is no appointment action awaiting confirmation.")

    decision = classify_confirmation(state.get("current_message"))
    if decision == "approve":
        return {
            "phase": AppointmentPhase.AWAITING_CONFIRMATION,
            "confirmation_status": ConfirmationStatus.APPROVED,
            "confirmation_action_id": pending["action_id"],
            "error": None,
        }
    if decision == "reject":
        return {
            **_clear(status=ConfirmationStatus.REJECTED),
            "phase": AppointmentPhase.COLLECTING,
            "error": None,
            "messages": [AIMessage(content="Okay, I will not make that appointment change.")],
        }
    return {
        "phase": AppointmentPhase.AWAITING_CONFIRMATION,
        "pending_action": pending,
        "confirmation_status": ConfirmationStatus.PENDING,
        "confirmation_action_id": None,
        "error": None,
        "messages": [AIMessage(content="Please reply with an explicit confirmation or rejection.")],
    }


def revalidate_pending_action(state: AppointmentState) -> dict:
    """Ensure an approved action still exactly matches the current appointment state."""
    pending = state.get("pending_action")
    if (
        not pending
        or state.get("confirmation_status") != ConfirmationStatus.APPROVED
        or state.get("confirmation_action_id") != pending.get("action_id")
        or state.get("operation") != pending.get("operation")
        or state.get("business_id") != pending.get("business_id")
        or state.get("customer_id") != pending.get("customer_id")
        or state.get("service_id") != pending.get("service_id")
        or state.get("cancellation_reason") != pending.get("cancellation_reason")
    ):
        return _stale_action()

    operation = pending["operation"]
    if operation in {AppointmentOperation.BOOK, AppointmentOperation.RESCHEDULE}:
        if (
            state.get("requested_start") != pending.get("requested_start")
            or state.get("requested_end") != pending.get("requested_end")
            or not _matching_availability(state)
        ):
            return _stale_action()
    if operation in {AppointmentOperation.RESCHEDULE, AppointmentOperation.CANCEL}:
        if state.get("selected_appointment") != pending.get("selected_before"):
            return _stale_action()

    return {"phase": AppointmentPhase.EXECUTING, "error": None}


def _stale_action() -> dict:
    return {
        **_clear(),
        "phase": AppointmentPhase.COLLECTING,
        "error": {
            "code": "stale_action",
            "message": "The appointment details changed, so please review them again.",
            "retryable": False,
        },
    }


def clear_pending_action(_: PendingAppointmentAction | None = None) -> dict:
    """Clear all approval state before a future mutation can be considered."""
    return _clear()


def _result_from_summary(
    summary: AppointmentSummary | AppointmentCancellationResponse,
) -> dict:
    return {
        "id": summary.id,
        "starts_at": summary.starts_at,
        "ends_at": summary.ends_at,
        "status": summary.status,
        "active": getattr(summary, "active", False),
    }


def _execution_failure(error: AppointmentApiError) -> dict:
    return {
        **_clear(),
        "phase": AppointmentPhase.FAILED,
        "error": {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        },
    }


def _execution_success(summary: AppointmentSummary, message: str) -> dict:
    return {
        **_clear(),
        "phase": AppointmentPhase.SUCCEEDED,
        "selected_appointment": None,
        "appointment_candidates": None,
        "availability_evidence": None,
        "result": {"appointment": _result_from_summary(summary), "message": message},
        "error": None,
        "messages": [AIMessage(content=message)],
    }


def _ready_action(state: AppointmentState, operation: AppointmentOperation) -> PendingAppointmentAction | None:
    """Revalidate immediately before a write and return only a matching snapshot."""
    pending = state.get("pending_action")
    if not pending or pending.get("operation") != operation:
        return None
    revalidated = revalidate_pending_action(state)
    if revalidated.get("phase") != AppointmentPhase.EXECUTING:
        return None
    return pending


def _not_ready(state: AppointmentState) -> dict:
    revalidated = revalidate_pending_action(state)
    if revalidated.get("phase") != AppointmentPhase.EXECUTING:
        return revalidated
    return _stage_error("execution_not_ready", "This appointment action is not ready to execute.")


async def execute_book_node(
    state: AppointmentState,
    *,
    client: AppointmentApiClient,
) -> dict:
    action = _ready_action(state, AppointmentOperation.BOOK)
    if action is None:
        return _not_ready(state)

    request = AppointmentBookingRequest(
        business_id=action["business_id"],
        customer_id=action["customer_id"],
        starts_at=action["requested_start"],
        ends_at=action["requested_end"],
    )
    try:
        summary = await client.book(request)
    except AppointmentApiError as error:
        return _execution_failure(error)
    return _execution_success(summary, "Your appointment has been booked.")


async def execute_reschedule_node(
    state: AppointmentState,
    *,
    client: AppointmentApiClient,
) -> dict:
    action = _ready_action(state, AppointmentOperation.RESCHEDULE)
    if action is None:
        return _not_ready(state)

    selected = action.get("selected_before") or {}
    if (
        selected.get("starts_at") == action.get("requested_start")
        and selected.get("ends_at") == action.get("requested_end")
    ):
        return _stage_error("unchanged_slot", "The new appointment time is the same as the current one.")

    request = AppointmentRescheduleRequest(
        business_id=action["business_id"],
        customer_id=action["customer_id"],
        starts_at=action["requested_start"],
        ends_at=action["requested_end"],
    )
    try:
        summary = await client.reschedule(action["appointment_id"], request)
    except AppointmentApiError as error:
        return _execution_failure(error)
    return _execution_success(summary, "Your appointment has been rescheduled.")


async def execute_cancel_node(
    state: AppointmentState,
    *,
    client: AppointmentApiClient,
) -> dict:
    action = _ready_action(state, AppointmentOperation.CANCEL)
    if action is None:
        return _not_ready(state)

    request = AppointmentCancellationRequest(
        business_id=action["business_id"],
        customer_id=action["customer_id"],
        reason=action.get("cancellation_reason"),
    )
    try:
        summary = await client.cancel(action["appointment_id"], request)
    except AppointmentApiError as error:
        return _execution_failure(error)
    return _execution_success(summary, "Your appointment has been cancelled.")
