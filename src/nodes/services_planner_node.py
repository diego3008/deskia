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
