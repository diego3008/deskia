from src.state import MessageGraphState
from src.agents.message_categorizer import message_categorizer_agent
from src.helpers import helpers

APPOINTMENT_CATEGORIES = {"new_appointment", "reschedule_appointment"}
FLOW_EXIT_CATEGORIES = {
    "greeting",
    "customer_complaint",
    "customer_feedback",
    "decline",
    "cancel_appointment",
}


def message_categorizer_node(state: MessageGraphState):
    body = state["current_message"]

    if not body:
        state["message_category"] = "no message"
        return state

    history = helpers["build_recent_history"](state["messages"])
    result = message_categorizer_agent().invoke(
        {"message": body, "history": history}
    )
    category = result.category.value
    state["message_category"] = category

    if category in FLOW_EXIT_CATEGORIES:
        state["current_flow"] = None
        state["pending_question"] = None
        state["next_action"] = None
        state["active_appointment"] = None
        state["confirmed_slot"] = None
    elif category in APPOINTMENT_CATEGORIES:
        state["current_flow"] = "appointment_services"

    return state
