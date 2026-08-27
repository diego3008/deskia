from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.nodes import SERVICES_REQUEST_NODES
from src.nodes.tools.services import tools
from src.state import MessageGraphState


class AppointmentServicesSubgraph:
    def __init__(self):
        workflow = StateGraph(MessageGraphState)
        workflow.add_node(
            "appointment_agent",
            SERVICES_REQUEST_NODES["services_request_node"],
        )
        workflow.add_node("tools", ToolNode(tools))

        workflow.add_edge(START, "appointment_agent")
        workflow.add_conditional_edges(
            "appointment_agent",
            tools_condition,
            {
                "tools": "tools",
                END: END,
            },
        )
        workflow.add_edge("tools", "appointment_agent")

        self.graph = workflow.compile()


appointment_services_subgraph = AppointmentServicesSubgraph().graph
