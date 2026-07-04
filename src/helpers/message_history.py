from langchain_core.messages import HumanMessage, SystemMessage


def build_recent_history(messages: list) -> str:
    """Build a "User: ..." / "Agent: ..." history string from the last 6 messages.

    Excludes SystemMessage entries. Falls back to "No previous messages." when
    there is nothing to show.
    """
    recent = [
        m for m in messages[-6:]
        if not isinstance(m, SystemMessage)
    ]
    return "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'Agent'}: {m.content}"
        for m in recent
    ) or "No previous messages."
