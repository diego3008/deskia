import unittest
from unittest.mock import patch
from uuid import uuid4

from src.nodes.user_services_validation.customer_creation_node import (
    customer_creation_node,
)
from src.nodes.user_services_validation.customer_lookup_node import customer_lookup_node


class JsonResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    response = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url):
        return self.response

    async def post(self, url, json):
        return self.response

    async def patch(self, url, json):
        return self.response


class ValidatedCustomerHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_lookup_publishes_customer_and_customer_id(self):
        customer_id = str(uuid4())
        FakeClient.response = JsonResponse(
            {"id": customer_id, "email": "ana@example.com"}
        )

        with patch(
            "src.nodes.user_services_validation.customer_lookup_node.httpx.AsyncClient",
            FakeClient,
        ):
            result = await customer_lookup_node(
                {"business_id": uuid4(), "user_data": {"email": "ana@example.com"}}
            )

        self.assertEqual(result.get("customer_id"), customer_id)
        self.assertEqual((result.get("customer") or {}).get("id"), customer_id)
        self.assertEqual(result["user_data"]["customer"]["id"], customer_id)

    async def test_creation_publishes_customer_and_customer_id(self):
        customer_id = str(uuid4())
        FakeClient.response = JsonResponse(
            {"id": customer_id, "email": "ana@example.com"}
        )

        with patch(
            "src.nodes.user_services_validation.customer_creation_node.httpx.AsyncClient",
            FakeClient,
        ):
            result = await customer_creation_node(
                {
                    "business_id": uuid4(),
                    "user_data": {
                        "email": "ana@example.com",
                        "first_name": "Ana",
                        "last_name": "López",
                    },
                }
            )

        self.assertEqual(result.get("customer_id"), customer_id)
        self.assertEqual((result.get("customer") or {}).get("id"), customer_id)
        self.assertEqual(result["user_data"]["customer"]["id"], customer_id)

    async def test_lookup_retries_when_customer_id_is_missing(self):
        FakeClient.response = JsonResponse({"email": "ana@example.com"})

        with patch(
            "src.nodes.user_services_validation.customer_lookup_node.httpx.AsyncClient",
            FakeClient,
        ):
            result = await customer_lookup_node(
                {"business_id": uuid4(), "user_data": {"email": "ana@example.com"}}
            )

        self.assertEqual(result.get("next_action"), "retry_customer_lookup")

    async def test_creation_retries_when_customer_id_is_missing(self):
        FakeClient.response = JsonResponse({"email": "ana@example.com"})

        with patch(
            "src.nodes.user_services_validation.customer_creation_node.httpx.AsyncClient",
            FakeClient,
        ):
            result = await customer_creation_node(
                {
                    "business_id": uuid4(),
                    "user_data": {
                        "email": "ana@example.com",
                        "first_name": "Ana",
                        "last_name": "López",
                    },
                }
            )

        self.assertEqual(result.get("next_action"), "retry_customer_creation")


if __name__ == "__main__":
    unittest.main()
