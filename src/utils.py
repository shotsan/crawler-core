"""
Utility functions for the web crawler.
Includes logging setup, file operations, and helper functions.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


def setup_logging(log_level: str = 'INFO', log_file: str = None) -> logging.Logger:
    """
    Set up logging configuration for the crawler.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger('web_crawler')
    logger.setLevel(getattr(logging, log_level.upper()))
    logger.debug(f"Setting log level to: {log_level}")

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Could not create log file {log_file}: {e}")

    return logger


def save_results_to_json(results: Dict[str, Any], output_file: str) -> None:
    """
    Save crawling results to JSON file.

    Args:
        results: Results dictionary to save
        output_file: Output file path
    """
    logger.info(f"Saving results to JSON file: {output_file}")
    logger.debug(f"Results contain {len(results)} top-level keys")

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Results saved successfully to {output_file}")
        print(f"Results saved to {output_file}")
    except Exception as e:
        logger.error(f"Error saving results to {output_file}: {e}")
        print(f"Error saving results to {output_file}: {e}")


def print_summary(summary: Dict[str, Any]) -> None:
    """
    Print a formatted summary of crawling results.

    Args:
        summary: Summary dictionary from crawler
    """
    print("\n" + "="*60)
    print("WEB CRAWLER SUMMARY")
    print("="*60)

    print(f"Total execution time: {summary['total_time']:.2f} seconds")
    print(f"Websites processed: {summary['total_websites']}")
    print(f"Successful: {summary['successful_websites']}")
    print(f"Failed: {summary['failed_websites']}")
    print(f"Total pages scraped: {summary['total_pages']}")
    print(f"Total screenshots taken: {summary['total_screenshots']}")
    print(f"Total HTML files saved: {summary['total_html_saved']}")
    print(f"Total errors encountered: {summary['total_errors']}")

    perf = summary['performance']
    print("\nPerformance:")
    print(f"  Pages per second: {perf['pages_per_second']:.2f}")
    print(f"  Websites per minute: {perf['websites_per_minute']:.2f}")
    print(f"  Avg pages per website: {perf['avg_pages_per_website']:.1f}")

    print("\n" + "="*60)


def create_sample_csv(output_file: str = 'websites.csv') -> None:
    """
    Create a sample CSV file with example websites.

    Args:
        output_file: Path for the sample CSV file
    """
    logger.info(f"Creating sample CSV file: {output_file}")

    sample_data = """website,name,category
https://example.com,Example Site,Demo
https://httpbin.org,HTTPBin,Testing
https://quotes.toscrape.com,Quotes to Scrape,Tutorial
"""

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(sample_data)
        logger.info(f"Sample CSV created successfully: {output_file}")
        print(f"Sample CSV created: {output_file}")
        print("You can edit this file to add your own websites.")
    except Exception as e:
        logger.error(f"Error creating sample CSV: {e}")
        print(f"Error creating sample CSV: {e}")


def validate_dependencies() -> bool:
    """
    Validate that all required dependencies are installed.

    Returns:
        True if all dependencies are available
    """
    logger.debug("Validating required dependencies")
    missing_deps = []

    try:
        import playwright
        logger.debug("✓ playwright available")
    except ImportError:
        missing_deps.append('playwright')
        logger.debug("✗ playwright missing")

    try:
        import aiofiles
        logger.debug("✓ aiofiles available")
    except ImportError:
        missing_deps.append('aiofiles')
        logger.debug("✗ aiofiles missing")

    if missing_deps:
        logger.error(f"Missing required dependencies: {missing_deps}")
        print("Missing required dependencies:")
        for dep in missing_deps:
            print(f"  - {dep}")
        print("\nInstall with: pip install " + " ".join(missing_deps))
        if 'playwright' in missing_deps:
            print("Also run: playwright install chromium")
        return False

    logger.info("All required dependencies are available")
    return True


def cleanup_old_data(base_dir: str, days_old: int = 7) -> None:
    """
    Clean up old crawled data directories.

    Args:
        base_dir: Base directory containing crawled data
        days_old: Remove directories older than this many days
    """
    import time
    import shutil

    base_path = Path(base_dir)
    if not base_path.exists():
        return

    current_time = time.time()
    cutoff_time = current_time - (days_old * 24 * 60 * 60)

    for dir_path in base_path.iterdir():
        if dir_path.is_dir():
            try:
                dir_mtime = dir_path.stat().st_mtime
                if dir_mtime < cutoff_time:
                    print(f"Removing old directory: {dir_path}")
                    shutil.rmtree(dir_path)
            except Exception as e:
                print(f"Error removing {dir_path}: {e}")


class ProgressTracker:
    """Simple progress tracker for long-running operations."""

    def __init__(self, total_items: int, description: str = "Processing"):
        self.total = total_items
        self.current = 0
        self.description = description
        self.start_time = datetime.now()

    def update(self, increment: int = 1) -> None:
        """Update progress by increment."""
        self.current += increment
        self._print_progress()

    def set_current(self, current: int) -> None:
        """Set current progress directly."""
        self.current = current
        self._print_progress()

    def _print_progress(self) -> None:
        """Print current progress."""
        percentage = (self.current / self.total) * 100 if self.total > 0 else 0
        elapsed = datetime.now() - self.start_time
        print(f"\r{self.description}: {self.current}/{self.total} ({percentage:.1f}%) - {elapsed}", end='', flush=True)

    def complete(self) -> None:
        """Mark progress as complete."""
        elapsed = datetime.now() - self.start_time
        print(f"\n{self.description} completed in {elapsed}")
