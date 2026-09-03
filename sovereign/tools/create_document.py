"""
create_document() agent tool.

Milestone 3 gives this a genuinely working (if simple) DOCX writer — a
title plus heading/body sections — so the full tool-dispatch loop is
real end to end today. The richer "Approval Note" template (structured
sections tuned for the industrial workflow, formatted evidence
citations) is Milestone 4 (feat/docx-generation); this is a working
foundation for that, not the final version.
"""

from pathlib import Path

import docx


class DocumentCreationError(Exception):
    pass


def create_document(title: str, sections, output_dir: str) -> str:
    """sections: list of {"heading": str, "body": str} dicts, in order."""
    title = (title or "").strip()
    if not title:
        raise DocumentCreationError("A title is required")
    if not sections:
        raise DocumentCreationError("At least one section is required")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip()
    safe_name = safe_name or "document"
    out_path = out_dir / f"{safe_name}.docx"

    d = docx.Document()
    d.add_heading(title, level=0)
    written_sections = 0
    for section in sections:
        heading = (section.get("heading") or "").strip()
        body = (section.get("body") or "").strip()
        if not heading and not body:
            continue
        if heading:
            d.add_heading(heading, level=1)
        if body:
            d.add_paragraph(body)
        written_sections += 1

    if written_sections == 0:
        raise DocumentCreationError("Every section was empty — nothing to write")

    d.save(str(out_path))
    return f"Created {out_path.name} with {written_sections} section(s) at {out_path}"
