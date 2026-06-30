

from src.nodes.tools.services.services_tools import (
    check_available_appointments,
    create_appointment,
    find_customer_appointment,
    reschedule_appointment,
)


# All four services tools, bound every turn (ReAct loop; ordering enforced by per-tool guards).
tools = [
    find_customer_appointment,
    check_available_appointments,
    reschedule_appointment,
    create_appointment,
]
