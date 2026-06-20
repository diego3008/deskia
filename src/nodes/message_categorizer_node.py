from src.state import MessageGraphState
from langchain_anthropic import ChatAnthropic
from src.agents.message_categorizer import message_categorizer_agent
from langchain_core.messages import AIMessage

def message_categorizer_node(state: MessageGraphState):
    
    body = state['current_message']

    if not body:
        state['message_category'] = "no message"
        return state

    result = message_categorizer_agent().invoke({"message": body})

    state['message_category'] = result.category.value

    return state
