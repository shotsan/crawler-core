"""
Configuration module for the web crawler.
Handles all configurable parameters including CPU usage, timeouts, and scraping settings.
Supports YAML configuration files for better developer experience.
"""

import logging
import os
import multiprocessing
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class CrawlerConfig:
    """Configuration class for the web crawler with all settings."""

    def __init__(self):
        logger.debug("Initializing CrawlerConfig")
        # CPU and multiprocessing settings
        self.max_cpus = multiprocessing.cpu_count()
        self.use_cpus = self.max_cpus  # Default to maximum CPUs
        logger.debug(f"CPU configuration: max={self.max_cpus}, use={self.use_cpus}")

        # Timeout settings (in seconds)
        self.page_load_timeout = 30
        self.network_timeout = 10
        self.element_wait_timeout = 5

        # Screenshot settings
        self.screenshot_full_page = True
        self.screenshot_width = 1920
        self.screenshot_height = 1080

        # Scraping settings
        self.max_pages_per_website = 50000  # High default limit (safety check, not used in recursive discovery)
        self.wait_after_load = 2  # Seconds to wait after page load for popups
        self.max_retries = 3
        self.max_discovery_depth = 100  # Maximum depth for directory discovery

        # Output settings
        self.output_base_dir = "crawled_data"
        self.screenshot_dir = "screenshots"
        self.html_dir = "html"

        # Browser settings
        self.browser_headless = True
        self.browser_args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--single-process',  # Important for stability
            '--disable-gpu'
        ]

        # CSV settings
        self.csv_delimiter = ','
        self.csv_website_column = 'website'
        self.csv_encoding = 'utf-8'
        
        # Rate limiting settings
        self.delay_between_pages_min = 2.0  # Minimum delay between pages (seconds)
        self.delay_between_pages_max = 5.0  # Maximum delay between pages (seconds)
        self.max_requests_per_domain_per_minute = 30  # Max requests per domain per minute
        
        # Human behavior simulation settings
        self.enable_mouse_movements = True  # Enable mouse movement simulation
        self.enable_scrolling_simulation = True  # Enable scrolling simulation
        self.scroll_delay_min = 0.2  # Minimum delay between scroll steps (seconds)
        self.scroll_delay_max = 0.8  # Maximum delay between scroll steps (seconds)
        
        # Stealth plugin settings
        self.enable_stealth = False  # Disable stealth by default (can cause blocking issues)

    def update_from_yaml(self, yaml_config: Dict[str, Any]) -> None:
        """
        Update configuration from YAML config dictionary.
        
        Handles nested YAML structure and maps to flat config attributes.
        
        Args:
            yaml_config: Dictionary loaded from YAML file
        """
        logger.debug(f"Updating configuration from YAML with {len(yaml_config)} top-level keys")
        
        # Performance settings
        if 'performance' in yaml_config:
            perf = yaml_config['performance']
            if 'cpus' in perf and perf['cpus'] is not None:
                self.use_cpus = min(perf['cpus'], self.max_cpus)
            if 'max_pages_per_website' in perf:
                self.max_pages_per_website = perf['max_pages_per_website']
            if 'wait_after_load' in perf:
                self.wait_after_load = perf['wait_after_load']
            if 'max_retries' in perf:
                self.max_retries = perf['max_retries']
            if 'max_discovery_depth' in perf:
                self.max_discovery_depth = perf['max_discovery_depth']
        
        # Timeout settings
        if 'timeouts' in yaml_config:
            timeouts = yaml_config['timeouts']
            if 'page_load' in timeouts:
                self.page_load_timeout = timeouts['page_load']
            if 'network' in timeouts:
                self.network_timeout = timeouts['network']
            if 'element_wait' in timeouts:
                self.element_wait_timeout = timeouts['element_wait']
        
        # Browser settings
        if 'browser' in yaml_config:
            browser = yaml_config['browser']
            if 'headless' in browser:
                self.browser_headless = browser['headless']
            if 'viewport' in browser:
                viewport = browser['viewport']
                if 'width' in viewport:
                    self.screenshot_width = viewport['width']
                if 'height' in viewport:
                    self.screenshot_height = viewport['height']
            if 'args' in browser:
                self.browser_args = browser['args']
            if 'enable_stealth' in browser:
                self.enable_stealth = browser['enable_stealth']
        
        # Screenshot settings
        if 'screenshot' in yaml_config:
            screenshot = yaml_config['screenshot']
            if 'full_page' in screenshot:
                self.screenshot_full_page = screenshot['full_page']
            if 'width' in screenshot:
                self.screenshot_width = screenshot['width']
            if 'height' in screenshot:
                self.screenshot_height = screenshot['height']
        
        # Output settings
        if 'output' in yaml_config:
            output = yaml_config['output']
            if 'base_dir' in output:
                self.output_base_dir = output['base_dir']
            if 'screenshot_dir' in output:
                self.screenshot_dir = output['screenshot_dir']
            if 'html_dir' in output:
                self.html_dir = output['html_dir']
        
        # CSV settings
        if 'csv' in yaml_config:
            csv = yaml_config['csv']
            if 'delimiter' in csv:
                self.csv_delimiter = csv['delimiter']
            if 'website_column' in csv:
                self.csv_website_column = csv['website_column']
            if 'encoding' in csv:
                self.csv_encoding = csv['encoding']
        
        # Rate limiting settings
        if 'rate_limiting' in yaml_config:
            rate_limiting = yaml_config['rate_limiting']
            if 'delay_between_pages_min' in rate_limiting:
                self.delay_between_pages_min = rate_limiting['delay_between_pages_min']
            if 'delay_between_pages_max' in rate_limiting:
                self.delay_between_pages_max = rate_limiting['delay_between_pages_max']
            if 'max_requests_per_domain_per_minute' in rate_limiting:
                self.max_requests_per_domain_per_minute = rate_limiting['max_requests_per_domain_per_minute']
        
        # Human behavior settings
        if 'human_behavior' in yaml_config:
            human_behavior = yaml_config['human_behavior']
            if 'enable_mouse_movements' in human_behavior:
                self.enable_mouse_movements = human_behavior['enable_mouse_movements']
            if 'enable_scrolling_simulation' in human_behavior:
                self.enable_scrolling_simulation = human_behavior['enable_scrolling_simulation']
            if 'scroll_delay_min' in human_behavior:
                self.scroll_delay_min = human_behavior['scroll_delay_min']
            if 'scroll_delay_max' in human_behavior:
                self.scroll_delay_max = human_behavior['scroll_delay_max']
        
        logger.info("Configuration updated from YAML")

    def update_from_dict(self, config_dict: Dict[str, Any]) -> None:
        """Update configuration from dictionary (legacy method, kept for compatibility)."""
        logger.debug(f"Updating configuration from dictionary with {len(config_dict)} items")
        updated_keys = []
        for key, value in config_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)
                updated_keys.append(key)
            else:
                logger.warning(f"Ignoring unknown configuration key: {key}")
        logger.debug(f"Updated configuration keys: {updated_keys}")

    def update_from_env(self) -> None:
        """Update configuration from environment variables."""
        logger.debug("Updating configuration from environment variables")

        env_mappings = {
            'CRAWLER_MAX_CPUS': ('use_cpus', int),
            'CRAWLER_PAGE_TIMEOUT': ('page_load_timeout', int),
            'CRAWLER_NETWORK_TIMEOUT': ('network_timeout', int),
            'CRAWLER_HEADLESS': ('browser_headless', lambda x: x.lower() == 'true'),
            'CRAWLER_OUTPUT_DIR': ('output_base_dir', str),
            'CRAWLER_MAX_PAGES': ('max_pages_per_website', int),
        }

        updated_from_env = []
        for env_var, (attr, converter) in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                try:
                    setattr(self, attr, converter(value))
                    updated_from_env.append(env_var)
                    logger.debug(f"Set {attr} from {env_var}: {value}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid value for {env_var}: {value} - {e}")
                    print(f"Warning: Invalid value for {env_var}: {value}")

        if updated_from_env:
            logger.info(f"Updated configuration from environment variables: {updated_from_env}")
        else:
            logger.debug("No environment variables found for configuration")

    def validate(self) -> bool:
        """Validate configuration values."""
        logger.debug("Validating configuration values")

        validation_warnings = []

        if self.use_cpus < 1 or self.use_cpus > self.max_cpus:
            warning = f"use_cpus ({self.use_cpus}) should be between 1 and {self.max_cpus}"
            validation_warnings.append(warning)
            logger.warning(f"Configuration validation warning: {warning}")
            print(f"Warning: {warning}")
            self.use_cpus = min(self.use_cpus, self.max_cpus)

        if self.page_load_timeout < 5:
            warning = "page_load_timeout should be at least 5 seconds"
            validation_warnings.append(warning)
            logger.warning(f"Configuration validation warning: {warning}")
            print(f"Warning: {warning}")
            self.page_load_timeout = 5

        if self.network_timeout < 1:
            warning = "network_timeout should be at least 1 second"
            validation_warnings.append(warning)
            logger.warning(f"Configuration validation warning: {warning}")
            print(f"Warning: {warning}")
            self.network_timeout = 1

        if validation_warnings:
            logger.info(f"Configuration validation completed with {len(validation_warnings)} warnings")
        else:
            logger.debug("Configuration validation completed successfully")

        return True

    def get_browser_context_settings(self) -> Dict[str, Any]:
        """
        Get browser context settings for Playwright.
        Note: This method is kept for compatibility but _create_stealth_context in scraper.py
        should be used instead for better anti-detection.
        """
        from src.fingerprint import get_random_fingerprint
        fingerprint = get_random_fingerprint()
        settings = {
            'viewport': fingerprint['viewport'],
            'user_agent': fingerprint['user_agent'],
            'locale': fingerprint['locale'],
            'timezone_id': fingerprint['timezone_id']
        }
        logger.debug(f"Generated browser context settings with fingerprint")
        return settings

    def __str__(self) -> str:
        """String representation of configuration."""
        return f"""Crawler Configuration:
- CPUs: {self.use_cpus}/{self.max_cpus} available
- Timeouts: page={self.page_load_timeout}s, network={self.network_timeout}s
- Headless: {self.browser_headless}
- Output directory: {self.output_base_dir}
- Max pages per website: {self.max_pages_per_website}
"""


# Global configuration instance
config = CrawlerConfig()
