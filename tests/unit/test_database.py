"""Unit tests for the Database class."""

import pytest

from scanbox.database import Database, _folder_name, _slugify


class TestSlugify:
    def test_basic_name(self):
        assert _slugify("John Doe") == "john-doe"

    def test_special_chars(self):
        assert _slugify("Mary O'Brien-Smith") == "mary-o-brien-smith"

    def test_empty_string(self):
        assert _slugify("") == "unnamed"

    def test_whitespace(self):
        assert _slugify("  Jane  ") == "jane"


class TestFolderName:
    def test_basic_name(self):
        assert _folder_name("John Doe") == "John_Doe"

    def test_special_chars(self):
        assert _folder_name("Mary O'Brien") == "Mary_OBrien"


class TestDatabasePersons:
    @pytest.fixture
    async def db(self, tmp_path):
        database = Database(tmp_path / "test.db")
        await database.init()
        yield database
        await database.close()

    async def test_create_person(self, db):
        person = await db.create_person("Test User")
        assert person["display_name"] == "Test User"
        assert person["slug"] == "test-user"
        assert person["id"] == "test-user"

    async def test_create_duplicate_slug(self, db):
        p1 = await db.create_person("Test User")
        p2 = await db.create_person("Test User")
        assert p1["id"] == "test-user"
        assert p2["id"] == "test-user-2"

    async def test_list_persons(self, db):
        await db.create_person("Alice")
        await db.create_person("Bob")
        persons = await db.list_persons()
        assert len(persons) == 2

    async def test_get_person(self, db):
        created = await db.create_person("Alice")
        fetched = await db.get_person(created["id"])
        assert fetched["display_name"] == "Alice"

    async def test_get_person_not_found(self, db):
        result = await db.get_person("nonexistent")
        assert result is None

    async def test_update_person(self, db):
        person = await db.create_person("Old Name")
        updated = await db.update_person(person["id"], "New Name")
        assert updated["display_name"] == "New Name"

    async def test_delete_person(self, db):
        person = await db.create_person("To Delete")
        result = await db.delete_person(person["id"])
        assert result is True
        assert await db.get_person(person["id"]) is None

    async def test_delete_person_with_sessions(self, db):
        person = await db.create_person("Has Sessions")
        await db.create_session(person["id"])
        result = await db.delete_person(person["id"])
        assert result is False


class TestDatabaseSessions:
    @pytest.fixture
    async def db(self, tmp_path):
        database = Database(tmp_path / "test.db")
        await database.init()
        yield database
        await database.close()

    async def test_create_session(self, db):
        person = await db.create_person("Test")
        session = await db.create_session(person["id"])
        assert session["person_id"] == person["id"]
        assert session["id"].startswith("sess-")

    async def test_list_sessions(self, db):
        person = await db.create_person("Test")
        await db.create_session(person["id"])
        await db.create_session(person["id"])
        sessions = await db.list_sessions(person["id"])
        assert len(sessions) == 2

    async def test_list_sessions_all(self, db):
        p1 = await db.create_person("P1")
        p2 = await db.create_person("P2")
        await db.create_session(p1["id"])
        await db.create_session(p2["id"])
        all_sessions = await db.list_sessions()
        assert len(all_sessions) == 2

    async def test_get_session(self, db):
        person = await db.create_person("Test")
        session = await db.create_session(person["id"])
        fetched = await db.get_session(session["id"])
        assert fetched["id"] == session["id"]

    async def test_get_session_not_found(self, db):
        assert await db.get_session("nonexistent") is None


class TestDatabaseBatches:
    @pytest.fixture
    async def db(self, tmp_path):
        database = Database(tmp_path / "test.db")
        await database.init()
        yield database
        await database.close()

    async def test_create_batch(self, db):
        person = await db.create_person("Test")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        assert batch["session_id"] == session["id"]
        assert batch["batch_num"] == 1
        assert batch["state"] == "scanning_fronts"

    async def test_batch_num_increments(self, db):
        person = await db.create_person("Test")
        session = await db.create_session(person["id"])
        b1 = await db.create_batch(session["id"])
        b2 = await db.create_batch(session["id"])
        assert b1["batch_num"] == 1
        assert b2["batch_num"] == 2

    async def test_update_batch_state(self, db):
        person = await db.create_person("Test")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        updated = await db.update_batch_state(batch["id"], "review")
        assert updated["state"] == "review"

    async def test_update_batch_state_with_kwargs(self, db):
        person = await db.create_person("Test")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        updated = await db.update_batch_state(batch["id"], "fronts_done", fronts_page_count=5)
        assert updated["fronts_page_count"] == 5

    async def test_get_batch_not_found(self, db):
        assert await db.get_batch("nonexistent") is None

    async def test_list_batches(self, db):
        person = await db.create_person("Test")
        session = await db.create_session(person["id"])
        await db.create_batch(session["id"])
        await db.create_batch(session["id"])
        batches = await db.list_batches(session["id"])
        assert len(batches) == 2


class TestDatabaseDocuments:
    @pytest.fixture
    async def db(self, tmp_path):
        database = Database(tmp_path / "test.db")
        await database.init()
        yield database
        await database.close()

    async def _make_batch(self, db):
        person = await db.create_person("Test")
        session = await db.create_session(person["id"])
        return await db.create_batch(session["id"])

    async def test_create_document(self, db):
        batch = await self._make_batch(db)
        doc = await db.create_document(
            batch_id=batch["id"],
            start_page=1,
            end_page=3,
            filename="test.pdf",
            document_type="Lab Results",
        )
        assert doc["start_page"] == 1
        assert doc["end_page"] == 3
        assert doc["document_type"] == "Lab Results"
        assert doc["filename"] == "test.pdf"
        assert doc["user_edited"] is False

    async def test_update_document(self, db):
        batch = await self._make_batch(db)
        doc = await db.create_document(
            batch_id=batch["id"], start_page=1, end_page=1, filename="t.pdf"
        )
        updated = await db.update_document(
            doc["id"], document_type="Radiology Report", user_edited=True
        )
        assert updated["document_type"] == "Radiology Report"
        assert updated["user_edited"] is True

    async def test_get_document_not_found(self, db):
        assert await db.get_document("nonexistent") is None

    async def test_list_documents_ordered(self, db):
        batch = await self._make_batch(db)
        await db.create_document(batch_id=batch["id"], start_page=3, end_page=4, filename="b.pdf")
        await db.create_document(batch_id=batch["id"], start_page=1, end_page=2, filename="a.pdf")
        docs = await db.list_documents(batch["id"])
        assert len(docs) == 2
        assert docs[0]["start_page"] == 1
        assert docs[1]["start_page"] == 3

    async def test_delete_documents_by_batch(self, db):
        batch = await self._make_batch(db)
        await db.create_document(batch_id=batch["id"], start_page=1, end_page=1, filename="a.pdf")
        await db.create_document(batch_id=batch["id"], start_page=2, end_page=2, filename="b.pdf")
        count = await db.delete_documents_by_batch(batch["id"])
        assert count == 2
        docs = await db.list_documents(batch["id"])
        assert len(docs) == 0
