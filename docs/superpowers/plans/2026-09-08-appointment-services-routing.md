# Appointment Services Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the appointment tool loop with validated intent routing and five explicit appointment operation nodes whose API integrations remain pending.

**Architecture:** Follow the existing user-services pattern: entry router, validation node, conditional operation dispatch, and terminal operation/fallback nodes. Reuse the current message categorizer and message writer, persist appointment intent through customer identification, and disconnect the appointment tool loop from the parent workflow.

**Tech Stack:** Python >=3.12 (project floor), LangGraph StateGraph, LangChain AIMessage, existing structured categorizer, stdlib unittest/unittest.mock; no new packages.

**Spec:** [2026-09-08-appointment-services-routing-design.md](../specs/2026-09-08-appointment-services-routing-design.md)

## Global Constraints

- Add no dependencies; reuse Python, LangGraph, LangChain messages, Pydantic, and stdlib unittest/unittest.mock already used in this repository.
- Do not consume appointment APIs or fabricate successful appointment results in this phase.
- Preserve existing customer identification and the message_writer handoff; return customer-facing messages in Spanish.
- Preserve unrelated working-tree edits, especially the existing changes in src/prompts/tasks.py, pyproject.toml, src/utils/rag_utils.py, and uv.lock.
- Do not start test processes without explicit user authorization, as required by AGENTS.md.

Status: Implemented on 2026-09-08 after user approval. Test execution was separately authorized. See the execution record below; code examples describe the original plan, with DRY refinements recorded there. Read the spec before execution. Obtain authorization before the first test command; authorization for the agreed set of checks persists and need not be requested for each command. If unavailable, finish authorized edits and static review, then report tests as unrun. Do not start servers, install dependencies, or call live APIs as a substitute for tests.

## File map

| File | Responsibility |
| --- | --- |
| Modify `src/structured_outputs.py` | Two categories and shared `APPOINTMENT_INTENTS` map |
| Modify `src/state.py` | Persist `appointment_intent` in parent/customer state; nullable `next_action` annotations |
| Modify `src/prompts/tasks.py` | Distinguish booking, availability, viewing, service inquiry, decline, and ambiguous intent |
| Modify `src/nodes/message_categorizer_node.py` | Maintain intent and clear stale state at transitions |
| Create `src/nodes/appointment_services/appointment_validation_node.py` | Deterministic validation of category and saved intent |
| Create `src/nodes/appointment_services/appointment_action_nodes.py` | Five named operation functions and shared API-pending response reset |
| Create `src/nodes/appointment_services/__init__.py` | Local `NODES` registry |
| Modify `src/graph/appointment_services_subgraph.py` | Entry router, validation router, explicit graph, fallback |
| Modify `src/graph/appointment_booking_graph.py` | Route all actions and ambiguous service requests through identity/appointment flow |
| Modify `src/graph/user_services_validation_subgraph.py` | Recognize the expanded appointment entry categories |
| Modify `src/nodes/user_services_validation/user_validation_node.py` | Start identification for the expanded categories |
| Modify `tests/test_appointment_services_subgraph.py` | Replace tool-loop checks; cover intent, nodes, continuity, and writer integration |

Keep the existing customer HTTP tools, old appointment tools, planner, dependency files, and graph export configuration unchanged. `langgraph.json` already exposes the parent graph; this feature does not need another public graph.

## Task 1: Define appointment intent and categorizer transitions

**Files:** `src/structured_outputs.py`, `src/state.py`, `src/prompts/tasks.py`, `src/nodes/message_categorizer_node.py`, `tests/test_appointment_services_subgraph.py`.

**Interfaces:**
- Consumes `CategorizerMessageOutput.category.value`, `pending_question`, `next_action`, and the current appointment state.
- Produces `APPOINTMENT_INTENTS: dict[str, str]`, the two new enum values, and `appointment_intent: str | None` on `MessageGraphState` and `UserValidationState`.
- Existing `message_categorizer_node(state)` signature remains unchanged.

- [x] **Step 1: Add a focused category-transition check.** Use existing `SimpleNamespace`, `patch`, and `HumanMessage` imports in the test module.

