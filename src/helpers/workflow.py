from collections.abc import Mapping


CUSTOMER_QUESTION_ACTIONS = {
    "existing_customer_email": "request_existing_customer_email",
    "confirm_create_customer": "confirm_create_customer",
    "new_customer_details": "request_new_customer_details",
}
CUSTOMER_RETRY_ACTIONS = {"retry_customer_lookup", "retry_customer_creation"}


def customer_validation_pending(state: Mapping) -> bool:
    return (
        state.get("pending_question") in CUSTOMER_QUESTION_ACTIONS
        or state.get("next_action") in CUSTOMER_RETRY_ACTIONS
    )


def has_validated_customer(state: Mapping) -> bool:
    customer = state.get("customer")
    return bool(
        state.get("customer_id")
        or (isinstance(customer, dict) and customer.get("id"))
    )


def clear_appointment_state() -> dict:
    return {
        "appointment_intent": None,
        "current_flow": None,
        "pending_question": None,
        "next_action": None,
        "active_appointment": None,
        "confirmed_slot": None,
    }
