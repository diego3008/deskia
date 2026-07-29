from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.state import MessageGraphState
from src.nodes.customer_node import customer_node
from src.nodes.tools import customer_tools


def build_customer_graph():
    workflow = StateGraph(MessageGraphState)

    workflow.add_node("customer_node", customer_node)
    workflow.add_node("customer_tools", ToolNode(customer_tools))

    workflow.add_edge(START, "customer_node")
    workflow.add_conditional_edges(
        "customer_node",
        tools_condition,
        {
            "tools": "customer_tools",
            END: END,
        },
    )
    workflow.add_conditional_edges(
        "customer_tools",
        route_after_tools,
        {
            "customer_node": "customer_node",
            END: END,
        },
    )

    return workflow.compile()


def route_after_tools(state: MessageGraphState) -> Literal["customer_node", "__end__"]:
    # Customer already identified — stop here so the outer graph can hand off to
    # services_subgraph without customer_node adding a second, redundant AIMessage
    # on top of the one find_customer/create_customer already produced.
    if state.get("customer") is not None:
        return END
    return "customer_node"

customer_graph = build_customer_graph()