```python
class AppointmentIntentTests(unittest.TestCase):
    def categorize(self, category, **state):
        message = HumanMessage(content="Solicitud de prueba")
        agent = SimpleNamespace(invoke=lambda inputs: SimpleNamespace(
            category=SimpleNamespace(value=category)))
        with patch(
            "src.nodes.message_categorizer_node.message_categorizer_agent",
            return_value=agent,
        ):
            return message_categorizer_node({
                **state, "current_message": message, "messages": [message],
            })

    def test_all_actions_and_identity_continuity(self):
        from src.structured_outputs import APPOINTMENT_INTENTS, MessageCategory
        for category, intent in APPOINTMENT_INTENTS.items():
            with self.subTest(category=category):
                self.assertEqual(MessageCategory(category).value, category)
                result = self.categorize(category)
                self.assertEqual(result["appointment_intent"], intent)
                self.assertEqual(result["current_flow"], "appointment_services")
                result = self.categorize("confirmation", **result)
                self.assertEqual(result["appointment_intent"], intent)

    def test_switch_preserves_customer_question_but_clears_slot(self):
        result = self.categorize(
            "cancel_appointment", appointment_intent="book_appointment",
            current_flow="appointment_services",
            pending_question="existing_customer_email",
            next_action="request_existing_customer_email",
            confirmed_slot={"starts_at": "2026-09-10T10:00:00"},
            active_appointment={"id": "old"},
        )
        self.assertEqual(result["appointment_intent"], "cancel_appointment")
        self.assertEqual(result["pending_question"], "existing_customer_email")
        self.assertIsNone(result["confirmed_slot"])
        self.assertIsNone(result["active_appointment"])

    def test_decline_and_service_inquiry_clear_intent(self):
        for category in ("decline", "service_inquiry", "greeting"):
            result = self.categorize(
                category, appointment_intent="cancel_appointment",
                current_flow="appointment_services",
            )
            self.assertIsNone(result["appointment_intent"])
            self.assertIsNone(result["current_flow"])
```

- [x] **Step 2: With test authorization, run the focused check and confirm it fails on missing categories/map.**

```bash
uv run python -m unittest discover -s tests -p 'test_appointment_services_subgraph.py' -k AppointmentIntentTests -v
```

- [x] **Step 3: Add the contracts.** Add the enum members inside the existing `MessageCategory` and append the map in `src/structured_outputs.py`. Leave legacy `BookingIntent` and `PlannerIntentOutput` intact.

```python
# Inside MessageCategory:
check_availability = "check_availability"
view_appointment = "view_appointment"

# At module scope:
APPOINTMENT_INTENTS = {
    "new_appointment": "book_appointment",
    "check_availability": "check_availability",
    "reschedule_appointment": "reschedule_appointment",
    "cancel_appointment": "cancel_appointment",
    "view_appointment": "view_appointment",
}

# Inside both MessageGraphState and UserValidationState:
appointment_intent: str | None
next_action: str | None  # Replace the existing annotation; do not duplicate it.
```

- [x] **Step 4: Narrowly edit the existing categorizer prompt, preserving the user's other prompt edits.** Replace the current new-appointment/service-inquiry definitions and add the following entries/rules. Add availability and viewing to the existing writer's clear-and-helpful tone list.

```text
- new_appointment: An explicit request to create a new appointment.
- check_availability: Asking whether appointment dates or time slots are free,
  without asking to book (e.g. "¿Tienen horario mañana?").
- view_appointment: Asking to see an existing appointment or its details
  (e.g. "¿Cuándo es mi cita?", "Muéstrame mis citas").
- service_inquiry: Asking about offered treatments, prices, or service duration;
  appointment time-slot availability belongs to check_availability.
- service_request: An ambiguous appointment request without a clear operation,
  including multiple incompatible appointment actions with no dominant intent.

An availability question alone never authorizes a new booking. An explicit
request to cancel an existing appointment is cancel_appointment; declining a
suggestion is decline. A generic "sí" without an established appointment goal
does not establish new_appointment. Keep confirmation for short affirmations.
```

