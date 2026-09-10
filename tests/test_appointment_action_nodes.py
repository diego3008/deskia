import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, call, patch
from uuid import UUID

import httpx

from src.models.appointments import AppointmentCreate
from src.nodes.appointment_services.appointment_action_nodes import (
    book_appointment_node,
    cancel_appointment_node,
    check_availability_node,
    lookup_appointment_node,
    reschedule_appointment_node,
    view_appointment_node,
)


class BookingNodeTests(unittest.IsolatedAsyncioTestCase):
    appointment = {
        "business_id": "11111111-1111-1111-1111-111111111111",
        "customer_id": "22222222-2222-2222-2222-222222222222",
        "service_id": "33333333-3333-3333-3333-333333333333",
        "business_staff_id": "44444444-4444-4444-4444-444444444444",
        "starts_at": datetime.fromisoformat("2026-09-10T10:00:00-06:00"),
        "ends_at": datetime.fromisoformat("2026-09-10T11:00:00-06:00"),
    }

    def test_create_model_accepts_service_and_staff_ids(self):
        appointment = AppointmentCreate.model_validate(self.appointment)

        self.assertEqual(appointment.service_id, UUID(self.appointment["service_id"]))
        self.assertEqual(
            appointment.business_staff_id,
            UUID(self.appointment["business_staff_id"]),
        )

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.API_URL",
        "https://api.example.test",
    )
    async def test_posts_exact_payload_and_clears_state_after_success(self, client_class):
        response = Mock()
        response.json.return_value = {
            "starts_at": "2026-09-10T10:00:00-06:00",
            "ends_at": "2026-09-10T11:00:00-06:00",
        }
        client = AsyncMock()
        client.post.return_value = response
        client_class.return_value.__aenter__.return_value = client

        result = await book_appointment_node(self.appointment)

        client_class.assert_called_once_with(timeout=30)
        client.post.assert_awaited_once_with(
            "https://api.example.test/appointments/book",
            json={
                "business_id": self.appointment["business_id"],
                "starts_at": "2026-09-10T10:00:00-06:00",
                "ends_at": "2026-09-10T11:00:00-06:00",
                "customer_id": self.appointment["customer_id"],
                "business_staff_id": self.appointment["business_staff_id"],
                "service_id": self.appointment["service_id"],
            },
        )
        self.assertEqual(response.method_calls, [call.raise_for_status(), call.json()])
        self.assertIn("agendada", result["messages"][0].content)
        for field in (
            "appointment_intent",
            "current_flow",
            "pending_question",
            "next_action",
            "starts_at",
            "ends_at",
            "service_name",
            "service_id",
            "business_staff_id",
            "appointment_outcome",
        ):
            self.assertIsNone(result[field])

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_missing_required_field_does_not_call_api(self, client_class):
        for field in self.appointment:
            with self.subTest(field=field):
                state = {
                    **self.appointment,
                    "appointment_intent": "book_appointment",
                    "next_action": "book_appointment",
                    field: None,
                }
                result = await book_appointment_node(state)
                merged = {**state, **result}

                self.assertIn("Necesito", result["messages"][0].content)
                self.assertNotIn("agendada", result["messages"][0].content)
                self.assertEqual(set(result), {"messages"})
                for retained in (
                    "starts_at",
                    "ends_at",
                    "service_id",
                    "business_staff_id",
                    "appointment_intent",
                    "next_action",
                ):
                    self.assertEqual(merged[retained], state[retained])
        client_class.assert_not_called()

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_validation_error_retains_collected_state(self, client_class):
        state = {
            **self.appointment,
            "business_staff_id": "not-a-uuid",
            "appointment_intent": "book_appointment",
            "next_action": "book_appointment",
        }

        result = await book_appointment_node(state)
        merged = {**state, **result}

        self.assertEqual(set(result), {"messages"})
        for field in (
            "starts_at",
            "ends_at",
            "service_id",
            "business_staff_id",
            "appointment_intent",
            "next_action",
        ):
            self.assertEqual(merged[field], state[field])
        client_class.assert_not_called()

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_http_error_does_not_parse_json_or_report_success(self, client_class):
        response = Mock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "bad response", request=Mock(), response=response
        )
        client = AsyncMock()
        client.post.return_value = response
        client_class.return_value.__aenter__.return_value = client

        state = {
            **self.appointment,
            "appointment_intent": "book_appointment",
            "next_action": "book_appointment",
        }
        result = await book_appointment_node(state)
        merged = {**state, **result}

        response.json.assert_not_called()
        self.assertNotIn("agendada", result["messages"][0].content)
        self.assertEqual(set(result), {"messages"})
        for field in (
            "starts_at",
            "ends_at",
            "service_id",
            "business_staff_id",
            "appointment_intent",
            "next_action",
        ):
            self.assertEqual(merged[field], state[field])

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_json_error_does_not_report_success(self, client_class):
        response = Mock()
        response.json.side_effect = ValueError("invalid JSON")
        client = AsyncMock()
        client.post.return_value = response
        client_class.return_value.__aenter__.return_value = client

        state = {
            **self.appointment,
            "appointment_intent": "book_appointment",
            "next_action": "book_appointment",
        }
        result = await book_appointment_node(state)
        merged = {**state, **result}

        self.assertNotIn("agendada", result["messages"][0].content)
        self.assertEqual(set(result), {"messages"})
        for field in (
            "starts_at",
            "ends_at",
            "service_id",
            "business_staff_id",
            "appointment_intent",
            "next_action",
        ):
            self.assertEqual(merged[field], state[field])

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_semantically_malformed_2xx_does_not_report_success(self, client_class):
        response = Mock()
        client = AsyncMock()
        client.post.return_value = response
        client_class.return_value.__aenter__.return_value = client
        state = {
            **self.appointment,
            "appointment_intent": "book_appointment",
            "next_action": "book_appointment",
        }

        for payload in (
            False,
            None,
            [],
            {},
            {"starts_at": "2026-09-10T10:00:00-06:00"},
            {"ends_at": "2026-09-10T11:00:00-06:00"},
            {"starts_at": "", "ends_at": "2026-09-10T11:00:00-06:00"},
            {"starts_at": "2026-09-10T10:00:00-06:00", "ends_at": ""},
        ):
            with self.subTest(payload=payload):
                response.json.return_value = payload

                result = await book_appointment_node(state)
                merged = {**state, **result}

                self.assertNotIn("agendada", result["messages"][0].content)
                self.assertEqual(set(result), {"messages"})
                for field in (
                    "starts_at",
                    "ends_at",
                    "service_id",
                    "business_staff_id",
                    "appointment_intent",
                    "next_action",
                ):
                    self.assertEqual(merged[field], state[field])


