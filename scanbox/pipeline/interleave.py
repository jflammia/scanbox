"""Two-pass duplex page interleaving.

When scanning duplex on a simplex-only ADF:
  Pass 1 (fronts): [F1, F2, F3, ..., Fn] — face up
  Pass 2 (backs):  [Bn, Bn-1, ..., B1]   — flipped stack, so reversed

This module interleaves them into correct order:
  [F1, B1, F2, B2, ..., Fn, Bn]
"""

from pathlib import Path

import pikepdf


def interleave_pages(
    fronts_path: Path,
    backs_path: Path | None,
    output_path: Path,
) -> Path:
    """Interleave front and back page scans into a single PDF.

    Args:
        fronts_path: PDF of front-side pages in scan order.
        backs_path: PDF of back-side pages in scan order (reversed from physical).
                    None if single-sided batch (fronts copied as-is).
        output_path: Where to write the interleaved PDF.

    Returns:
        output_path after writing.

    Raises:
        ValueError: If there are more back pages than front pages.
    """
    fronts_pdf = pikepdf.Pdf.open(fronts_path)
    n_fronts = len(fronts_pdf.pages)

    if backs_path is None:
        # Single-sided: just copy fronts
        fronts_pdf.save(output_path)
        return output_path

    backs_pdf = pikepdf.Pdf.open(backs_path)
    n_backs = len(backs_pdf.pages)

    if n_backs > n_fronts:
        raise ValueError(
            f"Got more back pages ({n_backs}) than front pages ({n_fronts}). "
            f"Did a page get stuck in the scanner?"
        )

    # Reverse the backs to undo the physical flip
    back_pages = list(reversed(range(n_backs)))

    # Interleave: F1, B1, F2, B2, ...
    result = pikepdf.Pdf.new()
    for i in range(n_fronts):
        result.pages.append(fronts_pdf.pages[i])
        if i < n_backs:
            result.pages.append(backs_pdf.pages[back_pages[i]])

    result.save(output_path)
    return output_path