- [x] **Step 5: Update categorizer state transitions.** Import `APPOINTMENT_INTENTS`; use its keys instead of the local two-category set. Remove cancellation from `FLOW_EXIT_CATEGORIES`, add `service_inquiry`, and include `appointment_intent = None` in the existing exit reset. Replace the appointment-category branch with:

```python
elif category in APPOINTMENT_INTENTS:
    intent = APPOINTMENT_INTENTS[category]
    if state.get("appointment_intent") != intent:
        state["active_appointment"] = None
        state["confirmed_slot"] = None
        identity_pending = state.get("pending_question") in {
            "existing_customer_email", "confirm_create_customer", "new_customer_details",
        } or state.get("next_action") in {
            "retry_customer_lookup", "retry_customer_creation",
        }
        if not identity_pending:
            state["pending_question"] = None
            state["next_action"] = None
    state["appointment_intent"] = intent
    state["current_flow"] = "appointment_services"
elif category == "service_request":
    state["current_flow"] = "appointment_services"
    identity_pending = state.get("pending_question") in {
        "existing_customer_email", "confirm_create_customer", "new_customer_details",
    } or state.get("next_action") in {
        "retry_customer_lookup", "retry_customer_creation",
    }
    if not identity_pending:
        state["appointment_intent"] = None
        state["next_action"] = None
        state["pending_question"] = None
        state["active_appointment"] = None
        state["confirmed_slot"] = None
```

Retain the existing history/summary inputs and model invocation. Generic confirmation leaves saved intent intact. Unsupported categories are checked by the validation node in Task 2, so they cannot dispatch stale intent.

- [x] **Step 6: With authorization, rerun the focused command.** Expected: all `AppointmentIntentTests` pass. Inspect `git diff` to ensure unrelated prompt edits remain intact.
- [x] **Step 7: Review the contract change as one unit.** Suggested commit: `feat(appointment): define explicit appointment intents`. If committing, stage only task hunks, especially in the already modified prompt file.

## Task 2: Replace the appointment tool loop with explicit nodes

**Files:** create `src/nodes/appointment_services/appointment_validation_node.py`, `appointment_action_nodes.py`, and `__init__.py`; replace `src/graph/appointment_services_subgraph.py`; update `tests/test_appointment_services_subgraph.py`.

**Interfaces:**
- Consumes `MessageGraphState` and `APPOINTMENT_INTENTS` from Task 1.
- Produces `appointment_validation_node(state: MessageGraphState) -> dict`, five action functions of the same signature, and local `NODES`.
- Preserves public `AppointmentServicesSubgraph` and compiled `appointment_services_subgraph` exports.
- Routers: `router_request(state: MessageGraphState) -> str` and `route_appointment_validation(state: MessageGraphState) -> str`.

- [x] **Step 1: Replace only `AppointmentServicesGraphTests` and `AppointmentServicesGraphIntegrationTests`, which require the old loop.** Keep customer handoff, writer, continuity, and legacy tool lifecycle tests. Add the following graph/behavior checks:

```python
class AppointmentExplicitGraphTests(unittest.TestCase):
    def test_actions_are_terminal_and_do_not_consume_apis(self):
        from src.graph.appointment_services_subgraph import appointment_services_subgraph
        from src.structured_outputs import APPOINTMENT_INTENTS
        graph = appointment_services_subgraph.get_graph()
        edges = {(e.source, e.target) for e in graph.edges}
        self.assertNotIn("tools", graph.nodes)
        self.assertNotIn("appointment_agent", graph.nodes)
        self.assertIn("appointment_validation", graph.nodes)
        for category, action in APPOINTMENT_INTENTS.items():
            with self.subTest(action=action), patch(
                "httpx.AsyncClient", side_effect=AssertionError("Unexpected HTTP")
            ), patch(
                "langchain_openrouter.ChatOpenRouter",
                side_effect=AssertionError("Unexpected appointment LLM"),
            ):
                self.assertIn((action, "__end__"), edges)
                result = appointment_services_subgraph.invoke({
                    "messages": [HumanMessage(content="Solicitud")],
                    "message_category": category,
                    "business_id": str(uuid4()), "customer_id": "customer-1",
                    "current_flow": "appointment_services",
                    "confirmed_slot": {"starts_at": "stale"},
                    "active_appointment": {"id": "stale"},
                })
                self.assertIsInstance(result["messages"][-1], AIMessage)
                self.assertIn("pendiente", result["messages"][-1].content)
                expected_phrase = {
                    "book_appointment": "agendar citas",
                    "check_availability": "consultar horarios",
                    "reschedule_appointment": "reprogramar citas",
                    "cancel_appointment": "cancelar citas",
                    "view_appointment": "consultar tus citas",
                }[action]
                self.assertIn(expected_phrase, result["messages"][-1].content)
                self.assertEqual(result["customer_id"], "customer-1")
                for field in ("appointment_intent", "current_flow", "next_action",
                              "pending_question", "confirmed_slot", "active_appointment"):
                    self.assertIsNone(result[field])

    def test_validation_rejects_stale_intent_and_contextless_confirmation(self):
        from src.nodes.appointment_services.appointment_validation_node import (
            appointment_validation_node,
        )
        for category in ("unrelated", "", "not_a_category", "confirmation"):
            state = {"message_category": category,
                     "appointment_intent": "book_appointment",
                     "next_action": "book_appointment"}
            self.assertEqual(appointment_validation_node(state)["next_action"],
                             "clarify_appointment_intent")
        result = appointment_validation_node({
            "message_category": "confirmation", "appointment_intent": "view_appointment",
            "current_flow": "appointment_services",
        })
        self.assertEqual(result["next_action"], "view_appointment")

    def test_unknown_intent_clarifies_and_missing_identity_terminates(self):
        from src.graph.appointment_services_subgraph import appointment_services_subgraph
        base = {"messages": [HumanMessage(content="Sí")],
                "message_category": "confirmation", "current_flow": "appointment_services",
                "business_id": str(uuid4()), "customer_id": "customer-1"}
        result = appointment_services_subgraph.invoke(base)
        self.assertEqual(result["pending_question"], "appointment_intent")
        self.assertEqual(result["next_action"], "clarify_appointment_intent")
        for missing in ("business_id", "customer_id"):
            result = appointment_services_subgraph.invoke({
                **base, missing: None, "message_category": "cancel_appointment",
            })
            self.assertIsNone(result["current_flow"])
            self.assertIn("validar", result["messages"][-1].content)
```

- [x] **Step 2: With authorization, run the new check.** Expected before replacement: failures for missing explicit nodes and validation module.

```bash
uv run python -m unittest discover -s tests -p 'test_appointment_services_subgraph.py' -k AppointmentExplicitGraphTests -v
```

- [x] **Step 3: Implement `appointment_validation_node.py`.** Validate each turn; do not skip because `next_action` was saved previously.

```python
from src.state import MessageGraphState
from src.structured_outputs import APPOINTMENT_INTENTS


def appointment_validation_node(state: MessageGraphState) -> dict:
    category = state.get("message_category")
    intent = APPOINTMENT_INTENTS.get(category)
    customer_handoff = (
        state.get("next_action") == "collect_appointment_details"
        and state.get("customer_status") in {"existing", "new"}
    )
    if (
        intent is None
        and (category == "confirmation" or customer_handoff)
        and state.get("current_flow") == "appointment_services"
        and state.get("appointment_intent") in APPOINTMENT_INTENTS.values()
    ):
        intent = state["appointment_intent"]
    return {
        "appointment_intent": intent,
        "next_action": intent or "clarify_appointment_intent",
        "pending_question": None if intent else "appointment_intent",
    }
```

- [x] **Step 4: Implement `appointment_action_nodes.py`.** These five functions are distinct graph operations despite sharing a module.