class ExistingAppointmentNodeTests(unittest.IsolatedAsyncioTestCase):
    api_appointment = {
        "appointment_id": "appointment-1",
        "starts_at": "2026-09-18T10:00:00-06:00",
        "service_name": "Corte de cabello",
        "staff_name": "Ana García",
    }
    appointment = {
        "id": "appointment-1",
        "starts_at": "2026-09-18T10:00:00-06:00",
        "service_name": "Corte de cabello",
        "staff_name": "Ana García",
    }

    @staticmethod
    def client(response):
        client = AsyncMock()
        client.get.return_value = response
        client.put.return_value = response
        return client

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.API_URL",
        "https://api.example.test",
    )
    async def test_view_fetches_customer_appointment_and_clears_flow(
        self, client_class
    ):
        response = Mock()
        response.json.return_value = self.api_appointment
        client = self.client(response)
        client_class.return_value.__aenter__.return_value = client

        result = await view_appointment_node(
            {
                "business_id": "business-1",
                "customer_id": "customer-1",
                "appointment_intent": "view_appointment",
                "current_flow": "appointment_services",
            }
        )

        client.get.assert_awaited_once_with(
            "https://api.example.test/appointments/find_customer_appointment",
            params={"customer_id": "customer-1", "business_id": "business-1"},
        )
        self.assertEqual(response.method_calls, [call.raise_for_status(), call.json()])
        self.assertIn("Corte de cabello", result["messages"][0].content)
        self.assertIn("2026-09-18", result["messages"][0].content)
        self.assertIsNone(result["appointment_intent"])
        self.assertIsNone(result["active_appointment"])

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.LOCAL_TZ",
        timezone(timedelta(hours=-6)),
    )
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_view_converts_api_time_to_local_timezone(self, client_class):
        response = Mock()
        response.json.return_value = {
            **self.api_appointment,
            "starts_at": "2026-09-18T16:00:00+00:00",
        }
        client = self.client(response)
        client_class.return_value.__aenter__.return_value = client

        result = await view_appointment_node(
            {"business_id": "business-1", "customer_id": "customer-1"}
        )

        self.assertIn("2026-09-18 10:00", result["messages"][0].content)

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.LOCAL_TZ",
        timezone(timedelta(hours=-6)),
    )
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_lookup_maps_find_customer_appointment_response(self, client_class):
        response = Mock()
        response.json.return_value = {
            "appointment_id": "edb7ecd8-1bf5-419b-affc-2c00bde57c5a",
            "starts_at": "2026-09-21T16:00:00Z",
            "service_name": "Blanqueamiento Dental",
            "staff_name": "Ana García",
        }
        client = self.client(response)
        client_class.return_value.__aenter__.return_value = client

        result = await lookup_appointment_node(
            {
                "business_id": "business-1",
                "customer_id": "customer-1",
                "appointment_intent": "reschedule_appointment",
            }
        )

        self.assertEqual(
            result["active_appointment"],
            {
                "id": "edb7ecd8-1bf5-419b-affc-2c00bde57c5a",
                "starts_at": "2026-09-21T10:00:00-06:00",
                "service_name": "Blanqueamiento Dental",
                "staff_name": "Ana García",
            },
        )

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_view_handles_malformed_nested_service(self, client_class):
        response = Mock()
        response.json.return_value = {
            **{
                key: value
                for key, value in self.api_appointment.items()
                if key != "service_name"
            },
            "service": "Corte",
        }
        client = self.client(response)
        client_class.return_value.__aenter__.return_value = client

        result = await view_appointment_node(
            {"business_id": "business-1", "customer_id": "customer-1"}
        )

        self.assertIn("No pude consultar", result["messages"][0].content)

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_lookup_prepares_cancel_confirmation_without_mutating(
        self, client_class
    ):
        response = Mock()
        response.json.return_value = self.api_appointment
        client = self.client(response)
        client_class.return_value.__aenter__.return_value = client

        result = await lookup_appointment_node(
            {
                "business_id": "business-1",
                "customer_id": "customer-1",
                "appointment_intent": "cancel_appointment",
            }
        )

        client.put.assert_not_awaited()
        self.assertEqual(result["active_appointment"], self.appointment)
        self.assertEqual(result["pending_question"], "cancel_confirmation")
        self.assertEqual(result["next_action"], "cancel_appointment")
        self.assertIn("cancelar", result["messages"][0].content.lower())

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_lookup_prepares_reschedule_details(self, client_class):
        response = Mock()
        response.json.return_value = self.api_appointment
        client = self.client(response)
        client_class.return_value.__aenter__.return_value = client

        result = await lookup_appointment_node(
            {
                "business_id": "business-1",
                "customer_id": "customer-1",
                "appointment_intent": "reschedule_appointment",
            }
        )

        self.assertEqual(result["active_appointment"], self.appointment)
        self.assertEqual(result["service_name"], "Corte de cabello")
        self.assertEqual(result["next_action"], "collect_appointment_details")
        self.assertIsNone(result["pending_question"])
        self.assertNotIn("messages", result)

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_reschedule_lookup_rejects_missing_service_name(
        self, client_class
    ):
        response = Mock()
        response.json.return_value = {
            key: value
            for key, value in self.api_appointment.items()
            if key != "service_name"
        }
        client = self.client(response)
        client_class.return_value.__aenter__.return_value = client

        result = await lookup_appointment_node(
            {
                "business_id": "business-1",
                "customer_id": "customer-1",
                "appointment_intent": "reschedule_appointment",
            }
        )

        self.assertIn("No pude consultar", result["messages"][0].content)
        self.assertNotIn("active_appointment", result)

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_cancel_refuses_to_mutate_without_confirmation(self, client_class):
        result = await cancel_appointment_node(
            {
                "business_id": "business-1",
                "active_appointment": self.appointment,
                "appointment_intent": "cancel_appointment",
            }
        )

        client_class.assert_not_called()
        self.assertEqual(result["pending_question"], "cancel_confirmation")
        self.assertEqual(result["next_action"], "cancel_appointment")

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.API_URL",
        "https://api.example.test",
    )
    async def test_confirmed_cancel_patches_exact_appointment_and_clears_flow(
        self, client_class
    ):
        response = Mock()
        client = self.client(response)
        client_class.return_value.__aenter__.return_value = client

        result = await cancel_appointment_node(
            {
                "business_id": "business-1",
                "active_appointment": self.appointment,
                "appointment_intent": "cancel_appointment",
                "message_category": "confirmation",
                "pending_question": "cancel_confirmation",
            }
        )

        client.put.assert_awaited_once_with(
            "https://api.example.test/appointments/cancel",
            params={
                "appointment_id": "appointment-1",
                "business_id": "business-1",
            },
        )
        self.assertEqual(response.method_calls, [call.raise_for_status()])
        self.assertIn("cancelada", result["messages"][0].content)
        self.assertIsNone(result["appointment_intent"])
        self.assertIsNone(result["active_appointment"])

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_reschedule_refuses_to_mutate_without_confirmation(
        self, client_class
    ):
        result = await reschedule_appointment_node(
            {
                "business_id": "business-1",
                "active_appointment": self.appointment,
                "starts_at": datetime.fromisoformat("2026-09-20T10:00:00-06:00"),
                "ends_at": datetime.fromisoformat("2026-09-20T11:00:00-06:00"),
                "appointment_intent": "reschedule_appointment",
            }
        )

        client_class.assert_not_called()
        self.assertEqual(result["pending_question"], "reschedule_confirmation")
        self.assertEqual(result["next_action"], "reschedule_appointment")

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.API_URL",
        "https://api.example.test",
    )
    async def test_confirmed_reschedule_patches_new_slot_and_clears_flow(
        self, client_class
    ):
        response = Mock()
        client = self.client(response)
        client_class.return_value.__aenter__.return_value = client
        starts_at = datetime.fromisoformat("2026-09-20T10:00:00-06:00")
        ends_at = datetime.fromisoformat("2026-09-20T11:00:00-06:00")

        result = await reschedule_appointment_node(
            {
                "business_id": "business-1",
                "active_appointment": self.appointment,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "appointment_intent": "reschedule_appointment",
                "message_category": "confirmation",
                "pending_question": "reschedule_confirmation",
            }
        )

        client.put.assert_awaited_once_with(
            "https://api.example.test/appointments/reschedule",
            params={
                "business_id": "business-1",
                "appointment_id": "appointment-1",
            },
            json={
                "starts_at": "2026-09-20T10:00:00-06:00",
                "ends_at": "2026-09-20T11:00:00-06:00",
            },
        )
        self.assertEqual(response.method_calls, [call.raise_for_status()])
        self.assertIn("reprogramada", result["messages"][0].content)
        self.assertIsNone(result["appointment_intent"])
        self.assertIsNone(result["active_appointment"])


