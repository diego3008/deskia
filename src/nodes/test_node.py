from sre_parse import State

from langchain_anthropic import ChatAnthropic
from dotenv import load_dotenv
import os
load_dotenv()


llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)

def call_llm(state: State) -> dict:
    """Send messages to the LLM and return the response."""
    response = llm.invoke(state["messages"])
    return {
        "messages": [response],
        "step_log": ["call_llm"],
    }
 
 
def summarise(state: State) -> dict:
    """Log the last assistant message length as a sanity check."""
    last = state["messages"][-1]
    chars = len(last.content)
    print(f"\n✅ Response received ({chars} chars): {last.content[:120]}...")
    return {"step_log": ["summarise"]}
 