```python
from langchain_core.messages import AIMessage
from src.state import MessageGraphState


def _api_pending(message: str) -> dict:
    return {
        "messages": [AIMessage(content=message)],
        "appointment_intent": None, "current_flow": None,
        "pending_question": None, "next_action": None,
        "active_appointment": None, "confirmed_slot": None,
    }


def book_appointment_node(state: MessageGraphState) -> dict:
    return _api_pending("La integración para agendar citas está pendiente. No he creado ninguna cita.")


def check_availability_node(state: MessageGraphState) -> dict:
    return _api_pending("La integración para consultar horarios está pendiente. No puedo confirmar disponibilidad.")


def reschedule_appointment_node(state: MessageGraphState) -> dict:
    return _api_pending("La integración para reprogramar citas está pendiente. No he cambiado ninguna cita.")


def cancel_appointment_node(state: MessageGraphState) -> dict:
    return _api_pending("La integración para cancelar citas está pendiente. No he cancelado ninguna cita.")


def view_appointment_node(state: MessageGraphState) -> dict:
    return _api_pending("La integración para consultar tus citas está pendiente. No puedo mostrar citas confirmadas.")
```

- [x] **Step 5: Implement the local registry in `__init__.py`.**

```python
from .appointment_validation_node import appointment_validation_node
from .appointment_action_nodes import (
    book_appointment_node, check_availability_node, reschedule_appointment_node,
    cancel_appointment_node, view_appointment_node,
)

NODES = {
    "appointment_validation": appointment_validation_node,
    "book_appointment": book_appointment_node,
    "check_availability": check_availability_node,
    "reschedule_appointment": reschedule_appointment_node,
    "cancel_appointment": cancel_appointment_node,
    "view_appointment": view_appointment_node,
}
```

- [x] **Step 6: Replace the subgraph module.** Remove its imports of `SERVICES_REQUEST_NODES`, `ToolNode`, `tools_condition`, and appointment tools.

```python
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from src.nodes.appointment_services import NODES
from src.state import MessageGraphState
from src.structured_outputs import APPOINTMENT_INTENTS


def _has_context(state: MessageGraphState) -> bool:
    customer_id = state.get("customer_id") or (state.get("customer") or {}).get("id")
    return bool(state.get("business_id") and customer_id)


def router_request(state: MessageGraphState) -> str:
    if _has_context(state) and (
        state.get("message_category") in APPOINTMENT_INTENTS
        or state.get("message_category") == "service_request"
        or state.get("current_flow") == "appointment_services"
    ):
        return "appointment_validation"
    return "fallback"


def route_appointment_validation(state: MessageGraphState) -> str:
    action = state.get("next_action")
    return action if action in APPOINTMENT_INTENTS.values() else "fallback"


def fallback_node(state: MessageGraphState) -> dict:
    has_context = _has_context(state)
    message = (
        "¿Quieres agendar una cita, consultar horarios, reprogramar, cancelar o ver tus citas?"
        if has_context else
        "Necesito validar el negocio y el cliente antes de gestionar citas."
    )
    return {
        "messages": [AIMessage(content=message)],
        "appointment_intent": None,
        "current_flow": "appointment_services" if has_context else None,
        "pending_question": "appointment_intent" if has_context else None,
        "next_action": "clarify_appointment_intent" if has_context else None,
        "active_appointment": None, "confirmed_slot": None,
    }


class AppointmentServicesSubgraph:
    def __init__(self):
        workflow = StateGraph(MessageGraphState)
        for name, node in NODES.items():
            workflow.add_node(name, node)
        workflow.add_node("fallback", fallback_node)
        workflow.add_conditional_edges(START, router_request, {
            "appointment_validation": "appointment_validation", "fallback": "fallback",
        })
        workflow.add_conditional_edges(
            "appointment_validation", route_appointment_validation,
            {**{action: action for action in APPOINTMENT_INTENTS.values()},
             "fallback": "fallback"},
        )
        for action in APPOINTMENT_INTENTS.values():
            workflow.add_edge(action, END)
        workflow.add_edge("fallback", END)
        self.graph = workflow.compile()


appointment_services_subgraph = AppointmentServicesSubgraph().graph
```

- [x] **Step 7: With authorization, rerun the focused check.** Expected: explicit graph checks pass, all five responses terminate, and network/model guards remain untouched.
- [x] **Step 8: Review the new subgraph as one unit.** Suggested commit: `refactor(appointment): route validated intent to explicit operation nodes`.

