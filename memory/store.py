"""
Memory Store — Three-layer memory system
All data in ~/.sam_data — survives reinstalls.
ChromaDB: semantic/vector memory
SQLite: episodic memory
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger("SAM.MemoryStore")

SAM_DATA_DIR = Path.home() / ".sam_data"


class MemoryStore:
    def __init__(self, settings):
        self.settings = settings
        self._chroma_client = None
        self._collection = None
        self._db_path = Path(settings.sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()
        self._init_chroma()

    def _init_sqlite(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_input TEXT NOT NULL,
                    response TEXT NOT NULL,
                    action TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_model (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    project_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    tone TEXT DEFAULT 'default',
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    folder_path TEXT NOT NULL,
                    context TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
        logger.info(f"SQLite at {self._db_path}")

    def save_episode(self, user_input: str, response: str,
                     action: Optional[str], timestamp: str):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO episodes (timestamp, user_input, response, action) VALUES (?,?,?,?)",
                (timestamp, user_input, response, action)
            )
            conn.commit()

    def get_recent_episodes(self, limit: int = 10, retention_days: Optional[int] = None) -> List[Dict]:
        """
        retention_days: if set, only episodes from the last N days are
        returned — the free-tier memory cap. None (default) returns
        everything, unchanged from before this existed.
        """
        with sqlite3.connect(self._db_path) as conn:
            if retention_days is not None:
                cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
                rows = conn.execute(
                    "SELECT timestamp, user_input, response, action FROM episodes "
                    "WHERE timestamp >= ? ORDER BY id DESC LIMIT ?",
                    (cutoff, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT timestamp, user_input, response, action FROM episodes ORDER BY id DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        return [{"timestamp": r[0], "user": r[1], "response": r[2], "action": r[3]} for r in rows]

    def _init_chroma(self):
        try:
            import chromadb
            chroma_path = Path(self.settings.chroma_path)
            chroma_path.mkdir(parents=True, exist_ok=True)
            self._chroma_client = chromadb.PersistentClient(path=str(chroma_path))
            self._collection = self._chroma_client.get_or_create_collection(
                name="sam_memory",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB at {chroma_path}")
        except ImportError:
            logger.warning("ChromaDB not installed")
        except Exception as e:
            logger.error(f"ChromaDB init error: {e}")

    def save_semantic(self, content: str, metadata: dict = None):
        if self._collection is None:
            return
        try:
            embedding = self._get_embedding(content)
            doc_id = f"mem_{datetime.now().timestamp()}"
            self._collection.add(
                documents=[content],
                embeddings=[embedding],
                metadatas=[metadata or {}],
                ids=[doc_id]
            )
        except Exception as e:
            logger.error(f"Semantic save error: {e}")

    def search_semantic(self, query: str, top_k: int = 5, retention_days: Optional[int] = None) -> List[Dict]:
        """
        retention_days: if set, results with a metadata timestamp older
        than N days are filtered out post-query — same free-tier cap as
        get_recent_episodes. Post-filtered rather than queried via a
        ChromaDB `where` clause to keep this simple and avoid relying on
        string-comparison query syntax; safe_k already bounds the amount
        to filter.
        """
        if self._collection is None:
            return []
        try:
            count = self._collection.count()
            if count == 0:
                return []
            safe_k = min(top_k, count)
            embedding = self._get_embedding(query)
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=safe_k,
                include=["documents", "metadatas", "distances"]
            )
            memories = []
            cutoff = (datetime.now() - timedelta(days=retention_days)) if retention_days is not None else None
            if results["documents"]:
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0]
                ):
                    if cutoff is not None:
                        ts = (meta or {}).get("timestamp")
                        try:
                            if ts and datetime.fromisoformat(ts) < cutoff:
                                continue
                        except (ValueError, TypeError):
                            pass
                    memories.append({"content": doc, "metadata": meta, "relevance": 1 - dist})
            return memories
        except Exception as e:
            logger.error(f"Semantic search error: {e}")
            return []

    def _get_embedding(self, text: str) -> List[float]:
        import requests
        response = requests.post(
            f"{self.settings.ollama_host}/api/embeddings",
            json={"model": self.settings.embedding_model, "prompt": text},
            timeout=30
        )
        return response.json()["embedding"]

    def extract_and_save(self, user_input: str, response: str):
        try:
            import requests
            prompt = f"""Extract important facts or preferences about the user from this conversation.
