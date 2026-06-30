from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage

from src.state import MessageGraphState
from src.nodes.tools import messages_tools


ENQUIRY_SYSTEM_PROMPT = """You are a helpful assistant for a business's customer support, 
specializing in handling appointment-related inquiries.

You have two tools available:
- check_available_appointments: checks if a specific date/time is open
- create_appointment: books the appointment once availability is confirmed

Follow this process:
1. If the user has provided a date, and time, call check_available_appointments first.
2. If the requested time IS available:
   - If the user already clearly wants to book it (e.g. they asked to "book" or "schedule" 
     an appointment, not just "check"), call create_appointment immediately to complete the booking, 
     then confirm it to them.
   - Otherwise, confirm it's available and ask if they'd like to book it.
3. If the requested time is NOT available, apologize briefly and ask if they'd like to try 
   a different date or time — never just say "no" and stop.
4. Always reference the specific date being discussed so the user knows what you're confirming.

Keep responses concise and friendly, suitable for a chat conversation. Use clean formats for 
the messages, don't use special characters in the response.
"""


def enquiry_node(state: MessageGraphState):

      business_id = state["business_id"]

      llm = ChatAnthropic(
         model="claude-haiku-4-5-20251001", temperature=0
      )

      
      llm_with_tools = llm.bind_tools(messages_tools)

      messages = [SystemMessage(
         content=ENQUIRY_SYSTEM_PROMPT)] + state["messages"]

      response = llm_with_tools.invoke(messages,
                           config={"configurable": {"business_id": str(business_id)}})

      return {"messages": [response]}
