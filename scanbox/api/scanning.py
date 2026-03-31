"""Background scanning and pipeline execution.

Coordinates the eSCL scanner, pipeline runner, and database
to perform the full scan-to-documents workflow.
"""

import asyncio
import logging
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated

import pikepdf
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from scanbox.api.import_batch import import_batch as do_import_batch
from scanbox.api.sse import event_bus
from scanbox.api.webhooks import dispatch_webhook_event
from scanbox.config import Config
from scanbox.database import Database
from scanbox.models import PipelineResult
from scanbox.pipeline.runner import PipelineContext, run_pipeline
from scanbox.pipeline.state import PipelineState
from scanbox.scanner.escl import ESCLClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["scanning"])


async def _acquire_pages(scanner: ESCLClient, output_pdf: Path, on_page: callable = None) -> int:
    """Scan all pages from the ADF into a single PDF. Returns page count."""
    job_url = await scanner.start_scan()

    pages: list[bytes] = []
    while True:
        page_data = await scanner.get_next_page(job_url)
        if page_data is None:
            break
        pages.append(page_data)
        if on_page:
            await on_page(len(pages))

    if not pages:
        return 0

    # Merge individual page PDFs into one combined PDF
    combined = pikepdf.Pdf.new()
    for page_bytes in pages:
        page_pdf = pikepdf.Pdf.open(BytesIO(page_bytes))
        combined.pages.extend(page_pdf.pages)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    combined.save(output_pdf)
    return len(pages)


async def scan_fronts_task(batch_id: str, db: Database) -> None:
    """Background task: scan front sides via ADF, update batch state."""
    cfg = Config()
    scanner = ESCLClient(cfg.SCANNER_IP)

    try:
        batch = await db.get_batch(batch_id)
        session = await db.get_session(batch["session_id"])
        batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch_id
        fronts_pdf = batch_dir / "fronts.pdf"

        await event_bus.publish(batch_id, {"type": "progress", "stage": "scanning_fronts"})

        async def on_page_fronts(n):
            await event_bus.publish(batch_id, {"type": "page_scanned", "side": "fronts", "page": n})

        page_count = await _acquire_pages(scanner, fronts_pdf, on_page=on_page_fronts)

        await db.update_batch_state(batch_id, "fronts_done", fronts_page_count=page_count)
        await event_bus.publish(
            batch_id,
            {"type": "scan_complete", "side": "fronts", "pages": page_count},
        )
        await dispatch_webhook_event(
            "scan.completed",
            {"batch_id": batch_id, "side": "fronts", "page_count": page_count},
        )
    except Exception as e:
        logger.exception("Front scan failed for batch %s", batch_id)
        await db.update_batch_state(batch_id, "error", error_message=str(e))
        await event_bus.publish(batch_id, {"type": "error", "message": str(e)})
    finally:
        await scanner.close()


async def scan_backs_task(batch_id: str, db: Database) -> None:
    """Background task: scan back sides via ADF, then trigger pipeline."""
    cfg = Config()
    scanner = ESCLClient(cfg.SCANNER_IP)

    try:
        batch = await db.get_batch(batch_id)
        session = await db.get_session(batch["session_id"])
        batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch_id
        backs_pdf = batch_dir / "backs.pdf"

        await event_bus.publish(batch_id, {"type": "progress", "stage": "scanning_backs"})

        async def on_page_backs(n):
            await event_bus.publish(batch_id, {"type": "page_scanned", "side": "backs", "page": n})

        page_count = await _acquire_pages(scanner, backs_pdf, on_page=on_page_backs)

        await db.update_batch_state(batch_id, "backs_done", backs_page_count=page_count)
        await event_bus.publish(
            batch_id,
            {"type": "scan_complete", "side": "backs", "pages": page_count},
        )
        await dispatch_webhook_event(
            "scan.completed",
            {"batch_id": batch_id, "side": "backs", "page_count": page_count},
        )

        # Trigger pipeline processing
        await _run_processing(batch_id, db, has_backs=True)
    except Exception as e:
        logger.exception("Back scan failed for batch %s", batch_id)
        await db.update_batch_state(batch_id, "error", error_message=str(e))
        await event_bus.publish(batch_id, {"type": "error", "message": str(e)})
    finally:
        await scanner.close()


async def process_after_skip_backs(batch_id: str, db: Database) -> None:
    """Background task: run pipeline after backs are skipped (single-sided)."""
    try:
        await _run_processing(batch_id, db, has_backs=False)
    except Exception as e:
        logger.exception("Processing failed for batch %s", batch_id)
        await db.update_batch_state(batch_id, "error", error_message=str(e))
        await event_bus.publish(batch_id, {"type": "error", "message": str(e)})


