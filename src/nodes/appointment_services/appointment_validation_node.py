from src.state import MessageGraphState
from src.structured_outputs import APPOINTMENT_INTENTS


def appointment_validation_node(state: MessageGraphState) -> dict:
    category = state.get("message_category")
    intent = APPOINTMENT_INTENTS.get(category)
    customer_handoff = (
        state.get("next_action") == "collect_appointment_details"
        and state.get("customer_status") in {"existing", "new"}
    )
    if (
        intent is None
        and (category == "confirmation" or customer_handoff)
        and state.get("current_flow") == "appointment_services"
        and state.get("appointment_intent") in APPOINTMENT_INTENTS.values()
    ):
        intent = state["appointment_intent"]
    return {
        "appointment_intent": intent,
        "next_action": intent or "clarify_appointment_intent",
        "pending_question": None if intent else "appointment_intent",
    }
