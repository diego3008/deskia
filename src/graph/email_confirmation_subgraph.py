from langgraph.graph import END, START, StateGraph

from src.nodes.email_confirmation_nodes import (
    route_email_draft,
    send_email_node,
    write_email_node,
)
from src.state import MessageGraphState


class EmailConfirmationGraph:
    def __init__(self):
        workflow = StateGraph(MessageGraphState)
        workflow.add_node("write_email", write_email_node)
        workflow.add_node("send_email", send_email_node)
        workflow.add_edge(START, "write_email")
        workflow.add_conditional_edges(
            "write_email",
            route_email_draft,
            {"send_email": "send_email", "end": END},
        )
        workflow.add_edge("send_email", END)

        self.graph = workflow.compile()


email_confirmation_graph = EmailConfirmationGraph().graph
