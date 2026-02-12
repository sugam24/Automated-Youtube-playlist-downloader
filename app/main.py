"""Interactive CLI entry-point for the YouTube playlist downloader."""

from __future__ import annotations

import sys
import time
from typing import Any

from app.downloader import (
    PlaylistInfo,
    download_playlist,
    extract_playlist_info,
    parse_video_range,
)
from app.pdf_generator import generate_pdf


# ---------------------------------------------------------------------------
# Pretty-printing helpers
# ---------------------------------------------------------------------------

_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _banner() -> None:
    """Print a startup banner."""
    print(f"\n{_BOLD}{_CYAN}{'='*60}")
    print(f"   ▶  YouTube Playlist Downloader")
    print(f"{'='*60}{_RESET}\n")


def _section(title: str) -> None:
    print(f"\n{_BOLD}{_CYAN}── {title} {'─'*(55 - len(title))}{_RESET}")


def _info(label: str, value: str) -> None:
    print(f"  {_DIM}{label:<18}{_RESET} {value}")


def _success(msg: str) -> None:
    print(f"  {_GREEN}✔{_RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"  {_YELLOW}⚠{_RESET} {msg}")


def _error(msg: str) -> None:
    print(f"  {_RED}✖{_RESET} {msg}")


def _format_elapsed(secs: float) -> str:
    """Format seconds into ``Xm Ys`` or ``Ys``."""
    m, s = divmod(int(secs), 60)
    return f"{m}m {s}s" if m else f"{s}s"


def _progress_bar(current: int, total: int, width: int = 30) -> str:
    """Build a simple ASCII progress bar ``[████░░░░░░] 40%``."""
    pct = current / total if total else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct*100:5.1f}%"


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

def _prompt_url() -> str:
    """Ask the user for a YouTube playlist URL."""
    while True:
        url = input(f"  {_BOLD}Enter playlist URL:{_RESET} ").strip()
        if url:
            return url
        _warn("URL cannot be empty. Please try again.")


def _prompt_range(playlist_info: PlaylistInfo) -> list[int]:
    """Show playlist contents and ask for an optional video range.

    Displays all videos with their indices so the user can choose.
    """
    total = playlist_info["total_videos"]
    entries = playlist_info["entries"]

    _section("Playlist contents")
    print()
    for i, entry in enumerate(entries, start=1):
        title = (entry.get("title") if entry else None) or "Untitled"
        duration = entry.get("duration") if entry else None
        dur_str = ""
        if duration:
            m, s = divmod(int(duration), 60)
            dur_str = f" {_DIM}({m}:{s:02d}){_RESET}"
        print(f"    {_BOLD}{i:>3}.{_RESET} {title}{dur_str}")

    print(f"\n  {_DIM}Total: {total} video(s){_RESET}")
    print()
    print(f"  {_DIM}Range formats:  5  |  1-10  |  1,3,7  |  1-3,8,12-15{_RESET}")
    print(f"  {_DIM}Leave empty to download ALL videos.{_RESET}")
    print()

    while True:
        range_str = input(f"  {_BOLD}Enter video range [all]:{_RESET} ").strip()
        try:
            indices = parse_video_range(range_str, total)
            return indices
        except ValueError as exc:
            _warn(str(exc))


def _prompt_output_dir() -> str:
    """Ask for an output directory (default: downloads)."""
    default = "downloads"
    raw = input(f"  {_BOLD}Output directory [{default}]:{_RESET} ").strip()
    return raw or default


# ---------------------------------------------------------------------------
# Progress callback (called from downloader)
# ---------------------------------------------------------------------------

