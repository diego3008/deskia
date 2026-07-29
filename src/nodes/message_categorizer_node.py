from src.state import MessageGraphState
from langchain_anthropic import ChatAnthropic
from src.agents.message_categorizer import message_categorizer_agent
from src.helpers import helpers

SERVICE_CATEGORIES = {"service_request", "confirmation", "decline"}
TOPIC_CHANGE_CATEGORIES = {"greeting", "customer_complaint", "customer_feedback"}


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
    category = result.category.value
    state['message_category'] = category

    
    if category in TOPIC_CHANGE_CATEGORIES:
        state['active_flow'] = None
        state['service_plan'] = None
    elif category in SERVICE_CATEGORIES or prev_flow == "booking":
        state['active_flow'] = "booking"

    # C1: when a brand-new service flow starts (not a mid-flow continuation),
    # drop any stale appointment/slot gates left from an abandoned earlier flow.
    # Within-flow staleness is backstopped by the API re-validating availability.
    if category == "service_request" and prev_flow != "booking":
        state['active_appointment'] = None
        state['confirmed_slot'] = None
        state['service_plan'] = None
        state["customer"] = None

    return state
