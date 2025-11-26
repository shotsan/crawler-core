"""
CSV reader module for loading websites from CSV files.
Handles various CSV formats and validates website URLs.
"""

import csv
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import os

logger = logging.getLogger(__name__)


class WebsiteCSVReader:
    """Handles reading and validating websites from CSV files."""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def read_websites(self, csv_file_path: str) -> List[Dict[str, Any]]:
        """
        Read websites from CSV file.

        Args:
            csv_file_path: Path to the CSV file

        Returns:
            List of dictionaries containing website data
        """
        self.logger.info(f"Reading websites from CSV file: {csv_file_path}")

        if not os.path.exists(csv_file_path):
            self.logger.error(f"CSV file not found: {csv_file_path}")
            raise FileNotFoundError(f"CSV file not found: {csv_file_path}")

        websites = []
        processed_rows = 0
        valid_websites = 0

        try:
            self.logger.debug(f"Opening CSV file with encoding: {self.config.csv_encoding}")
            with open(csv_file_path, 'r', encoding=self.config.csv_encoding) as file:
                # Try to detect delimiter if not specified
                sample = file.read(1024)
                file.seek(0)
                delimiter = self._detect_delimiter(sample)

                self.logger.debug(f"Detected CSV delimiter: '{delimiter}'")

                reader = csv.DictReader(file, delimiter=delimiter)
                self.logger.debug(f"CSV headers: {list(reader.fieldnames) if reader.fieldnames else 'None'}")

                for row_num, row in enumerate(reader, start=2):  # Start at 2 for header
                    processed_rows += 1
                    try:
                        website_data = self._process_row(row, row_num)
                        if website_data:
                            websites.append(website_data)
                            valid_websites += 1
                        else:
                            self.logger.debug(f"Row {row_num} skipped - invalid website data")
                    except Exception as e:
                        self.logger.warning(f"Error processing row {row_num}: {e}")
                        continue

        except Exception as e:
            self.logger.error(f"Error reading CSV file: {e}")
            raise RuntimeError(f"Error reading CSV file: {e}")

        self.logger.info(f"Successfully loaded {len(websites)} websites from {csv_file_path} "
                        f"({processed_rows} rows processed, {valid_websites} valid websites)")
        return websites

    def _detect_delimiter(self, sample: str) -> str:
        """Detect CSV delimiter from sample text."""
        delimiters = [',', ';', '\t', '|']
        counts = {}

        for delimiter in delimiters:
            count = sample.count(delimiter)
            if count > 0:
                counts[delimiter] = count

        if counts:
            # Return most common delimiter
            return max(counts, key=counts.get)

        return self.config.csv_delimiter

    def _process_row(self, row: Dict[str, str], row_num: int) -> Optional[Dict[str, Any]]:
        """Process a single CSV row and validate the website URL."""
        self.logger.debug(f"Processing row {row_num}")

        # Get website URL from the specified column
        website_url = row.get(self.config.csv_website_column)

        if not website_url:
            self.logger.warning(f"Row {row_num}: Missing website URL in column '{self.config.csv_website_column}'")
            return None

        # Clean and validate URL
        website_url = website_url.strip()

        if not website_url:
            self.logger.warning(f"Row {row_num}: Empty website URL")
            return None

        # Add protocol if missing
        original_url = website_url
        if not website_url.startswith(('http://', 'https://')):
            website_url = f'https://{website_url}'
            self.logger.debug(f"Row {row_num}: Added HTTPS protocol to URL")

        # Validate URL format
        try:
            parsed = urlparse(website_url)
            if not parsed.netloc:
                raise ValueError("Invalid URL format")
        except Exception as e:
            self.logger.warning(f"Row {row_num}: Invalid URL '{original_url}': {e}")
            return None

        self.logger.debug(f"Row {row_num}: Valid URL found: {website_url}")

        # Create website data dictionary
        website_data = {
            'url': website_url,
            'domain': parsed.netloc,
            'original_row': row,
            'row_number': row_num
        }

        # Add any additional columns from CSV
        for key, value in row.items():
            if key != self.config.csv_website_column:
                website_data[f'csv_{key.lower()}'] = value

        return website_data

    def validate_csv_format(self, csv_file_path: str) -> bool:
        """
        Validate CSV file format and check for required columns.

        Returns:
            True if valid, raises exception if invalid
        """
        self.logger.info(f"Validating CSV file format: {csv_file_path}")

        try:
            self.logger.debug(f"Opening CSV file for validation with encoding: {self.config.csv_encoding}")
            with open(csv_file_path, 'r', encoding=self.config.csv_encoding) as file:
                sample = file.read(1024)
                file.seek(0)

                delimiter = self._detect_delimiter(sample)
                self.logger.debug(f"Detected delimiter for validation: '{delimiter}'")

                reader = csv.DictReader(file, delimiter=delimiter)

                # Check if header exists
                if not reader.fieldnames:
                    self.logger.error("CSV file must have a header row")
                    raise ValueError("CSV file must have a header row")

                fieldnames = list(reader.fieldnames)
                self.logger.debug(f"CSV headers found: {fieldnames}")

                # Check for required website column
                if self.config.csv_website_column not in reader.fieldnames:
                    available_columns = list(reader.fieldnames)
                    self.logger.error(f"Required column '{self.config.csv_website_column}' not found. "
                                    f"Available columns: {available_columns}")
                    raise ValueError(
                        f"Required column '{self.config.csv_website_column}' not found. "
                        f"Available columns: {available_columns}"
                    )

                self.logger.info(f"CSV validation passed. Columns: {fieldnames}")

        except Exception as e:
            self.logger.error(f"CSV validation failed: {e}")
            raise ValueError(f"CSV validation failed: {e}")

        return True
