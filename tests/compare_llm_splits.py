"""Compare AI splitting results across different LLM configurations.

Usage:
    # Compare two models on the minimal pile:
    python -m tests.compare_llm_splits 06-minimal-quick \
        --model openai/mlx-community/Qwen3.5-35B-A3B-4bit \
        --model anthropic/claude-haiku-4-5-20251001

    # Just show the manifest (expected documents):
    python -m tests.compare_llm_splits 06-minimal-quick --manifest-only

Runs interleave + blank removal + OCR once (shared), then the splitting
stage separately for each model. Prints a comparison table.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

SUITE_DIR = Path(__file__).parent / "fixtures" / "test_suite"


def _load_manifest(pile_name: str) -> dict:
    manifest_path = SUITE_DIR / pile_name / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: pile '{pile_name}' not found in {SUITE_DIR}")
        print(f"Available piles: {', '.join(sorted(p.name for p in SUITE_DIR.iterdir()))}")
        sys.exit(1)
    return json.loads(manifest_path.read_text())


def _print_manifest(manifest: dict) -> None:
    print(f"\nPatient: {manifest['patient']['name']}")
    print(f"Sheets: {manifest['num_sheets']}, Logical pages: {manifest['num_logical_pages']}")
    print(f"Expected documents: {len(manifest['documents'])}")
    print()
    for i, doc in enumerate(manifest["documents"], 1):
        sided = "single-sided" if doc["single_sided"] else "double-sided"
        print(f"  {i}. {doc['name']} ({doc['pages']} pages, {sided})")
        print(f"     {doc['description']}")
    print()


def _prepare_batch(pile_name: str, work_dir: Path) -> tuple[dict[int, str], str]:
    """Run interleave + blank removal + OCR, return page texts and person name."""
    from scanbox.pipeline.blank_detect import remove_blank_pages
    from scanbox.pipeline.interleave import interleave_pages
    from scanbox.pipeline.ocr import run_ocr

    pile_dir = SUITE_DIR / pile_name
    manifest = _load_manifest(pile_name)
    person_name = manifest["patient"]["name"]

    work_dir.mkdir(parents=True, exist_ok=True)

    fronts_path = pile_dir / "fronts.pdf"
    backs_path = pile_dir / "backs.pdf"
    combined_path = work_dir / "combined.pdf"
    cleaned_path = work_dir / "cleaned.pdf"
    ocr_path = work_dir / "ocr.pdf"
    text_path = work_dir / "text_by_page.json"

    # Check for cached OCR results
    if text_path.exists():
        print("  Using cached OCR results")
        page_texts_raw = json.loads(text_path.read_text())
        return {int(k): v for k, v in page_texts_raw.items()}, person_name

    print("  Interleaving pages...")
    interleave_pages(
        fronts_path,
        backs_path if backs_path.exists() else None,
        combined_path,
    )

    print("  Removing blank pages...")
    remove_blank_pages(combined_path, cleaned_path, threshold=0.01)

    print("  Running OCR...")
    run_ocr(cleaned_path, ocr_path, text_path)

    page_texts_raw = json.loads(text_path.read_text())
    return {int(k): v for k, v in page_texts_raw.items()}, person_name


async def _run_split(model: str, page_texts: dict[int, str], person_name: str) -> dict:
    """Run splitting with a single model, return result dict."""
    from scanbox.pipeline.splitter import split_documents

    try:
        docs = await split_documents(page_texts, person_name, model_override=model)
        return {
            "status": "ok",
            "document_count": len(docs),
            "documents": [
                {
                    "start_page": d.start_page,
                    "end_page": d.end_page,
                    "document_type": d.document_type,
                    "description": d.description,
                    "confidence": d.confidence,
                }
                for d in docs
            ],
            "avg_confidence": round(sum(d.confidence for d in docs) / len(docs), 3) if docs else 0,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "document_count": 0,
            "documents": [],
            "avg_confidence": 0,
        }


def _print_comparison(
    models: list[str],
    results: dict[str, dict],
    manifest: dict,
    total_pages: int,
) -> None:
    expected_count = len(manifest["documents"])

    print(f"\n{'=' * 80}")
    print(f"COMPARISON: {total_pages} pages, {expected_count} expected documents")
    print(f"{'=' * 80}")

    # Summary table
    print(f"\n{'Model':<50} {'Docs':>5} {'Avg Conf':>10} {'Match':>6}")
    print("-" * 75)
    for model in models:
        r = results[model]
        if r["status"] == "error":
            print(f"{model:<50} {'ERROR':>5} {'':>10} {'':>6}")
            continue
        match = "YES" if r["document_count"] == expected_count else "no"
        print(f"{model:<50} {r['document_count']:>5} {r['avg_confidence']:>10.3f} {match:>6}")

    # Detail per model
    for model in models:
        r = results[model]
        print(f"\n--- {model} ---")
        if r["status"] == "error":
            print(f"  Error: {r['error']}")
            continue
        for i, doc in enumerate(r["documents"], 1):
            pages = f"p{doc['start_page']}-{doc['end_page']}"
            print(
                f"  {i}. [{pages}] {doc['document_type']}: "
                f"{doc['description']} (conf: {doc['confidence']:.2f})"
            )

    print()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Compare LLM splitting results")
    parser.add_argument("pile", help="Test pile name from tests/fixtures/test_suite/")
    parser.add_argument(
        "--model", action="append", dest="models", help="LLM model ID (repeat for multiple)"
    )
    parser.add_argument(
        "--manifest-only", action="store_true", help="Only show expected documents, don't run"
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Working directory for intermediate files (default: /tmp/scanbox-compare/<pile>)",
    )
    args = parser.parse_args()

    manifest = _load_manifest(args.pile)
    _print_manifest(manifest)

    if args.manifest_only:
        return

    if not args.models or len(args.models) < 1:
        print("Error: at least one --model is required (unless using --manifest-only)")
        sys.exit(1)

    work_dir = args.work_dir or Path("/tmp/scanbox-compare") / args.pile

    print("Preparing batch (shared across all models)...")
    page_texts, person_name = _prepare_batch(args.pile, work_dir)
    total_pages = len(page_texts)
    print(f"  {total_pages} pages ready for splitting\n")

    results = {}
    for model in args.models:
        print(f"Splitting with {model}...")
        results[model] = await _run_split(model, page_texts, person_name)
        if results[model]["status"] == "ok":
            print(f"  Found {results[model]['document_count']} documents")
        else:
            print(f"  Error: {results[model]['error']}")

    _print_comparison(args.models, results, manifest, total_pages)


if __name__ == "__main__":
    asyncio.run(main())
