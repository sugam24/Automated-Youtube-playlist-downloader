"""Playlist downloading and metadata extraction using yt-dlp Python API."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable, TypedDict

import yt_dlp


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

class VideoMetadata(TypedDict):
    """Metadata extracted for a single video."""

    title: str
    description: str
    upload_date: str
    url: str


class PlaylistInfo(TypedDict):
    """Lightweight playlist info returned by the extraction phase."""

    title: str
    sanitized_title: str
    total_videos: int
    entries: list[dict[str, Any]]


class PlaylistResult(TypedDict):
    """Result returned after downloading a playlist."""

    playlist_title: str
    output_dir: Path
    videos_dir: Path
    metadata: list[VideoMetadata]
    skipped: int
    failed: list[str]


# ---------------------------------------------------------------------------
# Callback type used to report per-video progress back to the caller
# ---------------------------------------------------------------------------
ProgressCallback = Callable[[dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Replace characters that are unsafe for filenames.

    Args:
        name: Raw string to sanitize.

    Returns:
        A filesystem-safe string.
    """
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", name)
    sanitized = sanitized.strip(". ")
    return sanitized or "Untitled"


def _format_upload_date(raw: str | None) -> str:
    """Convert yt-dlp date string (YYYYMMDD) to readable format.

    Args:
        raw: Date string from yt-dlp, e.g. ``"20240315"``.

    Returns:
        Formatted date like ``"2024-03-15"`` or ``"Unknown"`` on failure.
    """
    if not raw or len(raw) != 8:
        return "Unknown"
    try:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    except (IndexError, TypeError):
        return "Unknown"


def _format_duration(seconds: int | float | None) -> str:
    """Format seconds into a human-readable ``HH:MM:SS`` or ``MM:SS`` string."""
    if not seconds:
        return "Unknown"
    seconds = int(seconds)
    hrs, remainder = divmod(seconds, 3600)
    mins, secs = divmod(remainder, 60)
    if hrs:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def _format_size(size_bytes: int | float | None) -> str:
    """Format bytes into a human-readable string (KB / MB / GB)."""
    if not size_bytes:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _check_video_exists(title: str, videos_dir: Path) -> Path | None:
    """Check if a video with the given title already exists in the directory.
    
    Args:
        title: Video title to search for
        videos_dir: Directory to search in
        
    Returns:
        Path to existing file if found, None otherwise
    """
    if not title:
        return None
        
    sanitized_title = sanitize_filename(title)
    common_extensions = [".mp4", ".webm", ".mkv", ".avi", ".mov", ".m4v"]
    
    for ext in common_extensions:
        potential_file = videos_dir / f"{sanitized_title}{ext}"
        if potential_file.exists():
            return potential_file
            
    # Also check for any file that starts with the sanitized title
    # to handle cases where yt-dlp might have added extra suffixes
    try:
        for file_path in videos_dir.iterdir():
            if file_path.is_file() and file_path.stem.startswith(sanitized_title):
                return file_path
    except (OSError, PermissionError):
        pass
        
    return None


def parse_video_range(range_str: str, total: int) -> list[int]:
    """Parse a human-friendly range string into a sorted list of 0-based indices.

    Accepted formats (1-based input from the user):
        * ``""`` or whitespace → all videos ``[0 .. total-1]``
        * ``"3"`` → single video
        * ``"1-5"`` → inclusive range
        * ``"1,3,7"`` → comma-separated
        * ``"1-3,7,10-12"`` → mixed ranges and singles

    Args:
        range_str: User-provided range string (1-based).
        total: Total number of videos in the playlist.

    Returns:
        Sorted list of **0-based** indices.

    Raises:
        ValueError: If the range string is malformed or out of bounds.
    """
    range_str = range_str.strip()
    if not range_str:
        return list(range(total))

    indices: set[int] = set()
    for part in range_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", maxsplit=1)
            if len(bounds) != 2 or not bounds[0].strip().isdigit() or not bounds[1].strip().isdigit():
                raise ValueError(f"Invalid range segment: '{part}'")
            lo, hi = int(bounds[0].strip()), int(bounds[1].strip())
            if lo < 1 or hi > total or lo > hi:
                raise ValueError(
                    f"Range {lo}-{hi} is out of bounds (playlist has {total} videos)."
                )
            indices.update(range(lo - 1, hi))  # convert to 0-based
        else:
            if not part.isdigit():
                raise ValueError(f"Invalid number: '{part}'")
            num = int(part)
            if num < 1 or num > total:
                raise ValueError(
                    f"Video #{num} is out of bounds (playlist has {total} videos)."
                )
            indices.add(num - 1)

    return sorted(indices)


