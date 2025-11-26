"""
YAML configuration loader for the web crawler.
Provides clean, developer-friendly configuration management.
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Handles loading and validation of YAML configuration files."""

    @staticmethod
    def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration from YAML file.

        Search order:
        1. Explicit config_path if provided
        2. config.yaml in current directory
        3. config.yaml in project root
        4. Returns empty dict (will use defaults)

        Args:
            config_path: Optional explicit path to config file

        Returns:
            Dictionary of configuration values
        """
        config_file = None

        # Try explicit path first
        if config_path:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"Config file not found at explicit path: {config_path}")
                return {}
        else:
            # Try current directory
            config_file = Path("config.yaml")
            if not config_file.exists():
                # Try project root (one level up from src/)
                config_file = Path(__file__).parent.parent / "config.yaml"
                if not config_file.exists():
                    logger.info("No config.yaml found, using defaults")
                    return {}

        if config_file and config_file.exists():
            try:
                logger.info(f"Loading configuration from: {config_file}")
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f) or {}
                logger.info(f"Successfully loaded configuration from {config_file}")
                return config_data
            except yaml.YAMLError as e:
                logger.error(f"Error parsing YAML config file: {e}")
                raise ValueError(f"Invalid YAML in config file: {e}")
            except Exception as e:
                logger.error(f"Error reading config file: {e}")
                raise

        return {}

    @staticmethod
    def create_sample_config(output_path: Path = Path("config.yaml")) -> None:
        """
        Create a sample config.yaml file with all available options.

        Args:
            output_path: Path where to create the sample config file
        """
        sample_config = {
            '# Web Crawler Configuration': None,
            '# All settings are optional - defaults will be used if not specified': None,
            '': None,
            
            '# Input file': None,
            'csv_file': 'websites.csv',
            '': None,

            '# Performance Settings': None,
            'performance': {
                'cpus': None,  # None = use all available CPUs
                'max_pages_per_website': 50000,
                'wait_after_load': 2,  # seconds
                'max_retries': 3,
            },
            '': None,

            '# Timeout Settings (seconds)': None,
            'timeouts': {
                'page_load': 30,
                'network': 10,
                'element_wait': 5,
            },
            '': None,

            '# Browser Settings': None,
            'browser': {
                'headless': True,
                'viewport': {
                    'width': 1920,
                    'height': 1080,
                },
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--single-process',
                    '--disable-gpu',
                ],
            },
            '': None,

            '# Screenshot Settings': None,
            'screenshot': {
                'full_page': True,
                'width': 1920,
                'height': 1080,
            },
            '': None,

            '# Output Settings': None,
            'output': {
                'base_dir': 'crawled_data',
                'screenshot_dir': 'screenshots',
                'html_dir': 'html',
            },
            '': None,

            '# CSV Settings': None,
            'csv': {
                'delimiter': ',',
                'website_column': 'website',
                'encoding': 'utf-8',
            },
            '': None,

            '# Logging Settings': None,
            'logging': {
                'level': 'INFO',  # DEBUG, INFO, WARNING, ERROR
                'file': None,  # Optional log file path
            },
            '': None,

            '# Results Settings': None,
            'results': {
                'save_json': None,  # Optional path to save results JSON
            },
        }

        # Convert to proper YAML format (remove comment keys)
        yaml_content = """# Web Crawler Configuration
# All settings are optional - defaults will be used if not specified

# Input file
csv_file: websites.csv

# Performance Settings
performance:
  cpus: null  # null = use all available CPUs, or specify a number
  max_pages_per_website: 50000
  wait_after_load: 2  # seconds
  max_retries: 3

# Timeout Settings (seconds)
timeouts:
  page_load: 30
  network: 10
  element_wait: 5

# Browser Settings
browser:
  headless: true
  viewport:
    width: 1920
    height: 1080
  args:
    - --no-sandbox
    - --disable-setuid-sandbox
    - --disable-dev-shm-usage
    - --disable-accelerated-2d-canvas
    - --no-first-run
    - --no-zygote
    - --single-process
    - --disable-gpu

# Screenshot Settings
screenshot:
  full_page: true
  width: 1920
  height: 1080

# Output Settings
output:
  base_dir: crawled_data
  screenshot_dir: screenshots
  html_dir: html

# CSV Settings
csv:
  delimiter: ','
  website_column: website
  encoding: utf-8

# Logging Settings
logging:
  level: INFO  # DEBUG, INFO, WARNING, ERROR
  file: null  # Optional log file path

# Results Settings
results:
  save_json: null  # Optional path to save results JSON
"""

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(yaml_content)
            logger.info(f"Sample config file created at: {output_path}")
            print(f"✅ Sample config file created at: {output_path}")
        except Exception as e:
            logger.error(f"Error creating sample config file: {e}")
            raise

