import os
from datetime import datetime

import httpx
from langchain_core.messages import AIMessage
from tzlocal import get_localzone

from src.helpers.workflow import clear_appointment_state
from src.models.appointments import AppointmentCreate
from src.state import MessageGraphState

API_URL = os.getenv("DESKIA_API_URL")
LOCAL_TZ = get_localzone()


def _api_pending(message: str) -> dict:
    return {**clear_appointment_state(), "messages": [AIMessage(content=message)]}


def _availability_error(state: MessageGraphState, message: str) -> dict:
    if (
        state.get("appointment_intent") == "reschedule_appointment"
        and state.get("active_appointment")
    ):
        return {
            "service_id": None,
            "business_staff_id": None,
            "ends_at": None,
            "pending_question": "appointment_details",
            "next_action": "collect_appointment_details",
            "messages": [AIMessage(content=message)],
        }
    return _api_pending(message)


async def _find_customer_appointment(state: MessageGraphState) -> dict | None:
    business_id = state.get("business_id")
    customer_id = state.get("customer_id") or (state.get("customer") or {}).get("id")
    if not business_id or not customer_id:
        raise ValueError("missing customer or business")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{API_URL}/appointments/find_customer_appointment",
            params={"customer_id": str(customer_id), "business_id": str(business_id)},
        )
        response.raise_for_status()
        appointment = response.json()

    if not appointment:
        return None
    field_map = {
        "appointment_id": "id",
        "starts_at": "starts_at",
        "service_name": "service_name",
        "staff_name": "staff_name",
    }
    if not isinstance(appointment, dict) or any(
        not isinstance(appointment.get(field), str) or not appointment[field].strip()
        for field in field_map
    ):
        raise ValueError("invalid appointment response")
    normalized = {
        target: appointment[source].strip() for source, target in field_map.items()
    }
    starts_at = datetime.fromisoformat(normalized["starts_at"])
    if starts_at.utcoffset() is None:
        raise ValueError("appointment timezone missing")
    normalized["starts_at"] = starts_at.astimezone(LOCAL_TZ).isoformat()
    return normalized


