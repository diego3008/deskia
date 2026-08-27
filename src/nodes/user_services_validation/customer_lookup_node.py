import os

import httpx
from dotenv import load_dotenv

from src.helpers import helpers
from src.state import UserValidationState


load_dotenv()
API_URL = os.getenv("DESKIA_API_URL")


async def customer_lookup_node(state: UserValidationState) -> dict:
    email = state.get("user_data", {}).get("email")
    if not email:
        return {
            "pending_question": "existing_customer_email",
            "next_action": "request_existing_customer_email",
        }

    url = helpers["url_query"](
        f"{API_URL}/customers/search",
        {"email": email, "business_id": state.get("business_id")},
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)

        if response.status_code == 404:
            return {
                "pending_question": "confirm_create_customer",
                "next_action": "confirm_create_customer",
            }

        response.raise_for_status()
        customer = response.json()
        if not isinstance(customer, dict):
            raise ValueError("customer response must be an object")
        customer_id = customer.get("id")
        if not customer_id:
            raise ValueError("customer response is missing id")
    except (httpx.HTTPError, ValueError):
        return {
            "next_action": "retry_customer_lookup",
            "error": "customer_lookup_failed",
        }

    return {
        "customer_status": "existing",
        "customer": customer,
        "customer_id": customer_id,
        "pending_question": None,
        "next_action": "collect_appointment_details",
        "user_data": {**state.get("user_data", {}), "customer": customer},
    }
