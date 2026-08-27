from datetime import datetime
import os
from typing import Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated

import httpx

from src.helpers import helpers
from src.models.appointments import AppointmentCreate, AppointmentInput
from tzlocal import get_localzone

LOCAL_TZ = get_localzone()


API_URL = os.getenv("DESKIA_API_URL")


def _slot_confirmed(state: dict, starts_at: datetime) -> bool:
    slot = state.get("confirmed_slot") or {}
    return slot.get("starts_at") == starts_at.isoformat()


@tool
async def check_available_appointments(
    tool_call_id: Annotated[str, InjectedToolCallId],
    starts_at: Optional[datetime] = None,
    state: Annotated[dict, InjectedState] = None,
):
    """This tool will help checking if there is availability for the appointment date requested by the user
        Args:
        starts_at: The exact date and time requested by the user (including the hour),
            e.g. 2026-06-21T15:30:00. If the user only gives a date with no time,
            ask them to clarify the time before calling this tool.
    """
    business_id = state["business_id"]
    try:
        url = f"{API_URL}/appointments/availability"
        req_url = helpers["url_query"](url, {"starts_at": starts_at, "business_id": business_id})
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(req_url)
            is_available = resp.json()
    except Exception as ex:
        return f"There was an error getting appointments: {ex}"

    if is_available and starts_at is not None:
        return Command(
            update={
                "confirmed_slot": {"starts_at": starts_at.isoformat()},
                "messages": [
                    ToolMessage(
                        content=f"{starts_at} is available.", tool_call_id=tool_call_id
                    )
                ],
            }
        )
    return {"available": is_available, "date_checked": str(starts_at)}


@tool
async def create_appointment(
    appointment: AppointmentInput,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState] = None,
):
    """Books a new appointment. Only call this after check_available_appointments
    has confirmed the requested slot is available.
        Args:
        appointment: An AppointmentInput with starts_at and ends_at.
    """
    if not _slot_confirmed(state, appointment.starts_at):
        return (
            "Please call check_available_appointments for this exact date and time "
            "and confirm it is available before booking."
        )
    business_id = state["business_id"]
    customer_id = state.get("customer_id") or (state.get("customer") or {}).get("id")
    full_appointment = AppointmentCreate(
        business_id=business_id,
        starts_at=appointment.starts_at,
        ends_at=appointment.ends_at,
        customer_id=customer_id,
    )
    try:
        url = f"{API_URL}/appointments/book"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=full_appointment.model_dump(mode="json"))
        resp.raise_for_status()
        created = resp.json()
    except Exception as ex:
        return f"There was an error creating appointment: {ex}"

    return Command(
        update={
            "confirmed_slot": None,
            "current_flow": None,
            "next_action": None,
            "pending_question": None,
            "messages": [
                ToolMessage(content=f"Appointment booked: {created}", tool_call_id=tool_call_id)
            ],
        }
    )


@tool
async def reschedule_appointment(
    appointment: AppointmentInput,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState] = None,
):
    """Reschedule the customer's existing appointment to a new date and time.
    Only call this after find_customer_appointment has located the appointment AND
    check_available_appointments has confirmed the new slot.
        Args:
        appointment: An AppointmentInput with the NEW starts_at and ends_at.
    """
    active = state.get("active_appointment") or {}
    appointment_id = active.get("id")
    if not appointment_id:
        return (
            "No appointment is selected to reschedule. "
            "Call find_customer_appointment first to locate the customer's appointment."
        )
    if not _slot_confirmed(state, appointment.starts_at):
        return (
            "Please call check_available_appointments for the new date and time and "
            "confirm it is available before rescheduling."
        )
    business_id = state["business_id"]
    try:
        # NOTE: the API must atomically re-validate availability and reject conflicts; confirmed_slot is only a UX gate, not a concurrency guarantee.
        # NOTE: confirm this endpoint/verb/payload against the API
        url = f"{API_URL}/appointments/{appointment_id}/reschedule"
        payload = {
            "starts_at": appointment.starts_at.isoformat(),
            "ends_at": appointment.ends_at.isoformat(),
            "business_id": str(business_id),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(url, json=payload)
        resp.raise_for_status()
        updated = resp.json()
    except Exception as ex:
        return f"There was an error rescheduling the appointment: {ex}"

    return Command(
        update={
            "active_appointment": None,
            "confirmed_slot": None,
            "current_flow": None,
            "next_action": None,
            "pending_question": None,
            "messages": [
                ToolMessage(content=f"Appointment rescheduled: {updated}", tool_call_id=tool_call_id)
            ],
        }
    )


@tool
async def find_customer_appointment(
    tool_call_id: Annotated[str, InjectedToolCallId],
    appointment_date: str = None,
    state: Annotated[dict, InjectedState] = None,
):
    """Look up the identified customer's appointment for this business. A customer
    can only have one appointment at a given time, so this returns at most one match.
    Call this first when the customer wants to reschedule. The customer is already
    identified, so no email is needed.
        Args:
        appointment_date: ISO date (e.g. 2026-07-01) to narrow the lookup to
            a specific date.
    """
    business_id = state["business_id"]
    customer_id = state.get("customer_id") or (state.get("customer") or {}).get("id")
    if not customer_id:
        return "The customer is not identified yet, so I cannot look up their appointments."
    try:
        url = f"{API_URL}/appointments/find_customer_appointment"
        params = {"customer_id": customer_id, "business_id": business_id}
        if appointment_date:
            params["appointment_date"] = appointment_date[:10]
        req_url = helpers["url_query"](url, params)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(req_url)
        resp.raise_for_status()
        appt = resp.json()
    except Exception as ex:
        return f"There was an error looking up the customer's appointment: {ex}"

    if not appt:
        if appointment_date:
            return (
                f"I could not find any appointment for this customer on {appointment_date[:10]}. "
                "Please double-check the date."
            )
        return "I could not find any upcoming appointment for this customer."
    
    appt["starts_at"] = datetime.fromisoformat(appt["starts_at"]).astimezone(LOCAL_TZ).isoformat()
    appt["ends_at"] = datetime.fromisoformat(appt["ends_at"]).astimezone(LOCAL_TZ).isoformat()

    return Command(
        update={
            "active_appointment": appt,
            "messages": [
                ToolMessage(content=f"Found appointment: {appt}", tool_call_id=tool_call_id)
            ],
        }
    )
