from langgraph.graph import END, START, StateGraph
from src.nodes import NODES
from src.state import MessageGraphState
import os

LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")

class TelegramSupportGraph:

    def __init__(self):
        workflow = StateGraph(MessageGraphState)
        
        workflow.add_node("message_listener", NODES["message_listener"])
        workflow.add_node("category", NODES["message_categorizer"])
        workflow.add_edge(START, "message_listener")
        workflow.add_edge("message_listener", "category")
        workflow.add_edge("category", END)

        self.graph = workflow.compile()

message_graph = TelegramSupportGraph().graph