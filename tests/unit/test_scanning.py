"""Unit tests for background scanning tasks with mocked scanner and pipeline."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pikepdf
import pytest

from scanbox.database import Database
from scanbox.models import SplitDocument


def _make_pdf(path: Path, num_pages: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    for _ in range(num_pages):
        pdf.add_blank_page(page_size=(612, 792))
    pdf.save(path)


def _make_page_bytes() -> bytes:
    """Create a valid single-page PDF as bytes."""
    from io import BytesIO

    buf = BytesIO()
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    pdf.save(buf)
    return buf.getvalue()


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


@pytest.fixture
async def batch_with_dirs(db, tmp_path, monkeypatch):
    """Create a person → session → batch and set up dirs."""
    monkeypatch.setenv("INTERNAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("SCANNER_IP", "192.168.1.100")

    person = await db.create_person("Test User")
    session = await db.create_session(person["id"])
    batch = await db.create_batch(session["id"])

    from scanbox.config import Config

    cfg = Config()
    batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch["id"]
    batch_dir.mkdir(parents=True, exist_ok=True)

    return {
        "person": person,
        "session": session,
        "batch": batch,
        "batch_dir": batch_dir,
        "db": db,
    }


class TestAcquirePages:
    @patch("scanbox.api.scanning.ESCLClient")
    async def test_acquire_pages_success(self, mock_escl_cls, tmp_path):
        from scanbox.api.scanning import _acquire_pages

        mock_scanner = AsyncMock()
        mock_scanner.start_scan.return_value = "http://scanner/job/1"
        page_bytes = _make_page_bytes()
        mock_scanner.get_next_page.side_effect = [page_bytes, page_bytes, None]

        output = tmp_path / "fronts.pdf"
        count = await _acquire_pages(mock_scanner, output)

        assert count == 2
        assert output.exists()
        pdf = pikepdf.Pdf.open(output)
        assert len(pdf.pages) == 2

    @patch("scanbox.api.scanning.ESCLClient")
    async def test_acquire_pages_empty_adf(self, mock_escl_cls, tmp_path):
        from scanbox.api.scanning import _acquire_pages

        mock_scanner = AsyncMock()
        mock_scanner.start_scan.return_value = "http://scanner/job/1"
        mock_scanner.get_next_page.return_value = None

        output = tmp_path / "fronts.pdf"
        count = await _acquire_pages(mock_scanner, output)

        assert count == 0
        assert not output.exists()

    @patch("scanbox.api.scanning.ESCLClient")
    async def test_acquire_pages_on_page_callback(self, mock_escl_cls, tmp_path):
        """on_page callback is called after each page with running count."""
        from scanbox.api.scanning import _acquire_pages

        mock_scanner = AsyncMock()
        mock_scanner.start_scan.return_value = "http://scanner/job/1"
        page_bytes = _make_page_bytes()
        mock_scanner.get_next_page.side_effect = [page_bytes, page_bytes, page_bytes, None]

        page_counts = []

        async def on_page(n):
            page_counts.append(n)

        output = tmp_path / "fronts.pdf"
        count = await _acquire_pages(mock_scanner, output, on_page=on_page)

        assert count == 3
        assert page_counts == [1, 2, 3]

    @patch("scanbox.api.scanning.ESCLClient")
    async def test_acquire_pages_no_callback(self, mock_escl_cls, tmp_path):
        """on_page=None is the default and works without error."""
        from scanbox.api.scanning import _acquire_pages

        mock_scanner = AsyncMock()
        mock_scanner.start_scan.return_value = "http://scanner/job/1"
        page_bytes = _make_page_bytes()
        mock_scanner.get_next_page.side_effect = [page_bytes, None]

        output = tmp_path / "fronts.pdf"
        count = await _acquire_pages(mock_scanner, output, on_page=None)

        assert count == 1


class TestScanFrontsTask:
    @patch("scanbox.api.scanning.event_bus")
    @patch("scanbox.api.scanning.ESCLClient")
    async def test_scan_fronts_success(self, mock_escl_cls, mock_bus, batch_with_dirs):
        from scanbox.api.scanning import scan_fronts_task

        mock_scanner = AsyncMock()
        mock_escl_cls.return_value = mock_scanner
        mock_scanner.start_scan.return_value = "http://scanner/job/1"
        page_bytes = _make_page_bytes()
        mock_scanner.get_next_page.side_effect = [page_bytes, page_bytes, page_bytes, None]
        mock_bus.publish = AsyncMock()

        db = batch_with_dirs["db"]
        batch_id = batch_with_dirs["batch"]["id"]

        await scan_fronts_task(batch_id, db)

        batch = await db.get_batch(batch_id)
        assert batch["state"] == "fronts_done"
        assert batch["fronts_page_count"] == 3
        mock_scanner.close.assert_awaited_once()

    @patch("scanbox.api.scanning.event_bus")
    @patch("scanbox.api.scanning.ESCLClient")
    async def test_scan_fronts_publishes_page_scanned_events(
        self, mock_escl_cls, mock_bus, batch_with_dirs
    ):
        """page_scanned events are published after each page is acquired."""
        from scanbox.api.scanning import scan_fronts_task

        mock_scanner = AsyncMock()
        mock_escl_cls.return_value = mock_scanner
        mock_scanner.start_scan.return_value = "http://scanner/job/1"
        page_bytes = _make_page_bytes()
        mock_scanner.get_next_page.side_effect = [page_bytes, page_bytes, None]
        mock_bus.publish = AsyncMock()

        db = batch_with_dirs["db"]
        batch_id = batch_with_dirs["batch"]["id"]

        await scan_fronts_task(batch_id, db)

        published = [call.args[1] for call in mock_bus.publish.call_args_list]
        page_events = [e for e in published if e.get("type") == "page_scanned"]
        assert len(page_events) == 2
        assert page_events[0] == {"type": "page_scanned", "side": "fronts", "page": 1}
        assert page_events[1] == {"type": "page_scanned", "side": "fronts", "page": 2}

    @patch("scanbox.api.scanning.event_bus")
    @patch("scanbox.api.scanning.ESCLClient")
    async def test_scan_fronts_error(self, mock_escl_cls, mock_bus, batch_with_dirs):
        from scanbox.api.scanning import scan_fronts_task

        mock_scanner = AsyncMock()
        mock_escl_cls.return_value = mock_scanner
        mock_scanner.start_scan.side_effect = Exception("Scanner offline")
        mock_bus.publish = AsyncMock()

        db = batch_with_dirs["db"]
        batch_id = batch_with_dirs["batch"]["id"]

        await scan_fronts_task(batch_id, db)

        batch = await db.get_batch(batch_id)
        assert batch["state"] == "error"
        assert "Scanner offline" in batch["error_message"]
        mock_scanner.close.assert_awaited_once()


class TestScanBacksTask:
    @patch("scanbox.api.scanning._run_processing")
    @patch("scanbox.api.scanning.event_bus")
    @patch("scanbox.api.scanning.ESCLClient")
    async def test_scan_backs_triggers_processing(
        self, mock_escl_cls, mock_bus, mock_run_proc, batch_with_dirs
    ):
        from scanbox.api.scanning import scan_backs_task

        mock_scanner = AsyncMock()
        mock_escl_cls.return_value = mock_scanner
        mock_scanner.start_scan.return_value = "http://scanner/job/2"
        page_bytes = _make_page_bytes()
        mock_scanner.get_next_page.side_effect = [page_bytes, None]
        mock_bus.publish = AsyncMock()
        mock_run_proc.return_value = None

        db = batch_with_dirs["db"]
        batch_id = batch_with_dirs["batch"]["id"]
        # Move to fronts_done first
        await db.update_batch_state(batch_id, "fronts_done")

        await scan_backs_task(batch_id, db)

        # _run_processing was called
        mock_run_proc.assert_awaited_once_with(batch_id, db, has_backs=True)

    @patch("scanbox.api.scanning._run_processing")
    @patch("scanbox.api.scanning.event_bus")
    @patch("scanbox.api.scanning.ESCLClient")
    async def test_scan_backs_publishes_page_scanned_events(
        self, mock_escl_cls, mock_bus, mock_run_proc, batch_with_dirs
    ):
        """page_scanned events with side=backs are published after each page."""
        from scanbox.api.scanning import scan_backs_task

        mock_scanner = AsyncMock()
        mock_escl_cls.return_value = mock_scanner
        mock_scanner.start_scan.return_value = "http://scanner/job/2"
        page_bytes = _make_page_bytes()
        mock_scanner.get_next_page.side_effect = [page_bytes, page_bytes, None]
        mock_bus.publish = AsyncMock()
        mock_run_proc.return_value = None

        db = batch_with_dirs["db"]
        batch_id = batch_with_dirs["batch"]["id"]
        await db.update_batch_state(batch_id, "fronts_done")

        await scan_backs_task(batch_id, db)

        published = [call.args[1] for call in mock_bus.publish.call_args_list]
        page_events = [e for e in published if e.get("type") == "page_scanned"]
        assert len(page_events) == 2
        assert page_events[0] == {"type": "page_scanned", "side": "backs", "page": 1}
        assert page_events[1] == {"type": "page_scanned", "side": "backs", "page": 2}


class TestProcessAfterSkipBacks:
    @patch("scanbox.api.scanning._run_processing")
    async def test_success(self, mock_run_proc, batch_with_dirs):
        from scanbox.api.scanning import process_after_skip_backs

        mock_run_proc.return_value = None

        db = batch_with_dirs["db"]
        batch_id = batch_with_dirs["batch"]["id"]

        await process_after_skip_backs(batch_id, db)
        mock_run_proc.assert_awaited_once_with(batch_id, db, has_backs=False)

    @patch("scanbox.api.scanning.event_bus")
    @patch("scanbox.api.scanning._run_processing")
    async def test_error_updates_batch(self, mock_run_proc, mock_bus, batch_with_dirs):
        from scanbox.api.scanning import process_after_skip_backs

        mock_run_proc.side_effect = Exception("Pipeline crashed")
        mock_bus.publish = AsyncMock()

        db = batch_with_dirs["db"]
        batch_id = batch_with_dirs["batch"]["id"]

        await process_after_skip_backs(batch_id, db)

        batch = await db.get_batch(batch_id)
        assert batch["state"] == "error"
        assert "Pipeline crashed" in batch["error_message"]


class TestRunProcessing:
    @patch("scanbox.api.scanning.event_bus")
    @patch("scanbox.api.scanning.run_pipeline")
    async def test_creates_documents_in_db(self, mock_pipeline, mock_bus, batch_with_dirs):
        from scanbox.api.scanning import _run_processing

        mock_bus.publish = AsyncMock()
        mock_pipeline.return_value = [
            SplitDocument(
                start_page=1,
                end_page=2,
                document_type="Lab Results",
                filename="2026-01-15_Test-User_Lab-Results.pdf",
            ),
            SplitDocument(
                start_page=3,
                end_page=3,
                document_type="Letter",
                filename="2026-01-20_Test-User_Letter.pdf",
            ),
        ]

        db = batch_with_dirs["db"]
        batch_id = batch_with_dirs["batch"]["id"]

        await _run_processing(batch_id, db, has_backs=False)

        batch = await db.get_batch(batch_id)
        assert batch["state"] == "review"

        docs = await db.list_documents(batch_id)
        assert len(docs) == 2
        assert docs[0]["document_type"] == "Lab Results"
        assert docs[0]["filename"] == "2026-01-15_Test-User_Lab-Results.pdf"
        assert docs[1]["document_type"] == "Letter"

        # Verify done event was published
        mock_bus.publish.assert_any_call(batch_id, {"type": "done", "document_count": 2})

    @patch("scanbox.api.scanning.event_bus")
    @patch("scanbox.api.scanning.run_pipeline")
    async def test_fallback_filename(self, mock_pipeline, mock_bus, batch_with_dirs):
        """Documents without filenames get a generated fallback name."""
        from scanbox.api.scanning import _run_processing

        mock_bus.publish = AsyncMock()
        mock_pipeline.return_value = [
            SplitDocument(start_page=1, end_page=3, document_type="Other", filename=""),
        ]

        db = batch_with_dirs["db"]
        batch_id = batch_with_dirs["batch"]["id"]

        await _run_processing(batch_id, db, has_backs=False)

        docs = await db.list_documents(batch_id)
        assert docs[0]["filename"] == "Other_1-3.pdf"

    @patch("scanbox.api.scanning.event_bus")
    @patch("scanbox.api.scanning.run_pipeline")
    async def test_on_progress_stage_complete_event_type(
        self, mock_pipeline, mock_bus, batch_with_dirs
    ):
        """on_progress with complete=True publishes stage_complete, not progress."""
        from scanbox.api.scanning import _run_processing

        mock_bus.publish = AsyncMock()

        captured_on_progress = None

        async def capture_on_progress(ctx, on_progress=None):
            nonlocal captured_on_progress
            captured_on_progress = on_progress
            return [
                SplitDocument(start_page=1, end_page=1, document_type="Other", filename="x.pdf")
            ]

        mock_pipeline.side_effect = capture_on_progress

        db = batch_with_dirs["db"]
        batch_id = batch_with_dirs["batch"]["id"]

        await _run_processing(batch_id, db, has_backs=False)

        assert captured_on_progress is not None

        # Call with complete=True — should publish stage_complete
        await captured_on_progress("ocr", "OCR complete", complete=True)
        mock_bus.publish.assert_any_call(
            batch_id, {"type": "stage_complete", "stage": "ocr", "detail": "OCR complete"}
        )

        # Call with complete=False — should publish progress
        await captured_on_progress("ocr", "Reading...", complete=False)
        mock_bus.publish.assert_any_call(
            batch_id, {"type": "progress", "stage": "ocr", "detail": "Reading..."}
        )
