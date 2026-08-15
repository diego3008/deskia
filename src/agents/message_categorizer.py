from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv

from src.structured_outputs import CategorizerMessageOutput
from ..prompts import MESSAGE_CATEGORIZER_PROMPT
from langchain_anthropic import ChatAnthropic
# from langchain_openai import ChatOpenAI
from langchain_openrouter import ChatOpenRouter

load_dotenv()


def message_categorizer_agent():
    message_categorizer_prompt = PromptTemplate(
        template=MESSAGE_CATEGORIZER_PROMPT,
        input_variables=["message"]
    )

    llm = ChatOpenRouter(model="google/gemini-3.5-flash-lite", temperature=0)
    # llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    return message_categorizer_prompt | llm.with_structured_output(CategorizerMessageOutput)
