# Appointment Email Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Send a Gmail confirmation as the booking graph's finishing step only after a confirmed booking, reschedule, or cancellation.

**Architecture:** A typed mutation outcome drives conditional routing after `message_writer`. The email subgraph composes deterministic Spanish content and attempts delivery, recording notification status separately from appointment success. Existing API-pending nodes never emit a successful outcome.

**Tech Stack:** Python >=3.12, existing Pydantic/LangGraph/LangChain messages, Google API client/auth packages already declared, stdlib email/base64/asyncio/unittest.

**Spec:** [Appointment Email Confirmation](../specs/2026-09-08-appointment-email-confirmation-design.md)

## Global constraints

- Preserve the user's unfinished Gmail/email-subgraph work, prior appointment implementation, dependency edits, RAG edits, and deleted email_support_graph.py; do not restore or overwrite unrelated work.
- Keep appointment APIs pending; never infer operation success from intent, slot availability, or assistant text.
- Reuse the declared Google libraries and Python standard library; no new dependencies or notification framework.
- Keep emails in Spanish and preserve the existing chat response/history.
- No live emails or OAuth authorization during planning, implementation, or automated tests without separate explicit authorization.
- Existing authorization covers the appointment, pending-question, and compaction checks; request authorization before running the new Gmail/email tests, per AGENTS.md.

Status: Implemented and verified. All 93 authorized mocked checks pass. No live email sends or OAuth authorization were performed. Backend appointment APIs remain pending.

## File map and execution order

| Task | Files | Responsibility |
| --- | --- | --- |
| 1 | Modify `src/models/appointments.py`, `src/state.py`, `src/helpers/workflow.py`, `src/nodes/message_listener_node.py`; create `tests/test_email_confirmation.py` | Verified success contract and state lifecycle |
| 2 | Modify `src/utils/gmail_utils.py`; create `tests/test_gmail_utils.py` | Headless Gmail transport and separate operator authorization |
| 3 | Create `src/nodes/email_confirmation_nodes.py`; modify `src/graph/email_confirmation_subgraph.py`; extend `tests/test_email_confirmation.py` | Compose/send nodes, receipts, controlled failures, runnable subgraph |
| 4 | Modify `src/graph/appointment_booking_graph.py`, `tests/test_pending_question_flow.py`, `tests/test_appointment_services_subgraph.py`; extend `tests/test_email_confirmation.py`; update feature docs | Conditional finishing step and regression verification |

Tasks 1 and 2 have separate implementation files and may run in parallel with subagents. Task 3 depends on both; Task 4 follows Task 3. The main agent supplies the spec and exact interfaces to each worker, reviews their diffs, and runs the combined checks. Avoid importing the unfinished parent graph in Task 1/2 tests: its current invalid email-subgraph imports are a known baseline issue resolved by Task 3.

## Task 1: Define the mutation result and clear stale per-turn notification state

**Consumes:** current customer/business state and, in future integrations, the successful backend mutation result.

**Produces:** `AppointmentOutcome`, `MessageGraphState.appointment_outcome`, `email_draft`, `email_confirmation`, and `email_receipts`.

- [x] **Write contract tests in `tests/test_email_confirmation.py` before implementation.** Keep graph imports inside tests that need them. This fixture is synthetic test data, not a runtime success producer.

```python
import unittest
from pydantic import ValidationError

SUCCESS = {
    "status": "succeeded", "operation": "booked", "operation_id": "mutation-1",
    "appointment_id": "appointment-1", "business_id": "business-1",
    "customer_id": "customer-1", "recipient_email": "ana@example.com",
    "starts_at": "2026-09-10T10:00:00-06:00",
}

class OutcomeTests(unittest.TestCase):
    def test_only_confirmed_mutations_with_usable_dates_are_valid(self):
        from src.models.appointments import AppointmentOutcome
        for operation in ("booked", "rescheduled", "cancelled"):
            self.assertEqual(AppointmentOutcome.model_validate(
                {**SUCCESS, "operation": operation}).operation, operation)
        for change in (
            {"status": "failed"}, {"operation": "check_availability"},
            {"operation_id": ""}, {"starts_at": None},
            {"starts_at": "2026-09-10T10:00:00"},
            {"ends_at": "2026-09-10T09:00:00-06:00"},
        ):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                AppointmentOutcome.model_validate({**SUCCESS, **change})
        cancelled = AppointmentOutcome.model_validate(
            {**SUCCESS, "operation": "cancelled", "starts_at": None})
        self.assertEqual(cancelled.appointment_id, "appointment-1")
```

