from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.tools.retriever import create_retriever_tool
from dotenv import load_dotenv

load_dotenv()

loader = TextLoader("src/data/dental_services.txt")


def retriever_tool():
    documents = loader.load()
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=100,
        chunk_overlap=50
    )
    docs_splits = text_splitter.split_documents(documents)

    vectorstore = Chroma.from_documents(documents=docs_splits, embedding=OpenAIEmbeddings(), persist_directory="./chroma_db")
    retriever = vectorstore.as_retriever(search_kwargs={"k":6})

    retriever_tool = create_retriever_tool(retriever, "retrieve_products_and_services_information", "Search and return information about products and serivices.")
    return retriever_tool

rag_tool = retriever_tool()
