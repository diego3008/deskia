
from src.utils import rag_tool
from src.state import ServicesInquiryNode

async def services_inquiry_node(state: ServicesInquiryNode) -> dict:

    message = state["messages"][-1]
    query = message.content if hasattr(message, "content") else str(message)
    context = await rag_tool.ainvoke({"query": query})

    return {"retrieved_services": context}