- [x] **Validate the outcome contract with authorized focused tests.** Initial missing-contract failure was established by static inspection while test authorization was pending; no initial red run is claimed.

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false UV_CACHE_DIR=/private/tmp/deskia-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_email_confirmation.py' -k OutcomeTests -v
```

- [x] **Add this model to `src/models/appointments.py`.** Replace `from anthropic import BaseModel` with the direct Pydantic imports below, merging the existing `Field` import. Reuse the existing `datetime` import and keep old payload schemas intact.

```python
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

class AppointmentOutcome(BaseModel):
    status: Literal["succeeded"]
    operation: Literal["booked", "rescheduled", "cancelled"]
    operation_id: str = Field(min_length=1)
    appointment_id: str = Field(min_length=1)
    business_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    recipient_email: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    previous_starts_at: datetime | None = None

    @field_validator("operation_id", "appointment_id", "business_id", "customer_id")
    @classmethod
    def nonblank_id(cls, value):
        if not value.strip():
            raise ValueError("identifier must not be blank")
        return value

    @field_validator("starts_at", "ends_at", "previous_starts_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("timezone offset required")
        return value

    @model_validator(mode="after")
    def valid_slot(self):
        if self.operation != "cancelled" and self.starts_at is None:
            raise ValueError("confirmed start required")
        if self.ends_at is not None and (
            self.starts_at is None or self.ends_at <= self.starts_at
        ):
            raise ValueError("end must follow start")
        return self
```

- [x] **Add the state channels and resets.** Add these annotations only to `MessageGraphState`. `UserValidationState` does not produce email outcomes.

```python
appointment_outcome: dict | None
email_draft: dict | None
email_confirmation: dict | None
email_receipts: dict[str, dict]

# Additional key in clear_appointment_state():
"appointment_outcome": None,

# Additional keys in BOTH return branches of message_listener_node():
"appointment_outcome": None,
"email_draft": None,
"email_confirmation": None,
```

Do not reset `email_receipts`. Update the existing exact listener-result assertion in Task 4. Add a new listener test with a stale success/draft and existing receipt; assert all three transient fields become `None` and the merged state retains the receipt. Also assert an API-pending action clears a stale `appointment_outcome` through the shared reset.

- [x] **Document the future producer integration, without activating it in current pending nodes.** Once the backend exists, each successful mutation returns this shape after confirming success; `outcome` is an `AppointmentOutcome` constructed from the backend/customer snapshot, and `response` is the normal appointment `AIMessage`:

```python
return {
    **clear_appointment_state(),
    "appointment_outcome": outcome.model_dump(mode="json"),
    "messages": [response],
}
```

Leave pending nodes and disconnected legacy HTTP tools without a success producer. A cancellation's `outcome` preserves available data before deleting/resetting state.

- [x] **Rerun authorized focused tests and review Task 1.** Expected: valid operations accepted; unsuccessful, unsupported, mismatched-date, and stale-turn cases rejected/reset. Suggested commit if committing: `feat(appointment): define confirmed mutation outcomes`.

## Task 2: Complete Gmail delivery and separate authorization

**Consumes:** `send_email(to: str, subject: str, body: str)` arguments and configured sender/token paths.

**Produces:** Gmail message ID as `str`, or an exception handled by the notification node. Export `GmailConfigurationError` for unavailable authorization/configuration.

- [x] **Write one MIME/delivery test and configuration boundary cases in `tests/test_gmail_utils.py`.** Patch `_get_gmail_service` so no credentials/network are accessed.

```python
import base64
import unittest
from email import policy
from email.parser import BytesParser
from unittest.mock import MagicMock, patch

class GmailSendTests(unittest.TestCase):
    def test_sends_encoded_spanish_content_and_returns_provider_id(self):
        from src.utils.gmail_utils import send_email
        service = MagicMock()
        request = service.users.return_value.messages.return_value.send
        request.return_value.execute.return_value = {"id": "gmail-1"}
        with patch("src.utils.gmail_utils._get_gmail_service", return_value=service), patch.dict(
            "os.environ", {"GMAIL_SENDER_EMAIL": "booker@example.com"}
        ):
            result = send_email("ana@example.com", "Cita confirmada", "Tu cita está confirmada.")
        self.assertEqual(result, "gmail-1")
        payload = request.call_args.kwargs
        self.assertEqual(payload["userId"], "me")
        message = BytesParser(policy=policy.default).parsebytes(
            base64.urlsafe_b64decode(payload["body"]["raw"]))
        self.assertEqual(message["To"], "ana@example.com")
        self.assertEqual(message["From"], "booker@example.com")
        self.assertEqual(message["Subject"], "Cita confirmada")
        self.assertIn("está confirmada", message.get_content())
        request.return_value.execute.assert_called_once_with(num_retries=0)
```

Additional concrete cases: CR/LF recipient/subject and multiple recipients must fail before service creation; missing token must raise `GmailConfigurationError` without invoking `InstalledAppFlow`; refreshable credentials use a mocked refresh; missing/blank Gmail response ID must raise `RuntimeError`, never report success. Use temporary test directories and synthetic token data only.

- [x] **Validate the Gmail boundary tests after authorization.** The malformed-token case was observed failing with `AttributeError`, then passing after the credential-boundary fix.

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false UV_CACHE_DIR=/private/tmp/deskia-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_gmail_utils.py' -v
```

- [x] **Replace the unfinished imports and sender with this transport core.** Remove the nonexistent `Email` import and unused datetime/uuid/MIMEText imports. These are the utility's concrete interfaces:

```python
import base64
import os
from email.headerregistry import Address
from email.message import EmailMessage
from email.errors import HeaderParseError

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

class GmailConfigurationError(RuntimeError):
    pass

def send_email(to: str, subject: str, body: str) -> str:
    sender = os.getenv("GMAIL_SENDER_EMAIL", "")
    if not sender:
        raise GmailConfigurationError("gmail_sender_missing")
    for address in (to, sender):
        if "\r" in address or "\n" in address:
            raise ValueError("invalid email header")
        try:
            parsed = Address(addr_spec=address)
        except (HeaderParseError, ValueError) as error:
            raise ValueError("single mailbox address required") from error
        if not parsed.username or not parsed.domain:
            raise ValueError("single mailbox address required")
    message = EmailMessage()
    message["To"], message["From"], message["Subject"] = to, sender, subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    service = _get_gmail_service()
    try:
        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute(num_retries=0)
    finally:
        service.close()
    message_id = result.get("id") if isinstance(result, dict) else None
    if not isinstance(message_id, str) or not message_id.strip():
        raise RuntimeError("gmail_message_id_missing")
    return message_id
```

This follows Google's MIME/raw send interface; the returned ID acknowledges acceptance by Gmail, not inbox delivery. [Sending guide](https://developers.google.com/workspace/gmail/api/guides/sending), [API reference](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send).

- [x] **Make service creation headless and give sending a finite timeout.** Keep Google imports in the utility, build a fresh client per send, and avoid writing refreshed access tokens during requests:

```python
from pathlib import Path
import httplib2
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build

def _get_gmail_service():
    try:
        creds = Credentials.from_authorized_user_file(
            os.getenv("GMAIL_TOKEN_PATH", "token.json"), SCOPES
        )
        if not creds.valid:
            if not (creds.expired and creds.refresh_token):
                raise GmailConfigurationError("gmail_authorization_required")
            creds.refresh(Request())
    except (OSError, ValueError, GoogleAuthError) as error:
        raise GmailConfigurationError("gmail_authorization_unavailable") from error
    transport = AuthorizedHttp(creds, http=httplib2.Http(timeout=30))
    return build("gmail", "v1", http=transport, cache_discovery=False)
```

- [x] **Move interactive authorization behind an explicit operator command.** It is setup-only, never called by `_get_gmail_service()`; setup tests mock the OAuth flow and write only synthetic tokens:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

def authorize_gmail():
    flow = InstalledAppFlow.from_client_secrets_file(
        os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json"), SCOPES
    )
    creds = flow.run_local_server(port=0)
    token_path = Path(os.getenv("GMAIL_TOKEN_PATH", "token.json"))
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as token:
        os.fchmod(token.fileno(), 0o600)
        token.write(creds.to_json())

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorize", action="store_true", required=True)
    parser.parse_args()
    authorize_gmail()
```

Document the Gmail API/OAuth setup and sender account requirements from the [Google Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python). Do not inspect actual token files, change `.env`, or run this command as part of implementation. `token.json`/`credentials.json` are already ignored; custom paths must be kept outside versioned files.

- [x] **Rerun authorized Gmail checks and review Task 2.** No dependency/lockfile modifications expected. Suggested commit: `feat(email): complete headless Gmail delivery`.

## Task 3: Implement email composition, receipts, and the subgraph

**Consumes:** `AppointmentOutcome` from Task 1 and `send_email`/`GmailConfigurationError` from Task 2.

**Produces:** in `src/nodes/email_confirmation_nodes.py`, `successful_outcome(state) -> AppointmentOutcome | None`, `write_email_node(state) -> dict`, `send_email_node(state) -> dict` (async), and `route_email_draft(state) -> str`. Subgraph exports existing `EmailConfirmationGraph` and `email_confirmation_graph` names.

- [x] **Add node/subgraph tests before implementation.** Use the existing `SUCCESS` fixture. These checks prove replay suppression and appointment/chat preservation:

```python
from unittest.mock import patch

class EmailGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_once_per_saved_operation_and_preserves_chat(self):
        from src.graph.email_confirmation_subgraph import email_confirmation_graph
        state = {"business_id": "business-1", "customer_id": "customer-1",
                 "appointment_outcome": SUCCESS, "message_response": "Tu cita está confirmada."}
        with patch("src.nodes.email_confirmation_nodes.send_email", return_value="gmail-1") as send:
            first = await email_confirmation_graph.ainvoke(state)
            again = await email_confirmation_graph.ainvoke(first)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(again["email_confirmation"]["status"], "sent")
        self.assertEqual(again["email_confirmation"]["gmail_message_id"], "gmail-1")
        self.assertEqual(again["message_response"], state["message_response"])
        self.assertEqual(again["appointment_outcome"], SUCCESS)

    async def test_transport_failure_does_not_undo_appointment(self):
        from src.graph.email_confirmation_subgraph import email_confirmation_graph
        state = {"business_id": "business-1", "customer_id": "customer-1",
                 "appointment_outcome": SUCCESS, "message_response": "Tu cita está confirmada."}
        with patch("src.nodes.email_confirmation_nodes.send_email", side_effect=TimeoutError):
            result = await email_confirmation_graph.ainvoke(state)
        self.assertEqual(result["email_confirmation"]["status"], "unknown")
        self.assertEqual(result["message_response"], state["message_response"])
        self.assertEqual(result["appointment_outcome"], SUCCESS)
```

Extend with literal expected subjects for all three operations; cancelled event without dates; two different reschedule operation IDs; missing recipient (`skipped`); configuration/content errors (`failed`); HTTP rejection (`failed`) versus server/transport uncertainty (`unknown`); and business/customer mismatch (no send). Seed a fake saved receipt and assert no automatic retry for each terminal status.

- [x] **Implement the nodes and run the authorized checks.** Tests were written first; the completion record claims the observed passing run, not an unrecorded initial red run. Use this validation and receipt core:

```python
import asyncio
from pydantic import ValidationError
from googleapiclient.errors import HttpError
from src.models.appointments import AppointmentOutcome
from src.utils.gmail_utils import GmailConfigurationError, send_email

def successful_outcome(state):
    try:
        outcome = AppointmentOutcome.model_validate(state.get("appointment_outcome"))
    except ValidationError:
        return None
    customer_id = state.get("customer_id") or (state.get("customer") or {}).get("id")
    if (outcome.business_id != str(state.get("business_id"))
            or outcome.customer_id != str(customer_id)):
        return None
    return outcome

def record_receipt(state, operation_id, status, **details):
    receipt = {"operation_id": operation_id, "status": status, **details}
    # ponytail: thread-state receipts cannot close the send/checkpoint crash window;
    # use a backend outbox for durable retries and cross-worker deduplication.
    return {"email_draft": None, "email_confirmation": receipt,
            "email_receipts": {**(state.get("email_receipts") or {}), operation_id: receipt}}

SUBJECTS = {"booked": "Confirmación de cita", "rescheduled": "Cita reprogramada",
            "cancelled": "Cita cancelada"}
DESCRIPTIONS = {"booked": "Tu cita ha sido agendada.",
                "rescheduled": "Tu cita ha sido reprogramada.",
                "cancelled": "Tu cita ha sido cancelada."}

def write_email_node(state):
    outcome = successful_outcome(state)
    if outcome is None:
        return {"email_draft": None, "email_confirmation": None}
    saved = (state.get("email_receipts") or {}).get(outcome.operation_id)
    if saved:
        return {"email_draft": None, "email_confirmation": saved}
    if not outcome.recipient_email or not outcome.recipient_email.strip():
        return record_receipt(state, outcome.operation_id, "skipped", reason="recipient_missing")
    lines = [DESCRIPTIONS[outcome.operation], f"Referencia: {outcome.appointment_id}"]
    for label, value in (("Fecha y hora", outcome.starts_at), ("Fin", outcome.ends_at),
                         ("Horario anterior", outcome.previous_starts_at)):
        if value is not None:
            lines.append(f"{label}: {value.strftime('%Y-%m-%d %H:%M %z')}")
    return {"email_confirmation": None, "email_draft": {
        "to": outcome.recipient_email, "subject": SUBJECTS[outcome.operation],
        "body": "\n".join(lines)}}

def route_email_draft(state):
    return "send_email" if state.get("email_draft") else "end"

async def send_email_node(state):
    outcome = successful_outcome(state)
    if outcome is None:
        return {"email_draft": None, "email_confirmation": None}
    saved = (state.get("email_receipts") or {}).get(outcome.operation_id)
    if saved:
        return {"email_draft": None, "email_confirmation": saved}
    draft = state.get("email_draft")
    if not draft:
        return record_receipt(state, outcome.operation_id, "skipped", reason="draft_missing")
    try:
        message_id = await asyncio.to_thread(send_email, **draft)
    except (GmailConfigurationError, ValueError):
        return record_receipt(state, outcome.operation_id, "failed", reason="email_configuration_or_content")
    except HttpError as error:
        definite = 400 <= error.resp.status < 500 and error.resp.status != 408
        return record_receipt(state, outcome.operation_id,
                              "failed" if definite else "unknown", reason="gmail_request_failed")
    except Exception:
        # External delivery failure must not invalidate the committed appointment.
        return record_receipt(state, outcome.operation_id, "unknown", reason="gmail_result_unknown")
    return record_receipt(state, outcome.operation_id, "sent", gmail_message_id=message_id)
```

`send_email` owns header validation/provider response validation; the subgraph owns eligibility, composing, and failure isolation. Do not attach email contents to `messages` or overwrite appointment/customer/response fields. No error branch loops back to an appointment node.

- [x] **Fix the unfinished subgraph and remove invalid/unused imports.** Use `MessageGraphState` and assign `self.graph`:

```python
from langgraph.graph import START, END, StateGraph
from src.state import MessageGraphState
from src.nodes.email_confirmation_nodes import write_email_node, send_email_node, route_email_draft

class EmailConfirmationGraph:
    def __init__(self):
        workflow = StateGraph(MessageGraphState)
        workflow.add_node("write_email", write_email_node)
        workflow.add_node("send_email", send_email_node)
        workflow.add_edge(START, "write_email")
        workflow.add_conditional_edges("write_email", route_email_draft,
                                       {"send_email": "send_email", "end": END})
        workflow.add_edge("send_email", END)
        self.graph = workflow.compile()

email_confirmation_graph = EmailConfirmationGraph().graph
```

- [x] **Rerun authorized email tests and review Task 3.** Expected: composition, no-send gates, failures, replay suppression, and chat preservation pass. Suggested commit: `feat(email): implement confirmation subgraph`.

## Task 4: Connect the finishing step and verify real graph boundaries

**Consumes:** `successful_outcome`, `email_confirmation_graph`, existing `message_writer`, and API-pending appointment nodes.

**Produces:** `route_after_message_writer(state) -> Literal["email_confirmation", "end"]` and a compiled parent that returns its usual chat response plus notification state.

- [x] **Add parent routing tests before changing its edges.** Include valid results for all three operations, absent result, failed/pending result, read-only operation, mismatched tenant/customer, and an existing receipt. Expected route is email only for a new eligible result. Do not use appointment category as the expected success gate.

```python
class EmailParentRoutingTests(unittest.TestCase):
    def test_only_fresh_confirmed_mutations_enter_email(self):
        from src.graph.appointment_booking_graph import route_after_message_writer
        state = {"business_id": "business-1", "customer_id": "customer-1",
                 "appointment_outcome": SUCCESS}
        self.assertEqual(route_after_message_writer(state), "email_confirmation")
        self.assertEqual(route_after_message_writer({"message_category": "new_appointment"}), "end")
        self.assertEqual(route_after_message_writer({**state, "appointment_outcome": None}), "end")
        self.assertEqual(route_after_message_writer({**state, "business_id": "other"}), "end")
        self.assertEqual(route_after_message_writer({**state, "email_receipts": {
            "mutation-1": {"operation_id": "mutation-1", "status": "sent"}}}), "end")
```

- [x] **Replace the direct writer→END edge and verify the authorized routing test.** Keep appointment_services→message_writer and email_confirmation→END, along with all existing customer-question/retry precedence:

```python
from src.nodes.email_confirmation_nodes import successful_outcome

def route_after_message_writer(state: MessageGraphState) -> Literal["email_confirmation", "end"]:
    outcome = successful_outcome(state)
    if outcome and outcome.operation_id not in (state.get("email_receipts") or {}):
        return "email_confirmation"
    return "end"

# In AppointmentBooking.__init__, replace add_edge("message_writer", END):
workflow.add_conditional_edges(
    "message_writer", route_after_message_writer,
    {"email_confirmation": "email_confirmation", "end": END},
)
```

- [x] **Add compiled-parent integration coverage.** Do not seed `appointment_outcome` in the parent's incoming state for a success test: the listener must clear it. In the test, patch `src.graph.appointment_booking_graph.appointment_services_subgraph` before constructing a fresh `AppointmentBooking()` with a small node returning `{appointment_outcome: SUCCESS, messages: [AIMessage(...)]}`. Patch the categorizer and Gmail utility at their consuming symbols. Assert the final result preserves the chat response and records `sent`; parameterize all three mutation operations. Then use the real API-pending subgraph and assert no send, including when the initial state contains stale success. Simulate Gmail failure with the successful test producer and assert appointment success/chat survive. This is test-only substitution; no production success stub is added.

- [x] **Update two intentionally changed regression assertions.** `tests/test_pending_question_flow.py` has an exact listener delta assertion: include the three new reset fields. Its `test_message_writer_is_a_terminal_graph_node` must reflect the conditional email/END destinations while still checking normal non-success responses end. Add the no-email expectation for all five existing pending nodes in `tests/test_appointment_services_subgraph.py`; retain the recent cached-customer/retry handoff regression.

- [x] **Run the authorized verification set.** Do not run the new tests until their authorization is granted. Disable tracing and use the writable uv cache; no real Google/backend credentials are needed by mocked checks.

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false UV_CACHE_DIR=/private/tmp/deskia-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_gmail_utils.py' -v
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false UV_CACHE_DIR=/private/tmp/deskia-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_email_confirmation.py' -v
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false UV_CACHE_DIR=/private/tmp/deskia-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_appointment_services_subgraph.py' -q
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false UV_CACHE_DIR=/private/tmp/deskia-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_pending_question_flow.py' -q
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false UV_CACHE_DIR=/private/tmp/deskia-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_compact_context_node.py' -q
git diff --check
```

- [x] **Main-agent review and completion record.** Review all state reset sites, success/receipt validation, failure paths, and parent/subgraph compilation. Confirm no real send/OAuth occurred, no existing user files were reverted, and no dependency churn was introduced. Record actual test results and the still-pending API producer boundary in the spec. Suggested commit: `feat(booking): finish confirmed mutations with email notification`.

## Completion definition

The finishing step is complete when the models, Gmail sender, subgraph, conditional parent routing, and mocked success/failure/replay checks work together. It is not live until authorized sender setup exists and the real appointment mutation nodes publish confirmed outcomes. Do not report a real email delivered or a real appointment changed based on synthetic fixtures. Leave runtime activation and a live send outside this planning task.


## Implementation record

All four implementation tasks are complete. The main agent reviewed the finished changes and ran the five authorized suites together: Gmail utility 11, email confirmation 16, appointment services 33, pending-question flow 31, context compaction 2. **93 tests passed** (exit 0); `git diff --check` passed. `.env` loading and tracing were disabled for the combined run. No live email, OAuth authorization, new dependencies, commits, or unrelated source edits were made.

Task 1 received an independent approved review. The remaining delegated reviewers hit an agent usage limit; the main agent completed the delivery and final integration reviews directly. No blocking findings remain. API success producers and sender setup are the documented future activation boundary, not unfinished implementation tasks in this phase.
