

from src.state import MessageGraphState


def message_listener_node(state: MessageGraphState) -> MessageGraphState:
    
    last_message = state["messages"][-1]
    if str(last_message).strip() == "":
        return state
    
    state["current_message"] = str(getattr(last_message, "content", last_message))

    return state
