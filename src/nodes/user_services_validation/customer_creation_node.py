


import os

import httpx
from dotenv import load_dotenv

from src.models.customers import CustomerCreate
from src.state import UserValidationState


load_dotenv()
API_URL = os.getenv("DESKIA_API_URL")


async def customer_creation_node(state: UserValidationState) -> dict:
    user_data = state.get("user_data", {})
    business_id = state.get("business_id")
    email = user_data.get("email")
    first_name = user_data.get("first_name")
    last_name = user_data.get("last_name")

    if not all((business_id, email, first_name, last_name)):
        return {
            "pending_question": "new_customer_details",
            "next_action": "request_new_customer_details",
            "error": "missing_customer_creation_data",
        }

    customer = CustomerCreate(
        business_id=business_id,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{API_URL}/customers/", json=customer.model_dump(mode="json")
            )
        response.raise_for_status()
        created_customer = response.json()
        if not isinstance(created_customer, dict):
            raise ValueError("customer response must be an object")
        customer_id = created_customer.get("id")
        if not customer_id:
            raise ValueError("customer response is missing id")
    except (httpx.HTTPError, ValueError):
        return {
            "next_action": "retry_customer_creation",
            "error": "customer_creation_failed",
        }

    return {
        "customer_status": "new",
        "customer": created_customer,
        "customer_id": customer_id,
        "pending_question": None,
        "next_action": "collect_appointment_details",
        "user_data": {**user_data, "customer": created_customer},
    }
