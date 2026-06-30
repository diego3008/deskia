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
    workflow.add_edge("customer_tools", "customer_node")

    return workflow.compile()


customer_graph = build_customer_graph()
