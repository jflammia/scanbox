"""Integration test: full pipeline from fronts+backs to named output documents."""

import shutil
from pathlib import Path

import pytest

from scanbox.pipeline.runner import PipelineContext


@pytest.fixture
def pipeline_ctx(tmp_path: Path, batch_fixtures_dir: Path) -> PipelineContext:
    """Create a pipeline context with fixture data."""
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    fronts = batch_fixtures_dir / "fronts_all_single_sided.pdf"
    if not fronts.exists():
        pytest.skip("Run generate_fixtures first")

    shutil.copy(fronts, batch_dir / "fronts.pdf")

    return PipelineContext(
        batch_dir=batch_dir,
        output_dir=output_dir,
        person_name="John Doe",
        person_slug="john-doe",
        person_folder="John_Doe",
        batch_num=1,
        scan_date="2026-03-28",
        has_backs=False,
    )


class TestPipelineRunner:
    def test_single_sided_produces_output(self, pipeline_ctx: PipelineContext):
        """Smoke test: pipeline completes without errors on single-sided batch."""
        # This test requires tesseract + a real or mocked LLM
        # For unit testing, we mock the LLM call — see conftest
        pytest.skip("Requires LLM mock — implement in task 10")

    def test_state_file_tracks_progress(self, pipeline_ctx: PipelineContext):
        state_path = pipeline_ctx.batch_dir / "state.json"
        # State file should be created at pipeline start
        assert not state_path.exists()  # Not yet started
