"""Analyze AI splitting confidence across test piles to calibrate thresholds.

Usage:
    python -m tests.calibrate_confidence                    # analyze all completed piles
    python -m tests.calibrate_confidence --threshold 0.5    # show impact of changing threshold
"""

import argparse
import json
import sys
from pathlib import Path

from scanbox.api.calibration import compute_calibration_data

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SUITE_DIR = FIXTURES_DIR / "test_suite"


def find_batch_dirs() -> list[Path]:
    """Find all directories containing splits.json in the test suite and fixture areas."""
    dirs: list[Path] = []

    # Look in test suite piles
    if SUITE_DIR.exists():
        for pile_dir in sorted(SUITE_DIR.iterdir()):
            if pile_dir.is_dir() and (pile_dir / "splits.json").exists():
                dirs.append(pile_dir)

    # Also look in any temp/output directories that may have batch data
    data_dir = FIXTURES_DIR / "batches"
    if data_dir.exists():
        for batch_dir in sorted(data_dir.iterdir()):
            if batch_dir.is_dir() and (batch_dir / "splits.json").exists():
                dirs.append(batch_dir)

    return dirs


def print_report(result: dict, threshold_override: float | None = None) -> None:
    """Print a human-readable calibration report."""
    print("=" * 60)
    print("  Confidence Calibration Report")
    print("=" * 60)
    print()

    if result["total_scores"] == 0:
        print("  No confidence scores found.")
        print("  Run the pipeline on some test piles first.")
        print()
        return

    print(f"  Total documents analyzed: {result['total_scores']}")
    print(f"  Current threshold:        {result['current_threshold']}")
    print(f"  Recommended threshold:    {result['recommended_threshold']}")
    print()

    # Percentiles
    p = result["percentiles"]
    print("  Percentiles:")
    print(f"    25th: {p['p25']:.3f}")
    print(f"    50th: {p['p50']:.3f}  (median)")
    print(f"    75th: {p['p75']:.3f}")
    print()

    # Distribution
    print("  Score Distribution:")
    dist = result["distribution"]
    for bucket in sorted(dist.keys()):
        count = dist[bucket]
        bar = "#" * count
        print(f"    {bucket}: {bar} ({count})")
    print()

    # Threshold impact
    print("  Threshold Impact Analysis:")
    print(f"    {'Threshold':>10}  {'Flagged':>8}  {'Passed':>8}  {'% Flagged':>10}")
    print(f"    {'─' * 10}  {'─' * 8}  {'─' * 8}  {'─' * 10}")
    for t_str, impact in sorted(result["threshold_impact"].items()):
        marker = " <-- current" if float(t_str) == result["current_threshold"] else ""
        if threshold_override and float(t_str) == threshold_override:
            marker = " <-- proposed"
        print(
            f"    {impact['threshold']:>10.1f}  "
            f"{impact['flagged']:>8}  "
            f"{impact['passed']:>8}  "
            f"{impact['flagged_pct']:>9.1f}%{marker}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze AI splitting confidence to calibrate thresholds."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Show impact of a specific threshold value.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted report.",
    )
    args = parser.parse_args()

    batch_dirs = find_batch_dirs()

    if not batch_dirs:
        print("No batch directories with splits.json found.", file=sys.stderr)
        print(f"Searched: {SUITE_DIR}", file=sys.stderr)
        sys.exit(1)

    current_threshold = args.threshold if args.threshold else 0.7
    result = compute_calibration_data(batch_dirs, current_threshold=current_threshold)

    if args.json:
        # Remove scores list for cleaner output
        output = {k: v for k, v in result.items() if k != "scores"}
        print(json.dumps(output, indent=2))
    else:
        print_report(result, threshold_override=args.threshold)


if __name__ == "__main__":
    main()
