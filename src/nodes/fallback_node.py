from src.state import MessageGraphState

def fallback_node(state: MessageGraphState) -> MessageGraphState:
    # Runs when classify_message couldn't confidently assign
    # a known category (e.g. category is None, "unknown", or
    # something not in your routing map)
    return {
        "messages": state["messages"] + [
            {"role": "assistant", "content": "Sorry, I'm not sure how to help with that yet."}
        ]
    }