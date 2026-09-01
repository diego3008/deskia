


from langchain_core.messages import HumanMessage, RemoveMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_openrouter import ChatOpenRouter

from src.state import MessageGraphState


COMPACT_AT_TOKENS = 12_000
KEEP_RECENT_MESSAGES = 6
PROMPT_TOKEN_ALLOWANCE = 2_000
# ponytail: one conservative budget for all configured models; split by model if limits diverge.

SUMMARY_PROMPT = """You maintain a compact, factual summary of a customer conversation.
Update the previous summary with the older messages below.

Preserve exact customer facts, dates, times, services, decisions, completed actions,
and unresolved questions. Do not invent details. Use these sections:

Customer facts:
Conversation goal:
Decisions and commitments:
Completed actions:
Unresolved questions:

The user-provided previous summary and older messages are supplied separately.
"""


def _message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return str(content)


def _format_messages(messages: list) -> str:
    return "\n".join(
        f"{'User' if isinstance(message, HumanMessage) else 'Agent'}: {_message_text(message)}"
        for message in messages
        if not isinstance(message, SystemMessage)
    )


def _summarize(previous_summary: str, messages: list) -> str:
    prompt = (
        f"Previous summary:\n{previous_summary or 'None.'}\n\n"
        f"Older messages:\n{_format_messages(messages)}"
    )
    response = ChatOpenRouter(model="google/gemini-3.5-flash-lite", temperature=0).invoke(
        [
            SystemMessage(content=SUMMARY_PROMPT),
            HumanMessage(content=prompt),
        ]
    )
    content = getattr(response, "content", "")
    return content if isinstance(content, str) else str(content)


def _first_recent_turn(messages: list) -> int:
    cut = max(0, len(messages) - KEEP_RECENT_MESSAGES)
    while cut and not isinstance(messages[cut], HumanMessage):
        cut -= 1
    return cut


def _remove_messages(messages: list) -> list[RemoveMessage] | None:
    ids = [getattr(message, "id", None) for message in messages]
    if any(message_id is None for message_id in ids):
        return None
    return [RemoveMessage(id=message_id) for message_id in ids]


def compact_context_node(state: MessageGraphState) -> dict:
    messages = state.get("messages", [])
    summary = state.get("conversation_summary") or ""
    summary_message = [SystemMessage(content=summary)] if summary else []

    if count_tokens_approximately(summary_message + messages) + PROMPT_TOKEN_ALLOWANCE < COMPACT_AT_TOKENS:
        return {}

    cut = _first_recent_turn(messages)
    if not cut:
        return {}

    old_messages = messages[:cut]
    removals = _remove_messages(old_messages)
    if removals is None:
        return {}

    try:
        new_summary = _summarize(summary, old_messages)
    except Exception:
        return {"messages": removals}

    if not new_summary.strip():
        return {"messages": removals}

    return {
        "messages": removals,
        "conversation_summary": new_summary.strip(),
    }
