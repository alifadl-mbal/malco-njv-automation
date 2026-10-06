"""Pure-Python, layout-preserving PDF text extraction.

Replaces the external `pdftotext -layout` binary (Poppler) so the engine runs
with nothing but `uv sync` — no system tools to install on Windows.

Why a custom renderer: the statement parser distinguishes a Debit from a Credit
by the COLUMN the amount sits in, so the text must preserve horizontal
position. pdfplumber's own `layout=True` collapses runs of whitespace between
columns, which loses exactly that signal. Here each phrase is placed on a
character grid derived from its x-coordinate, which keeps every column aligned
with its header — the property the parser relies on.
"""
from __future__ import annotations

from pathlib import Path

# Points of horizontal space represented by one output character.
PT_PER_CHAR = 3.0
# Words whose vertical midpoints are within this many points share a line.
LINE_TOLERANCE = 2.5


def _phrases(line_words: list[dict]) -> list[tuple[float, str]]:
    """Merge words separated by an ordinary space into one phrase.

    Without this, placing every word at its own column inserts stray gaps
    inside phrases ("USD   Transactions") and breaks phrase matching. Column
    structure is still preserved, because each PHRASE keeps its own x0.
    """
    out: list[tuple[float, str]] = []
    start_x: float | None = None
    parts: list[str] = []
    prev_end = 0.0
    prev_gap_limit = 0.0

    for w in sorted(line_words, key=lambda w: w["x0"]):
        gap_limit = max(1.5, 0.45 * (w["bottom"] - w["top"]))
        if start_x is None:
            start_x, parts, prev_end = w["x0"], [w["text"]], w["x1"]
        elif w["x0"] - prev_end <= max(gap_limit, prev_gap_limit):
            parts.append(w["text"])
            prev_end = w["x1"]
        else:
            out.append((start_x, " ".join(parts)))
            start_x, parts, prev_end = w["x0"], [w["text"]], w["x1"]
        prev_gap_limit = gap_limit

    if start_x is not None:
        out.append((start_x, " ".join(parts)))
    return out


def _render_page(words: list[dict]) -> list[str]:
    """Place phrases on a character grid, one string per visual line."""
    lines: list[tuple[float, list[dict]]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        mid = (w["top"] + w["bottom"]) / 2
        for ref, bucket in lines:
            if abs(mid - ref) <= LINE_TOLERANCE:
                bucket.append(w)
                break
        else:
            lines.append((mid, [w]))

    out: list[str] = []
    for _, bucket in lines:
        row: list[str] = []
        for x0, text in _phrases(bucket):
            col = int(round(x0 / PT_PER_CHAR))
            if col < len(row):                      # overlap: keep readable
                col = len(row) + 1
            row.extend(" " * (col - len(row)))
            row.extend(text)
        out.append("".join(row).rstrip())
    return out


def pdf_text(path: str | Path) -> str:
    """Extract layout-preserved text from a PDF. Pure Python, no binaries."""
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(
                use_text_flow=False, keep_blank_chars=False,
                x_tolerance=1.5, y_tolerance=2.0,
            )
            pages.append("\n".join(_render_page(words)))
    return "\n".join(pages)
