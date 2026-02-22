# YouTube Playlist Downloader

A command-line tool to download YouTube playlists with support for selective video ranges and PDF generation.

## Features

- Download entire YouTube playlists or select specific videos by range
- Extract playlist information including video titles and durations
- Generate PDF reports of downloaded content
- Interactive CLI interface with progress tracking
- Support for environment configuration via `.env` file

## Requirements

- Python 3.13 or higher
- `uv` package manager (or pip as alternative)

## Installation

### Using `uv` (Recommended)

1. Clone or navigate to the project directory:

```bash
cd /path/to/playlist
```

2. Create and activate a virtual environment:

```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
uv sync
```

### Using pip

```bash
pip install -e .
```

## Usage

### Run the main application

```bash
uv run main.py
```

or if using pip:

```bash
python main.py
```

### Run as installed command (if installed via pip)

```bash
yt-downloader
```

### Running with activated virtual environment

```bash
source .venv/bin/activate
python main.py
```

## Project Structure

```
playlist/
├── main.py              # Entry point for the application
├── app/
│   ├── main.py         # Interactive CLI interface
│   ├── downloader.py   # YouTube playlist downloading logic
│   ├── pdf_generator.py # PDF report generation
│   └── __init__.py
├── downloads/          # Directory where downloaded videos will be saved
├── pyproject.toml      # Project configuration and dependencies
└── README.md           # This file
```

## Configuration

Create a `.env` file in the project root to configure environment variables:

```env
# Add any environment-specific settings here
```

## Dependencies

- **python-dotenv** - Environment variable management
- **reportlab** - PDF generation
- **requests** - HTTP requests
- **yt-dlp** - YouTube video downloading

## Troubleshooting

### Module not found errors

Make sure the virtual environment is activated and dependencies are installed:

```bash
source .venv/bin/activate
uv sync
```

### Permission denied on Linux/Mac

Ensure you have proper permissions on the project directory:

```bash
chmod +x main.py
```

## License

Add your license information here.
