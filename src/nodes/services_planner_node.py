from src.state import MessageGraphState

from langchain_core.prompts import PromptTemplate
from langchain_anthropic import ChatAnthropic
from dotenv import load_dotenv

from src.structured_outputs import PlannerIntentOutput
from src.helpers import helpers

load_dotenv()

PLANNER_INTENT_PROMPT = """You classify a customer's appointment request.

Return exactly one intent:
- book: the customer wants a NEW appointment.
- reschedule: the customer wants to change or move an EXISTING appointment.
- unknown: it is not yet clear which of the two they want.

Recent conversation:
{history}

Latest customer message:
{message}
"""


def services_planner_agent():
    prompt = PromptTemplate(
        template=PLANNER_INTENT_PROMPT,
        input_variables=["message", "history"],
    )
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
    return prompt | llm.with_structured_output(PlannerIntentOutput)


# Ordered steps per intent. Terminal steps ("book"/"reschedule") are never marked
# done from gates — completing them ends the flow.
STEP_CATALOGS = {
    "book": ["availability", "book"],
    "reschedule": ["find", "availability", "reschedule"],
}


def plan_status(state: dict) -> dict:
    """Derive per-step status from existing state gates.

    Returns {"steps": [{"id", "status"}], "next": <first pending step id or None>}.
    """
    plan = state.get("service_plan")
    if not plan:
        return {"steps": [], "next": None}

    gate_done = {
        "find": state.get("active_appointment") is not None,
        "availability": state.get("confirmed_slot") is not None,
    }

    steps = []
    next_step = None
    for step in plan.get("steps", []):
        is_done = gate_done.get(step, False)
        steps.append({"id": step, "status": "done" if is_done else "pending"})
        if not is_done and next_step is None:
            next_step = step
    return {"steps": steps, "next": next_step}


def format_plan_block(plan: dict, status: dict) -> str:
    """Render the plan as an advisory checklist for the system prompt."""
    lines = []
    for step in status["steps"]:
        mark = "[x]" if step["status"] == "done" else "[ ]"
        lines.append(f"  {mark} {step['id']}")
    checklist = "\n".join(lines)
    nxt = status["next"] or "confirm the details and finish"
    return (
        f"CURRENT PLAN ({plan['intent']}). Follow these steps in order; the tools "
        f"enforce the prerequisites:\n{checklist}\nNEXT STEP: {nxt}"
    )


def services_planner_node(state: MessageGraphState) -> dict:
    # A plan already exists for this flow — pass through untouched.
    if state.get("service_plan"):
        return {}

    body = state.get("current_message") or ""
    if not body:
        return {}

    history = helpers["build_recent_history"](state.get("messages", []))

    # Graceful degradation: any failure leaves the plan unset and the subgraph
    # behaves like today's plain ReAct loop.
    try:
        result = services_planner_agent().invoke({"message": body, "history": history})
        intent = result.intent.value
    except Exception:
        return {}

    if intent not in STEP_CATALOGS:  # covers "unknown" and anything unexpected
        return {}

    return {"service_plan": {"intent": intent, "steps": STEP_CATALOGS[intent]}}
