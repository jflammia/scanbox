"""Pile assembly: sheet building, artifact application, front/back splitting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pikepdf

from tests.medical_documents import DocumentDef, DocumentEntry, PatientContext, PileConfig
from tests.medical_documents.helpers import add_blank_page, add_near_blank_page, new_pdf


class PileArtifact:
    """Base for all pile artifacts (scanning mistakes / organizational chaos)."""

    pass


@dataclass
class DuplicatePage(PileArtifact):
    """Same page scanned twice (ADF double-feed or manual re-scan)."""

    doc_index: int
    page: int  # 1-based


@dataclass
class DuplicateDocument(PileArtifact):
    """Entire document appears twice in the pile."""

    doc_index: int
    insert_at: int | None = None


@dataclass
class ShufflePages(PileArtifact):
    """Pages within a document are out of order."""

    doc_index: int
    order: list[int]  # 1-based page numbers


@dataclass
class InterleaveDocuments(PileArtifact):
    """Pages from two documents got mixed together."""

    doc_a_index: int
    doc_b_index: int
    pattern: list[int]  # 0 = next page from doc_a, 1 = next page from doc_b


@dataclass
class StrayDocument(PileArtifact):
    """A document that doesn't belong in the pile."""

    document_name: str
    position: int
    config: object = None


@dataclass
class WrongPatientDocument(PileArtifact):
    """Someone else's document mixed into this patient's pile."""

    document_name: str
    patient: PatientContext
    position: int
    config: object = None


@dataclass
class BlankSheetInserted(PileArtifact):
    """Random blank sheet in the pile."""

    position: int


@dataclass
class RotatedPage(PileArtifact):
    """Page fed upside-down through the ADF (180 degree rotation)."""

    doc_index: int
    page: int  # 1-based


