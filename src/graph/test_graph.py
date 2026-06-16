
from langgraph.graph import END, START, StateGraph
from src.nodes import NODES
from src.state import State
import os

LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")

builder = StateGraph(State)
 
builder.add_node("call_llm", NODES["call_llm"])
builder.add_node("summarise", NODES["summarise"])
 
builder.add_edge(START, "call_llm")
builder.add_edge("call_llm", "summarise")
builder.add_edge("summarise", END)
 
test_graph = builder.compile()
