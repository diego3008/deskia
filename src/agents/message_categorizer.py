from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv

from src.structured_outputs import CategorizerMessageOutput
from ..prompts import MESSAGE_CATEGORIZER_PROMPT
from langchain_openrouter import ChatOpenRouter

load_dotenv()


def message_categorizer_agent():
    message_categorizer_prompt = PromptTemplate(
        template=MESSAGE_CATEGORIZER_PROMPT,
        input_variables=["message", "history"]
    )

    llm = ChatOpenRouter(model="google/gemini-3.7-flash", temperature=0)
    
    return message_categorizer_prompt | llm.with_structured_output(CategorizerMessageOutput)
