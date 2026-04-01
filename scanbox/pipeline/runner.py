"""Pipeline orchestrator with checkpoint state machine.

Runs stages in sequence, checkpointing after each. If interrupted,
resumes from the last completed stage. Returns PipelineResult with
status indicating completed, paused, or error.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pikepdf

from scanbox.config import Config
from scanbox.models import PipelineResult, ProcessingStage, SplitDocument
from scanbox.pipeline.blank_detect import remove_blank_pages
from scanbox.pipeline.interleave import interleave_pages
from scanbox.pipeline.namer import generate_filename
from scanbox.pipeline.ocr import run_ocr
from scanbox.pipeline.output import embed_pdf_metadata
from scanbox.pipeline.splitter import split_documents
from scanbox.pipeline.state import DLQItem, PipelineConfig, PipelineState


@dataclass
class PipelineContext:
    batch_dir: Path
    output_dir: Path
    person_name: str
    person_slug: str
    person_folder: str
    batch_num: int
    scan_date: str
    has_backs: bool


def _state_path(ctx: PipelineContext) -> Path:
    return ctx.batch_dir / "state.json"


async def _run_stage(stage, ctx, state, on_progress):
    """Dispatch to the correct stage handler. Returns a result dict for state tracking."""
    if stage == ProcessingStage.INTERLEAVING:
        return await _run_interleaving(ctx, on_progress)
    if stage == ProcessingStage.BLANK_REMOVAL:
        return await _run_blank_removal(ctx, on_progress)
    if stage == ProcessingStage.OCR:
        return await _run_ocr(ctx, on_progress)
    if stage == ProcessingStage.SPLITTING:
        return await _run_splitting(ctx, state, on_progress)
    if stage == ProcessingStage.NAMING:
        return await _run_naming(ctx, state, on_progress)
    msg = f"Unknown stage: {stage}"
    raise ValueError(msg)


async def _run_interleaving(ctx, on_progress):
    if on_progress:
        await on_progress(ProcessingStage.INTERLEAVING.value, "Combining front and back pages...")
    combined_path = ctx.batch_dir / "combined.pdf"
    fronts_path = ctx.batch_dir / "fronts.pdf"
    backs_path = ctx.batch_dir / "backs.pdf" if ctx.has_backs else None
    interleave_pages(fronts_path, backs_path, combined_path)
    combined_pdf = pikepdf.Pdf.open(combined_path)
    total_pages = len(combined_pdf.pages)
    if on_progress:
        await on_progress(
            ProcessingStage.INTERLEAVING.value, f"Combined into {total_pages} pages", complete=True
        )
    return {"total_pages": total_pages}


async def _run_blank_removal(ctx, on_progress):
    if on_progress:
        await on_progress(ProcessingStage.BLANK_REMOVAL.value, "Removing blank pages...")
    combined_path = ctx.batch_dir / "combined.pdf"
    cleaned_path = ctx.batch_dir / "cleaned.pdf"
    result = remove_blank_pages(combined_path, cleaned_path, Config().BLANK_PAGE_THRESHOLD)
    removed_info = {
        "removed_indices": result.removed_indices,
        "total_pages": result.total_pages,
    }
    (ctx.batch_dir / "blank_removal.json").write_text(json.dumps(removed_info))
    kept = result.total_pages - len(result.removed_indices)
    if on_progress:
        await on_progress(
            ProcessingStage.BLANK_REMOVAL.value,
            f"{kept} pages, {len(result.removed_indices)} blank removed",
            complete=True,
        )
    return {
        "removed_indices": result.removed_indices,
        "total_pages": result.total_pages,
        "kept_pages": kept,
    }


async def _run_ocr(ctx, on_progress):
    if on_progress:
        await on_progress(ProcessingStage.OCR.value, "Reading text from your documents...")
    cleaned_path = ctx.batch_dir / "cleaned.pdf"
    ocr_path = ctx.batch_dir / "ocr.pdf"
    text_json_path = ctx.batch_dir / "text_by_page.json"
    run_ocr(cleaned_path, ocr_path, text_json_path)
    if on_progress:
        await on_progress(ProcessingStage.OCR.value, "OCR complete", complete=True)
    return {"ocr_complete": True}


async def _run_splitting(ctx, state, on_progress):
    if on_progress:
        await on_progress(
            ProcessingStage.SPLITTING.value,
            "Figuring out where each document starts and ends...",
        )
    text_json_path = ctx.batch_dir / "text_by_page.json"
    splits_path = ctx.batch_dir / "splits.json"
    page_texts_raw = json.loads(text_json_path.read_text())
    page_texts = {int(k): v for k, v in page_texts_raw.items()}

    # Remove excluded pages before AI splitting
    if state.excluded_pages:
        page_texts = {k: v for k, v in page_texts.items() if k not in state.excluded_pages}

    if not page_texts:
        # All pages excluded — no documents to find
        splits_path.write_text(json.dumps([]))
        if on_progress:
            await on_progress(
                ProcessingStage.SPLITTING.value,
                "No pages to process (all excluded)",
                complete=True,
            )
        return {"document_count": 0}

    documents = await split_documents(page_texts, ctx.person_name)
    splits_data = [doc.model_dump() for doc in documents]
    splits_path.write_text(json.dumps(splits_data, indent=2))
    if on_progress:
        await on_progress(
            ProcessingStage.SPLITTING.value, f"Found {len(documents)} documents", complete=True
        )
    return {"document_count": len(documents)}


async def _run_naming(ctx, state, on_progress):
    if on_progress:
        await on_progress(ProcessingStage.NAMING.value, "Organizing and naming your documents...")
    splits_path = ctx.batch_dir / "splits.json"
    ocr_path = ctx.batch_dir / "ocr.pdf"
    docs_dir = ctx.batch_dir / "documents"
    docs_dir.mkdir(exist_ok=True)
    splits_data = json.loads(splits_path.read_text())
    documents = [SplitDocument(**d) for d in splits_data]

    # Apply user overrides from previous processing run if present
    overrides_path = ctx.batch_dir / "user_overrides.json"
    if overrides_path.exists():
        overrides = json.loads(overrides_path.read_text())
        for doc in documents:
            for override in overrides:
                if (
                    doc.start_page == override["start_page"]
                    and doc.end_page == override["end_page"]
                ):
                    doc.document_type = override["document_type"]
                    doc.date_of_service = override["date_of_service"]
                    doc.facility = override["facility"]
                    doc.provider = override["provider"]
                    doc.description = override["description"]
                    doc.user_edited = True
                    break

    ocr_pdf = pikepdf.Pdf.open(ocr_path)

    # Determine which document indices are active (not excluded)
    excluded = set(state.excluded_documents)
    active_indices = [i for i in range(len(documents)) if i not in excluded]

    seen_names: dict[str, int] = {}
    for i in active_indices:
        doc = documents[i]
        # Extract pages
        doc_pdf = pikepdf.Pdf.new()
        for page_num in range(doc.start_page, doc.end_page + 1):
            doc_pdf.pages.append(ocr_pdf.pages[page_num - 1])

        # Generate filename (handle duplicates)
        base_name = generate_filename(
            person_name=ctx.person_name,
            document_type=doc.document_type,
            date_of_service=doc.date_of_service,
            facility=doc.facility,
            description=doc.description,
        )
        if base_name in seen_names:
            seen_names[base_name] += 1
            filename = generate_filename(
                person_name=ctx.person_name,
                document_type=doc.document_type,
                date_of_service=doc.date_of_service,
                facility=doc.facility,
                description=doc.description,
                duplicate_index=seen_names[base_name],
            )
        else:
            seen_names[base_name] = 1
            filename = base_name

        doc_path = docs_dir / filename
        doc_pdf.save(doc_path)

        # Embed PDF metadata
        title = f"{doc.document_type} — {doc.description}"
        embed_pdf_metadata(
            doc_path,
            title=title,
            author=doc.facility if doc.facility != "unknown" else "Unknown",
            subject=ctx.person_name,
            creation_date=doc.date_of_service,
        )

        # Store filename back on the document for callers
        doc.filename = filename

    # Write ALL documents back (including excluded) so indices stay stable
    splits_data = [doc.model_dump() for doc in documents]
    splits_path.write_text(json.dumps(splits_data, indent=2))

    named_count = len(active_indices)
    excluded_count = len(documents) - named_count
    if on_progress:
        detail = f"{named_count} documents named"
        if excluded_count:
            detail += f", {excluded_count} excluded"
        await on_progress(ProcessingStage.NAMING.value, detail, complete=True)
    return {"documents_named": named_count, "documents_excluded": excluded_count}


async def run_pipeline(
    ctx: PipelineContext,
    on_progress: callable = None,
    pipeline_config: PipelineConfig | None = None,
) -> PipelineResult:
    """Run the full processing pipeline with checkpointing.

    Args:
        ctx: Pipeline context with paths and metadata.
        on_progress: Optional async callback(stage_name, detail, complete) for SSE updates.
        pipeline_config: Optional pipeline config for confidence thresholds and DLQ behavior.

    Returns:
        PipelineResult with status, documents, and any pause/error info.
    """
    state = PipelineState.load(_state_path(ctx))

    # Apply pipeline_config if provided, otherwise keep state's config (or defaults)
    if pipeline_config is not None:
        state.config = pipeline_config

    for stage in state.pending_stages():
        state.mark_running(stage)
        state.save(_state_path(ctx))

        try:
            result = await _run_stage(stage, ctx, state, on_progress)
            state.mark_completed(stage, result)
            state.save(_state_path(ctx))
        except Exception as e:
            state.mark_error(stage, str(e))
            state.save(_state_path(ctx))
            return PipelineResult(status="error", error_stage=stage.value, error_message=str(e))

        # After SPLITTING: check document confidence
        if stage == ProcessingStage.SPLITTING:
            splits_path = ctx.batch_dir / "splits.json"
            splits_data = json.loads(splits_path.read_text())
            documents = [SplitDocument(**d) for d in splits_data]

            low_conf = [d for d in documents if d.confidence < state.config.confidence_threshold]
            if low_conf:
                if state.config.auto_advance_on_error:
                    for d in low_conf:
                        state.add_to_dlq(
                            DLQItem(
                                stage="splitting",
                                document=d.model_dump(),
                                reason=(
                                    f"Confidence {d.confidence:.2f} below"
                                    f" threshold {state.config.confidence_threshold}"
                                ),
                            )
                        )
                    state.save(_state_path(ctx))
                else:
                    reason = f"{len(low_conf)} documents below confidence threshold"
                    state.mark_paused(ProcessingStage.SPLITTING, reason)
                    state.save(_state_path(ctx))
                    return PipelineResult(
                        status="paused",
                        paused_stage="splitting",
                        paused_reason=reason,
                        documents=documents,
                    )

    # Read back final documents list
    splits_path = ctx.batch_dir / "splits.json"
    splits_data = json.loads(splits_path.read_text())
    all_documents = [SplitDocument(**d) for d in splits_data]

    # Filter excluded documents from the result
    excluded = set(state.excluded_documents)
    documents = [doc for i, doc in enumerate(all_documents) if i not in excluded]
    return PipelineResult(status="completed", documents=documents)
