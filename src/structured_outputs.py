
from enum import Enum

from pydantic import BaseModel, Field


class MessageCategory(str, Enum):
    service_request = "service_request"   
    confirmation = "confirmation"
    decline = "decline"                   
    customer_complaint = "customer_complaint"
    customer_feedback = "customer_feedback"
    greeting = "greeting"
    unrelated = "unrelated"


class CategorizerMessageOutput(BaseModel):
    category: MessageCategory = Field(..., description="The category assigned to the message, indicating its type based on predefined rules.")