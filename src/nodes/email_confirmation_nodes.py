import asyncio

from googleapiclient.errors import HttpError
from pydantic import ValidationError

from src.models.appointments import AppointmentOutcome
from src.utils.gmail_utils import GmailConfigurationError, send_email


SUBJECTS = {
    "booked": "Confirmación de cita",
    "rescheduled": "Cita reprogramada",
    "cancelled": "Cita cancelada",
}
DESCRIPTIONS = {
    "booked": "Tu cita ha sido agendada.",
    "rescheduled": "Tu cita ha sido reprogramada.",
    "cancelled": "Tu cita ha sido cancelada.",
}


def successful_outcome(state) -> AppointmentOutcome | None:
    try:
        outcome = AppointmentOutcome.model_validate(state.get("appointment_outcome"))
    except ValidationError:
        return None

    business_id = state.get("business_id")
    customer_id = state.get("customer_id")
    customer = state.get("customer")
    if customer_id is None and isinstance(customer, dict):
        customer_id = customer.get("id")
    if (
        business_id is None
        or customer_id is None
        or outcome.business_id != str(business_id)
        or outcome.customer_id != str(customer_id)
    ):
        return None
    return outcome


def record_receipt(state, operation_id, status, **details):
    receipt = {"operation_id": operation_id, "status": status, **details}
    # ponytail: thread-state receipts cannot close the send/checkpoint crash window;
    # use a backend outbox for durable retries and cross-worker deduplication.
    return {
        "email_draft": None,
        "email_confirmation": receipt,
        "email_receipts": {
            **(state.get("email_receipts") or {}),
            operation_id: receipt,
        },
    }


def write_email_node(state) -> dict:
    outcome = successful_outcome(state)
    if outcome is None:
        return {"email_draft": None, "email_confirmation": None}

    receipts = state.get("email_receipts") or {}
    if outcome.operation_id in receipts:
        return {
            "email_draft": None,
            "email_confirmation": receipts[outcome.operation_id],
        }
    if not outcome.recipient_email or not outcome.recipient_email.strip():
        return record_receipt(
            state,
            outcome.operation_id,
            "skipped",
            reason="recipient_missing",
        )

    lines = [
        DESCRIPTIONS[outcome.operation],
        f"Referencia: {outcome.appointment_id}",
    ]
    for label, value in (
        ("Fecha y hora", outcome.starts_at),
        ("Fin", outcome.ends_at),
        ("Horario anterior", outcome.previous_starts_at),
    ):
        if value is not None:
            lines.append(f"{label}: {value.strftime('%Y-%m-%d %H:%M %z')}")
    return {
        "email_confirmation": None,
        "email_draft": {
            "to": outcome.recipient_email,
            "subject": SUBJECTS[outcome.operation],
            "body": "\n".join(lines),
        },
    }


def route_email_draft(state) -> str:
    return "send_email" if state.get("email_draft") else "end"


async def send_email_node(state) -> dict:
    outcome = successful_outcome(state)
    if outcome is None:
        return {"email_draft": None, "email_confirmation": None}

    receipts = state.get("email_receipts") or {}
    if outcome.operation_id in receipts:
        return {
            "email_draft": None,
            "email_confirmation": receipts[outcome.operation_id],
        }
    draft = state.get("email_draft")
    if not draft:
        return record_receipt(
            state,
            outcome.operation_id,
            "skipped",
            reason="draft_missing",
        )

    try:
        message_id = await asyncio.to_thread(send_email, **draft)
    except (GmailConfigurationError, ValueError):
        return record_receipt(
            state,
            outcome.operation_id,
            "failed",
            reason="email_configuration_or_content",
        )
    except HttpError as error:
        definite = 400 <= error.resp.status < 500 and error.resp.status != 408
        return record_receipt(
            state,
            outcome.operation_id,
            "failed" if definite else "unknown",
            reason="gmail_request_failed",
        )
    except Exception:
        return record_receipt(
            state,
            outcome.operation_id,
            "unknown",
            reason="gmail_result_unknown",
        )
    return record_receipt(
        state,
        outcome.operation_id,
        "sent",
        gmail_message_id=message_id,
    )
