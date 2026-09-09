from threading import Lock

_rag_tool = None
_rag_tool_lock = Lock()



def _build_rag_tool():
    from dotenv import load_dotenv
    from langchain_chroma import Chroma
    from langchain_community.document_loaders import TextLoader
    from langchain_core.tools.retriever import create_retriever_tool
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    load_dotenv()

    embeddings = HuggingFaceEmbeddings(
        model_name="paraphrase-multilingual-MiniLM-L12-v2"
    )

    vectorstore = Chroma(
        collection_name="booker_services_v1",
        embedding_function=embeddings,
        persist_directory="./chroma_db",
    )

    # Evita insertar los mismos documentos cada vez que se inicializa el agente
    existing_docs = vectorstore.get(limit=1)

    if not existing_docs["ids"]:
        loader = TextLoader(
            "src/data/services.txt",
            encoding="utf-8"
        )

        documents = loader.load()

        for document in documents:
            document.metadata.update({
                "source_type": "services_catalog",
                "source": "services.txt",
            })

        text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=500,
            chunk_overlap=50,
        )

        docs_splits = text_splitter.split_documents(documents)

        vectorstore.add_documents(docs_splits)

    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": 10,
            "fetch_k": 30,
            "lambda_mult": 0.5,
        },
    )

    return create_retriever_tool(
        retriever,
        name="search_services_information",
        description=(
            "Search for specific information about services, prices, "
            "durations, requirements, and business policies. "
            "Do not use this tool when the user requests the complete "
            "list of services; use the service catalog tool instead."
        ),
    )


def get_rag_tool():
    global _rag_tool

    if _rag_tool is None:
        with _rag_tool_lock:
            if _rag_tool is None:
                _rag_tool = _build_rag_tool()

    return _rag_tool