class AvailabilityNodeTests(unittest.IsolatedAsyncioTestCase):
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_reschedule_availability_requests_confirmation(self, client_class):
        response = Mock()
        response.json.return_value = {
            "available": True,
            "service_id": "service-1",
            "business_staff_id": "staff-1",
            "ends_at": "2026-09-20T11:00:00-06:00",
        }
        client = AsyncMock()
        client.get.return_value = response
        client_class.return_value.__aenter__.return_value = client

        result = await check_availability_node(
            {
                "business_id": "business-1",
                "starts_at": datetime.fromisoformat("2026-09-20T10:00:00-06:00"),
                "service_name": "Corte de cabello",
                "appointment_intent": "reschedule_appointment",
                "active_appointment": ExistingAppointmentNodeTests.appointment,
            }
        )

        self.assertEqual(result["pending_question"], "reschedule_confirmation")
        self.assertEqual(result["next_action"], "confirm_reschedule")
        self.assertIn("reprogramar", result["messages"][0].content.lower())

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_unavailable_reschedule_keeps_detail_collection_active(
        self, client_class
    ):
        response = Mock()
        response.json.return_value = False
        client = AsyncMock()
        client.get.return_value = response
        client_class.return_value.__aenter__.return_value = client

        result = await check_availability_node(
            {
                "business_id": "business-1",
                "starts_at": datetime.fromisoformat("2026-09-20T10:00:00-06:00"),
                "service_name": "Corte de cabello",
                "appointment_intent": "reschedule_appointment",
                "active_appointment": ExistingAppointmentNodeTests.appointment,
            }
        )

        self.assertEqual(result["pending_question"], "appointment_details")
        self.assertEqual(result["next_action"], "collect_appointment_details")
        self.assertIn("otro horario", result["messages"][0].content.lower())

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_reschedule_http_error_preserves_retry_context(self, client_class):
        response = Mock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "bad response", request=Mock(), response=response
        )
        client = AsyncMock()
        client.get.return_value = response
        client_class.return_value.__aenter__.return_value = client
        state = {
            "business_id": "business-1",
            "starts_at": datetime.fromisoformat("2026-09-20T10:00:00-06:00"),
            "service_name": "Corte de cabello",
            "appointment_intent": "reschedule_appointment",
            "current_flow": "appointment_services",
            "active_appointment": ExistingAppointmentNodeTests.appointment,
        }

        result = await check_availability_node(state)
        merged = {**state, **result}

        self.assertEqual(merged["appointment_intent"], "reschedule_appointment")
        self.assertEqual(merged["active_appointment"], state["active_appointment"])
        self.assertEqual(result["pending_question"], "appointment_details")
        self.assertEqual(result["next_action"], "collect_appointment_details")
        response.json.assert_not_called()
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.API_URL",
        "https://api.example.test",
    )
    async def test_bookable_availability_requests_booking_confirmation(self, client_class):
        response = Mock()
        response.json.return_value = {
            "available": True,
            "service_id": "service-1",
            "business_staff_id": "staff-1",
            "ends_at": "2026-09-10T11:00:00-06:00",
        }
        client = AsyncMock()
        client.get.return_value = response
        client_class.return_value.__aenter__.return_value = client

        result = await check_availability_node(
            {
                "business_id": "business-1",
                "starts_at": datetime.fromisoformat("2026-09-10T10:00:00-06:00"),
                "service_name": "Corte de cabello",
                "appointment_intent": "book_appointment",
            }
        )

        self.assertEqual(result["pending_question"], "booking_confirmation")
        self.assertEqual(result["next_action"], "confirm_booking")
        self.assertIn("reserve", result["messages"][0].content)

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.API_URL",
        "https://api.example.test",
    )
    async def test_available_response_uses_starts_at_and_returns_service_and_end(self, client_class):
        response = Mock()
        response.json.return_value = {
            "available": True,
            "service_id": "service-1",
            "business_staff_id": "staff-1",
            "ends_at": "2026-09-10T11:00:00-06:00",
        }
        client = AsyncMock()
        client.get.return_value = response
        client_class.return_value.__aenter__.return_value = client

        result = await check_availability_node(
            {
                "business_id": "business-1",
                "starts_at": datetime.fromisoformat("2026-09-10T10:00:00-06:00"),
                "service_name": "Corte de cabello",
            }
        )

        client.get.assert_awaited_once_with(
            "https://api.example.test/appointments/validate-date",
            params={
                "business_id": "business-1",
                "requested_start_date": "2026-09-10T10:00:00-06:00",
                "service_name": "Corte de cabello",
            },
        )
        self.assertEqual(response.method_calls, [call.raise_for_status(), call.json()])
        self.assertIn("disponible", result["messages"][0].content)
        self.assertEqual(result["service_id"], "service-1")
        self.assertEqual(result["business_staff_id"], "staff-1")
        self.assertEqual(
            result["ends_at"],
            datetime.fromisoformat("2026-09-10T11:00:00-06:00"),
        )
        self.assertNotIn("starts_at", result)
        self.assertNotIn("service_name", result)

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.API_URL",
        "https://api.example.test",
    )
    async def test_available_response_without_end_is_not_usable_for_booking(self, client_class):
        response = Mock()
        response.json.return_value = {
            "available": True,
            "service_id": "service-1",
            "business_staff_id": "staff-1",
        }
        client = AsyncMock()
        client.get.return_value = response
        client_class.return_value.__aenter__.return_value = client

        result = await check_availability_node(
            {
                "business_id": "business-1",
                "starts_at": datetime.fromisoformat("2026-09-10T10:00:00-06:00"),
                "service_name": "Corte de cabello",
            }
        )

        self.assertIn("No pude confirmar", result["messages"][0].content)
        self.assertIsNone(result["service_id"])
        self.assertIsNone(result["business_staff_id"])
        self.assertIsNone(result["ends_at"])

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.API_URL",
        "https://api.example.test",
    )
    async def test_handles_unavailable_response(self, client_class):
        response = Mock()
        response.json.return_value = False
        client = AsyncMock()
        client.get.return_value = response
        client_class.return_value.__aenter__.return_value = client

        state = {
            "business_id": "business-1",
            "starts_at": datetime.fromisoformat("2026-09-10T10:00:00-06:00"),
            "service_name": "Corte de cabello",
            "business_staff_id": "stale-staff",
        }
        result = await check_availability_node(state)
        merged = {**state, **result}

        self.assertIn("no está disponible", result["messages"][0].content)
        self.assertIsNone(result["service_id"])
        self.assertIsNone(result["ends_at"])
        self.assertIsNone(merged["business_staff_id"])

    async def test_missing_appointment_fields_uses_pending_reset(self):
        result = await check_availability_node(
            {
                "business_id": "business-1",
                "starts_at": None,
                "service_name": None,
                "service_id": "stale-service",
                "business_staff_id": "stale-staff",
                "ends_at": "stale-end",
                "user_data": {
                    "requested_start_date": "2026-09-10T10:00:00",
                    "service_name": "Corte de cabello",
                },
            }
        )

        self.assertIn("fecha, hora y servicio", result["messages"][0].content)
        self.assertIsNone(result["starts_at"])
        self.assertIsNone(result["ends_at"])
        self.assertIsNone(result["service_name"])
        self.assertIsNone(result["service_id"])
        self.assertIsNone(result["business_staff_id"])

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_http_error_uses_pending_reset_without_parsing_json(self, client_class):
        response = Mock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "bad response", request=Mock(), response=response
        )
        client = AsyncMock()
        client.get.return_value = response
        client_class.return_value.__aenter__.return_value = client

        result = await check_availability_node(
            {
                "business_id": "business-1",
                "starts_at": datetime.fromisoformat("2026-09-10T10:00:00-06:00"),
                "service_name": "Corte de cabello",
            }
        )

        self.assertIn("No pude confirmar", result["messages"][0].content)
        self.assertIsNone(result["service_id"])
        self.assertIsNone(result["ends_at"])
        response.json.assert_not_called()

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_malformed_response_uses_pending_reset(self, client_class):
        response = Mock()
        client = AsyncMock()
        client.get.return_value = response
        client_class.return_value.__aenter__.return_value = client

        for payload in (
            {"available": True, "service_id": "service-1"},
            {
                "available": True,
                "service_id": "service-1",
                "business_staff_id": "staff-1",
                "ends_at": "not-a-date",
            },
        ):
            with self.subTest(payload=payload):
                response.json.return_value = payload
                result = await check_availability_node(
                    {
                        "business_id": "business-1",
                        "starts_at": datetime.fromisoformat(
                            "2026-09-10T10:00:00-06:00"
                        ),
                        "service_name": "Corte de cabello",
                        "business_staff_id": "stale-staff",
                    }
                )

                self.assertIn("No pude confirmar", result["messages"][0].content)
                self.assertIsNone(result["service_id"])
                self.assertIsNone(result["business_staff_id"])
                self.assertIsNone(result["ends_at"])

    @patch(
        "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient"
    )
    async def test_naive_start_does_not_call_api(self, client_class):
        for starts_at in (
            datetime(2026, 9, 10, 10, 0),
            "2026-09-10T10:00:00",
        ):
            with self.subTest(starts_at=starts_at):
                result = await check_availability_node(
                    {
                        "business_id": "business-1",
                        "starts_at": starts_at,
                        "service_name": "Corte de cabello",
                    }
                )

                self.assertIn("zona horaria", result["messages"][0].content)
        client_class.assert_not_called()
