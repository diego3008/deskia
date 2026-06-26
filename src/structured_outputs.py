
from enum import Enum

from pydantic import BaseModel, Field


class MessageCategory(str, Enum):
    inquiry = "inquiry"
    confirmation = "confirmation"        # "yes", "sure", "go ahead", "ok"
    cancellation = "cancellation"        # "no", "cancel", "never mind"
    customer_complaint = "customer_complaint"
    customer_feedback = "customer_feedback"
    greeting = "greeting"
    unrelated = "unrelated"

class CategorizerMessageOutput(BaseModel):
    category: MessageCategory = Field(..., description="The category assigned to the message, indicating its type based on predefined rules.")