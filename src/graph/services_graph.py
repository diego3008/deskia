
from langgraph.graph import StateGraph

from src.state import MessageGraphState


class ServicesGraph:
    """
    A graph that represents the flow of services interactions.
    """

    def __init__(self):
        
        workflow = StateGraph(MessageGraphState)
        

        graph = workflow.compile()

services_graph = ServicesGraph().graph