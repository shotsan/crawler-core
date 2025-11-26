# Multi-Process Web Crawler

A highly modular, multi-process web crawler built with Python and Playwright that takes screenshots and saves HTML content from websites listed in a CSV file.

## Features

- **Multi-Process**: Utilizes configurable CPU cores for parallel processing
- **Modular Architecture**: Separated concerns across multiple files for easy maintenance
- **Screenshot & HTML Capture**: Takes full-page screenshots and saves HTML content
- **Popup Handling**: Automatically handles common popups and overlays
- **Comprehensive Discovery**: Crawls all pages in the website root folder
- **Robust Error Handling**: Continues processing even if individual pages fail
- **Configurable Timeouts**: Network and page load timeouts to handle slow sites
- **CSV Input**: Reads websites from CSV files with flexible column mapping

## Project Structure

```
crawler/
├── src/
│   ├── __init__.py      # Package initialization
│   ├── main.py          # Main entry point and CLI
│   ├── config.py        # Configuration management
│   ├── crawler.py       # Multi-processing orchestration
│   ├── scraper.py       # Core Playwright scraping logic
│   ├── popup_handler.py # Popup and overlay handling
│   ├── csv_reader.py    # CSV file processing and validation
│   └── utils.py         # Utility functions and logging
├── tests/               # Unit tests
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Installation

1. **Clone or download the project files**

2. **Create and activate virtual environment (only if it doesn't exist):**
   
   Check if `venv` directory exists:
   ```bash
   ls venv
   ```
   
   If `venv` doesn't exist, create it:
   ```bash
   python3 -m venv venv
   ```
   
   **Note:** Only create the virtual environment if the `venv` directory is not present. If it already exists, skip this step.
   
   Activate the virtual environment:
   ```bash
   # On Linux/macOS:
   source venv/bin/activate
   
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers:**
   ```bash
   playwright install chromium
   ```

## Usage

### Create a Sample CSV File

First, create a sample CSV file to understand the expected format:

```bash
python -m src.main --sample-csv
```

This creates `websites.csv` with example websites.

### Prepare Your CSV File

Your CSV file should have at least one column containing website URLs. By default, the crawler looks for a column named `website`, but this can be configured.

Example CSV format:
```csv
website,name,category
https://example.com,Example Site,Demo
https://httpbin.org,HTTPBin,Testing
https://quotes.toscrape.com,Quotes to Scrape,Tutorial
```

### Run the Crawler

**Important:** Make sure the virtual environment is activated before running the crawler:
```bash
source venv/bin/activate  # On Linux/macOS
# or
venv\Scripts\activate      # On Windows
```

## Quick Start

1. **Create a sample configuration file:**
```bash
python -m src.main --sample-config
```

2. **Edit `config.yaml`** to customize settings (optional - defaults work fine)

3. **Create a CSV file with websites:**
```bash
python -m src.main --sample-csv
```

4. **Run the crawler:**
```bash
python -m src.main
```

That's it! The crawler will use `config.yaml` for all settings.

### Alternative: Specify CSV file directly

If you want to use a different CSV file without editing config.yaml:

```bash
python -m src.main my_websites.csv
```

### Helper Commands

```bash
# Create sample config.yaml
python -m src.main --sample-config

# Create sample websites.csv
python -m src.main --sample-csv

# Show help
python -m src.main --help
```

## Output Structure

The crawler creates the following directory structure:

```
crawled_data/
├── example_com/
│   ├── screenshots/
│   │   ├── example_com_123456.png
│   │   └── example_com_789012.png
│   └── html/
│       ├── example_com_123456.html
│       └── example_com_789012.html
├── httpbin_org/
│   ├── screenshots/
│   └── html/
└── quotes_toscrape_com/
    ├── screenshots/
    └── html/
```

## Configuration

The crawler uses **YAML configuration files** for a clean, developer-friendly experience.

### Configuration Priority

1. **`config.yaml`** (recommended) - Edit this file to customize all settings
2. **Environment variables** - Can override YAML settings
3. **Default values** - Used if nothing else is specified

### Creating Your Config File

```bash
python -m src.main --sample-config
```

This creates `config.yaml` with all available options and documentation.

### Configuration Options

Edit `config.yaml` to customize:

- **`csv_file`**: Path to your CSV file with websites
- **`performance`**: CPU usage, max pages, retries
- **`timeouts`**: Page load, network, element wait timeouts
- **`browser`**: Headless mode, viewport size, browser arguments
- **`screenshot`**: Full page capture, dimensions
- **`output`**: Output directories for screenshots and HTML
- **`csv`**: CSV parsing settings (delimiter, column names)
- **`logging`**: Log level and optional log file
- **`results`**: Optional JSON results file

### Environment Variables (Optional Override)

You can still use environment variables to override YAML settings:

- `CRAWLER_MAX_CPUS`: Number of CPU cores to use
- `CRAWLER_PAGE_TIMEOUT`: Page load timeout in seconds
- `CRAWLER_NETWORK_TIMEOUT`: Network timeout in seconds
- `CRAWLER_HEADLESS`: Run in headless mode (true/false)
- `CRAWLER_OUTPUT_DIR`: Output directory path
- `CRAWLER_MAX_PAGES`: Maximum pages per website

## Architecture Details

### Modular Design

- **`main.py`**: Command-line interface and orchestration
- **`config.py`**: Centralized configuration management
- **`crawler.py`**: Multi-processing coordination using `ProcessPoolExecutor`
- **`scraper.py`**: Playwright-based page scraping and screenshot capture
- **`csv_reader.py`**: CSV parsing and website validation
- **`utils.py`**: Helper functions, logging, and utilities

### Multi-Processing Strategy

The crawler uses Python's `ProcessPoolExecutor` to distribute website crawling across multiple CPU cores. Each process:

1. Creates its own Playwright browser instance
2. Processes one website at a time
3. Discovers all pages on the website
4. Takes screenshots and saves HTML for each page
5. Reports results back to the main process

### Page Discovery

For each website, the crawler:
1. Starts with the root URL
2. Extracts all links from the page
3. Follows links within the same domain
4. Limits to root-level pages (configurable)
5. Avoids duplicate pages

### Popup Handling

The crawler attempts to handle common popups by:
1. Waiting for pages to stabilize after loading
2. Looking for common popup selectors
3. Clicking close/dismiss buttons
4. Pressing the Escape key as fallback

## Error Handling

The crawler is designed to be resilient:
- Individual page failures don't stop website processing
- Website failures don't stop the overall crawl
- Comprehensive logging at multiple levels
- Detailed error reporting in results

## Performance Considerations

- **CPU Usage**: Configurable core usage (default: maximum available)
- **Memory**: Each process has its own browser instance
- **Network**: Parallel processing of multiple websites
- **Timeouts**: Prevent hanging on slow/unresponsive sites
- **Rate Limiting**: Built-in delays to avoid overwhelming servers

## Troubleshooting

### Common Issues

1. **Browser Launch Failed**
   ```bash
   playwright install chromium
   ```

2. **Permission Errors**
   - Ensure write permissions for output directory
   - Check if ports are available for browser instances

3. **Memory Issues**
   - Reduce `--cpus` if running out of memory
   - Increase system RAM or use fewer processes

4. **Slow Performance**
   - Increase `--timeout` for slow sites
   - Reduce `--max-pages` to limit scope
   - Use `--visible` to debug browser behavior

### Debug Mode

Enable detailed logging:
```bash
python -m src.main websites.csv --log-level DEBUG --log-file debug.log
```

## Requirements

- Python 3.8+
- Playwright
- aiofiles

## License

This project is open source. Feel free to modify and distribute.
