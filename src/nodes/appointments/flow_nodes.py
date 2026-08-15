"""Non-transport nodes used by the appointment graph."""

from datetime import UTC, datetime

from langchain_core.messages import AIMessage

from src.nodes.appointments.config import DEFAULT_BUSINESS_TIMEZONE
from src.state import AppointmentState
from src.structured_outputs import AppointmentOperation


def fallback_appointment_node(_: AppointmentState) -> dict:
    return {"messages": [AIMessage(content="Please tell me which appointment action you would like help with.")]}


def extract_appointment_details_node(state: AppointmentState) -> dict:
    """Fill typed details only; this node cannot route or execute an action."""
    if state.get("operation") == AppointmentOperation.CANCEL:
        return {}
    update = {}
    if state.get("requested_start") is None or state.get("requested_end") is None:
        from src.agents.appointment_details import extract_appointment_details

        details = extract_appointment_details(
            message=state.get("current_message", ""),
            business_timezone=state.get("business_timezone") or DEFAULT_BUSINESS_TIMEZONE,
            current_time=datetime.now(UTC),
        )
        if details.starts_at is not None and details.ends_at is not None:
            update["requested_start"] = details.starts_at
            update["requested_end"] = details.ends_at
        if details.cancellation_reason is not None:
            update["cancellation_reason"] = details.cancellation_reason
    if update.get("requested_start", state.get("requested_start")) is None:
        update["messages"] = [AIMessage(content="What date and start time would you like?")]
    elif update.get("requested_end", state.get("requested_end")) is None:
        update["messages"] = [AIMessage(content="What end time would you like?")]
    return update
