import os
from datetime import datetime

import httpx
from langchain_core.messages import AIMessage

from src.helpers.workflow import clear_appointment_state
from src.models.appointments import AppointmentCreate
from src.state import MessageGraphState

API_URL = os.getenv("DESKIA_API_URL")


def _api_pending(message: str) -> dict:
    return {**clear_appointment_state(), "messages": [AIMessage(content=message)]}


async def book_appointment_node(state: MessageGraphState) -> dict:
    fields = {
        field: state.get(field)
        for field in (
            "business_id",
            "starts_at",
            "ends_at",
            "customer_id",
            "business_staff_id",
            "service_id",
        )
    }
    if any(value is None for value in fields.values()):
        return {
            "messages": [
                AIMessage(
                    content=(
                        "Necesito negocio, cliente, servicio, personal, inicio y fin "
                        "para agendar la cita."
                    )
                )
            ]
        }

    try:
        appointment = AppointmentCreate(**fields)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{API_URL}/appointments/book",
                json=appointment.model_dump(mode="json"),
            )
            response.raise_for_status()
            saved_appointment = response.json()
            if (
                not isinstance(saved_appointment, dict)
                or not saved_appointment.get("starts_at")
                or not saved_appointment.get("ends_at")
            ):
                raise ValueError("invalid booking response")
    except (httpx.HTTPError, TypeError, ValueError):
        return {
            "messages": [AIMessage(content="No pude agendar la cita en este momento.")]
        }

    return {
        **clear_appointment_state(),
        "messages": [AIMessage(content=f"Listo!. Tu cita de {state.get("service_name")} para el día {state.get("starts_at").date()} ya fue agendada.")],
    }


async def check_availability_node(state: MessageGraphState) -> dict:
    business_id = state.get("business_id")
    starts_at = state.get("starts_at")
    service_name = state.get("service_name")

    if not business_id or not starts_at or not service_name:
        return _api_pending(
            "Necesito la fecha, hora y servicio para consultar disponibilidad."
        )

    try:
        start = (
            starts_at
            if isinstance(starts_at, datetime)
            else datetime.fromisoformat(starts_at)
        )
    except (TypeError, ValueError):
        return _api_pending(
            "Necesito una fecha y hora válidas para consultar disponibilidad."
        )

    if start.utcoffset() is None:
        return _api_pending(
            "Necesito confirmar la zona horaria de la cita antes de consultar disponibilidad."
        )
    requested_start_date = start.isoformat()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{API_URL}/appointments/validate-date",
                params={
                    "business_id": str(business_id),
                    "requested_start_date": requested_start_date,
                    "service_name": service_name,
                },
            )
            response.raise_for_status()
            availability = response.json()
    except Exception:
        return _api_pending("No pude confirmar la disponibilidad en este momento.")
    if isinstance(availability, bool) and not availability:
        return {
            "service_id": None,
            "business_staff_id": None,
            "ends_at": None,
            "messages": [
                AIMessage(content="El horario solicitado no está disponible.")
            ],
        }

    if (
        not isinstance(availability, dict)
        or availability.get("available") is not True
        or not availability.get("service_id")
        or not availability.get("business_staff_id")
        or not availability.get("ends_at")
    ):
        return _api_pending("No pude confirmar la disponibilidad en este momento.")

    try:
        ends_at = (
            availability["ends_at"]
            if isinstance(availability["ends_at"], datetime)
            else datetime.fromisoformat(availability["ends_at"])
        )
    except (TypeError, ValueError):
        return _api_pending("No pude confirmar la disponibilidad en este momento.")

    booking_confirmation = state.get("appointment_intent") == "book_appointment"
    return {
        "service_id": availability["service_id"],
        "ends_at": ends_at,
        "business_staff_id": availability["business_staff_id"],
        "pending_question": "booking_confirmation" if booking_confirmation else None,
        "next_action": "confirm_booking" if booking_confirmation else "check_availability",
        "messages": [
            AIMessage(
                content=(
                    "El horario solicitado está disponible. ¿Deseas que lo reserve?"
                    if booking_confirmation
                    else "El horario solicitado está disponible."
                )
            )
        ],
    }


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
