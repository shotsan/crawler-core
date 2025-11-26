"""
Main crawler module that orchestrates multi-processing for website scraping.
Handles parallel processing of websites using configurable CPU cores.
"""

import asyncio
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from pathlib import Path

from src.scraper import WebsiteScraper
from src.csv_reader import WebsiteCSVReader

logger = logging.getLogger(__name__)


class MultiProcessCrawler:
    """Handles multi-processing orchestration for website crawling."""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing MultiProcessCrawler")
        self.logger.debug("Creating WebsiteScraper instance")
        self.scraper = WebsiteScraper(config)
        self.logger.debug("Creating WebsiteCSVReader instance")
        self.csv_reader = WebsiteCSVReader(config)
        self.logger.info("MultiProcessCrawler initialized successfully")

    def crawl_from_csv(self, csv_file_path: str) -> Dict[str, Any]:
        """
        Crawl websites from CSV file using multi-processing.

        Args:
            csv_file_path: Path to CSV file containing websites

        Returns:
            Dictionary with crawling results and statistics
        """
        start_time = time.time()
        self.logger.info(f"Starting crawl from CSV: {csv_file_path}")

        # Validate CSV and load websites
        self.logger.debug(f"Validating CSV file: {csv_file_path}")
        self.csv_reader.validate_csv_format(csv_file_path)

        self.logger.debug("Reading websites from CSV")
        websites = self.csv_reader.read_websites(csv_file_path)

        if not websites:
            self.logger.error("No valid websites found in CSV file")
            raise ValueError("No valid websites found in CSV file")

        self.logger.info(f"Starting crawl of {len(websites)} websites using {self.config.use_cpus} CPU cores")
        self.logger.debug(f"Website domains: {[w['domain'] for w in websites[:5]]}{'...' if len(websites) > 5 else ''}")

        # Create output directory
        self.logger.debug(f"Creating output directory: {self.config.output_base_dir}")
        Path(self.config.output_base_dir).mkdir(exist_ok=True)

        # Run crawling with multi-processing
        self.logger.debug("Starting parallel crawling process")
        results = self._run_parallel_crawling(websites)
        self.logger.debug(f"Parallel crawling completed, {len(results)} results received")

        # Generate summary
        self.logger.debug("Generating crawl summary")
        summary = self._generate_summary(results, start_time)

        self.logger.info(f"Crawling completed in {summary['total_time']:.2f} seconds")
        self.logger.info(f"Results: {summary['successful_websites']} successful, {summary['failed_websites']} failed, "
                        f"{summary['total_pages']} pages, {summary['total_screenshots']} screenshots")
        return summary

    def _run_parallel_crawling(self, websites: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run website crawling in parallel using ProcessPoolExecutor.

        Args:
            websites: List of website data dictionaries

        Returns:
            List of crawling results
        """
        results = []

        # Use ProcessPoolExecutor for CPU-bound tasks
        with ProcessPoolExecutor(max_workers=self.config.use_cpus) as executor:
            # Submit all crawling tasks
            future_to_website = {
                executor.submit(self._crawl_single_website, website): website
                for website in websites
            }

            # Process completed tasks as they finish
            completed_count = 0
            total_count = len(websites)

            for future in as_completed(future_to_website):
                website = future_to_website[future]
                try:
                    result = future.result(timeout=300)  # 5 minute timeout per website
                    results.append(result)
                    completed_count += 1

                    self.logger.info(
                        f"Completed {completed_count}/{total_count}: {website['domain']} "
                        f"({result.get('pages_scraped', 0)} pages)"
                    )

                except Exception as e:
                    error_result = {
                        'domain': website['domain'],
                        'url': website['url'],
                        'error': f"Failed to crawl: {str(e)}",
                        'pages_scraped': 0,
                        'screenshots_taken': 0,
                        'html_saved': 0,
                        'pages': []
                    }
                    results.append(error_result)
                    completed_count += 1

                    self.logger.error(f"Failed to crawl {website['domain']}: {e}")

        return results

    def _crawl_single_website(self, website_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crawl a single website. This method runs in a separate process.

        Args:
            website_data: Website data dictionary

        Returns:
            Crawling results for the website
        """
        # Set up logging for this process
        logging.basicConfig(
            level=logging.INFO,
            format=f'%(asctime)s - %(name)s - {website_data["domain"]} - %(levelname)s - %(message)s'
        )

        try:
            # Create new event loop for this process
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Create scraper instance for this process
            scraper = WebsiteScraper(self.config)

            # Run the scraping
            result = loop.run_until_complete(scraper.scrape_website(website_data))

            loop.close()
            return result

        except Exception as e:
            self.logger.error(f"Process error for {website_data['domain']}: {e}")
            return {
                'domain': website_data['domain'],
                'url': website_data['url'],
                'error': str(e),
                'pages_scraped': 0,
                'screenshots_taken': 0,
                'html_saved': 0,
                'pages': []
            }

    def _generate_summary(self, results: List[Dict[str, Any]], start_time: float) -> Dict[str, Any]:
        """
        Generate comprehensive summary of crawling results.

        Args:
            results: List of individual website results
            start_time: Start time of crawling process

        Returns:
            Dictionary with summary statistics
        """
        total_time = time.time() - start_time

        summary = {
            'total_time': total_time,
            'total_websites': len(results),
            'successful_websites': 0,
            'failed_websites': 0,
            'total_pages': 0,
            'total_screenshots': 0,
            'total_html_saved': 0,
            'total_errors': 0,
            'results': results,
            'performance': {
                'pages_per_second': 0,
                'websites_per_minute': 0,
                'avg_pages_per_website': 0
            }
        }

        for result in results:
            if 'error' in result and not result.get('pages_scraped', 0):
                summary['failed_websites'] += 1
            else:
                summary['successful_websites'] += 1

            summary['total_pages'] += result.get('pages_scraped', 0)
            summary['total_screenshots'] += result.get('screenshots_taken', 0)
            summary['total_html_saved'] += result.get('html_saved', 0)
            summary['total_errors'] += len(result.get('errors', []))

        # Calculate performance metrics
        if total_time > 0:
            summary['performance']['pages_per_second'] = summary['total_pages'] / total_time
            summary['performance']['websites_per_minute'] = (summary['successful_websites'] / total_time) * 60

        if summary['successful_websites'] > 0:
            summary['performance']['avg_pages_per_website'] = summary['total_pages'] / summary['successful_websites']

        return summary
