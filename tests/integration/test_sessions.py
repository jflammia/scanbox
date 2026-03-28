"""Integration tests for database layer — sessions, batches, documents, persons."""

import pytest

from scanbox.database import Database


@pytest.fixture
async def db(tmp_path):
    """Create a fresh in-memory database for each test."""
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


class TestPersons:
    async def test_create_person(self, db: Database):
        person = await db.create_person("John Doe")
        assert person["id"] == "john-doe"
        assert person["display_name"] == "John Doe"
        assert person["slug"] == "john-doe"
        assert person["folder_name"] == "John_Doe"

    async def test_create_person_slug_dedup(self, db: Database):
        p1 = await db.create_person("John Doe")
        p2 = await db.create_person("John Doe")
        assert p1["id"] != p2["id"]
        assert p2["id"] == "john-doe-2"

    async def test_list_persons(self, db: Database):
        await db.create_person("Alice")
        await db.create_person("Bob")
        persons = await db.list_persons()
        assert len(persons) == 2

    async def test_get_person(self, db: Database):
        created = await db.create_person("Jane Smith")
        fetched = await db.get_person(created["id"])
        assert fetched is not None
        assert fetched["display_name"] == "Jane Smith"

    async def test_get_nonexistent_person(self, db: Database):
        result = await db.get_person("nonexistent")
        assert result is None

    async def test_update_person(self, db: Database):
        person = await db.create_person("Old Name")
        updated = await db.update_person(person["id"], "New Name")
        assert updated["display_name"] == "New Name"

    async def test_delete_person(self, db: Database):
        person = await db.create_person("To Delete")
        deleted = await db.delete_person(person["id"])
        assert deleted is True
        assert await db.get_person(person["id"]) is None

    async def test_delete_person_with_sessions_fails(self, db: Database):
        person = await db.create_person("Has Sessions")
        await db.create_session(person["id"])
        deleted = await db.delete_person(person["id"])
        assert deleted is False


class TestSessions:
    async def test_create_session(self, db: Database):
        person = await db.create_person("John Doe")
        session = await db.create_session(person["id"])
        assert session["person_id"] == person["id"]
        assert "id" in session
        assert "created" in session

    async def test_list_sessions(self, db: Database):
        person = await db.create_person("John Doe")
        await db.create_session(person["id"])
        await db.create_session(person["id"])
        sessions = await db.list_sessions()
        assert len(sessions) == 2

    async def test_list_sessions_by_person(self, db: Database):
        p1 = await db.create_person("Alice")
        p2 = await db.create_person("Bob")
        await db.create_session(p1["id"])
        await db.create_session(p2["id"])
        sessions = await db.list_sessions(person_id=p1["id"])
        assert len(sessions) == 1

    async def test_get_session(self, db: Database):
        person = await db.create_person("John Doe")
        created = await db.create_session(person["id"])
        fetched = await db.get_session(created["id"])
        assert fetched is not None
        assert fetched["person_id"] == person["id"]


class TestBatches:
    async def test_create_batch(self, db: Database):
        person = await db.create_person("John Doe")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        assert batch["session_id"] == session["id"]
        assert batch["state"] == "scanning_fronts"
        assert batch["batch_num"] >= 1

    async def test_update_batch_state(self, db: Database):
        person = await db.create_person("John Doe")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        updated = await db.update_batch_state(batch["id"], "fronts_done")
        assert updated["state"] == "fronts_done"

    async def test_list_batches(self, db: Database):
        person = await db.create_person("John Doe")
        session = await db.create_session(person["id"])
        await db.create_batch(session["id"])
        await db.create_batch(session["id"])
        batches = await db.list_batches(session["id"])
        assert len(batches) == 2


class TestDocuments:
    async def test_create_document(self, db: Database):
        person = await db.create_person("John Doe")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        doc = await db.create_document(
            batch_id=batch["id"],
            start_page=1,
            end_page=3,
            document_type="Radiology Report",
            date_of_service="2025-06-15",
            facility="Memorial Hospital",
            provider="Dr. Chen",
            description="CT Abdomen",
            confidence=0.95,
            filename="test.pdf",
        )
        assert doc["batch_id"] == batch["id"]
        assert doc["document_type"] == "Radiology Report"

    async def test_update_document(self, db: Database):
        person = await db.create_person("John Doe")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        doc = await db.create_document(
            batch_id=batch["id"],
            start_page=1,
            end_page=1,
            document_type="Other",
            filename="doc.pdf",
        )
        updated = await db.update_document(doc["id"], document_type="Lab Results", user_edited=True)
        assert updated["document_type"] == "Lab Results"
        assert updated["user_edited"] is True

    async def test_list_documents(self, db: Database):
        person = await db.create_person("John Doe")
        session = await db.create_session(person["id"])
        batch = await db.create_batch(session["id"])
        await db.create_document(batch_id=batch["id"], start_page=1, end_page=2, filename="a.pdf")
        await db.create_document(batch_id=batch["id"], start_page=3, end_page=4, filename="b.pdf")
        docs = await db.list_documents(batch["id"])
        assert len(docs) == 2
