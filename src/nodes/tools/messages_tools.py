from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from langchain.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from dotenv import load_dotenv
import os
from src.helpers import helpers
import httpx

from src.models.appointments import AppointmentCreate, AppointmentInput
from src.models.customers import CustomerCreate, CustomerInput

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
    try:
        full_appointment = AppointmentCreate(
            business_id=business_id,
            starts_at=appointment.starts_at,
            ends_at=appointment.ends_at,
            customer_id=customer_id,
            service_id=state.get("service_id"),
            business_staff_id=state.get("business_staff_id"),
        )
        url = f"{API_URL}/appointments/book" 
        

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=full_appointment.model_dump(mode="json"))

        resp.raise_for_status()
        

        return resp.json()
    except Exception as ex:
        return f"There was an error creating appointment: {ex}"



@tool
async def find_customer(
    email: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState] = None,
):
    """
    Look up an existing customer for this business by email.
    Call this once you have the user's email address, before booking any appointment.

        Args:
        email: The customer's email address to search for.
    """
    business_id = state["business_id"]  # read directly from state
    try:
        url = f"{API_URL}/customers/search"
        req_url = helpers["url_query"](url, {"email": email, "business_id": business_id})

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(req_url)

        if resp.status_code == 404:
            return (
                f"No existing customer found for {email}. "
                "Ask the user for their first and last name, then call create_customer."
            )

        resp.raise_for_status()
        found = resp.json()
        return Command(
            update={
                "customer": found,
                "messages": [
                    ToolMessage(
                        content=f"Found existing customer: {found}",
                        tool_call_id=tool_call_id,
                    ),
                ],
                "customer_id": found.get("id"),
            }
        )
    except Exception as ex:
        return f"There was an error searching for customer: {ex}"


@tool
async def create_customer(
    customer: CustomerInput,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState] = None,
):
    """
    Register a new customer for the business.
    Use this only after find_customer reported no existing customer for the email,
    once you have collected the user's first and last name.

        Args:
        customer: A CustomerInput with required email, first_name, and last_name.
    """
    business_id = state["business_id"]  # read directly from state
    full_customer = CustomerCreate(
            business_id=business_id,
            email=customer.email,
            first_name=customer.first_name,
            last_name=customer.last_name,
        )
    try:
        url = f"{API_URL}/customers/"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=full_customer.model_dump(mode="json"))

        resp.raise_for_status()
        created = resp.json()
        return Command(
            update={
                "customer": created,
                "messages": [
                    ToolMessage(
                        content=f"Customer created: {created}",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage(content=f"{created.get('first_name', '')} {created.get('last_name', '')} you have been registered successfully."),
                ],
                "customer_id": created.get("id"),
            }
        )
    except Exception as ex:
        return f"There was an error creating customer: {ex}"


appointment_tools = [
    check_available_appointments,
    create_appointment,
]

customer_tools = [
    find_customer,
    create_customer,
]

# Backwards-compatible alias: the appointment loop binds this list.
tools = appointment_tools
