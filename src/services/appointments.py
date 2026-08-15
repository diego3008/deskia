
from datetime import date, datetime
from uuid import UUID

import httpx
from pydantic import ValidationError

from src.models.appointments import (
    AppointmentBookingRequest,
    AppointmentCancellationRequest,
    AppointmentCancellationResponse,
    AppointmentRescheduleRequest,
    AppointmentSummary,
)


class AppointmentApiError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class AppointmentApiClient:
    """Client for confirmed Deskia appointment API routes.

    The graph owns business and customer identity. This client accepts only typed
    request models and never accepts model-generated dictionaries or tool calls.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def check_availability(
        self,
        business_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> bool:
        response = await self._request(
            "GET",
            "/appointments/availability",
            params={
                "business_id": str(business_id),
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
            },
        )
        payload = self._json(response)
        if not isinstance(payload, bool):
            raise self._invalid_response()
        return payload

    async def list_customer_appointments(
        self,
        business_id: UUID,
        customer_id: UUID,
        *,
        appointment_date: date | None = None,
        include_cancelled: bool = False,
    ) -> list[AppointmentSummary]:
        params = {
            "business_id": str(business_id),
            "customer_id": str(customer_id),
            "include_cancelled": str(include_cancelled).lower(),
        }
        if appointment_date is not None:
            params["appointment_date"] = appointment_date.isoformat()
        response = await self._request("GET", "/appointments/customer", params=params)
        payload = self._json(response)
        if not isinstance(payload, list):
            raise self._invalid_response()
        try:
            return [AppointmentSummary.model_validate(item) for item in payload]
        except ValidationError as error:
            raise self._invalid_response() from error

    async def book(self, request: AppointmentBookingRequest) -> AppointmentSummary:
        response = await self._request(
            "POST",
            "/appointments/book",
            json=request.model_dump(mode="json"),
        )
        return self._summary(response)

    async def reschedule(
        self,
        appointment_id: UUID,
        request: AppointmentRescheduleRequest,
    ) -> AppointmentSummary:
        response = await self._request(
            "PATCH",
            f"/appointments/{appointment_id}/reschedule",
            json=request.model_dump(mode="json"),
        )
        return self._summary(response)

    async def cancel(
        self,
        appointment_id: UUID,
        request: AppointmentCancellationRequest,
    ) -> AppointmentCancellationResponse:
        response = await self._request(
            "POST",
            f"/appointments/{appointment_id}/cancel",
            json=request.model_dump(mode="json"),
        )
        try:
            return AppointmentCancellationResponse.model_validate(self._json(response))
        except ValidationError as error:
            raise self._invalid_response() from error

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.TimeoutException as error:
            raise AppointmentApiError(
                "transport_error",
                "The appointment service timed out. Please try again.",
                retryable=True,
            ) from error
        except httpx.RequestError as error:
            raise AppointmentApiError(
                "transport_error",
                "The appointment service is unavailable. Please try again.",
                retryable=True,
            ) from error

        if response.is_error:
            raise self._http_error(response.status_code)
        return response

    def _summary(self, response: httpx.Response) -> AppointmentSummary:
        try:
            return AppointmentSummary.model_validate(self._json(response))
        except ValidationError as error:
            raise self._invalid_response() from error

    @staticmethod
    def _json(response: httpx.Response):
        try:
            return response.json()
        except ValueError as error:
            raise AppointmentApiClient._invalid_response() from error

    @staticmethod
    def _invalid_response() -> AppointmentApiError:
        return AppointmentApiError(
            "invalid_response",
            "The appointment service returned an unexpected response.",
            retryable=False,
        )

    @staticmethod
    def _http_error(status_code: int) -> AppointmentApiError:
        errors = {
            401: ("unauthorized", "The appointment request was not authorized."),
            403: ("forbidden", "You do not have access to that appointment."),
            404: ("not_found", "The requested appointment was not found."),
            409: ("conflict", "That appointment action cannot be completed."),
            422: ("validation_error", "The appointment request is invalid."),
        }
        code, message = errors.get(
            status_code,
            ("service_error", "The appointment service is temporarily unavailable."),
        )
        return AppointmentApiError(code, message, retryable=status_code >= 500)
