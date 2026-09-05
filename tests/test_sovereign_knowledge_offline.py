"""
Offline smoke test for the Sovereign Workbench local knowledge layer
(SIH26117, Milestone 2) — core/embeddings.py and
sovereign/knowledge/{vector_index,retrieval}.py.

Covers three things:
1. core.embeddings.get_embedding() in isolation (mocked Ollama call).
2. That extracting it out of memory/store.py._get_embedding() did not
   change that method's external behavior — a regression check on an
   existing file this milestone touched.
3. VectorIndex/search_knowledge() against a FakeChromaClient (chromadb
   itself isn't installed in this sandbox — see the audit's Verified
   Evidence section — so this is dependency-injection testing of our
   orchestration logic, not of the real chromadb library). One test
   deliberately uses no injected client at all, to exercise the real
   ImportError fallback path for real, not mocked.

Usage:
    HOME=/tmp/sam_smoke_sovereign_knowledge python3 tests/test_sovereign_knowledge_offline.py
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings  # noqa: E402
from core.embeddings import get_embedding  # noqa: E402
from memory.store import MemoryStore  # noqa: E402
from sovereign.ingestion.chunk import Chunk  # noqa: E402
from sovereign.knowledge import RetrievalResult, VectorIndex, search_knowledge  # noqa: E402

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


def _fake_ollama_embedding_response(vector):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"embedding": vector}
    return mock_resp


class FakeCollection:
    """Minimal stand-in for a chromadb Collection — just enough surface
    (upsert/count/query) for VectorIndex to drive."""

    def __init__(self):
        self.ids, self.documents, self.embeddings, self.metadatas = [], [], [], []

    def upsert(self, ids, documents, embeddings, metadatas):
        for i, doc, emb, meta in zip(ids, documents, embeddings, metadatas):
            if i in self.ids:
                idx = self.ids.index(i)
                self.documents[idx], self.embeddings[idx], self.metadatas[idx] = doc, emb, meta
            else:
                self.ids.append(i)
                self.documents.append(doc)
                self.embeddings.append(emb)
                self.metadatas.append(meta)

    def count(self):
        return len(self.ids)

    def query(self, query_embeddings, n_results, include):
        n = min(n_results, len(self.ids))
        # Fabricated, deterministic, increasing distances so ordering /
        # relevance-direction logic is checkable without a real ANN index.
        distances = [round(0.1 * i, 2) for i in range(n)]
        return {
            "ids": [self.ids[:n]],
            "documents": [self.documents[:n]],
            "metadatas": [self.metadatas[:n]],
            "distances": [distances],
        }


class FakeChromaClient:
    def __init__(self):
        self._collections = {}

    def get_or_create_collection(self, name, metadata=None):
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]


def _make_chunk(chunk_id, text, filename="sop.docx", section="Approval Requirements", section_index=1, chunk_index=0):
    return Chunk(
        chunk_id=chunk_id, doc_id=chunk_id.split(":")[0], filename=filename, file_type="docx",
        content_hash=chunk_id.split(":")[0] + "0" * 48, section=section,
        section_index=section_index, chunk_index=chunk_index, text=text,
    )


def test_get_embedding_calls_ollama_correctly():
    with patch("core.embeddings.requests.post", return_value=_fake_ollama_embedding_response([0.1, 0.2, 0.3])) as mock_post:
        vec = get_embedding("hello world", "http://localhost:11434", "nomic-embed-text")
        check("get_embedding returns the mocked vector", vec == [0.1, 0.2, 0.3])
        args, kwargs = mock_post.call_args
        check("get_embedding posts to the right Ollama URL", args[0] == "http://localhost:11434/api/embeddings")
        check("get_embedding sends the configured model + prompt",
              kwargs["json"] == {"model": "nomic-embed-text", "prompt": "hello world"})


def test_memory_store_embedding_unchanged_after_extraction():
    """Regression check: memory/store.py._get_embedding() must behave
    identically after being pointed at core.embeddings.get_embedding()."""
    settings = Settings()
    store = MemoryStore(settings)
    with patch("core.embeddings.requests.post", return_value=_fake_ollama_embedding_response([0.4, 0.5])) as mock_post:
        vec = store._get_embedding("some memory text")
        check("MemoryStore._get_embedding still returns a plain vector", vec == [0.4, 0.5])
        args, kwargs = mock_post.call_args
        check("MemoryStore._get_embedding still uses settings.ollama_host/embedding_model",
              args[0] == f"{settings.ollama_host}/api/embeddings"
              and kwargs["json"]["model"] == settings.embedding_model)


def test_vector_index_unavailable_without_chromadb_or_injected_client():
    # No client injected, and chromadb genuinely isn't installed in this
    # sandbox — this exercises the real ImportError fallback, not a mock.
    settings = Settings()
    index = VectorIndex(settings)
    check("VectorIndex.available is False with no chromadb and no injected client", index.available is False)
    check("add_chunks on an unavailable index returns 0, not an error",
          index.add_chunks([_make_chunk("abc:1:0", "some text")]) == 0)
    check("query on an unavailable index returns the empty shape, not an error",
          index.query("anything") == {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]})


def test_vector_index_add_and_query_with_fake_client():
    settings = Settings()
    index = VectorIndex(settings, client=FakeChromaClient())
    chunks = [
        _make_chunk("doc1:1:0", "Two signatures are required for approval.", section="Approval Requirements"),
        _make_chunk("doc1:2:0", "Pressure must not exceed 150 PSI.", section="Pressure Limits", section_index=2),
    ]
    with patch("sovereign.knowledge.vector_index.get_embedding", return_value=[0.1, 0.1]):
        written = index.add_chunks(chunks)
        check("add_chunks writes both chunks", written == 2)

        raw = index.query("approval signatures", top_k=5)
        check("query returns both chunks when top_k exceeds count", len(raw["documents"][0]) == 2)
        check("query includes metadata", raw["metadatas"][0][0]["filename"] == "sop.docx")


def test_vector_index_upsert_is_idempotent():
    settings = Settings()
    index = VectorIndex(settings, client=FakeChromaClient())
    with patch("sovereign.knowledge.vector_index.get_embedding", return_value=[0.1, 0.1]):
        index.add_chunks([_make_chunk("doc2:1:0", "original text")])
        index.add_chunks([_make_chunk("doc2:1:0", "updated text")])
        raw = index.query("anything", top_k=5)
        check("Re-adding the same chunk_id replaces rather than duplicates", len(raw["documents"][0]) == 1)
        check("Replaced content reflects the latest upsert", raw["documents"][0][0] == "updated text")


def test_search_knowledge_translates_results_with_relevance_ordering():
    settings = Settings()
    index = VectorIndex(settings, client=FakeChromaClient())
    chunks = [
        _make_chunk("doc3:1:0", "First and most relevant chunk.", filename="report.pdf", section="page 1", section_index=1),
        _make_chunk("doc3:1:1", "Second, less relevant chunk.", filename="report.pdf", section="page 1", section_index=1, chunk_index=1),
    ]
    with patch("sovereign.knowledge.vector_index.get_embedding", return_value=[0.1, 0.1]):
        index.add_chunks(chunks)
        found = search_knowledge("deviation", index, top_k=5)

    check("search_knowledge returns RetrievalResult objects", all(isinstance(r, RetrievalResult) for r in found))
    check("search_knowledge preserves filename", found[0].filename == "report.pdf")
    check("search_knowledge preserves section", found[0].section == "page 1")
    check("First result is more relevant than the second (closer distance)", found[0].relevance > found[1].relevance)
    check("Relevance is within [0, 1]", all(0.0 <= r.relevance <= 1.0 for r in found))


def test_search_knowledge_respects_top_k():
    settings = Settings()
    index = VectorIndex(settings, client=FakeChromaClient())
    chunks = [_make_chunk(f"doc4:1:{i}", f"chunk number {i}", chunk_index=i) for i in range(5)]
    with patch("sovereign.knowledge.vector_index.get_embedding", return_value=[0.1, 0.1]):
        index.add_chunks(chunks)
        found = search_knowledge("chunk", index, top_k=2)
    check("search_knowledge respects top_k", len(found) == 2)


def test_search_knowledge_empty_index_returns_empty_list():
    settings = Settings()
    index = VectorIndex(settings, client=FakeChromaClient())
    found = search_knowledge("anything", index, top_k=5)
    check("search_knowledge on an empty index returns [] (not an error)", found == [])


def main():
    test_get_embedding_calls_ollama_correctly()
    test_memory_store_embedding_unchanged_after_extraction()
    test_vector_index_unavailable_without_chromadb_or_injected_client()
    test_vector_index_add_and_query_with_fake_client()
    test_vector_index_upsert_is_idempotent()
    test_search_knowledge_translates_results_with_relevance_ordering()
    test_search_knowledge_respects_top_k()
    test_search_knowledge_empty_index_returns_empty_list()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Sovereign Workbench local knowledge layer (Milestone 2) verified.")


if __name__ == "__main__":
    main()