## Task 3: Connect all intents through customer validation and verify the complete handoff

**Files:** `src/graph/appointment_booking_graph.py`, `src/graph/user_services_validation_subgraph.py`, `src/nodes/user_services_validation/user_validation_node.py`, `tests/test_appointment_services_subgraph.py`.

**Interfaces:**
- Consumes Task 1's category map/intent state and Task 2's compiled subgraph.
- Preserves `route_by_category`, `route_after_user_services`, the user-services `router_request`, and `user_validations_node` signatures.
- Produces the unchanged final `message_response` interface for the main workflow.

- [x] **Step 1: Add the expanded entry/continuity check.** Use existing fake HTTP helpers when extending the compiled customer handoff check below.

```python
class AppointmentExpandedRoutingTests(unittest.TestCase):
    def test_every_category_enters_identification_then_appointment_services(self):
        from src.graph.appointment_booking_graph import route_by_category, route_after_user_services
        from src.graph.user_services_validation_subgraph import router_request
        from src.nodes.user_services_validation.user_validation_node import user_validations_node
        from src.structured_outputs import APPOINTMENT_INTENTS
        for category in (*APPOINTMENT_INTENTS, "service_request"):
            with self.subTest(category=category):
                state = {"message_category": category,
                         "current_flow": "appointment_services",
                         "appointment_intent": APPOINTMENT_INTENTS.get(category)}
                self.assertEqual(route_by_category(state), "user_services")
                self.assertEqual(router_request(state), "user_validation")
                self.assertEqual(user_validations_node(state)["pending_question"],
                                 "existing_customer_email")
                validated = {**state, "customer": {"id": "customer-1"}}
                self.assertEqual(route_by_category(validated), "appointment_services")
                self.assertEqual(route_after_user_services(validated), "appointment_services")

    def test_customer_retry_still_wins_with_a_validated_customer(self):
        from src.graph.appointment_booking_graph import route_by_category
        self.assertEqual(route_by_category({
            "message_category": "view_appointment", "customer_id": "customer-1",
            "next_action": "retry_customer_lookup",
        }), "user_services")

    def test_pending_response_reaches_writer_unchanged(self):
        from src.graph.appointment_services_subgraph import appointment_services_subgraph
        result = appointment_services_subgraph.invoke({
            "messages": [HumanMessage(content="Cancela mi cita")],
            "message_category": "cancel_appointment",
            "business_id": str(uuid4()), "customer_id": "customer-1",
        })
        with patch("src.nodes.message_writer_node.message_writer") as model:
            written = message_writer_node(result)
        model.assert_not_called()
        self.assertEqual(written["message_response"],
            "La integración para cancelar citas está pendiente. No he cancelado ninguna cita.")
        self.assertNotIn("messages", written)
```

- [x] **Step 2: With authorization, run the focused check and confirm entry failures for the new categories.**

```bash
uv run python -m unittest discover -s tests -p 'test_appointment_services_subgraph.py' -k AppointmentExpandedRoutingTests -v
```

- [x] **Step 3: Expand parent routing using the shared map.** Import `APPOINTMENT_INTENTS` in the parent graph and replace its local appointment categories. Preserve customer retry/question precedence, writer routing, and the existing customer-ID fallback. Remove cancellation from the later user-services-only branch.

```python
APPOINTMENT_CATEGORIES = set(APPOINTMENT_INTENTS) | {"service_request"}

# After the existing appointment-flow branch in route_by_category:
if category == "service_inquiry":
    return "user_services"
```

The existing `route_after_user_services` can stay as written: the categorizer now starts the appointment flow for all five operations, and the shared intent survives customer follow-ups.

- [x] **Step 4: Expand the two user-services entry checks.** Import `APPOINTMENT_INTENTS` in both modules. Replace their current three-category literals with the map keys plus ambiguous service requests; retain pending questions and retry handling unchanged.

