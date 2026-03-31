"""Test that CSS classes used in templates are defined in app.css."""

import re
from pathlib import Path

SKIP_TOKENS = {
    "if",
    "else",
    "endif",
    "for",
    "endfor",
    "not",
    "in",
    "and",
    "or",
    "step",
    "completed",
    "step1Done",
    "step2Done",
    "current_step",
    "doc.confidence",
    "doc.date_of_service",
    "true",
    "false",
    "i",
    ":",
    "is",
    "none",
    "selectedPage",
    "page",
    "toast.type",
    "!toast.type",
    "excluded",
    "!excluded",
    "stage_key",
}


def _extract_defined_classes(css_text: str) -> set[str]:
    """Extract class names defined in CSS."""
    classes = set()
    for m in re.finditer(r"\.([\w\\:./\[\]-]+)\s*[{,>]", css_text):
        raw = m.group(1)
        # Unescape Tailwind notation
        raw = raw.replace("\\:", ":").replace("\\[", "[").replace("\\]", "]")
        raw = raw.replace("\\/", "/").replace("\\.", ".")
        classes.add(raw)
        # For pseudo-class variants like "hover:bg-brand-700:hover",
        # register just the Tailwind class name "hover:bg-brand-700"
        # by stripping the trailing CSS pseudo-class
        parts = raw.split(":")
        if len(parts) >= 2:
            # Register all prefix combinations: "hover:bg-brand-700"
            for i in range(1, len(parts)):
                classes.add(":".join(parts[:i]))
            classes.add(parts[-1])
    return classes


def _extract_used_classes(html_text: str) -> set[str]:
    """Extract class names used in HTML class attributes."""
    classes = set()
    for m in re.finditer(r'class="([^"]*)"', html_text):
        for token in m.group(1).split():
            # Skip Jinja2/Alpine expressions
            if any(c in token for c in "{}%()=<>|?"):
                continue
            if token in SKIP_TOKENS:
                continue
            # Skip quoted strings that leaked from :class bindings
            if "'" in token or '"' in token:
                continue
            # Skip numeric comparisons
            if re.match(r"^[\d.]+$", token):
                continue
            # Skip two-char operators
            if token in ("||", "&&", ">=", "<=", "==", "!=", "===", "!==", "}}"):
                continue
            classes.add(token)
    return classes


def test_all_template_classes_defined_in_css():
    root = Path(__file__).resolve().parent.parent.parent
    css_path = root / "static" / "css" / "app.css"
    templates_dir = root / "scanbox" / "templates"

    defined = _extract_defined_classes(css_path.read_text())
    missing_by_file: dict[str, list[str]] = {}

    for tmpl in sorted(templates_dir.glob("*.html")):
        used = _extract_used_classes(tmpl.read_text())
        missing = sorted(used - defined)
        if missing:
            missing_by_file[tmpl.name] = missing

    if missing_by_file:
        lines = ["CSS classes used in templates but not defined in app.css:"]
        for fname, classes in missing_by_file.items():
            for cls in classes:
                lines.append(f"  {cls:<35} ({fname})")
        raise AssertionError("\n".join(lines))
