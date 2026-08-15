"""Read-only appointment nodes.

These nodes may call only appointment API read methods. They return state updates
and leave all user-facing prose to ``response_nodes``.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.models.appointments import AppointmentSummary
from src.nodes.appointments.config import DEFAULT_BUSINESS_TIMEZONE
from src.services.appointments import AppointmentApiClient, AppointmentApiError
from src.state import AppointmentSelection, AppointmentState
from src.structured_outputs import AppointmentPhase


def _error(code: str, message: str, *, retryable: bool = False) -> dict:
    return {
        "phase": AppointmentPhase.COLLECTING,
        "availability_evidence": None,
        "error": {"code": code, "message": message, "retryable": retryable},
    }


def _aware(value: datetime | None) -> bool:
    return value is not None and value.tzinfo is not None and value.utcoffset() is not None


def _normalize_local_time(value: datetime, timezone_name: str) -> tuple[datetime | None, str | None]:
    """Attach the business timezone to a local time without guessing DST folds."""
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return None, "invalid_business_timezone"

    if _aware(value):
        return value, None

    first_fold = value.replace(tzinfo=timezone, fold=0)
    second_fold = value.replace(tzinfo=timezone, fold=1)
    first_valid = first_fold.astimezone(UTC).astimezone(timezone).replace(tzinfo=None) == value
    second_valid = second_fold.astimezone(UTC).astimezone(timezone).replace(tzinfo=None) == value

    if not first_valid and not second_valid:
        return None, "nonexistent_local_time"
    if first_valid and second_valid and first_fold.utcoffset() != second_fold.utcoffset():
        return None, "ambiguous_local_time"
    return first_fold if first_valid else second_fold, None


def _selection(appointment: AppointmentSummary) -> AppointmentSelection:
    return {
        "id": appointment.id,
        "starts_at": appointment.starts_at,
        "ends_at": appointment.ends_at,
        "status": appointment.status,
        "active": appointment.active,
    }


async def check_availability_node(
    state: AppointmentState,
    *,
    client: AppointmentApiClient,
) -> dict:
    """Check only the exact, timezone-aware interval held in appointment state."""
    starts_at = state.get("requested_start")
    ends_at = state.get("requested_end")
    business_id = state.get("business_id")
    business_timezone = state.get("business_timezone") or DEFAULT_BUSINESS_TIMEZONE

    if starts_at is None:
        return _error("missing_start", "Please provide the appointment start time.")
    if ends_at is None:
        return _error("missing_end", "Please provide the appointment end time.")
    starts_at, start_error = _normalize_local_time(starts_at, business_timezone)
    ends_at, end_error = _normalize_local_time(ends_at, business_timezone)
    time_error = start_error or end_error
    if time_error == "invalid_business_timezone":
        return _error(time_error, "The business timezone is invalid.")
    if time_error == "ambiguous_local_time":
        return _error(time_error, "Please clarify the appointment time around the daylight-saving change.")
    if time_error == "nonexistent_local_time":
        return _error(time_error, "That appointment time does not exist because of a daylight-saving change.")
    if starts_at is None or ends_at is None:
        return _error("timezone_required", "Please provide an appointment time with a known timezone.")
    if ends_at <= starts_at:
        return _error("invalid_interval", "The appointment end time must be after its start time.")
    if business_id is None:
        return _error("missing_business", "The business could not be identified.")

    try:
        available = await client.check_availability(business_id, starts_at, ends_at)
    except AppointmentApiError as error:
        return {
            "phase": AppointmentPhase.FAILED,
            "availability_evidence": None,
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        }

    return {
        "phase": AppointmentPhase.COLLECTING,
        "requested_start": starts_at,
        "requested_end": ends_at,
        "availability_evidence": {
            "starts_at": starts_at,
            "ends_at": ends_at,
            "service_id": state.get("service_id"),
            "available": available,
            "checked_at": datetime.now(UTC),
            "verification_token": None,
        },
        "error": None,
    }


async def lookup_appointments_node(
    state: AppointmentState,
    *,
    client: AppointmentApiClient,
) -> dict:
    """Look up owned appointments and select only an unambiguous result."""
    business_id = state.get("business_id")
    customer_id = state.get("customer_id")
    if business_id is None:
        return {
            "phase": AppointmentPhase.COLLECTING,
            "selected_appointment": None,
            "appointment_candidates": None,
            "error": {
                "code": "missing_business",
                "message": "The business could not be identified.",
                "retryable": False,
            },
        }
    if customer_id is None:
        return {
            "phase": AppointmentPhase.COLLECTING,
            "selected_appointment": None,
            "appointment_candidates": None,
            "error": {
                "code": "missing_customer",
                "message": "The customer could not be identified.",
                "retryable": False,
            },
        }

    requested_start = state.get("requested_start")
    appointment_date = requested_start.date() if _aware(requested_start) else None
    try:
        appointments = await client.list_customer_appointments(
            business_id,
            customer_id,
            appointment_date=appointment_date,
        )
    except AppointmentApiError as error:
        return {
            "phase": AppointmentPhase.FAILED,
            "selected_appointment": None,
            "appointment_candidates": None,
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        }

    candidates = [_selection(appointment) for appointment in appointments]
    if len(candidates) == 1:
        return {
            "phase": AppointmentPhase.COLLECTING,
            "selected_appointment": candidates[0],
            "appointment_candidates": None,
            "error": None,
        }
    return {
        "phase": AppointmentPhase.COLLECTING,
        "selected_appointment": None,
        "appointment_candidates": candidates,
        "error": None,
    }
