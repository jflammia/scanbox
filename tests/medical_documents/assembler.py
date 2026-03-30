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

        # Artifact application placeholder (Task 7)
        artifact_log = None

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
