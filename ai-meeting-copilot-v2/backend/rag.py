"""
RAG (Retrieval Augmented Generation) module.

- Chunks incoming text (documents / meeting notes / transcripts)
- Embeds chunks using a local Sentence-Transformers model (all-MiniLM-L6-v2)
- Stores vectors in a persistent ChromaDB collection, scoped per user
- Retrieves the most relevant chunks for a given query
"""
import os
import uuid
from typing import List, Dict

import chromadb
from chromadb.utils import embedding_functions

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
os.makedirs(CHROMA_DIR, exist_ok=True)

_client = chromadb.PersistentClient(path=CHROMA_DIR)

# ChromaDB's built-in default embedding function: a small ONNX-exported
# all-MiniLM-L6-v2 model. Runs locally, needs no API key, and avoids the
# heavy PyTorch/sentence-transformers install that fails on some Windows
# setups. Downloads the small ONNX model (~80MB) once on first run.
_embedding_fn = embedding_functions.DefaultEmbeddingFunction()

_collection = _client.get_or_create_collection(
    name="knowledge_base", embedding_function=_embedding_fn
)


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    """Simple sliding-window character chunker with overlap for better context continuity."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def ingest_text(text: str, user_id: int, source_name: str, doc_type: str = "document") -> int:
    """Chunk + embed + store text in the vector DB. Returns number of chunks stored."""
    chunks = chunk_text(text)
    if not chunks:
        return 0

    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [
        {"user_id": str(user_id), "source": source_name, "doc_type": doc_type}
        for _ in chunks
    ]
    _collection.add(documents=chunks, ids=ids, metadatas=metadatas)
    return len(chunks)


def retrieve(query: str, user_id: int, top_k: int = 4) -> List[Dict]:
    """Return the top_k most relevant chunks for this user, with their source filenames."""
    results = _collection.query(
        query_texts=[query],
        n_results=top_k,
        where={"user_id": str(user_id)},
    )
    if not results or not results.get("documents") or not results["documents"][0]:
        return []

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    return [{"text": d, "source": m.get("source", "unknown")} for d, m in zip(docs, metas)]


def delete_user_data(user_id: int):
    """Remove all vectors belonging to a user (e.g. on account deletion)."""
    _collection.delete(where={"user_id": str(user_id)})
