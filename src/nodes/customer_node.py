from langchain_anthropic import ChatAnthropic
# from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

from src.state import MessageGraphState
from src.nodes.tools import customer_tools
from src.helpers.language import LANGUAGE_DIRECTIVE


CUSTOMER_SYSTEM_PROMPT = """You are a helpful assistant for a business's customer support.
Your only job right now is to identify the customer before any appointment is handled.

Follow this process:
1. If you do not yet have the user's email address, ask for it politely.
2. Once you have the email, call find_customer with it.
3. If an existing customer is found, greet them by name (if available) and confirm you have
   their details. Do not ask for anything else.
4. If no customer is found, ask for their first and last name, then call create_customer.
5. Never check availability or book appointments yourself — that happens after this step.

Keep responses concise and friendly, suitable for a chat conversation. Use clean formats for
the messages, don't use special characters in the response.
"""


def customer_node(state: MessageGraphState):
    business_id = state["business_id"]

    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
    # llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    llm_with_tools = llm.bind_tools(customer_tools)

    messages = [SystemMessage(content=CUSTOMER_SYSTEM_PROMPT), LANGUAGE_DIRECTIVE] + state["messages"]

    response = llm_with_tools.invoke(
        messages, config={"configurable": {"business_id": str(business_id)}}
    )

    return {"messages": [response]}
