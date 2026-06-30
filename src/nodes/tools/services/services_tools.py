



from datetime import datetime
import os
from typing import Optional

from langchain_core.messages import ToolMessage
from langgraph.prebuilt import InjectedState
from langgraph_sdk.schema import Command
from typing_extensions import Annotated

import httpx
from langchain_core.tools import tool

from src.helpers import helpers
from src.models.appointments import AppointmentCreate, AppointmentInput

from src.models.appointments import AppointmentCreate


API_URL = os.getenv("DESKIA_API_URL")

@tool
async def check_available_appointments(
    starts_at: Optional[datetime] = None,
    state: Annotated[dict, InjectedState] = None,

):
    """This tool will help checking if there is availability for the appointment date requested by the user
        Args:
        starts_at: The exact date and time requested by the user (including the hour),
            e.g. 2026-06-21T15:30:00. If the user only gives a date with no time,
            ask them to clarify the time before calling this tool.
    """

    business_id = state["business_id"]  # read directly from state
    try:
        url = f"{API_URL}/appointments/availability"   # <- add /appointments prefix
        req_url = helpers["url_query"](url, {"starts_at": starts_at, "business_id": business_id})

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(req_url)
            is_available = resp.json()
        return {
            "available": is_available,
            "date_checked": str(starts_at),
        }
    except Exception as ex:
        return f"There was an error getting appointments: {ex}"


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
    email: str,
    state: Annotated[dict, InjectedState],
):
    """Look up the customer by email and check if they have an upcoming appointment.
    This MUST be called first, before checking availability or rescheduling.

    Args:
        email: The customer's email address, provided by the user.
    """
    business_id = state["business_id"]
    try:
        url = f"{API_URL}/customers/lookup"
        req_url = helpers["url_query"](url, {"email": email, "business_id": business_id})
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(req_url)
        data = resp.json()
    except Exception as ex:
        return f"There was an error looking up the customer: {ex}"

    appointment = data.get("upcoming_appointment")
    if not appointment:
        # No upcoming appointment -> stay in this stage, don't advance
        return Command(update={
            "messages": [ToolMessage(
                content="No upcoming appointment found for that email. Ask the user to double check it.",
            )],
        })

    return Command(update={
        "customer": data["customer"],
        "active_appointment": appointment,
        "flow_stage": "awaiting_new_time",
        "messages": [ToolMessage(
            content=f"Found appointment {appointment['id']} on {appointment['starts_at']}. "
                    f"Ask the user for the new date/time they'd like.",
        )],
    })