async def _run_processing(batch_id: str, db: Database, *, has_backs: bool) -> None:
    """Run the full pipeline and create document records in the database."""
    cfg = Config()
    batch = await db.get_batch(batch_id)
    session = await db.get_session(batch["session_id"])
    person = await db.get_person(session["person_id"])

    batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch_id
    scan_date = datetime.now(UTC).strftime("%Y-%m-%d")

    await db.update_batch_state(batch_id, "processing")

    ctx = PipelineContext(
        batch_dir=batch_dir,
        output_dir=cfg.OUTPUT_DIR,
        person_name=person["display_name"],
        person_slug=person["slug"],
        person_folder=person["folder_name"],
        batch_num=batch["batch_num"],
        scan_date=scan_date,
        has_backs=has_backs,
    )

    async def on_progress(stage_name: str, detail: str = "", complete: bool = False):
        event_type = "stage_complete" if complete else "progress"
        await event_bus.publish(
            batch_id,
            {"type": event_type, "stage": stage_name, "detail": detail},
        )
        # Emit stage_result event with the full result when complete
        if complete:
            state_path = batch_dir / "state.json"
            if state_path.exists():
                state = PipelineState.load(state_path)
                stage_state = state.stages.get(stage_name)
                if stage_state and stage_state.result:
                    await event_bus.publish(
                        batch_id,
                        {"type": "stage_result", "stage": stage_name, "result": stage_state.result},
                    )
        if not complete:
            await dispatch_webhook_event(
                "processing.stage_completed",
                {"batch_id": batch_id, "stage": stage_name, "detail": detail},
            )

    result: PipelineResult = await run_pipeline(ctx, on_progress=on_progress)

    if result.status == "completed":
        documents = result.documents

        # Create document records in DB using actual filenames from the pipeline
        for doc in documents:
            filename = doc.filename or f"{doc.document_type}_{doc.start_page}-{doc.end_page}.pdf"
            await db.create_document(
                batch_id=batch_id,
                start_page=doc.start_page,
                end_page=doc.end_page,
                document_type=doc.document_type,
                date_of_service=doc.date_of_service,
                facility=doc.facility,
                provider=doc.provider,
                description=doc.description,
                confidence=doc.confidence,
                filename=filename,
            )

        await db.update_batch_state(batch_id, "review")
        await event_bus.publish(batch_id, {"type": "done", "document_count": len(documents)})

        # Dispatch webhook for processing completion
        doc_summaries = [
            {
                "document_type": doc.document_type,
                "date_of_service": doc.date_of_service,
                "confidence": doc.confidence,
            }
            for doc in documents
        ]
        await dispatch_webhook_event(
            "processing.completed",
            {
                "batch_id": batch_id,
                "document_count": len(documents),
                "documents": doc_summaries,
            },
        )

        # Flag low-confidence documents for review
        for doc in documents:
            if doc.confidence < 0.7:
                await dispatch_webhook_event(
                    "review.needed",
                    {
                        "batch_id": batch_id,
                        "document_type": doc.document_type,
                        "confidence": doc.confidence,
                        "start_page": doc.start_page,
                        "end_page": doc.end_page,
                    },
                )

    elif result.status == "paused":
        await db.update_batch_state(batch_id, "paused")
        await event_bus.publish(
            batch_id,
            {
                "type": "pipeline_paused",
                "stage": result.paused_stage,
                "reason": result.paused_reason,
            },
        )

    elif result.status == "error":
        await db.update_batch_state(batch_id, "error", error_message=result.error_message)
        await event_bus.publish(batch_id, {"type": "error", "message": result.error_message})

    # Emit DLQ events for any items added during processing
    state_path = batch_dir / "state.json"
    if isinstance(state_path, Path) and state_path.exists():
        final_state = PipelineState.load(state_path)
        for dlq_item in final_state.dlq:
            await event_bus.publish(
                batch_id,
                {
                    "type": "dlq_item_added",
                    "item_id": dlq_item.id,
                    "stage": dlq_item.stage,
                    "reason": dlq_item.reason,
                },
            )


def _validate_pdf(data: bytes) -> None:
    """Raise ValueError if *data* is not a valid PDF."""
    try:
        pikepdf.Pdf.open(BytesIO(data))
    except Exception as exc:
        raise ValueError(str(exc)) from exc


@router.post("/batches/import", status_code=201)
async def import_batch_endpoint(
    fronts: Annotated[UploadFile, File()],
    backs: Annotated[UploadFile | None, File()] = None,
    person_name: Annotated[str, Form()] = "Test Patient",
    auto_advance_on_error: Annotated[bool, Form()] = False,
    confidence_threshold: Annotated[float, Form()] = 0.7,
):
    """Import pre-made PDFs into a new batch, bypassing the scanner."""
    from scanbox.main import get_db
    from scanbox.pipeline.state import PipelineConfig, PipelineState

    cfg = Config()

    # Read and validate fronts PDF
    fronts_bytes = await fronts.read()
    try:
        _validate_pdf(fronts_bytes)
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "Invalid fronts PDF"})

    # Read and validate backs PDF if provided
    backs_bytes = None
    if backs is not None:
        raw = await backs.read()
        if raw:
            try:
                _validate_pdf(raw)
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid backs PDF"})
            backs_bytes = raw

    db = get_db()
    result = await do_import_batch(
        db=db,
        data_dir=cfg.INTERNAL_DATA_DIR,
        fronts_bytes=fronts_bytes,
        backs_bytes=backs_bytes,
        person_name=person_name,
    )

    # Write initial pipeline state with config before triggering processing
    pipeline_cfg = PipelineConfig(
        auto_advance_on_error=auto_advance_on_error,
        confidence_threshold=confidence_threshold,
    )
    initial_state = PipelineState.new(pipeline_cfg)
    initial_state.save(result.batch_dir / "state.json")

    # Launch pipeline processing in the background
    asyncio.create_task(_run_processing(result.batch_id, db, has_backs=result.has_backs))

    return JSONResponse(
        status_code=201,
        content={
            "batch_id": result.batch_id,
            "session_id": result.session_id,
            "person_id": result.person_id,
            "state": "processing",
            "has_backs": result.has_backs,
            "fronts_pages": result.fronts_page_count,
            "backs_pages": result.backs_page_count,
            "status_url": f"/api/batches/{result.batch_id}",
        },
    )