def _make_progress_callback() -> callable:
    """Return a closure that pretty-prints download progress."""

    last_line_len: dict[str, int] = {"n": 0}

    def _clear_line() -> None:
        sys.stdout.write("\r" + " " * last_line_len["n"] + "\r")
        sys.stdout.flush()

    def callback(info: dict[str, Any]) -> None:
        status = info.get("status", "")

        if status == "start":
            _clear_line()
            seq = info["seq"]
            total = info["total_selected"]
            completed = info["completed"]
            remaining = info["remaining"]
            title = info["video_title"]
            elapsed = _format_elapsed(info.get("elapsed", 0))

            header = _progress_bar(completed, total)
            print(f"\n  {header}  {_DIM}Elapsed: {elapsed}{_RESET}")
            print(
                f"  {_CYAN}▶ [{seq}/{total}]{_RESET} {_BOLD}{title}{_RESET}"
                f"  {_DIM}(done: {completed} | left: {remaining}){_RESET}"
            )

        elif status == "downloading":
            pct = info.get("percent_str", "??%")
            speed = info.get("speed")
            speed_str = f"{speed/1024/1024:.1f} MB/s" if speed else "-- MB/s"
            eta = info.get("eta")
            eta_str = f"{eta}s" if eta else "--"
            line = f"    ↓  {pct}  at {speed_str}  ETA {eta_str}"
            _clear_line()
            sys.stdout.write(line)
            sys.stdout.flush()
            last_line_len["n"] = len(line)

        elif status == "finished":
            _clear_line()
            total_bytes = info.get("total_bytes", 0)
            if total_bytes:
                size_mb = total_bytes / 1024 / 1024
                print(f"    ↓  Merging … ({size_mb:.1f} MB downloaded)")
            else:
                print(f"    ↓  Merging …")

        elif status == "complete":
            _clear_line()
            title = info["video_title"]
            dur = info.get("duration", "?")
            size = info.get("filesize", "?")
            _success(
                f"Saved: {_BOLD}{title}{_RESET}"
                f"  {_DIM}[{dur} | {size}]{_RESET}"
            )

        elif status == "error":
            _clear_line()
            _error(f"Failed: {info.get('video_title', '?')} — {info.get('error', 'unknown')}")

    return callback


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main() -> None:
    """Interactive flow: prompt → extract → select → download → PDF."""
    _banner()

    # -- Step 1: collect inputs -----------------------------------------
    _section("Configuration")
    print()
    url = _prompt_url()
    output_dir = _prompt_output_dir()

    # -- Step 2: extract playlist info ----------------------------------
    _section("Fetching playlist info")
    print()
    try:
        playlist_info = extract_playlist_info(url)
    except Exception as exc:
        _error(f"Could not fetch playlist: {exc}")
        sys.exit(1)

    _info("Playlist", playlist_info["title"])
    _info("Videos found", str(playlist_info["total_videos"]))

    if playlist_info["total_videos"] == 0:
        _warn("Playlist is empty. Nothing to download.")
        return

    # -- Step 3: select range -------------------------------------------
    selected = _prompt_range(playlist_info)
    count = len(selected)
    action = "all" if count == playlist_info["total_videos"] else f"{count} selected"
    _info("Downloading", f"{count} video(s) ({action})")

    # -- Confirm --------------------------------------------------------
    print()
    confirm = input(f"  {_BOLD}Proceed? [Y/n]:{_RESET} ").strip().lower()
    if confirm and confirm not in ("y", "yes"):
        print("\n  Aborted.")
        return

    # -- Step 4: download -----------------------------------------------
    _section(f"Downloading {count} video(s)")
    progress_cb = _make_progress_callback()
    start = time.time()

    try:
        result = download_playlist(
            playlist_url=url,
            playlist_info=playlist_info,
            selected_indices=selected,
            base_output_dir=output_dir,
            on_progress=progress_cb,
        )
    except Exception as exc:
        _error(f"Download failed: {exc}")
        sys.exit(1)

    elapsed = time.time() - start

    # -- Summary --------------------------------------------------------
    _section("Download summary")
    print()
    _info("Playlist", result["playlist_title"])
    _info("Successful", str(len(result["metadata"])))
    _info("Skipped/Failed", str(result["skipped"]))
    _info("Time", _format_elapsed(elapsed))
    _info("Videos dir", str(result["videos_dir"]))

    if result["failed"]:
        print()
        _warn("Failed videos:")
        for title in result["failed"]:
            print(f"      – {title}")

    if not result["metadata"]:
        print()
        _warn("No video metadata collected — skipping PDF generation.")
        return

    # -- Step 5: PDF generation -----------------------------------------
    _section("Generating PDF")
    print()
    pdf_filename = f"{result['playlist_title']}_descriptions.pdf"
    pdf_path = result["output_dir"] / pdf_filename

    try:
        written = generate_pdf(result["playlist_title"], result["metadata"], pdf_path)
        _success(f"PDF saved: {written}")
    except Exception as exc:
        _error(f"PDF generation failed: {exc}")
        sys.exit(1)

    # -- Done -----------------------------------------------------------
    print(f"\n{_BOLD}{_GREEN}{'='*60}")
    print(f"   ✔  All done!")
    print(f"{'='*60}{_RESET}\n")


if __name__ == "__main__":
    main()

