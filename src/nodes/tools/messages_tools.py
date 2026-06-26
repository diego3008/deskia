from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from langchain.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import InjectedState

from dotenv import load_dotenv
import os
from src.helpers import helpers
import httpx

from src.models.appointments import AppointmentCreate, AppointmentInput

load_dotenv()
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

        async with httpx.AsyncClient() as client:
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
    full_appointment = AppointmentCreate(
            business_id=business_id,
            starts_at=appointment.starts_at,
            ends_at=appointment.ends_at,
        )
    try:
        url = f"{API_URL}/appointments/book" 
        

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=full_appointment.model_dump(mode="json"))

        resp.raise_for_status()
        
        return resp.json()
    except Exception as ex:
        return f"There was an error creating appointment: {ex}"


tools = [
    check_available_appointments,
    create_appointment
]