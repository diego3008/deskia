from typing import Annotated, List, TypedDict
from uuid import UUID

from langgraph.graph import add_messages
from pydantic import BaseModel


class State(TypedDict):
    messages: Annotated[list, add_messages]  # reducer: appends, never overwrites
    step_log: Annotated[list[str], list.__add__]  # accumulates node names visited


    

class IncomingMessage(BaseModel):
    """
    Normalized message sent to the agent service.
    Platform-agnostic — the agent never deals with raw Telegram objects.
    """
    platform: str
    chat_id: str
    user_id: str
    username: str | None = None
    metadata: dict = {}
    role: str = "user"
    content: str

class OutBoundsMessge(TypedDict):
    response: str

class MessageGraphState(TypedDict):
    messages: Annotated[list, add_messages]
    current_message: str
    message_category: str
    message_response: str
    business_id: UUID