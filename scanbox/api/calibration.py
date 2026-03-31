"""Confidence calibration analysis for AI splitting results."""

import json
import math
from pathlib import Path

from fastapi import APIRouter

from scanbox.config import Config

router = APIRouter(tags=["calibration"])

THRESHOLD_LEVELS = [0.5, 0.6, 0.7, 0.8, 0.9]


def compute_calibration_data(
    batch_dirs: list[Path],
    current_threshold: float = 0.7,
) -> dict:
    """Analyze confidence scores from splits.json files across batch directories.

    Args:
        batch_dirs: List of batch directories that may contain splits.json.
        current_threshold: The currently configured confidence threshold.

    Returns:
        Dict with scores, distribution, percentiles, threshold impact, and recommendation.
    """
    scores: list[float] = []

    for batch_dir in batch_dirs:
        splits_path = batch_dir / "splits.json"
        if not splits_path.exists():
            continue
        try:
            splits = json.loads(splits_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for doc in splits:
            conf = doc.get("confidence")
            if conf is not None:
                scores.append(float(conf))

    if not scores:
        return {
            "total_scores": 0,
            "scores": [],
            "distribution": {},
            "percentiles": {},
            "threshold_impact": {},
            "current_threshold": current_threshold,
            "recommended_threshold": current_threshold,
        }

    scores.sort()

    # Distribution: 0.1-wide buckets
    distribution: dict[str, int] = {}
    for s in scores:
        bucket_low = math.floor(s * 10) / 10
        bucket_high = bucket_low + 0.1
        # Clamp to 0.0-1.0 range
        bucket_low = max(0.0, bucket_low)
        bucket_high = min(1.0, bucket_high)
        label = f"{bucket_low:.1f}-{bucket_high:.1f}"
        distribution[label] = distribution.get(label, 0) + 1

    # Percentiles
    def percentile(data: list[float], p: float) -> float:
        k = (len(data) - 1) * (p / 100)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[int(k)]
        return data[f] * (c - k) + data[c] * (k - f)

    percentiles = {
        "p25": round(percentile(scores, 25), 3),
        "p50": round(percentile(scores, 50), 3),
        "p75": round(percentile(scores, 75), 3),
    }

    # Threshold impact analysis
    total = len(scores)
    threshold_impact: dict[str, dict] = {}
    for t in THRESHOLD_LEVELS:
        flagged = sum(1 for s in scores if s < t)
        threshold_impact[str(t)] = {
            "threshold": t,
            "flagged": flagged,
            "passed": total - flagged,
            "flagged_pct": round(flagged / total * 100, 1),
        }

    # Recommendation: use p25 as the recommended threshold, clamped to [0.3, 0.9]
    # This means ~25% of documents would be flagged for review
    recommended = round(max(0.3, min(0.9, percentiles["p25"])), 2)

    return {
        "total_scores": total,
        "scores": scores,
        "distribution": distribution,
        "percentiles": percentiles,
        "threshold_impact": threshold_impact,
        "current_threshold": current_threshold,
        "recommended_threshold": recommended,
    }


@router.get("/api/pipeline/calibration")
async def get_calibration_data():
    """Analyze confidence scores across all batches to recommend threshold tuning.

    Scans all batches that have splits.json and collects confidence data.
    Returns distribution, current threshold, and impact analysis.
    """
    from scanbox.main import get_db

    cfg = Config()
    db = get_db()

    sessions = await db.list_sessions()
    batch_dirs: list[Path] = []

    for session in sessions:
        batches = await db.list_batches(session["id"])
        for batch in batches:
            batch_dir = cfg.sessions_dir / session["id"] / "batches" / batch["id"]
            batch_dirs.append(batch_dir)

    result = compute_calibration_data(
        batch_dirs, current_threshold=cfg.PIPELINE_CONFIDENCE_THRESHOLD
    )

    # Remove raw scores from API response (could be large)
    api_result = {k: v for k, v in result.items() if k != "scores"}
    api_result["batch_count"] = len(batch_dirs)

    return api_result
