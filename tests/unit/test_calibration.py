"""Tests for confidence calibration tool and API endpoint."""

import json
from pathlib import Path

from scanbox.api.calibration import compute_calibration_data
from scanbox.pipeline.state import PipelineConfig, PipelineState, StageStatus


def _make_splits_json(batch_dir: Path, documents: list[dict]) -> None:
    """Write a splits.json file for testing."""
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "splits.json").write_text(json.dumps(documents, indent=2))


def _make_completed_state(batch_dir: Path, *, splitting_result: dict | None = None) -> None:
    """Write a state.json with splitting completed."""
    state = PipelineState.new(PipelineConfig())
    for stage_key in state.stages:
        state.stages[stage_key].status = StageStatus.COMPLETED
    if splitting_result:
        state.stages["splitting"].result = splitting_result
    state.save(batch_dir / "state.json")


class TestComputeCalibrationData:
    def test_single_batch(self, tmp_path):
        """Single batch with three docs produces correct distribution."""
        batch_dir = tmp_path / "batch1"
        _make_splits_json(
            batch_dir,
            [
                {"start_page": 1, "end_page": 2, "confidence": 0.95},
                {"start_page": 3, "end_page": 3, "confidence": 0.72},
                {"start_page": 4, "end_page": 5, "confidence": 0.45},
            ],
        )

        result = compute_calibration_data([batch_dir], current_threshold=0.7)

        assert result["total_scores"] == 3
        assert result["current_threshold"] == 0.7
        assert len(result["scores"]) == 3
        assert 0.95 in result["scores"]
        assert 0.72 in result["scores"]
        assert 0.45 in result["scores"]

    def test_multiple_batches(self, tmp_path):
        """Scores from multiple batches are aggregated."""
        batch1 = tmp_path / "batch1"
        _make_splits_json(batch1, [{"confidence": 0.9}, {"confidence": 0.8}])

        batch2 = tmp_path / "batch2"
        _make_splits_json(batch2, [{"confidence": 0.6}, {"confidence": 0.3}])

        result = compute_calibration_data([batch1, batch2], current_threshold=0.7)

        assert result["total_scores"] == 4

    def test_empty_batches(self, tmp_path):
        """No batches produces empty result."""
        result = compute_calibration_data([], current_threshold=0.7)

        assert result["total_scores"] == 0
        assert result["scores"] == []
        assert result["distribution"] == {}

    def test_threshold_impact(self, tmp_path):
        """Threshold impact shows flagged count at each level."""
        batch_dir = tmp_path / "batch1"
        _make_splits_json(
            batch_dir,
            [
                {"confidence": 0.95},
                {"confidence": 0.85},
                {"confidence": 0.75},
                {"confidence": 0.65},
                {"confidence": 0.55},
                {"confidence": 0.45},
            ],
        )

        result = compute_calibration_data([batch_dir], current_threshold=0.7)

        impact = result["threshold_impact"]
        # At 0.5: 1 doc flagged (0.45)
        assert impact["0.5"]["flagged"] == 1
        # At 0.6: 2 docs flagged (0.45, 0.55)
        assert impact["0.6"]["flagged"] == 2
        # At 0.7: 3 docs flagged (0.45, 0.55, 0.65)
        assert impact["0.7"]["flagged"] == 3
        # At 0.8: 4 docs flagged (0.45, 0.55, 0.65, 0.75)
        assert impact["0.8"]["flagged"] == 4
        # At 0.9: 5 docs flagged
        assert impact["0.9"]["flagged"] == 5

    def test_distribution_buckets(self, tmp_path):
        """Distribution groups scores into 0.1-wide buckets."""
        batch_dir = tmp_path / "batch1"
        _make_splits_json(
            batch_dir,
            [
                {"confidence": 0.92},
                {"confidence": 0.95},
                {"confidence": 0.73},
            ],
        )

        result = compute_calibration_data([batch_dir], current_threshold=0.7)

        # 0.92 and 0.95 -> "0.9-1.0" bucket, 0.73 -> "0.7-0.8" bucket
        assert result["distribution"]["0.9-1.0"] == 2
        assert result["distribution"]["0.7-0.8"] == 1

    def test_percentiles(self, tmp_path):
        """Percentiles are computed from the scores."""
        batch_dir = tmp_path / "batch1"
        # 10 scores: 0.1 through 1.0
        docs = [{"confidence": round(i / 10, 1)} for i in range(1, 11)]
        _make_splits_json(batch_dir, docs)

        result = compute_calibration_data([batch_dir], current_threshold=0.7)

        assert "p25" in result["percentiles"]
        assert "p50" in result["percentiles"]
        assert "p75" in result["percentiles"]

    def test_batch_without_splits_json_skipped(self, tmp_path):
        """Batch directories without splits.json are silently skipped."""
        batch_dir = tmp_path / "batch1"
        batch_dir.mkdir(parents=True)
        # No splits.json

        result = compute_calibration_data([batch_dir], current_threshold=0.7)

        assert result["total_scores"] == 0

    def test_recommendation_at_low_scores(self, tmp_path):
        """When most scores are low, recommendation is lower than default."""
        batch_dir = tmp_path / "batch1"
        docs = [{"confidence": 0.3}, {"confidence": 0.35}, {"confidence": 0.4}]
        _make_splits_json(batch_dir, docs)

        result = compute_calibration_data([batch_dir], current_threshold=0.7)

        # Should recommend a threshold based on the data
        assert "recommended_threshold" in result
        # With scores all below 0.5, recommended threshold should be low
        assert result["recommended_threshold"] < 0.7
