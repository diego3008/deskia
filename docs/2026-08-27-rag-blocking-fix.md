# RAG/Chroma Blocking Fix

Date: 2026-08-27

## Problem

The `services_inquiry` graph task failed in LangGraph development mode with:

```text
BlockingError: Blocking call to ScandirIterator.__next__
```

The traceback showed that the failure occurred before the RAG query itself:

```text
services_inquiry_node
  -> from src.utils import rag_tool
  -> src/utils/__init__.py
  -> src/utils/rag_utils.py
  -> import langchain_chroma
  -> import chromadb
  -> import jsonschema
  -> package schema directory scan
```

The original `asyncio.to_thread(rag_tool.invoke, ...)` change was insufficient because Chroma and its dependencies were still imported and initialized before that line ran.

## Root cause

[`src/utils/rag_utils.py`](../src/utils/rag_utils.py) performed eager initialization at import time:

```python
rag_tool = retriever_tool()
```

That statement loaded the service document, initialized embeddings, created the Chroma vector store, and imported dependencies while the async LangGraph task was running. LangGraph's blocking-call detector caught a synchronous filesystem scan performed by a Chroma dependency.

The blocking operation was therefore import-time RAG initialization, not the final retrieval call.

## Changes made

### 1. Removed eager RAG initialization

File: [`src/utils/rag_utils.py`](../src/utils/rag_utils.py)

Removed the module-level construction of `rag_tool`.

Why:

- Importing unrelated graph functionality no longer initializes Chroma.
- Chroma dependencies are not loaded during application startup.
- The service inquiry path controls when RAG initialization occurs.

### 2. Added lazy heavy imports

Chroma, OpenAI embeddings, document loading, text splitting, and retriever-tool imports now occur inside `_build_rag_tool()`.

Why:

The `langchain_chroma` import itself triggered the blocking filesystem scan. Moving only vector-store construction would not have been enough; the heavy imports also had to leave the async execution path.

### 3. Added a process-local cached singleton

`get_rag_tool()` now builds the RAG tool only once per process and protects initialization with a `threading.Lock`.

Why:

- Multiple requests do not rebuild the vector store.
- The service catalog is not re-embedded on every inquiry.
- Concurrent first requests cannot initialize multiple RAG instances at the same time.

The cache is process-local. If LangGraph runs multiple worker processes, each worker will have its own RAG instance.

### 4. Moved initialization and retrieval to worker threads

File: [`src/nodes/user_services_validation/services_inquiry_node.py`](../src/nodes/user_services_validation/services_inquiry_node.py)

The node now uses:

```python
rag_tool = await asyncio.to_thread(get_rag_tool)
context = await asyncio.to_thread(rag_tool.invoke, {"query": query})
```

Why:

The Chroma retriever uses synchronous operations. Running both initialization and retrieval in a worker thread prevents those operations from blocking LangGraph's async event loop.

### 5. Updated the utility export

File: [`src/utils/__init__.py`](../src/utils/__init__.py)

Changed the exported value from the eagerly-created `rag_tool` to the lazy `get_rag_tool` accessor.

Why:

Importing `src.utils` must remain safe. Re-exporting `rag_tool` would immediately trigger the same eager initialization problem.

## Resulting lifecycle

```text
Application imports src.utils
        |
        +-- no Chroma import
        +-- no embedding call
        +-- no filesystem scan from Chroma dependencies

First service inquiry
        |
        +-- get_rag_tool() runs in a worker thread
        +-- Chroma/RAG tool is built once
        +-- synchronous retrieval runs in a worker thread

Later service inquiries
        |
        +-- cached RAG tool is reused
        +-- synchronous retrieval runs in a worker thread
```

## Verification

Added [`tests/test_rag_initialization.py`](../tests/test_rag_initialization.py) to ensure the RAG tool is not constructed during module import.

Checks completed:

- Import smoke check: `chromadb_loaded=False` after importing `src.utils`.
- Focused RAG test: passed.
- Full test suite: **52 tests passed**.
- `git diff --check`: passed.

## Operational note

Restart `langgraph dev` after applying this change so the process does not retain the previous module state. The normal command should now be sufficient; `--allow-blocking` should not be required for this import-time error.

This fix does not redesign the RAG strategy or change the service catalog. It only moves blocking initialization and retrieval to an appropriate execution boundary.
