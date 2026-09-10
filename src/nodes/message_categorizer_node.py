import unicodedata

from src.state import MessageGraphState
from src.agents.message_categorizer import message_categorizer_agent
from src.helpers import helpers
from src.helpers.workflow import clear_appointment_state, customer_validation_pending
from src.structured_outputs import APPOINTMENT_CATEGORIES, APPOINTMENT_INTENTS

FLOW_EXIT_CATEGORIES = {
    "greeting",
    "customer_complaint",
    "customer_feedback",
    "decline",
    "service_inquiry",
}


def _is_booking_confirmation(state: MessageGraphState, category: str) -> bool:
    if (
        category == "new_appointment"
        and state.get("current_flow") == "appointment_services"
        and state.get("appointment_intent") == "check_availability"
        and state.get("next_action") == "check_availability"
        and all(
            state.get(field)
            for field in (
                "service_id",
                "business_staff_id",
                "starts_at",
                "ends_at",
            )
        )
    ):
        return True
    if state.get("pending_question") != "booking_confirmation":
        return False
    if category == "confirmation":
        return True

    current = state.get("current_message", "")
    text = current.content if hasattr(current, "content") else str(current)
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.strip().casefold())
        if not unicodedata.combining(char)
    )
    return (
        category in {"new_appointment", "check_availability", "service_request"}
        and text.startswith(("sí", "si", "claro", "ok", "confirmo", "adelante"))
        and any(word in text for word in ("reserv", "agend", "apart"))
    )


def message_categorizer_node(state: MessageGraphState):
    body = state["current_message"]

    if not body:
        state["message_category"] = "no message"
        return state

    history = helpers["build_recent_history"](
        state["messages"], state.get("conversation_summary")
    )
    result = message_categorizer_agent().invoke(
        {"message": body, "history": history}
    )
    category = result.category.value
    if _is_booking_confirmation(state, category):
        category = "confirmation"
        state["appointment_intent"] = "book_appointment"
    state["message_category"] = category

    details_pending = (
        state.get("current_flow") == "appointment_services"
        and state.get("pending_question") == "appointment_details"
        and category in {"service_request", "confirmation"}
    )
    if details_pending:
        return state
    if category in FLOW_EXIT_CATEGORIES:
        state.update(clear_appointment_state())
    elif category in APPOINTMENT_CATEGORIES:
        identity_pending = customer_validation_pending(state)
        intent = APPOINTMENT_INTENTS.get(category)
        if category == "service_request" and identity_pending:
            intent = state.get("appointment_intent")
        if intent is None or intent != state.get("appointment_intent"):
            reset = clear_appointment_state()
            if identity_pending:
                reset.pop("pending_question")
                reset.pop("next_action")
            state.update(reset)
        state["appointment_intent"] = intent
        state["current_flow"] = "appointment_services"

    return state
