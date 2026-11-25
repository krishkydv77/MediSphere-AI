from pathlib import Path
from typing import Optional
from app.core.config import settings
from app.core.logger import get_logger
logger = get_logger(__name__)

class MedicalRAG:
    def __init__(self):
        self._collection = None
        self._client = None
        self._embedder = None

    def _initialize(self):
        if self._collection is not None:
            return
        import chromadb
        from sentence_transformers import SentenceTransformer
        db_path = settings.path(settings.chroma_path)
        db_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(db_path))
        self._collection = self._client.get_or_create_collection(name="medlens_knowledge", metadata={"hnsw:space": "cosine"})
        self._embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        logger.info("ChromaDB + Sentence Transformers initialized at %s", db_path)
        self.ingest_knowledge_base()

    def ingest_knowledge_base(self):
        kb = settings.path(settings.kb_dir)
        kb.mkdir(parents=True, exist_ok=True)
        docs = list(kb.glob("*.md")) + list(kb.glob("*.txt"))
        for doc in docs:
            content = doc.read_text(encoding="utf-8", errors="ignore")
            chunks = [content[i:i+900] for i in range(0, len(content), 750) if content[i:i+900].strip()]
            ids = [f"{doc.stem}-{i}" for i in range(len(chunks))]
            if chunks:
                existing = set(self._collection.get(ids=ids).get("ids", []))
                new_chunks = [(idx, chunk) for idx, chunk in zip(ids, chunks) if idx not in existing]
                if new_chunks:
                    ids_new, texts_new = zip(*new_chunks)
                    embeddings = self._embedder.encode(list(texts_new), normalize_embeddings=True).tolist()
                    self._collection.add(ids=list(ids_new), documents=list(texts_new), embeddings=embeddings, metadatas=[{"source": doc.name} for _ in texts_new])
                    logger.info("Added %s chunks from %s", len(new_chunks), doc.name)

    def search(self, query: str, k: int = 4) -> list[dict]:
        self._initialize()
        vector = self._embedder.encode([query], normalize_embeddings=True).tolist()
        result = self._collection.query(query_embeddings=vector, n_results=min(k, max(1, self._collection.count())))
        hits = []
        for i, doc in enumerate((result.get("documents") or [[]])[0]):
            hits.append({"text": doc, "source": ((result.get("metadatas") or [[]])[0][i] or {}).get("source", "knowledge_base"), "distance": ((result.get("distances") or [[]])[0][i])})
        logger.info("RAG search returned %d hits", len(hits))
        return hits

rag = MedicalRAG()
