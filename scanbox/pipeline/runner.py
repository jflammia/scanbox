"""Pipeline orchestrator with checkpoint state machine.

Runs stages in sequence, checkpointing after each. If interrupted,
resumes from the last completed stage.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pikepdf

from scanbox.config import config
from scanbox.models import ProcessingStage, SplitDocument
from scanbox.pipeline.blank_detect import remove_blank_pages
from scanbox.pipeline.interleave import interleave_pages
from scanbox.pipeline.namer import generate_filename
from scanbox.pipeline.ocr import run_ocr
from scanbox.pipeline.output import embed_pdf_metadata
from scanbox.pipeline.splitter import split_documents


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


def _read_state(ctx: PipelineContext) -> dict:
    path = _state_path(ctx)
    if path.exists():
        return json.loads(path.read_text())
    return {"stage": ProcessingStage.INTERLEAVING.value}


def _write_state(ctx: PipelineContext, stage: ProcessingStage, **extra) -> None:
    state = {"stage": stage.value, **extra}
    _state_path(ctx).write_text(json.dumps(state, indent=2))


async def run_pipeline(
    ctx: PipelineContext,
    on_progress: callable = None,
) -> list[SplitDocument]:
    """Run the full processing pipeline with checkpointing.

    Args:
        ctx: Pipeline context with paths and metadata.
        on_progress: Optional async callback(stage_name, detail, complete) for SSE updates.
    """
    state = _read_state(ctx)
    current_stage = ProcessingStage(state["stage"])

    async def progress(stage: ProcessingStage, detail: str = ""):
        _write_state(ctx, stage)
        if on_progress:
            await on_progress(stage.value, detail)

    async def stage_done(stage: ProcessingStage, detail: str = ""):
        if on_progress:
            await on_progress(stage.value, detail, complete=True)

    # Stage 1: Interleave
    combined_path = ctx.batch_dir / "combined.pdf"
    if current_stage == ProcessingStage.INTERLEAVING:
        await progress(ProcessingStage.INTERLEAVING, "Combining front and back pages...")
        fronts_path = ctx.batch_dir / "fronts.pdf"
        backs_path = ctx.batch_dir / "backs.pdf" if ctx.has_backs else None
        interleave_pages(fronts_path, backs_path, combined_path)
        combined_pdf = pikepdf.Pdf.open(combined_path)
        total_pages = len(combined_pdf.pages)
        await stage_done(ProcessingStage.INTERLEAVING, f"Combined into {total_pages} pages")
        current_stage = ProcessingStage.BLANK_REMOVAL

    # Stage 2: Blank removal
    cleaned_path = ctx.batch_dir / "cleaned.pdf"
    if current_stage == ProcessingStage.BLANK_REMOVAL:
        await progress(ProcessingStage.BLANK_REMOVAL, "Removing blank pages...")
        result = remove_blank_pages(combined_path, cleaned_path, config.BLANK_PAGE_THRESHOLD)
        removed_info = {
            "removed_indices": result.removed_indices,
            "total_pages": result.total_pages,
        }
        (ctx.batch_dir / "blank_removal.json").write_text(json.dumps(removed_info))
        kept = result.total_pages - len(result.removed_indices)
        await stage_done(
            ProcessingStage.BLANK_REMOVAL,
            f"{kept} pages, {len(result.removed_indices)} blank removed",
        )
        current_stage = ProcessingStage.OCR

    # Stage 3: OCR
    ocr_path = ctx.batch_dir / "ocr.pdf"
    text_json_path = ctx.batch_dir / "text_by_page.json"
    if current_stage == ProcessingStage.OCR:
        await progress(ProcessingStage.OCR, "Reading text from your documents...")
        run_ocr(cleaned_path, ocr_path, text_json_path)
        await stage_done(ProcessingStage.OCR, "OCR complete")
        current_stage = ProcessingStage.SPLITTING

    # Stage 4: AI Splitting
    splits_path = ctx.batch_dir / "splits.json"
    if current_stage == ProcessingStage.SPLITTING:
        await progress(
            ProcessingStage.SPLITTING, "Figuring out where each document starts and ends..."
        )
        page_texts_raw = json.loads(text_json_path.read_text())
        page_texts = {int(k): v for k, v in page_texts_raw.items()}
        documents = await split_documents(page_texts, ctx.person_name)
        splits_data = [doc.model_dump() for doc in documents]
        splits_path.write_text(json.dumps(splits_data, indent=2))
        await stage_done(ProcessingStage.SPLITTING, f"Found {len(documents)} documents")
        current_stage = ProcessingStage.NAMING

    # Stage 5: Split, embed metadata, name
    docs_dir = ctx.batch_dir / "documents"
    if current_stage == ProcessingStage.NAMING:
        await progress(ProcessingStage.NAMING, "Organizing and naming your documents...")
        docs_dir.mkdir(exist_ok=True)
        splits_data = json.loads(splits_path.read_text())
        documents = [SplitDocument(**d) for d in splits_data]
        ocr_pdf = pikepdf.Pdf.open(ocr_path)

        seen_names: dict[str, int] = {}
        for doc in documents:
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

        # Write final documents with filenames
        splits_data = [doc.model_dump() for doc in documents]
        splits_path.write_text(json.dumps(splits_data, indent=2))
        _write_state(ctx, ProcessingStage.DONE)
        await stage_done(ProcessingStage.NAMING, "All documents named")

    # Read back final documents list
    splits_data = json.loads(splits_path.read_text())
    return [SplitDocument(**d) for d in splits_data]
