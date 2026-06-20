from datetime import date
from typing import Optional
from uuid import UUID

from langchain.tools import tool
from dotenv import load_dotenv
import os
from src.helpers import helpers
import httpx

load_dotenv()
API_URL = os.getenv("DESKIA_API_URL")

@tool
async def check_available_appointments(
    starts_at: Optional[date] = None,
    business_id: Optional[UUID] = None,
):
    """This tool will help checking if there is availability for the appointment date requested by the user"""
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


tools = [
    check_available_appointments
]