"""Generate a structured PDF containing video descriptions from a playlist."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.downloader import VideoMetadata


def _build_styles() -> dict[str, ParagraphStyle]:
    """Create reusable paragraph styles for the PDF.

    Returns:
        A mapping of style names to ``ParagraphStyle`` objects.
    """
    base = getSampleStyleSheet()

    styles: dict[str, ParagraphStyle] = {
        "playlist_title": ParagraphStyle(
            "PlaylistTitle",
            parent=base["Title"],
            fontSize=24,
            leading=30,
            spaceAfter=20,
            alignment=1,  # centre
        ),
        "video_title": ParagraphStyle(
            "VideoTitle",
            parent=base["Heading2"],
            fontSize=14,
            leading=18,
            spaceAfter=6,
            textColor="#1a1a1a",
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            spaceAfter=4,
            textColor="#555555",
        ),
        "description": ParagraphStyle(
            "Description",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            spaceAfter=12,
            wordWrap="CJK",  # improves wrapping for long unbroken strings
        ),
    }
    return styles


def _escape(text: str) -> str:
    """Escape XML-sensitive characters for ReportLab Paragraphs.

    Args:
        text: Raw text that may contain ``&``, ``<``, or ``>``.

    Returns:
        Escaped text safe for use inside ``Paragraph``.
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def generate_pdf(
    playlist_title: str,
    metadata: list[VideoMetadata],
    output_path: str | Path,
) -> Path:
    """Create a single PDF file containing all video descriptions.

    Layout:
        * **Page 1** – playlist title as a centred heading.
        * **Per video** – bold title, URL, upload date, description,
          followed by a horizontal rule separator.

    Args:
        playlist_title: Human-readable playlist name.
        metadata: List of ``VideoMetadata`` dicts (one per video).
        output_path: Destination file path for the PDF.

    Returns:
        The ``Path`` to the written PDF file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    styles = _build_styles()
    story: list = []

    # -- Cover heading --------------------------------------------------
    story.append(Paragraph(_escape(playlist_title), styles["playlist_title"]))
    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            f"{len(metadata)} video(s) in this playlist",
            styles["meta"],
        )
    )
    story.append(Spacer(1, 30))

    # -- Per-video sections ---------------------------------------------
    for idx, video in enumerate(metadata, start=1):
        # Title
        title_text = f"{idx}. {_escape(video['title'])}"
        story.append(Paragraph(f"<b>{title_text}</b>", styles["video_title"]))

        # URL
        url = _escape(video["url"])
        story.append(
            Paragraph(
                f'<b>URL:</b> <a href="{url}" color="blue">{url}</a>',
                styles["meta"],
            )
        )

        # Upload date
        story.append(
            Paragraph(
                f"<b>Upload Date:</b> {_escape(video['upload_date'])}",
                styles["meta"],
            )
        )

        story.append(Spacer(1, 6))

        # Description
        description = video.get("description") or "No description available."
        # Preserve line-breaks in the original description
        desc_html = _escape(description).replace("\n", "<br/>")
        story.append(Paragraph(desc_html, styles["description"]))

        story.append(Spacer(1, 10))

        # Separator between videos
        story.append(
            HRFlowable(
                width="100%",
                thickness=0.5,
                color="#cccccc",
                spaceAfter=14,
                spaceBefore=4,
            )
        )

    doc.build(story)
    return output_path