# ---------------------------------------------------------------------------
# Phase 1: lightweight playlist extraction
# ---------------------------------------------------------------------------

def extract_playlist_info(playlist_url: str) -> PlaylistInfo:
    """Fetch playlist metadata without downloading any video.

    Args:
        playlist_url: Full URL of the YouTube playlist.

    Returns:
        A ``PlaylistInfo`` dict with the playlist title, entry count, and
        flat entry list.
    """
    extract_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(extract_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)

    if info is None:
        raise RuntimeError("Failed to extract playlist information.")

    entries = list(info.get("entries") or [])
    raw_title = info.get("title", "Untitled_Playlist")

    # Construct and return a PlaylistInfo object containing
    # both raw and sanitized titles along with playlist metadata.
    return PlaylistInfo(
        title=raw_title,  # Original playlist title as extracted from source
        sanitized_title=sanitize_filename(raw_title),  
        # Filesystem-safe version of the title (removes/escapes invalid characters)

        total_videos=len(entries),  
        # Total number of videos in the playlist (derived from entries list)

        entries=entries,  
        # List of video metadata objects belonging to the playlist
    )


# ---------------------------------------------------------------------------
# Phase 2: download selected videos with progress reporting
# ---------------------------------------------------------------------------

def download_playlist(
    playlist_url: str,
    playlist_info: PlaylistInfo,
    selected_indices: list[int],
    base_output_dir: str = "downloads",
    on_progress: ProgressCallback | None = None,
) -> PlaylistResult:
    """Download selected videos from a YouTube playlist and extract metadata.

    Args:
        playlist_url: Full URL of the YouTube playlist.
        playlist_info: Pre-fetched ``PlaylistInfo`` from :func:`extract_playlist_info`.
        selected_indices: 0-based indices of videos to download.
        base_output_dir: Root directory for downloads.
        on_progress: Optional callback invoked with a progress dict
            for every yt-dlp progress hook event.

    Returns:
        A ``PlaylistResult`` dict.
    """
    playlist_title = playlist_info["sanitized_title"]

    # -- Prepare directories --------------------------------------------
    output_dir = Path(base_output_dir) / playlist_title
    videos_dir = output_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    metadata: list[VideoMetadata] = []
    failed: list[str] = []
    total_selected = len(selected_indices)

    # Build yt-dlp playlist_items string (1-based, comma-separated)
    items_str = ",".join(str(i + 1) for i in selected_indices)

    # -- Progress hook --------------------------------------------------
    _current_video_title: dict[str, str] = {"title": ""}

    def _progress_hook(d: dict[str, Any]) -> None:
        """Forward yt-dlp download progress to the caller's callback."""
        if on_progress is None:
            return

        status = d.get("status", "")
        info: dict[str, Any] = {"status": status, "video_title": _current_video_title["title"]}

        if status == "downloading":
            info["downloaded_bytes"] = d.get("downloaded_bytes", 0)
            info["total_bytes"] = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            info["speed"] = d.get("speed", 0)
            info["eta"] = d.get("eta", 0)
            pct = d.get("_percent_str", "").strip()
            info["percent_str"] = pct
        elif status == "finished":
            info["filename"] = d.get("filename", "")
            info["total_bytes"] = d.get("total_bytes") or d.get("total_bytes_estimate", 0)

        on_progress(info)

    # -- Download options -----------------------------------------------
    download_opts: dict[str, Any] = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(videos_dir / "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "noplaylist": False,
        "playlist_items": items_str,
        "restrictfilenames": False,
        "writethumbnail": False,
        "progress_hooks": [_progress_hook],
    }

    # -- Download one-by-one for granular reporting ---------------------
    completed = 0
    skipped = 0
    start_time = time.time()

    for seq, idx in enumerate(selected_indices, start=1):
        entry = playlist_info["entries"][idx] if idx < len(playlist_info["entries"]) else None
        entry_title = (entry.get("title") if entry else None) or f"Video #{idx + 1}"
        _current_video_title["title"] = entry_title

        # Check if video already exists
        existing_file = _check_video_exists(entry_title, videos_dir)
        if existing_file:
            # Video already exists, skip download
            skipped += 1
            completed += 1  # Count as completed since we don't need to download it
            
            # Add to metadata anyway since the file exists
            video_meta: VideoMetadata = {
                "title": entry_title,
                "description": "Video already downloaded - skipped",
                "upload_date": "Unknown",
                "url": entry.get("url") or entry.get("webpage_url", "N/A") if entry else "N/A",
            }
            metadata.append(video_meta)
            
            if on_progress:
                on_progress({
                    "status": "complete",
                    "video_title": entry_title,
                    "seq": seq,
                    "total_selected": total_selected,
                    "completed": completed,
                    "remaining": total_selected - completed,
                    "elapsed": time.time() - start_time,
                    "duration": "Unknown",
                    "filesize": _format_size(existing_file.stat().st_size if existing_file.exists() else None),
                    "skipped_existing": True,
                })
            
            continue

        # Notify caller about which video we're starting
        if on_progress:
            on_progress({
                "status": "start",
                "video_title": entry_title,
                "video_index": idx + 1,
                "seq": seq,
                "total_selected": total_selected,
                "completed": completed,
                "remaining": total_selected - completed,
                "elapsed": time.time() - start_time,
            })

        single_opts = {
            **download_opts,
            "playlist_items": str(idx + 1),
        }

        try:
            with yt_dlp.YoutubeDL(single_opts) as ydl:
                result = ydl.extract_info(playlist_url, download=True)

            if result is None:
                failed.append(entry_title)
                skipped += 1
                if on_progress:
                    on_progress({"status": "error", "video_title": entry_title, "error": "No info returned"})
                continue

            # result can be playlist wrapper or single entry
            entries = result.get("entries") or [result]
            downloaded_entry = None
            for e in entries:
                if e is not None:
                    downloaded_entry = e
                    break

            if downloaded_entry is None:
                failed.append(entry_title)
                skipped += 1
                continue

            video_meta: VideoMetadata = {
                "title": downloaded_entry.get("title", "Untitled"),
                "description": downloaded_entry.get("description", "No description available."),
                "upload_date": _format_upload_date(downloaded_entry.get("upload_date")),
                "url": downloaded_entry.get("webpage_url") or downloaded_entry.get("url", "N/A"),
            }
            metadata.append(video_meta)
            completed += 1

            if on_progress:
                on_progress({
                    "status": "complete",
                    "video_title": video_meta["title"],
                    "seq": seq,
                    "total_selected": total_selected,
                    "completed": completed,
                    "remaining": total_selected - completed,
                    "elapsed": time.time() - start_time,
                    "duration": _format_duration(downloaded_entry.get("duration")),
                    "filesize": _format_size(downloaded_entry.get("filesize") or downloaded_entry.get("filesize_approx")),
                })

        except Exception as exc:
            failed.append(entry_title)
            skipped += 1
            if on_progress:
                on_progress({"status": "error", "video_title": entry_title, "error": str(exc)})

    return PlaylistResult(
        playlist_title=playlist_title,
        output_dir=output_dir,
        videos_dir=videos_dir,
        metadata=metadata,
        skipped=skipped,
        failed=failed,
    )

