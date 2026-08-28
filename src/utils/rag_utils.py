from threading import Lock

_rag_tool = None
_rag_tool_lock = Lock()



def _build_rag_tool():
    from dotenv import load_dotenv
    from langchain_chroma import Chroma
    from langchain_community.document_loaders import TextLoader
    from langchain_core.tools.retriever import create_retriever_tool
    from langchain_huggingface import HuggingFaceEmbeddings  # <-- Cambio clave    
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    model = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")    
    load_dotenv()
    loader = TextLoader("src/data/services.txt")
    documents = loader.load()
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=100,
        chunk_overlap=50
    )
    docs_splits = text_splitter.split_documents(documents)

    vectorstore = Chroma.from_documents(documents=docs_splits, embedding=model, persist_directory="./chroma_db")
    retriever = vectorstore.as_retriever(search_kwargs={"k":6})

    retriever_tool = create_retriever_tool(retriever, "retrieve_products_and_services_information", "Search and return information about products and serivices.")
    return retriever_tool


def get_rag_tool():
    global _rag_tool

    if _rag_tool is None:
        with _rag_tool_lock:
            if _rag_tool is None:
                _rag_tool = _build_rag_tool()

    return _rag_tool
