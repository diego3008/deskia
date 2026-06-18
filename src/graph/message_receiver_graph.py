import os

from langgraph.graph import END, START, StateGraph

from src.nodes import NODES
from src.state import MessageGraphState

LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")


class TelegramSupportGraph:

    def __init__(self):
        workflow = StateGraph(MessageGraphState)

        workflow.add_node("message_listener", NODES["message_listener"])
        workflow.add_node("category", NODES["message_categorizer"])
        workflow.add_node("message_writer", NODES["message_writer"])

        workflow.add_edge(START, "message_listener")
        workflow.add_edge("message_listener", "category")
        workflow.add_edge("category", "message_writer")
        workflow.add_edge("message_writer", END)

        self.graph = workflow.compile()


message_graph = TelegramSupportGraph().graph