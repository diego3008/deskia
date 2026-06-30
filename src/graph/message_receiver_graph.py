import os
from typing import Literal
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.nodes import NODES
from src.state import MessageGraphState
from src.nodes.tools import messages_tools
from src.graph.customer_graph import customer_graph

LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")

SERVICE_CATEGORIES = {"service_request", "confirmation", "decline"}
WRITER_CATEGORIES = {"greeting", "customer_complaint", "customer_feedback"}


class TelegramSupportGraph:

    def __init__(self):

        workflow = StateGraph(MessageGraphState)

        workflow.add_node("message_listener", NODES["message_listener"])
        workflow.add_node("category", NODES["message_categorizer"])
        workflow.add_node("message_writer", NODES["message_writer"])
        workflow.add_node("customer_subgraph", customer_graph)
        workflow.add_node("enquiry_node", NODES["enquiry"])
        workflow.add_node("message_tools", ToolNode(messages_tools))
        workflow.add_node("fallback_node", NODES["fallback"])

        workflow.add_edge(START, "message_listener")
        workflow.add_edge("message_listener", "category")

        workflow.add_conditional_edges(
            "category",
            self.route_by_category,
            {
                "customer_subgraph": "customer_subgraph",
                "enquiry_node": "enquiry_node",
                "message_writer": "message_writer",
                "fallback_node": "fallback_node",
            },
        )

        workflow.add_conditional_edges(
            "customer_subgraph",
            self.route_after_customer,
            {
                "enquiry_node": "enquiry_node",
                END: END,
            },
        )

        workflow.add_conditional_edges(
            "enquiry_node",
            tools_condition,
            {
                "tools": "message_tools",
                END: END,
            },
        )

        workflow.add_edge("message_tools", "enquiry_node")
        workflow.add_edge("fallback_node", END)
        workflow.add_edge("message_writer", END)

        self.graph = workflow.compile()

        

    def route_by_category(
        self, state: MessageGraphState
    ) -> Literal["customer_subgraph", "enquiry_node", "message_writer", "fallback_node"]:
        category = state.get("message_category")

        if category in WRITER_CATEGORIES:
            return "message_writer"

        if state.get("active_flow") == "booking" or category in SERVICE_CATEGORIES:
            if state.get("customer") is None:
                return "customer_subgraph"
            return "enquiry_node"

        return "fallback_node"

    def route_after_customer(
        self, state: MessageGraphState
    ) -> Literal["enquiry_node", "__end__"]:
        if state.get("customer") is not None:
            return "enquiry_node"
        return END


message_graph = TelegramSupportGraph().graph
