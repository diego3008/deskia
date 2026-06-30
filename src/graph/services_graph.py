from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.nodes import SERVICES_REQUEST_NODES
from src.nodes.tools.services import tools
from src.state import MessageGraphState


class ServicesGraph:
    """
    A graph that represents the flow of services interactions.
    """

    def __init__(self):

        workflow = StateGraph(MessageGraphState)
        workflow.add_node("services_request_node", SERVICES_REQUEST_NODES["services_request_node"])
        workflow.add_node("tools", ToolNode(tools))
        workflow.add_edge(START, "services_request_node")
        workflow.add_conditional_edges(
            "services_request_node",
            tools_condition,
            {
                "tools": "tools", 
                END: END
            } 
        )
        workflow.add_edge("tools", "services_request_node")
        
        self.graph = workflow.compile()

services_graph = ServicesGraph().graph