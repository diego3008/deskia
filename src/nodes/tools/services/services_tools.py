



from datetime import datetime
import os
from typing import Optional

from langgraph.prebuilt import InjectedState
from typing_extensions import Annotated

import httpx
from langchain_core.tools import tool

from src import helpers
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


async def reschedule_appointment():
    pass

async def cancel_appointment():
    pass

async def list_customer_appointments():
    pass
