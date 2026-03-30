"""Integration tests: load test pile fixtures and verify pipeline readiness."""

import json
from pathlib import Path

import pikepdf

SUITE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "test_suite"


class TestLoadTestPile:
    async def test_loads_standard_pile(self, load_test_pile):
        batch_id, ctx = await load_test_pile("01-standard-clean")
        assert ctx.batch_dir.exists()
        assert (ctx.batch_dir / "fronts.pdf").exists()
        assert (ctx.batch_dir / "backs.pdf").exists()
        assert ctx.has_backs is True

    async def test_loads_single_sided(self, load_test_pile):
        batch_id, ctx = await load_test_pile("02-single-sided-only")
        assert (ctx.batch_dir / "fronts.pdf").exists()
        assert ctx.has_backs is True

    async def test_uses_manifest_patient_name(self, load_test_pile):
        batch_id, ctx = await load_test_pile("01-standard-clean")
        assert ctx.person_name == "Elena R. Martinez"

    async def test_uses_custom_patient_name(self, load_test_pile):
        batch_id, ctx = await load_test_pile("01-standard-clean", person_name="Override Name")
        assert ctx.person_name == "Override Name"

    async def test_different_patient_pile(self, load_test_pile):
        batch_id, ctx = await load_test_pile("11-different-patient")
        assert ctx.person_name == "John A. Doe"

    async def test_minimal_pile(self, load_test_pile):
        batch_id, ctx = await load_test_pile("06-minimal-quick")
        fronts = pikepdf.Pdf.open(ctx.batch_dir / "fronts.pdf")
        assert len(fronts.pages) == 3

    async def test_page_counts_match_manifest(self, load_test_pile):
        batch_id, ctx = await load_test_pile("01-standard-clean")
        manifest = json.loads((SUITE_DIR / "01-standard-clean" / "manifest.json").read_text())
        fronts = pikepdf.Pdf.open(ctx.batch_dir / "fronts.pdf")
        assert len(fronts.pages) == manifest["num_sheets"]

    async def test_returns_valid_batch_id(self, load_test_pile):
        batch_id, ctx = await load_test_pile("06-minimal-quick")
        assert batch_id.startswith("batch-")

    async def test_pipeline_context_fields(self, load_test_pile):
        batch_id, ctx = await load_test_pile("01-standard-clean")
        assert ctx.person_slug is not None
        assert ctx.person_folder is not None
        assert ctx.batch_num == 1
        assert ctx.scan_date is not None
        assert ctx.output_dir.exists()