```python
# src/graph/user_services_validation_subgraph.py, inside router_request:
if state.get("message_category") in APPOINTMENT_INTENTS or state.get("message_category") == "service_request":
    return "user_validation"

# src/nodes/user_services_validation/user_validation_node.py:
if not pending_question and (
    state.get("message_category") in APPOINTMENT_INTENTS
    or state.get("message_category") == "service_request"
):
    return {
        "pending_question": "existing_customer_email",
        "next_action": "request_existing_customer_email",
        "user_data": {},
    }
```

- [x] **Step 5: Add a compiled user-subgraph continuity check.** This verifies the state-schema boundary, rather than assuming dictionary-only routing checks prove persistence. In the existing async handoff test class, add:

```python
async def test_all_intents_survive_compiled_customer_lookup(self):
    from src.graph.user_services_validation_subgraph import user_services_subgraph
    from src.graph.appointment_services_subgraph import appointment_services_subgraph
    from src.graph.appointment_booking_graph import route_after_user_services
    from src.structured_outputs import APPOINTMENT_INTENTS
    FakeClient.response = JsonResponse({"id": "customer-1", "email": "ana@example.com"})
    for intent in APPOINTMENT_INTENTS.values():
        with self.subTest(intent=intent), patch(
            "src.nodes.user_services_validation.customer_lookup_node.httpx.AsyncClient",
            FakeClient,
        ):
            result = await user_services_subgraph.ainvoke({
                "messages": [HumanMessage(content="ana@example.com")],
                "business_id": uuid4(), "message_category": "unrelated",
                "current_flow": "appointment_services", "appointment_intent": intent,
                "pending_question": "existing_customer_email",
            })
        self.assertEqual(result["appointment_intent"], intent)
        self.assertEqual(route_after_user_services(result), "appointment_services")
        final = await appointment_services_subgraph.ainvoke(result)
        self.assertIn("pendiente", final["messages"][-1].content)
        self.assertIsNone(final["appointment_intent"])

async def test_intent_survives_creation_confirmation_and_details(self):
    from src.graph.user_services_validation_subgraph import user_services_subgraph
    from src.structured_outputs import APPOINTMENT_INTENTS
    for intent in APPOINTMENT_INTENTS.values():
        result = await user_services_subgraph.ainvoke({
            "messages": [HumanMessage(content="Sí")],
            "business_id": uuid4(), "message_category": "confirmation",
            "current_flow": "appointment_services", "appointment_intent": intent,
            "pending_question": "confirm_create_customer",
            "user_data": {"email": "ana@example.com"},
        })
        self.assertEqual(result["pending_question"], "new_customer_details")
        self.assertEqual(result["appointment_intent"], intent)
        FakeClient.response = JsonResponse({"id": "customer-1", "email": "ana@example.com"})
        with patch(
            "src.nodes.user_services_validation.customer_creation_node.httpx.AsyncClient",
            FakeClient,
        ):
            result = await user_services_subgraph.ainvoke({
                **result, "messages": [HumanMessage(content="Ana López")],
            })
        self.assertEqual(result["appointment_intent"], intent)
        self.assertEqual(result["customer_id"], "customer-1")
```

- [x] **Step 6: With authorization, run the affected regression files.** These use fakes/mocks. Do not invoke a live model or backend; retain the existing mock setup in the other test files.

```bash
uv run python -m unittest discover -s tests -p 'test_appointment_services_subgraph.py' -v
uv run python -m unittest discover -s tests -p 'test_pending_question_flow.py' -v
uv run python -m unittest discover -s tests -p 'test_compact_context_node.py' -v
```

Expected: expanded entry/continuity, explicit graph, writer passthrough, customer identification, and compaction checks pass. Legacy tool tests may remain because their modules are retained, but they must not imply the new graph invokes those tools. Investigate actual failures before proposing dependency changes; preserve the user's current dependency work.

- [x] **Step 7: Review the complete behavior against the spec.** Confirm every category reaches the named operation, invalid intent clarifies, identity continuity is preserved, pending operations cannot claim success, and the new subgraph has no executable appointment API path. Inspect `git diff --check` and the changed file list. Update the spec status only after implementation and report actual validation results.
- [x] **Step 8: Review parent integration as one unit.** Suggested commit: `feat(appointment): connect all appointment actions through customer validation`. Stage only intended hunks; do not bundle the user's existing unrelated edits.

