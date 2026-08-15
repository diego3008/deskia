from copy import deepcopy
from typing import Any, Mapping

from src.nodes.appointments.config import DEFAULT_BUSINESS_TIMEZONE
from src.state import AppointmentState, MessageGraphState
from src.structured_outputs import AppointmentPhase, ConfirmationStatus


APPOINTMENT_PRIVATE_STATE_KEYS = (
    "operation",
    "phase",
    "service_id",
    "cancellation_reason",
    "requested_start",
    "requested_end",
    "selected_appointment",
    "appointment_candidates",
    "availability_evidence",
    "pending_action",
    "confirmation_status",
    "confirmation_action_id",
    "result",
    "error",
)


def reset_appointment_state() -> AppointmentState:
    """Return a neutral appointment state with no action eligible to execute."""
    return {
        "phase": AppointmentPhase.COLLECTING,
        "service_id": None,
        "cancellation_reason": None,
        "requested_start": None,
        "requested_end": None,
        "selected_appointment": None,
        "appointment_candidates": None,
        "availability_evidence": None,
        "pending_action": None,
        "confirmation_status": ConfirmationStatus.NOT_REQUESTED,
        "confirmation_action_id": None,
        "result": None,
        "error": None,
    }


def to_appointment_input(parent_state: MessageGraphState) -> AppointmentState:
    """Project authoritative parent context and private appointment state to a child run."""
    child_state = reset_appointment_state()
    stored_appointment = parent_state.get("appointment") or {}

    for key in APPOINTMENT_PRIVATE_STATE_KEYS:
        if key in stored_appointment:
            child_state[key] = deepcopy(stored_appointment[key])

    messages = list(parent_state.get("messages", []))
    child_state.update(
        {
            "business_id": parent_state["business_id"],
            "business_timezone": parent_state.get("business_timezone")
            or DEFAULT_BUSINESS_TIMEZONE,
            "customer_id": parent_state.get("customer_id"),
            "current_message": parent_state.get("current_message", ""),
            "messages": messages,
            "message_history_length": len(messages),
        }
    )
    return child_state


def from_appointment_output(child_output: Mapping[str, Any]) -> dict[str, Any]:
    """Map a completed child run back to appointment state and a message delta only."""
    appointment_state = {
        key: deepcopy(child_output[key])
        for key in APPOINTMENT_PRIVATE_STATE_KEYS
        if key in child_output
    }
    update: dict[str, Any] = {}
    if appointment_state:
        update["appointment"] = appointment_state

    messages = child_output.get("messages") or []
    history_length = child_output.get("message_history_length", 0)
    if isinstance(history_length, int) and history_length >= 0:
        message_delta = list(messages[history_length:])
    else:
        message_delta = list(messages)

    if message_delta:
        update["messages"] = message_delta

        last_message = message_delta[-1]
        update["message_response"] = str(
            getattr(last_message, "content", last_message)
        )
    return update
