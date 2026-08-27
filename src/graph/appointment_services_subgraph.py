from langgraph.graph import StateGraph, START, END

from src.state import MessageGraphState

class AppointmentServicesSubgraph:


    def __init__(self):
        workflow = StateGraph(MessageGraphState)

        self.graph = workflow.compile()
        pass

    

appointment_services_subgraph = AppointmentServicesSubgraph.graph