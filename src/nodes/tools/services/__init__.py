

from src.nodes.tools.services.services_tools import (
    check_available_appointments,
    create_appointment,
    find_customer_appointment,
    reschedule_appointment,
)


# Union of every tool any stage can bind (+ create_appointment for the booking path).
# The ToolNode must be able to execute anything get_tools_for_stage() can offer.
tools = [
    find_customer_appointment,
    check_available_appointments,
    reschedule_appointment,
    create_appointment,
]