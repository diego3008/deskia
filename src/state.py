from typing import Annotated, TypedDict

from langgraph.graph import add_messages


class State(TypedDict):
    messages: Annotated[list, add_messages]  # reducer: appends, never overwrites
    step_log: Annotated[list[str], list.__add__]  # accumulates node names visited
 