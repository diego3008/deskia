import asyncio
from datetime import datetime, timezone
from uuid import UUID

from src.models.appointments import AppointmentSummary
from src.nodes.appointments.read_nodes import (
    check_availability_node,
    lookup_appointments_node,
)
from src.nodes.appointments.response_nodes import (
    availability_response_node,
    lookup_response_node,
)
from src.services.appointments import AppointmentApiError
from src.structured_outputs import AppointmentPhase


BUSINESS_ID = UUID("11111111-1111-1111-1111-111111111111")
CUSTOMER_ID = UUID("22222222-2222-2222-2222-222222222222")
APPOINTMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
START = datetime(2026, 8, 20, 14, 30, tzinfo=timezone.utc)
END = datetime(2026, 8, 20, 15, 30, tzinfo=timezone.utc)


def _run(awaitable):
    return asyncio.run(awaitable)


class ReadOnlyClient:
    def __init__(self, *, available=True, appointments=None, error=None):
        self.available = available
        self.appointments = appointments or []
        self.error = error
        self.availability_calls = []
        self.lookup_calls = []

    async def check_availability(self, business_id, starts_at, ends_at):
        self.availability_calls.append((business_id, starts_at, ends_at))
        if self.error:
            raise self.error
        return self.available

    async def list_customer_appointments(self, business_id, customer_id, **kwargs):
        self.lookup_calls.append((business_id, customer_id, kwargs))
        if self.error:
            raise self.error
        return self.appointments

    async def book(self, *args, **kwargs):
        raise AssertionError("Read flow must not book an appointment")

    async def reschedule(self, *args, **kwargs):
        raise AssertionError("Read flow must not reschedule an appointment")

    async def cancel(self, *args, **kwargs):
        raise AssertionError("Read flow must not cancel an appointment")


def _state(**overrides):
    state = {
        "business_id": BUSINESS_ID,
        "business_timezone": "America/Monterrey",
        "customer_id": CUSTOMER_ID,
        "requested_start": START,
        "requested_end": END,
    }
    state.update(overrides)
    return state


def _appointment(appointment_id=APPOINTMENT_ID):
    return AppointmentSummary(
        id=appointment_id,
        status="pending",
        starts_at=START,
        ends_at=END,
        active=True,
    )


def test_missing_start_prompts_for_only_the_next_required_detail_without_an_api_call():
    client = ReadOnlyClient()

    update = _run(check_availability_node(_state(requested_start=None), client=client))
    reply = availability_response_node(update)["messages"][0]

    assert update["error"]["code"] == "missing_start"
    assert client.availability_calls == []
    assert "start time" in reply.content.lower()
    assert "end time" not in reply.content.lower()


def test_missing_business_timezone_uses_the_monterrey_demo_default():
    client = ReadOnlyClient()

    update = _run(
        check_availability_node(
            _state(
                business_timezone=None,
                requested_start=datetime(2026, 8, 20, 14, 30),
                requested_end=datetime(2026, 8, 20, 15, 30),
            ),
            client=client,
        )
    )

    normalized_start = update["requested_start"]
    assert normalized_start.tzinfo.key == "America/Monterrey"
    assert client.availability_calls == [(BUSINESS_ID, normalized_start, update["requested_end"])]


def test_naive_interval_is_normalized_in_the_business_timezone_not_the_host_timezone():
    client = ReadOnlyClient()
    naive_start = datetime(2026, 8, 20, 14, 30)
    naive_end = datetime(2026, 8, 20, 15, 30)

    update = _run(
        check_availability_node(
            _state(requested_start=naive_start, requested_end=naive_end), client=client
        )
    )

    normalized_start = update["requested_start"]
    normalized_end = update["requested_end"]
    assert normalized_start.tzinfo.key == "America/Monterrey"
    assert normalized_end.tzinfo.key == "America/Monterrey"
    assert client.availability_calls == [(BUSINESS_ID, normalized_start, normalized_end)]


def test_ambiguous_dst_local_time_requires_clarification_without_an_api_call():
    client = ReadOnlyClient()

    update = _run(
        check_availability_node(
            _state(
                business_timezone="America/New_York",
                requested_start=datetime(2026, 11, 1, 1, 30),
                requested_end=datetime(2026, 11, 1, 2, 30),
            ),
            client=client,
        )
    )

    assert update["error"]["code"] == "ambiguous_local_time"
    assert client.availability_calls == []


def test_nonexistent_dst_local_time_requires_clarification_without_an_api_call():
    client = ReadOnlyClient()

    update = _run(
        check_availability_node(
            _state(
                business_timezone="America/New_York",
                requested_start=datetime(2026, 3, 8, 2, 30),
                requested_end=datetime(2026, 3, 8, 3, 30),
            ),
            client=client,
        )
    )

    assert update["error"]["code"] == "nonexistent_local_time"
    assert client.availability_calls == []


def test_available_slot_records_evidence_bound_to_the_exact_interval():
    client = ReadOnlyClient(available=True)

    update = _run(check_availability_node(_state(), client=client))

    assert client.availability_calls == [(BUSINESS_ID, START, END)]
    assert update["phase"] == AppointmentPhase.COLLECTING
    assert update["availability_evidence"]["available"] is True
    assert update["availability_evidence"]["starts_at"] == START
    assert update["availability_evidence"]["ends_at"] == END


def test_unavailable_slot_is_recorded_without_reaching_a_write_method():
    client = ReadOnlyClient(available=False)

    update = _run(check_availability_node(_state(), client=client))

    assert update["availability_evidence"]["available"] is False
    assert update["error"] is None


def test_read_transport_error_becomes_a_structured_safe_error():
    client = ReadOnlyClient(
        error=AppointmentApiError("transport_error", "internal detail", retryable=True)
    )

    update = _run(check_availability_node(_state(), client=client))

    assert update["phase"] == AppointmentPhase.FAILED
    assert update["error"] == {
        "code": "transport_error",
        "message": "internal detail",
        "retryable": True,
    }


def test_lookup_with_no_appointments_keeps_selection_empty():
    client = ReadOnlyClient(appointments=[])

    update = _run(lookup_appointments_node(_state(), client=client))

    assert update["selected_appointment"] is None
    assert update["appointment_candidates"] == []
    assert "could not find" in lookup_response_node(update)["messages"][0].content.lower()


def test_lookup_selects_an_appointment_only_when_there_is_exactly_one():
    client = ReadOnlyClient(appointments=[_appointment()])

    update = _run(lookup_appointments_node(_state(), client=client))

    assert update["selected_appointment"]["id"] == APPOINTMENT_ID
    assert update["appointment_candidates"] is None


def test_lookup_with_multiple_appointments_requires_user_selection():
    second_id = UUID("44444444-4444-4444-4444-444444444444")
    client = ReadOnlyClient(appointments=[_appointment(), _appointment(second_id)])

    update = _run(lookup_appointments_node(_state(), client=client))
    reply = lookup_response_node(update)["messages"][0]

    assert update["selected_appointment"] is None
    assert [candidate["id"] for candidate in update["appointment_candidates"]] == [
        APPOINTMENT_ID,
        second_id,
    ]
    assert "which appointment" in reply.content.lower()