class PileAssembler:
    """Assembles documents into fronts.pdf and backs.pdf for scanner simulation."""

    def generate(self, config: PileConfig) -> tuple[Path, Path]:
        from tests.medical_documents.documents import REGISTRY

        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        patient = config.patient

        # Normalize document entries (str -> DocumentEntry)
        entries: list[DocumentEntry] = []
        for doc in config.documents:
            if isinstance(doc, str):
                entries.append(DocumentEntry(name=doc))
            else:
                entries.append(doc)

        # Render each document and collect metadata
        doc_pdfs: list[bytes] = []
        doc_metas: list[dict] = []
        for entry in entries:
            doc_def = REGISTRY[entry.name]
            entry_patient = entry.patient or patient
            entry_config = entry.config
            if entry_config is None and doc_def.default_config_cls is not None:
                entry_config = doc_def.default_config_cls()

            pdf_bytes = self._render_doc(doc_def, entry_patient, entry_config)
            doc_pdfs.append(pdf_bytes)

            # Determine single_sided: entry override takes precedence
            single_sided = (
                entry.single_sided if entry.single_sided is not None else doc_def.single_sided
            )

            # Count pages
            with pikepdf.Pdf.open(BytesIO(pdf_bytes)) as pdf:
                num_pages = len(pdf.pages)

            doc_metas.append(
                {
                    "name": entry.name,
                    "description": doc_def.description,
                    "pages": num_pages,
                    "single_sided": single_sided,
                    "back_artifact": doc_def.back_artifact,
                }
            )

        # Build sheet list
        sheets = self._build_sheets(doc_pdfs, doc_metas)

        # Apply artifacts (scanning mistakes / chaos)
        sheets, artifact_log = self._apply_artifacts(config, sheets, doc_pdfs, doc_metas)

        # Split into fronts/backs
        fronts_path, backs_path = self._split_fronts_backs(sheets, output_dir)

        # Write manifest
        self._write_manifest(config, doc_metas, sheets, artifact_log)

        return fronts_path, backs_path

    def _render_doc(self, doc_def: DocumentDef, patient: PatientContext, config) -> bytes:
        fpdf = new_pdf()
        doc_def.render(fpdf, patient, config)
        buf = BytesIO()
        fpdf.output(buf)
        return buf.getvalue()

    def _build_sheets(self, doc_pdfs: list[bytes], doc_metas: list[dict]) -> list[dict]:
        sheets = []

        for pdf_bytes, meta in zip(doc_pdfs, doc_metas, strict=True):
            pdf = pikepdf.Pdf.open(BytesIO(pdf_bytes))
            pages = list(pdf.pages)
            num_pages = len(pages)
            single_sided = meta["single_sided"]
            back_artifact = meta["back_artifact"]
            doc_name = meta["name"]

            if single_sided:
                # Each page gets its own sheet, back is blank/near-blank
                for page_idx, page in enumerate(pages):
                    sheets.append(
                        {
                            "front": page,
                            "back": None,
                            "back_type": back_artifact,
                            "front_doc": doc_name,
                            "front_page": page_idx + 1,
                            "back_doc": None,
                            "back_page": None,
                            "_source_pdf": pdf,
                        }
                    )
            else:
                # Double-sided: pair pages (0+1, 2+3, etc.)
                for i in range(0, num_pages, 2):
                    front_page = pages[i]
                    if i + 1 < num_pages:
                        back_page = pages[i + 1]
                        back_type = "content"
                        back_doc = doc_name
                        back_page_num = i + 2
                    else:
                        # Odd number of pages -- last back is blank
                        back_page = None
                        back_type = back_artifact
                        back_doc = None
                        back_page_num = None

                    sheets.append(
                        {
                            "front": front_page,
                            "back": back_page,
                            "back_type": back_type,
                            "front_doc": doc_name,
                            "front_page": i + 1,
                            "back_doc": back_doc,
                            "back_page": back_page_num,
                            "_source_pdf": pdf,
                        }
                    )

        return sheets

    def _apply_artifacts(
        self,
        config: PileConfig,
        sheets: list[dict],
        doc_pdfs: list[bytes],
        doc_metas: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """Apply all configured artifacts and return (modified_sheets, artifact_log)."""
        from tests.medical_documents.documents import REGISTRY

        if not config.artifacts:
            return sheets, []

        artifact_log = []
        for artifact in config.artifacts:
            if isinstance(artifact, ShufflePages):
                entry = self._apply_shuffle(artifact, sheets, doc_metas)
            elif isinstance(artifact, DuplicatePage):
                sheets, entry = self._apply_duplicate_page(artifact, sheets, doc_metas)
            elif isinstance(artifact, DuplicateDocument):
                sheets, entry = self._apply_duplicate_doc(
                    artifact, sheets, doc_pdfs, doc_metas, config.patient
                )
            elif isinstance(artifact, BlankSheetInserted):
                sheets, entry = self._apply_blank_insert(artifact, sheets)
            elif isinstance(artifact, (WrongPatientDocument, StrayDocument)):
                sheets, entry = self._apply_foreign_doc(artifact, config, sheets, REGISTRY)
            elif isinstance(artifact, RotatedPage):
                entry = self._apply_rotation(artifact, sheets, doc_metas)
            else:
                continue
            artifact_log.append(entry)

        return sheets, artifact_log

    def _apply_duplicate_page(
        self, artifact: DuplicatePage, sheets: list[dict], doc_metas: list[dict]
    ) -> tuple[list[dict], dict]:
        """Insert a duplicate of a specific page as a new sheet after the original."""
        doc_name = doc_metas[artifact.doc_index]["name"]

        # Find the sheet whose front page matches
        insert_after = None
        source_sheet = None
        for idx, sheet in enumerate(sheets):
            if sheet["front_doc"] == doc_name and sheet["front_page"] == artifact.page:
                insert_after = idx
                source_sheet = sheet
                break

        if source_sheet is None:
            return sheets, {
                "type": "DuplicatePage",
                "doc_index": artifact.doc_index,
                "page": artifact.page,
                "result": "Page not found — skipped",
            }

        # Create a duplicate sheet with the same front but blank back
        dup_sheet = {
            "front": source_sheet["front"],
            "back": None,
            "back_type": "blank",
            "front_doc": source_sheet["front_doc"],
            "front_page": source_sheet["front_page"],
            "back_doc": None,
            "back_page": None,
            "_source_pdf": source_sheet.get("_source_pdf"),
        }
        sheets = sheets[: insert_after + 1] + [dup_sheet] + sheets[insert_after + 1 :]

        return sheets, {
            "type": "DuplicatePage",
            "doc_index": artifact.doc_index,
            "page": artifact.page,
            "result": f"Inserted duplicate of page {artifact.page} from {doc_name}",
        }

    def _apply_duplicate_doc(
        self,
        artifact: DuplicateDocument,
        sheets: list[dict],
        doc_pdfs: list[bytes],
        doc_metas: list[dict],
        patient: PatientContext,
    ) -> tuple[list[dict], dict]:
        """Re-render a document and insert its sheets as a duplicate."""
        from tests.medical_documents.documents import REGISTRY

        meta = doc_metas[artifact.doc_index]
        doc_name = meta["name"]
        doc_def = REGISTRY[doc_name]

        entry_config = None
        if doc_def.default_config_cls is not None:
            entry_config = doc_def.default_config_cls()

        pdf_bytes = self._render_doc(doc_def, patient, entry_config)
        dup_metas = [meta.copy()]
        dup_sheets = self._build_sheets([pdf_bytes], dup_metas)

        # Find insert position: after last sheet of the original doc, or artifact.insert_at
        if artifact.insert_at is not None:
            pos = min(artifact.insert_at, len(sheets))
        else:
            pos = 0
            for idx, sheet in enumerate(sheets):
                if sheet["front_doc"] == doc_name:
                    pos = idx + 1
            # pos is now after the last sheet of that doc

        sheets = sheets[:pos] + dup_sheets + sheets[pos:]

        return sheets, {
            "type": "DuplicateDocument",
            "doc_index": artifact.doc_index,
            "result": f"Inserted duplicate of {doc_name} at position {pos}",
        }

    def _apply_shuffle(
        self, artifact: ShufflePages, sheets: list[dict], doc_metas: list[dict]
    ) -> dict:
        """Reorder sheets for a document according to artifact.order."""
        doc_name = doc_metas[artifact.doc_index]["name"]

        # Collect indices of sheets belonging to this document
        doc_indices = [idx for idx, s in enumerate(sheets) if s["front_doc"] == doc_name]

        if not doc_indices:
            return {
                "type": "ShufflePages",
                "doc_index": artifact.doc_index,
                "order": artifact.order,
                "result": "No sheets found — skipped",
            }

        # Reorder: artifact.order is 1-based page numbers
        # Map page numbers to sheet indices
        page_to_sheet = {}
        for idx in doc_indices:
            page_to_sheet[sheets[idx]["front_page"]] = sheets[idx]

        reordered = []
        for page_num in artifact.order:
            if page_num in page_to_sheet:
                reordered.append(page_to_sheet[page_num])

        # Replace in sheets list
        for i, doc_idx in enumerate(doc_indices):
            if i < len(reordered):
                sheets[doc_idx] = reordered[i]

        return {
            "type": "ShufflePages",
            "doc_index": artifact.doc_index,
            "order": artifact.order,
            "result": f"Reordered {doc_name} sheets to page order {artifact.order}",
        }

    def _apply_blank_insert(
        self, artifact: BlankSheetInserted, sheets: list[dict]
    ) -> tuple[list[dict], dict]:
        """Insert a blank sheet at the specified position."""
        blank_page_buf = self._make_page_pdf("blank")
        blank_pdf = pikepdf.Pdf.open(blank_page_buf)
        blank_page = blank_pdf.pages[0]

        blank_sheet = {
            "front": blank_page,
            "back": None,
            "back_type": "blank",
            "front_doc": "_blank",
            "front_page": 1,
            "back_doc": None,
            "back_page": None,
            "_source_pdf": blank_pdf,
        }

        pos = max(0, min(artifact.position, len(sheets)))
        sheets = sheets[:pos] + [blank_sheet] + sheets[pos:]

        return sheets, {
            "type": "BlankSheetInserted",
            "position": artifact.position,
            "result": f"Inserted blank sheet at position {pos}",
        }

    def _apply_foreign_doc(
        self, artifact, config: PileConfig, sheets: list[dict], registry: dict
    ) -> tuple[list[dict], dict]:
        """Insert a foreign document (WrongPatient or Stray) into the pile."""
        if isinstance(artifact, WrongPatientDocument):
            patient = artifact.patient
            doc_name = artifact.document_name
        else:
            # StrayDocument
            patient = config.patient
            doc_name = artifact.document_name

        doc_def = registry[doc_name]
        entry_config = artifact.config
        if entry_config is None and doc_def.default_config_cls is not None:
            entry_config = doc_def.default_config_cls()

        pdf_bytes = self._render_doc(doc_def, patient, entry_config)

        single_sided = doc_def.single_sided
        with pikepdf.Pdf.open(BytesIO(pdf_bytes)) as pdf:
            num_pages = len(pdf.pages)

        foreign_metas = [
            {
                "name": doc_name,
                "description": doc_def.description,
                "pages": num_pages,
                "single_sided": single_sided,
                "back_artifact": doc_def.back_artifact,
            }
        ]
        foreign_sheets = self._build_sheets([pdf_bytes], foreign_metas)

        pos = max(0, min(artifact.position, len(sheets)))
        sheets = sheets[:pos] + foreign_sheets + sheets[pos:]

        entry = {
            "type": type(artifact).__name__,
            "document_name": doc_name,
            "position": pos,
            "result": f"Inserted {doc_name} at position {pos}",
        }
        if isinstance(artifact, WrongPatientDocument):
            entry["patient"] = artifact.patient.name

        return sheets, entry

    def _apply_rotation(
        self, artifact: RotatedPage, sheets: list[dict], doc_metas: list[dict]
    ) -> dict:
        """Rotate a specific page 180 degrees."""
        doc_name = doc_metas[artifact.doc_index]["name"]

        for sheet in sheets:
            if sheet["front_doc"] == doc_name and sheet["front_page"] == artifact.page:
                # Rotate the pikepdf page object directly
                page = sheet["front"]
                page.rotate(180, relative=True)
                return {
                    "type": "RotatedPage",
                    "doc_index": artifact.doc_index,
                    "page": artifact.page,
                    "result": f"Rotated page {artifact.page} of {doc_name} by 180 degrees",
                }

        return {
            "type": "RotatedPage",
            "doc_index": artifact.doc_index,
            "page": artifact.page,
            "result": "Page not found — skipped",
        }

    def _split_fronts_backs(self, sheets: list[dict], output_dir: Path) -> tuple[Path, Path]:
        fronts_pdf = pikepdf.Pdf.new()
        backs_pdf = pikepdf.Pdf.new()

        # Fronts: all front pages in sheet order
        for sheet in sheets:
            page_buf = self._page_to_pdf_bytes(sheet["front"])
            src = pikepdf.Pdf.open(BytesIO(page_buf))
            fronts_pdf.pages.append(src.pages[0])

        # Backs: all back pages in REVERSED sheet order (pile flip)
        for sheet in reversed(sheets):
            if sheet["back"] is not None:
                page_buf = self._page_to_pdf_bytes(sheet["back"])
                src = pikepdf.Pdf.open(BytesIO(page_buf))
                backs_pdf.pages.append(src.pages[0])
            else:
                # Non-content back: blank or near-blank
                page_buf = self._make_page_pdf(sheet["back_type"])
                src = pikepdf.Pdf.open(page_buf)
                backs_pdf.pages.append(src.pages[0])

        fronts_path = output_dir / "fronts.pdf"
        backs_path = output_dir / "backs.pdf"
        fronts_pdf.save(fronts_path)
        backs_pdf.save(backs_path)

        return fronts_path, backs_path

    def _page_to_pdf_bytes(self, page) -> bytes:
        """Extract a single pikepdf page into standalone PDF bytes."""
        tmp = pikepdf.Pdf.new()
        tmp.pages.append(page)
        buf = BytesIO()
        tmp.save(buf)
        return buf.getvalue()

    def _make_page_pdf(self, page_type: str) -> BytesIO:
        """Make a single blank or near-blank page as a PDF."""
        fpdf = new_pdf()
        if page_type == "near_blank_smudge":
            add_near_blank_page(fpdf, artifact="smudge")
        elif page_type == "near_blank_footer":
            add_near_blank_page(fpdf, artifact="footer")
        else:
            # Default: blank
            add_blank_page(fpdf)
        buf = BytesIO()
        fpdf.output(buf)
        buf.seek(0)
        return buf

    def _write_manifest(
        self,
        config: PileConfig,
        doc_metas: list[dict],
        sheets: list[dict],
        artifact_log=None,
    ) -> None:
        output_dir = Path(config.output_dir)

        # Count back types
        content_backs = sum(1 for s in sheets if s["back_type"] == "content")
        blank_backs = sum(1 for s in sheets if s["back_type"] == "blank")
        near_blank_backs = sum(1 for s in sheets if s["back_type"] not in ("content", "blank"))

        total_logical_pages = sum(m["pages"] for m in doc_metas)

        # Build sheets manifest (without internal pikepdf references)
        sheets_manifest = []
        for idx, sheet in enumerate(sheets):
            sheet_entry = {
                "index": idx,
                "front": {
                    "doc": sheet["front_doc"],
                    "page": sheet["front_page"],
                },
                "back": {
                    "type": sheet["back_type"],
                    "doc": sheet["back_doc"],
                    "page": sheet["back_page"],
                },
            }
            sheets_manifest.append(sheet_entry)

        manifest = {
            "generated_at": datetime.now(UTC).isoformat(),
            "patient": {
                "name": config.patient.name,
                "mrn": config.patient.mrn,
                "dob": config.patient.dob,
            },
            "num_sheets": len(sheets),
            "num_logical_pages": total_logical_pages,
            "documents": [
                {
                    "name": m["name"],
                    "description": m["description"],
                    "pages": m["pages"],
                    "single_sided": m["single_sided"],
                }
                for m in doc_metas
            ],
            "sheets": sheets_manifest,
            "backs_order": "reversed",
            "artifacts_applied": artifact_log or [],
            "counts": {
                "content_backs": content_backs,
                "blank_backs": blank_backs,
                "near_blank_backs": near_blank_backs,
            },
        }

        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
