# Python engine

This folder contains both approaches:

## Option A - notebook execution
- `LangChain_Project_parameterized.ipynb`
- `run_notebook_indexer.py`

Use this when you want notebook-first development and easy experimentation.

Papermill parameterizes notebooks using a `parameters` cell and then executes them with injected values. citeturn966466search0turn966466search4

## Option B - normal scripts
- `index_documents.py`
- `answer_question.py`
- `stream_answer.py`

Use this in production. The shared logic is inside `shared/`.

## Chroma
The code supports:
- local persistent Chroma
- HTTP Chroma mode

Chroma collections are created per conversation. Querying the collection with a `where` filter scoped to the conversation is the retrieval step. citeturn966466search1turn966466search13turn966466search17
