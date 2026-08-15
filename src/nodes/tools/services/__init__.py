

from src.nodes.tools.services.services_tools import (
    check_available_appointments,
    create_appointment,
    find_customer_appointment,
    reschedule_appointment,
)


# The deterministic appointment subgraph is the sole appointment mutation path.
# Do not bind the historical functions to an LLM loop.
tools = []