Return a JSON array of strings. If nothing important, return [].

User: {user_input}
SAM: {response}

Return ONLY a JSON array."""
            r = requests.post(
                f"{self.settings.ollama_host}/api/generate",
                json={"model": self.settings.primary_model, "prompt": prompt, "stream": False, "format": "json"},
                timeout=30
            )
            facts = json.loads(r.json().get("response", "[]"))
            if isinstance(facts, list):
                for fact in facts:
                    if isinstance(fact, str) and len(fact) > 10:
                        self.save_semantic(fact, metadata={
                            "source": "auto_extract",
                            "timestamp": datetime.now().isoformat()
                        })
                logger.info(f"Extracted {len(facts)} memories")
        except Exception as e:
            logger.debug(f"Memory extraction skipped: {e}")

    # ─── Chat Conversations Persistence ───────────────────────────────────

    def save_conversation(self, conv_id: str, title: str, project_id: Optional[str] = None) -> Dict:
        now = datetime.now().isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, title, project_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    project_id = COALESCE(excluded.project_id, conversations.project_id),
                    updated_at = excluded.updated_at
                """,
                (conv_id, title, project_id, now, now)
            )
            conn.commit()
        return {"id": conv_id, "title": title, "project_id": project_id, "updated_at": now}

    def list_conversations(self, project_id: Optional[str] = None) -> List[Dict]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if project_id:
                cur = conn.execute(
                    "SELECT * FROM conversations WHERE project_id = ? ORDER BY updated_at DESC",
                    (project_id,)
                )
            else:
                cur = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC")
            return [dict(row) for row in cur.fetchall()]

    def delete_conversation(self, conv_id: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            conn.commit()
        return True

    def save_chat_message(self, msg_id: str, conversation_id: str, role: str,
                          content: str, timestamp: Optional[str] = None,
                          tone: str = "default", metadata: Optional[Dict] = None) -> Dict:
        ts = timestamp or datetime.now().isoformat()
        meta_str = json.dumps(metadata or {})
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (id, conversation_id, role, content, timestamp, tone, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content = excluded.content,
                    tone = excluded.tone,
                    metadata = excluded.metadata
                """,
                (msg_id, conversation_id, role, content, ts, tone, meta_str)
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (ts, conversation_id)
            )
            conn.commit()
        return {
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "timestamp": ts,
            "tone": tone
        }

    def get_conversation_messages(self, conversation_id: str) -> List[Dict]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM chat_messages WHERE conversation_id = ? ORDER BY timestamp ASC",
                (conversation_id,)
            )
            return [dict(row) for row in cur.fetchall()]

    # ─── Projects & Workspace Context ─────────────────────────────────────

    def save_project(self, proj_id: str, name: str, folder_path: str, context: str = "") -> Dict:
        now = datetime.now().isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, folder_path, context, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    folder_path = excluded.folder_path,
                    context = excluded.context,
                    updated_at = excluded.updated_at
                """,
                (proj_id, name, folder_path, context, now, now)
            )
            conn.commit()
        return {
            "id": proj_id,
            "name": name,
            "folder_path": folder_path,
            "context": context,
            "created_at": now,
            "updated_at": now
        }

    def list_projects(self) -> List[Dict]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC")
            return [dict(row) for row in cur.fetchall()]

    def delete_project(self, proj_id: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (proj_id,))
            conn.commit()
        return True

    def clear_memory(self) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM episodes")
            conn.execute("DELETE FROM user_model")
            conn.commit()
        if self._collection is not None:
            try:
                self._collection.delete(where={"source": "auto_extract"})
            except Exception:
                pass
        return True
