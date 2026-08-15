import asyncio
import json
from datetime import date, datetime, timezone
from uuid import UUID

import httpx
import pytest

from src.models.appointments import (
    AppointmentBookingRequest,
    AppointmentCancellationRequest,
    AppointmentRescheduleRequest,
)
from src.services.appointments import AppointmentApiClient, AppointmentApiError


BUSINESS_ID = UUID("11111111-1111-1111-1111-111111111111")
CUSTOMER_ID = UUID("22222222-2222-2222-2222-222222222222")
APPOINTMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
START = datetime(2026, 8, 20, 14, 30, tzinfo=timezone.utc)
END = datetime(2026, 8, 20, 15, 30, tzinfo=timezone.utc)


def _run(awaitable):
    return asyncio.run(awaitable)


def _client(handler):
    return AppointmentApiClient(
        "https://api.example.test",
        transport=httpx.MockTransport(handler),
    )


def _summary():
    return {
        "id": str(APPOINTMENT_ID),
        "status": "pending",
        "starts_at": START.isoformat(),
        "ends_at": END.isoformat(),
        "active": True,
    }


def test_availability_sends_the_exact_requested_interval():
    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert request.url.path == "/appointments/availability"
        assert dict(request.url.params) == {
            "business_id": str(BUSINESS_ID),
            "starts_at": START.isoformat(),
            "ends_at": END.isoformat(),
        }
        return httpx.Response(200, json=True)

    assert _run(_client(handler).check_availability(BUSINESS_ID, START, END)) is True


def test_lookup_scopes_customer_appointments_and_returns_all_candidates():
    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert request.url.path == "/appointments/customer"
        assert dict(request.url.params) == {
            "business_id": str(BUSINESS_ID),
            "customer_id": str(CUSTOMER_ID),
            "appointment_date": "2026-08-20",
            "include_cancelled": "false",
        }
        return httpx.Response(200, json=[_summary()])

    results = _run(
        _client(handler).list_customer_appointments(
            BUSINESS_ID,
            CUSTOMER_ID,
            appointment_date=date(2026, 8, 20),
        )
    )

    assert [appointment.id for appointment in results] == [APPOINTMENT_ID]


def test_book_sends_only_the_typed_authoritative_request_values():
    request_model = AppointmentBookingRequest(
        business_id=BUSINESS_ID,
        customer_id=CUSTOMER_ID,
        starts_at=START,
        ends_at=END,
    )

    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == "/appointments/book"
        assert json.loads(request.content) == request_model.model_dump(mode="json")
        return httpx.Response(201, json=_summary())

    result = _run(_client(handler).book(request_model))

    assert result.id == APPOINTMENT_ID
    assert result.status == "pending"


def test_reschedule_sends_the_selected_appointment_and_owned_scope():
    request_model = AppointmentRescheduleRequest(
        business_id=BUSINESS_ID,
        customer_id=CUSTOMER_ID,
        starts_at=START,
        ends_at=END,
    )

    def handler(request: httpx.Request):
        assert request.method == "PATCH"
        assert request.url.path == f"/appointments/{APPOINTMENT_ID}/reschedule"
        assert json.loads(request.content) == request_model.model_dump(mode="json")
        return httpx.Response(200, json=_summary())

    result = _run(_client(handler).reschedule(APPOINTMENT_ID, request_model))

    assert result.id == APPOINTMENT_ID


def test_cancel_sends_owned_scope_and_parses_the_cancellation_outcome():
    request_model = AppointmentCancellationRequest(
        business_id=BUSINESS_ID,
        customer_id=CUSTOMER_ID,
        reason="Customer requested cancellation",
    )

    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == f"/appointments/{APPOINTMENT_ID}/cancel"
        assert json.loads(request.content) == request_model.model_dump(mode="json")
        return httpx.Response(
            200,
            json={
                "id": str(APPOINTMENT_ID),
                "status": "cancelled",
                "cancelled_at": START.isoformat(),
                "starts_at": START.isoformat(),
                "ends_at": END.isoformat(),
            },
        )

    result = _run(_client(handler).cancel(APPOINTMENT_ID, request_model))

    assert result.status == "cancelled"
    assert result.cancelled_at == START


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [(422, "validation_error"), (404, "not_found"), (409, "conflict"), (403, "forbidden")],
)
def test_http_errors_are_mapped_to_safe_domain_errors(status_code, expected_code):
    def handler(request: httpx.Request):
        return httpx.Response(status_code, json={"detail": "backend detail"})

    with pytest.raises(AppointmentApiError) as error:
        _run(_client(handler).check_availability(BUSINESS_ID, START, END))

    assert error.value.code == expected_code
    assert error.value.retryable is False
    assert error.value.message != "backend detail"


def test_timeout_is_a_retryable_domain_error():
    def handler(request: httpx.Request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(AppointmentApiError) as error:
        _run(_client(handler).check_availability(BUSINESS_ID, START, END))

    assert error.value.code == "transport_error"
    assert error.value.retryable is True


def test_malformed_success_response_is_not_treated_as_an_appointment():
    def handler(request: httpx.Request):
        return httpx.Response(201, json={"starts_at": START.isoformat()})

    request_model = AppointmentBookingRequest(
        business_id=BUSINESS_ID,
        customer_id=CUSTOMER_ID,
        starts_at=START,
        ends_at=END,
    )

    with pytest.raises(AppointmentApiError) as error:
        _run(_client(handler).book(request_model))

    assert error.value.code == "invalid_response"
