"""SQLite database for sessions, batches, documents, and persons."""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    slug TEXT NOT NULL,
    folder_name TEXT NOT NULL,
    created TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES persons(id),
    created TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    batch_num INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'scanning_fronts',
    processing_stage TEXT,
    fronts_page_count INTEGER DEFAULT 0,
    backs_page_count INTEGER DEFAULT 0,
    error_message TEXT,
    created TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batches(id),
    start_page INTEGER NOT NULL,
    end_page INTEGER NOT NULL,
    document_type TEXT NOT NULL DEFAULT 'Other',
    date_of_service TEXT DEFAULT 'unknown',
    facility TEXT DEFAULT 'unknown',
    provider TEXT DEFAULT 'unknown',
    description TEXT DEFAULT 'Document',
    confidence REAL DEFAULT 1.0,
    user_edited INTEGER DEFAULT 0,
    filename TEXT NOT NULL,
    created TEXT NOT NULL
);
"""


def _slugify(name: str) -> str:
    """Convert a display name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "unnamed"


def _folder_name(name: str) -> str:
    """Convert a display name to a filesystem folder name."""
    return re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _gen_id() -> str:
    return uuid.uuid4().hex[:12]


class Database:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    # --- Persons ---

    async def create_person(self, display_name: str) -> dict:
        slug = _slugify(display_name)
        person_id = slug

        # Deduplicate slug
        suffix = 1
        while True:
            async with self._conn.execute(
                "SELECT id FROM persons WHERE id = ?", (person_id,)
            ) as cursor:
                if await cursor.fetchone() is None:
                    break
            suffix += 1
            person_id = f"{slug}-{suffix}"

        folder = _folder_name(display_name)
        now = _now_iso()
        await self._conn.execute(
            "INSERT INTO persons (id, display_name, slug, folder_name, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (person_id, display_name, person_id, folder, now),
        )
        await self._conn.commit()
        return {
            "id": person_id,
            "display_name": display_name,
            "slug": person_id,
            "folder_name": folder,
            "created": now,
        }

    async def list_persons(self) -> list[dict]:
        async with self._conn.execute("SELECT * FROM persons ORDER BY created") as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_person(self, person_id: str) -> dict | None:
        async with self._conn.execute("SELECT * FROM persons WHERE id = ?", (person_id,)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_person(self, person_id: str, display_name: str) -> dict | None:
        await self._conn.execute(
            "UPDATE persons SET display_name = ? WHERE id = ?",
            (display_name, person_id),
        )
        await self._conn.commit()
        return await self.get_person(person_id)

    async def delete_person(self, person_id: str) -> bool:
        """Delete a person. Returns False if they have sessions."""
        async with self._conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE person_id = ?", (person_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row[0] > 0:
                return False
        await self._conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
        await self._conn.commit()
        return True

    # --- Sessions ---

    async def create_session(self, person_id: str) -> dict:
        session_id = f"sess-{_gen_id()}"
        now = _now_iso()
        await self._conn.execute(
            "INSERT INTO sessions (id, person_id, created) VALUES (?, ?, ?)",
            (session_id, person_id, now),
        )
        await self._conn.commit()
        return {"id": session_id, "person_id": person_id, "created": now}

    async def list_sessions(self, person_id: str | None = None) -> list[dict]:
        if person_id:
            query = "SELECT * FROM sessions WHERE person_id = ? ORDER BY created DESC"
            params = (person_id,)
        else:
            query = "SELECT * FROM sessions ORDER BY created DESC"
            params = ()
        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_session(self, session_id: str) -> dict | None:
        async with self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    # --- Batches ---

    async def create_batch(self, session_id: str) -> dict:
        batch_id = f"batch-{_gen_id()}"
        now = _now_iso()

        # Determine batch_num
        async with self._conn.execute(
            "SELECT COUNT(*) FROM batches WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
            batch_num = row[0] + 1

        await self._conn.execute(
            "INSERT INTO batches (id, session_id, batch_num, state, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (batch_id, session_id, batch_num, "scanning_fronts", now),
        )
        await self._conn.commit()
        return {
            "id": batch_id,
            "session_id": session_id,
            "batch_num": batch_num,
            "state": "scanning_fronts",
            "processing_stage": None,
            "fronts_page_count": 0,
            "backs_page_count": 0,
            "error_message": None,
            "created": now,
        }

    async def update_batch_state(self, batch_id: str, state: str, **kwargs) -> dict | None:
        sets = ["state = ?"]
        params: list = [state]
        for key, val in kwargs.items():
            sets.append(f"{key} = ?")
            params.append(val)
        params.append(batch_id)
        await self._conn.execute(
            f"UPDATE batches SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        await self._conn.commit()
        return await self.get_batch(batch_id)

    async def get_batch(self, batch_id: str) -> dict | None:
        async with self._conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_batches(self, session_id: str) -> list[dict]:
        async with self._conn.execute(
            "SELECT * FROM batches WHERE session_id = ? ORDER BY batch_num",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # --- Documents ---

    async def create_document(
        self,
        batch_id: str,
        start_page: int,
        end_page: int,
        filename: str,
        document_type: str = "Other",
        date_of_service: str = "unknown",
        facility: str = "unknown",
        provider: str = "unknown",
        description: str = "Document",
        confidence: float = 1.0,
    ) -> dict:
        doc_id = f"doc-{_gen_id()}"
        now = _now_iso()
        await self._conn.execute(
            """INSERT INTO documents
            (id, batch_id, start_page, end_page, document_type, date_of_service,
             facility, provider, description, confidence, user_edited, filename, created)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            (
                doc_id,
                batch_id,
                start_page,
                end_page,
                document_type,
                date_of_service,
                facility,
                provider,
                description,
                confidence,
                filename,
                now,
            ),
        )
        await self._conn.commit()
        return await self.get_document(doc_id)

    async def update_document(self, doc_id: str, **kwargs) -> dict | None:
        if not kwargs:
            return await self.get_document(doc_id)
        # Convert user_edited bool to int for SQLite
        if "user_edited" in kwargs:
            kwargs["user_edited"] = int(kwargs["user_edited"])
        sets = [f"{k} = ?" for k in kwargs]
        params = list(kwargs.values())
        params.append(doc_id)
        await self._conn.execute(
            f"UPDATE documents SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        await self._conn.commit()
        return await self.get_document(doc_id)

    async def get_document(self, doc_id: str) -> dict | None:
        async with self._conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["user_edited"] = bool(d["user_edited"])
        return d

    async def list_documents(self, batch_id: str) -> list[dict]:
        async with self._conn.execute(
            "SELECT * FROM documents WHERE batch_id = ? ORDER BY start_page",
            (batch_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["user_edited"] = bool(d["user_edited"])
            result.append(d)
        return result