## Completion and execution handoff

The implementation is complete and remains uncommitted in the existing feature branch. It intentionally changes the main appointment flow from working legacy tool calls to explicit API-pending responses until integration contracts are supplied. Execute inline with `superpowers:executing-plans`, or use `superpowers:subagent-driven-development` if the user selects delegated execution. Test execution remains subject to the repository's explicit authorization requirement.


## Execution record — 2026-09-08

- Completed all three implementation tasks using the existing classifier, graph state, and writer.
- Added `src/helpers/workflow.py` to share customer-question/retry checks, customer identity checks, and appointment reset state across the consuming nodes and routers. Added the shared `APPOINTMENT_CATEGORIES` set beside `APPOINTMENT_INTENTS`; no new dependencies or interface hierarchy.
- Extended user validation to preserve unfinished identity questions when an explicit appointment request arrives. A failing check demonstrated that cancellation text otherwise cleared creation confirmation or became a customer name; the shared-node fix passes that check.
- Kept five distinct operation nodes with their API-pending responses. The main appointment graph no longer runs the legacy tools.
- Used literal appointment cases in checks so a missing category cannot silently remove its own test coverage.
- Before implementation, the focused intent checks failed for missing intent behavior; a focused validator check failed for the missing module. Before parent integration, expanded entry checks failed for availability, viewing, and generic service requests. All focused checks passed after their corresponding changes.
- Initial implementation results: **31 appointment tests + 31 pending-question tests + 2 compaction tests = 64 passed**. Final runs disabled LangSmith/LangChain tracing; initial graph checks had connection warnings from environment-enabled tracing.
- Ran the approved commands with `uv run --no-sync` and `UV_CACHE_DIR=/private/tmp/deskia-uv-cache` because the default uv cache is outside sandbox write permissions. No dependency installation or lockfile update was needed.
- Independent read-only review found no additional actionable issues. `git diff --check` passed.
- Verified `pyproject.toml`, `uv.lock`, and `src/utils/rag_utils.py` against their pre-task hashes; all unchanged. Preserved the user's original prompt footer.
- Reviewed the three task units without making the suggested commits. Changes remain in the current workspace on `feature/stable-appointment-booking`; no merge, push, or PR was performed.

Reproduce the authorized regression checks from the repository root:

```bash
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false UV_CACHE_DIR=/private/tmp/deskia-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_appointment_services_subgraph.py' -q
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false UV_CACHE_DIR=/private/tmp/deskia-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_pending_question_flow.py' -q
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false UV_CACHE_DIR=/private/tmp/deskia-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_compact_context_node.py' -q
```


## Completion audit

Three subagents independently audited Tasks 1/3, Task 2, and documentation/test coverage. The main agent reviewed their findings and implementation changes.

| Task | Final status | Evidence |
| --- | --- | --- |
| 1: Intent contracts and categorizer transitions | Complete | Shared category map/state, intent-switch handling, classifier prompt, and regression checks |
| 2: Explicit appointment nodes | Complete | Entry and validation routers, five terminal API-pending nodes, fallback, writer passthrough |
| 3: Customer/parent integration | Complete after audit fix | Post-customer router now blocks appointment handoff while customer questions or retries remain pending, even with cached identity |

The audit fix adds one guard using `customer_validation_pending(state)`. Its tests reproduced ten pending-state/identity failures and loss of retry state after a failed lookup in the compiled parent graph before the fix. They pass after the fix, including two successive failed lookups. Active-flow stale-intent negative coverage was also strengthened, and the spec's historical behavior descriptions were corrected.

Final main-agent validation: **33 appointment tests + 31 pending-question tests + 2 compaction tests = 66 passed**. All three authorized commands completed with exit code 0; `git diff --check` passed. No appointment API implementation, commits, merge, push, or PR was added. Appointment APIs remain intentionally deferred, and changes remain uncommitted in the workspace.
