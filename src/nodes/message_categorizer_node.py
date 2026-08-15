from src.state import MessageGraphState
from src.agents.message_categorizer import message_categorizer_agent
from src.helpers import helpers
from src.structured_outputs import MessageCategory


APPOINTMENT_CATEGORIES = {
    MessageCategory.BOOK_APPOINTMENT,
    MessageCategory.CHECK_AVAILABILITY,
    MessageCategory.RESCHEDULE_APPOINTMENT,
    MessageCategory.CANCEL_APPOINTMENT,
    MessageCategory.VIEW_APPOINTMENT,
}

TOPIC_CHANGE_CATEGORIES = {
    MessageCategory.GREETING,
    MessageCategory.OUT_OF_SCOPE,
    MessageCategory.SERVICE_INFORMATION,
    MessageCategory.SERVICE_DETAILS,
    MessageCategory.BUSINESS_INFORMATION,
}


def message_categorizer_node(state: MessageGraphState):
    body = state['current_message']

    if not body:
        state['message_category'] = "no message"
        return state

    # Build conversation history from last 6 messages
    history = helpers["build_recent_history"](state["messages"])

    result = message_categorizer_agent().invoke({
        "message": body,
        "history": history
    })

    prev_flow = state.get('active_flow')
    category = MessageCategory(result.category.value)
    state['message_category'] = category.value
    
    if category in TOPIC_CHANGE_CATEGORIES:
        state['active_flow'] = None
        state['service_plan'] = None
    elif category in APPOINTMENT_CATEGORIES or (
        category == MessageCategory.PROVIDE_INFORMATION and prev_flow == "booking"
    ):
        state['active_flow'] = "booking"

    if category in APPOINTMENT_CATEGORIES and prev_flow != "booking":
        state['active_appointment'] = None
        state['confirmed_slot'] = None
        state['service_plan'] = None

    return state
