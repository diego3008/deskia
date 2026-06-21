import os
from typing import Literal
from langchain.tools import tool
from langgraph.graph import END, START, StateGraph
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import ToolNode, tools_condition

from src.nodes import NODES
from src.state import MessageGraphState
from src.nodes.tools import messages_tools

LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")

class TelegramSupportGraph:

    def __init__(self):

        workflow = StateGraph(MessageGraphState)

        workflow.add_node("message_listener", NODES["message_listener"])
        workflow.add_node("category", NODES["message_categorizer"])
        workflow.add_node("message_writer", NODES["message_writer"])
        workflow.add_node("inquiry_node", NODES["inquiry"])
        workflow.add_node("message_tools", ToolNode(messages_tools))
        workflow.add_node("fallback_node", NODES["fallback"])
        workflow.add_edge(START, "message_listener")
        workflow.add_edge("message_listener", "category")

        workflow.add_conditional_edges(
            "category",
            self.route_by_message_category,
            {
                "inquiry": "inquiry_node",
                "customer_complaint": "message_writer",
                "customer_feedback": "message_writer",
                "greeting": "message_writer",
                "unrelated": "fallback_node",
            }
        )

        workflow.add_conditional_edges(
            "inquiry_node",
            tools_condition,
            {
                "tools": "message_tools",
                END: END,
            }
        )

        workflow.add_edge("message_tools", "inquiry_node")  # <- changed from END
        workflow.add_edge("fallback_node", END)
        workflow.add_edge("message_writer", END)

        self.graph = workflow.compile()

    def route_by_message_category(
        self, state: MessageGraphState
    ) -> Literal["inquiry", "customer_complaint", "customer_feedback", "greeting", "unrelated"]:
        category = state["message_category"]
        valid_categories = {"inquiry", "customer_complaint", "customer_feedback", "greeting"}
        return category if category in valid_categories else "unrelated"


message_graph = TelegramSupportGraph().graph