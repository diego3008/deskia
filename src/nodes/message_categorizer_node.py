from src.state import MessageGraphState
from langchain_anthropic import ChatAnthropic
from src.agents.message_categorizer import message_categorizer_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

SERVICE_CATEGORIES = {"service_request", "confirmation", "decline"}
TOPIC_CHANGE_CATEGORIES = {"greeting", "customer_complaint", "customer_feedback"}


def message_categorizer_node(state: MessageGraphState):
    body = state['current_message']

    if not body:
        state['message_category'] = "no message"
        return state

    # Build conversation history from last 6 messages
    recent = [
        m for m in state["messages"][-6:]
        if not isinstance(m, SystemMessage)
    ]
    history = "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'Agent'}: {m.content}"
        for m in recent
    ) or "No previous messages."

    result = message_categorizer_agent().invoke({
        "message": body,
        "history": history  # ← pass history
    })

    category = result.category.value
    state['message_category'] = category

    # Track the booking flow across turns so mid-flow replies (a bare email,
    # a name) stay in the flow even if the categorizer mislabels them.
    if category in TOPIC_CHANGE_CATEGORIES:
        state['active_flow'] = None
    elif category in SERVICE_CATEGORIES or state.get('active_flow') == "booking":
        state['active_flow'] = "booking"

    return state
