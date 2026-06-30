



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

from src.models.appointments import AppointmentCreate


API_URL = os.getenv("DESKIA_API_URL")

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
    state: Annotated[dict, InjectedState] = None,

    ):
    """
    This tool handles appointment creation when the date provided
    by the user is available.
    ...
        Args:
        appointment: An object of type AppointmentInput...
        Fields of AppointmentInput:
        starts_at: ...
        ends_at: ...
    """
    business_id = state["business_id"]  # read directly from state
    customer_id = state.get("customer", {}).get("id")  # read directly from state
    full_appointment =  AppointmentCreate(
            business_id=business_id,
            starts_at=appointment.starts_at,
            ends_at=appointment.ends_at,
            customer_id=customer_id
        )
    try:
        url = f"{API_URL}/appointments/book" 
        

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=full_appointment.model_dump(mode="json"))

        resp.raise_for_status()
        

        return resp.json()
    except Exception as ex:
        return f"There was an error creating appointment: {ex}"


@tool
async def reschedule_appointment(
    appointment: AppointmentInput,
    state: Annotated[dict, InjectedState] = None,
):
    """Reschedule the customer's existing appointment to a new date and time.
    Call this only after the appointment to move has been identified (find_customer_appointment)
    and the new slot has been confirmed available (check_available_appointments).

        Args:
        appointment: An AppointmentInput with the NEW starts_at and ends_at for the appointment.
    """
    business_id = state["business_id"]
    active = state.get("active_appointment") or {}
    appointment_id = active.get("id")
    if not appointment_id:
        return (
            "No appointment is selected to reschedule. "
            "Call find_customer_appointment first to locate the customer's appointment."
        )
    try:
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
        return resp.json()
    except Exception as ex:
        return f"There was an error rescheduling the appointment: {ex}"


async def cancel_appointment():
    pass

async def list_customer_appointments() :
    pass

@tool
async def find_customer_appointment(
    tool_call_id: Annotated[str, InjectedToolCallId],
    appointment_date: Optional[str] = None,
    state: Annotated[dict, InjectedState] = None,
):
    """Look up the identified customer's upcoming appointment(s) for this business.
    Call this first when the customer wants to reschedule. The customer is already
    identified, so no email is needed.
        Args:
        appointment_date: Optional ISO date (e.g. 2026-07-01) to pick a specific
            appointment when the customer has more than one. Ask the user which date
            first, then call again with it.
    """
    business_id = state["business_id"]
    customer_id = state.get("customer_id") or (state.get("customer") or {}).get("id")
    if not customer_id:
        return "The customer is not identified yet, so I cannot look up their appointments."
    try:
        # NOTE: confirm this lists a customer's appointments against the API
        url = f"{API_URL}/appointments"
        req_url = helpers["url_query"](url, {"customer_id": customer_id, "business_id": business_id})
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(req_url)
        resp.raise_for_status()
        appointments = resp.json()
    except Exception as ex:
        return f"There was an error looking up the customer's appointments: {ex}"

    if not appointments:
        return "I could not find any upcoming appointments for this customer."

    if appointment_date:
        matches = [a for a in appointments if str(a.get("starts_at", "")).startswith(appointment_date[:10])]
        appointments = matches or appointments

    if len(appointments) > 1:
        return (
            f"This customer has multiple upcoming appointments: {appointments}. "
            "Ask the user which date they mean, then call find_customer_appointment "
            "again with that date in appointment_date."
        )

    appt = appointments[0]
    return Command(
        update={
            "active_appointment": appt,
            "messages": [
                ToolMessage(content=f"Found appointment: {appt}", tool_call_id=tool_call_id)
            ],
        }
    )