def _service_name(appointment: dict) -> str | None:
    name = appointment.get("service_name") or (
        appointment.get("service") or {}
    ).get("name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _appointment_label(appointment: dict) -> str:
    service = _service_name(appointment)
    starts_at = datetime.fromisoformat(appointment["starts_at"])
    return f"{service or 'servicio'} del {starts_at:%Y-%m-%d %H:%M}"


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
        return _availability_error(
            state, "No pude confirmar la disponibilidad en este momento."
        )
    if isinstance(availability, bool) and not availability:
        retry = (
            {
                "pending_question": "appointment_details",
                "next_action": "collect_appointment_details",
            }
            if state.get("appointment_intent")
            in {"book_appointment", "reschedule_appointment"}
            else {}
        )
        return {
            "service_id": None,
            "business_staff_id": None,
            "ends_at": None,
            **retry,
            "messages": [
                AIMessage(
                    content="El horario solicitado no está disponible. Indícame otro horario."
                )
            ],
        }

    if (
        not isinstance(availability, dict)
        or availability.get("available") is not True
        or not availability.get("service_id")
        or not availability.get("business_staff_id")
        or not availability.get("ends_at")
    ):
        return _availability_error(
            state, "No pude confirmar la disponibilidad en este momento."
        )

    try:
        ends_at = (
            availability["ends_at"]
            if isinstance(availability["ends_at"], datetime)
            else datetime.fromisoformat(availability["ends_at"])
        )
    except (TypeError, ValueError):
        return _availability_error(
            state, "No pude confirmar la disponibilidad en este momento."
        )

    intent = state.get("appointment_intent")
    pending_question = {
        "book_appointment": "booking_confirmation",
        "reschedule_appointment": "reschedule_confirmation",
    }.get(intent)
    next_action = {
        "book_appointment": "confirm_booking",
        "reschedule_appointment": "confirm_reschedule",
    }.get(intent, "check_availability")
    if intent == "book_appointment":
        message = "El horario solicitado está disponible. ¿Deseas que lo reserve?"
    elif intent == "reschedule_appointment":
        message = "El horario solicitado está disponible. ¿Deseas reprogramar tu cita?"
    else:
        message = "El horario solicitado está disponible."
    return {
        "service_id": availability["service_id"],
        "ends_at": ends_at,
        "business_staff_id": availability["business_staff_id"],
        "pending_question": pending_question,
        "next_action": next_action,
        "messages": [AIMessage(content=message)],
    }


async def lookup_appointment_node(state: MessageGraphState) -> dict:
    try:
        appointment = await _find_customer_appointment(state)
    except (httpx.HTTPError, TypeError, ValueError):
        return {"messages": [AIMessage(content="No pude consultar tu cita ahora.")]}
    if appointment is None:
        return _api_pending("No encontré una cita próxima para ti.")

    result = {
        "active_appointment": appointment,
        "service_name": _service_name(appointment),
    }
    if state.get("appointment_intent") == "cancel_appointment":
        return {
            **result,
            "pending_question": "cancel_confirmation",
            "next_action": "cancel_appointment",
            "messages": [
                AIMessage(
                    content=(
                        f"Encontré tu cita de {_appointment_label(appointment)}. "
                        "¿Confirmas que deseas cancelarla?"
                    )
                )
            ],
        }
    return {
        **result,
        "pending_question": None,
        "next_action": "collect_appointment_details",
    }


async def reschedule_appointment_node(state: MessageGraphState) -> dict:
    if not (
        state.get("message_category") == "confirmation"
        and state.get("pending_question") == "reschedule_confirmation"
    ):
        return {
            "pending_question": "reschedule_confirmation",
            "next_action": "reschedule_appointment",
            "messages": [
                AIMessage(content="¿Confirmas que deseas reprogramar la cita?")
            ],
        }
    appointment_id = (state.get("active_appointment") or {}).get("id")
    business_id = state.get("business_id")
    starts_at = state.get("starts_at")
    ends_at = state.get("ends_at")
    if not all((appointment_id, business_id, starts_at, ends_at)):
        return {"messages": [AIMessage(content="Faltan datos para reprogramar la cita.")]}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.put(
                f"{API_URL}/appointments/reschedule",
                params={
                    "business_id": str(business_id),
                    "appointment_id": str(appointment_id),
                },
                json={
                    "starts_at": starts_at.isoformat(),
                    "ends_at": ends_at.isoformat(),
                },
            )
            response.raise_for_status()
    except (AttributeError, httpx.HTTPError, TypeError, ValueError):
        return {"messages": [AIMessage(content="No pude reprogramar la cita ahora.")]}
    return {
        **clear_appointment_state(),
        "messages": [AIMessage(content="Listo, tu cita fue reprogramada.")],
    }


async def cancel_appointment_node(state: MessageGraphState) -> dict:
    if not (
        state.get("message_category") == "confirmation"
        and state.get("pending_question") == "cancel_confirmation"
    ):
        return {
            "pending_question": "cancel_confirmation",
            "next_action": "cancel_appointment",
            "messages": [AIMessage(content="¿Confirmas que deseas cancelar la cita?")],
        }
    appointment_id = (state.get("active_appointment") or {}).get("id")
    business_id = state.get("business_id")
    if not appointment_id or not business_id:
        return {"messages": [AIMessage(content="Faltan datos para cancelar la cita.")]}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.put(
                f"{API_URL}/appointments/cancel",
                params={
                    "appointment_id": str(appointment_id),
                    "business_id": str(business_id),
                },
            )
            response.raise_for_status()
    except (httpx.HTTPError, TypeError, ValueError):
        return {"messages": [AIMessage(content="No pude cancelar la cita ahora.")]}
    return {
        **clear_appointment_state(),
        "messages": [AIMessage(content="Listo, tu cita fue cancelada.")],
    }


async def view_appointment_node(state: MessageGraphState) -> dict:
    try:
        appointment = await _find_customer_appointment(state)
    except (httpx.HTTPError, TypeError, ValueError):
        return {"messages": [AIMessage(content="No pude consultar tus citas ahora.")]}
    if appointment is None:
        return _api_pending("No encontré una cita próxima para ti.")
    return {
        **clear_appointment_state(),
        "messages": [
            AIMessage(content=f"Tu próxima cita es {_appointment_label(appointment)}.")
        ],
    }
