from langchain_core.messages import AIMessage

from src.helpers.workflow import clear_appointment_state
from src.state import MessageGraphState


def _api_pending(message: str) -> dict:
    return {**clear_appointment_state(), "messages": [AIMessage(content=message)]}


def book_appointment_node(state: MessageGraphState) -> dict:
    return _api_pending(
        "La integración para agendar citas está pendiente. No he creado ninguna cita."
    )


def check_availability_node(state: MessageGraphState) -> dict:
    return _api_pending(
        "La integración para consultar horarios está pendiente. "
        "No puedo confirmar disponibilidad."
    )


def reschedule_appointment_node(state: MessageGraphState) -> dict:
    return _api_pending(
        "La integración para reprogramar citas está pendiente. No he cambiado ninguna cita."
    )


def cancel_appointment_node(state: MessageGraphState) -> dict:
    return _api_pending(
        "La integración para cancelar citas está pendiente. No he cancelado ninguna cita."
    )


def view_appointment_node(state: MessageGraphState) -> dict:
    return _api_pending(
        "La integración para consultar tus citas está pendiente. "
        "No puedo mostrar citas confirmadas."
    )
