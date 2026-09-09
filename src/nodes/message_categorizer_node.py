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
    state["message_category"] = category

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
