import os
from typing import Literal
from langgraph.graph import END, START, StateGraph

from src.nodes import NODES
from src.state import MessageGraphState
from src.graph.customer_graph import customer_graph
from src.graph.services_graph import services_graph

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
        workflow.add_node("services_subgraph", services_graph)
        workflow.add_node("fallback_node", NODES["fallback"])

        workflow.add_edge(START, "message_listener")
        workflow.add_edge("message_listener", "category")

        workflow.add_conditional_edges(
            "category",
            self.route_by_category,
            {
                "customer_subgraph": "customer_subgraph",
                "services_subgraph": "services_subgraph",
                "message_writer": "message_writer",
                "fallback_node": "fallback_node",
            },
        )

        workflow.add_conditional_edges(
            "customer_subgraph",
            self.route_after_customer,
            {
                "services_subgraph": "services_subgraph",
                END: END,
            },
        )

        workflow.add_edge("services_subgraph", END)
        workflow.add_edge("fallback_node", END)
        workflow.add_edge("message_writer", END)

        self.graph = workflow.compile()

    def route_by_category(
        self, state: MessageGraphState
    ) -> Literal["customer_subgraph", "services_subgraph", "message_writer", "fallback_node"]:
        category = state.get("message_category")

        if category in WRITER_CATEGORIES:
            return "message_writer"

        if state.get("active_flow") == "booking" or category in SERVICE_CATEGORIES:
            if state.get("customer") is None:
                return "customer_subgraph"
            return "services_subgraph"

        return "fallback_node"

    def route_after_customer(
        self, state: MessageGraphState
    ) -> Literal["services_subgraph", "__end__"]:
        if state.get("customer") is not None:
            return "services_subgraph"
        return END


message_graph = TelegramSupportGraph().graph
