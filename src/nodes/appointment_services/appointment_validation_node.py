from src.state import MessageGraphState
from src.structured_outputs import APPOINTMENT_INTENTS


def appointment_validation_node(state: MessageGraphState) -> dict:
    category = state.get("message_category")
    intent = APPOINTMENT_INTENTS.get(category)
    customer_handoff = (
        state.get("next_action") == "collect_appointment_details"
        and state.get("customer_status") in {"existing", "new"}
    )
    details_followup = (
        state.get("pending_question") == "appointment_details"
        and category in {"service_request", "confirmation"}
    )
    if (
        intent is None
        and (category == "confirmation" or customer_handoff or details_followup)
        and state.get("current_flow") == "appointment_services"
        and state.get("appointment_intent") in APPOINTMENT_INTENTS.values()
    ):
        intent = state["appointment_intent"]
    next_action = intent
    booking_confirmed = (
        category == "confirmation"
        and intent == "book_appointment"
        and all(
            state.get(field)
            for field in (
                "service_id",
                "business_staff_id",
                "starts_at",
                "ends_at",
            )
        )
    )
    if intent in {"book_appointment", "check_availability"} and not booking_confirmed:
        next_action = "collect_appointment_details"
    return {
        "appointment_intent": intent,
        "next_action": next_action or "clarify_appointment_intent",
        "pending_question": None if intent else "appointment_intent",
    }
