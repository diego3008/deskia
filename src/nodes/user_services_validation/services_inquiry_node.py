
import asyncio

from src.state import ServicesInquiryNode
from src.utils import get_rag_tool

async def services_inquiry_node(state: ServicesInquiryNode) -> dict:
    message = state["messages"][-1]
    query = message.content if hasattr(message, "content") else str(message)
    rag_tool = await asyncio.to_thread(get_rag_tool)
    context = await asyncio.to_thread(rag_tool.invoke, {"query": query})

    return {"retrieved_services": context}
