#!/usr/bin/env python3
"""
Main entry point for the web crawler application.
Uses YAML configuration for clean, developer-friendly setup.
"""

import logging
import sys
import shutil
from datetime import datetime
from pathlib import Path

from src.config import config
from src.config_loader import ConfigLoader
from src.crawler import MultiProcessCrawler
from src.utils import setup_logging, print_summary, save_results_to_json, create_sample_csv, validate_dependencies

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the web crawler."""
    global logger
    
    # Load YAML configuration
    try:
        yaml_config = ConfigLoader.load_config()
        
        # Update config from YAML
        if yaml_config:
            config.update_from_yaml(yaml_config)
            logger.info("Configuration loaded from YAML")
    except Exception as e:
        logger.warning(f"Could not load YAML config, using defaults: {e}")
        print(f"⚠️  Warning: Could not load config.yaml, using defaults: {e}")
    
    # Still allow environment variables to override
    config.update_from_env()
    
    # Get CSV file path from YAML config or use default
    csv_file = yaml_config.get('csv_file', 'websites.csv') if yaml_config else 'websites.csv'
    
    # Handle special commands (check sys.argv directly for simplicity)
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        if arg == '--sample-config':
            logger.info("Creating sample config file")
            ConfigLoader.create_sample_config()
            print("\n✅ Sample config.yaml created!")
            print("   Edit config.yaml to customize settings, then run: python -m src.main")
            return
        
        if arg == '--sample-csv':
            logger.info("Creating sample CSV file")
            create_sample_csv()
            logger.info("Sample CSV created successfully")
            return
        
        if arg == '--help' or arg == '-h':
            print("""
Web Crawler - YAML Configuration Based

Usage:
  python -m src.main                    # Run with config.yaml (or defaults)
  python -m src.main --sample-config     # Create sample config.yaml
  python -m src.main --sample-csv        # Create sample websites.csv

Configuration:
  The crawler uses config.yaml in the current directory or project root.
  If no config.yaml exists, sensible defaults are used.
  
  Create a config file:
    python -m src.main --sample-config
    
  Then edit config.yaml to customize:
    - CSV file path
    - CPU usage
    - Timeouts
    - Browser settings
    - Output directories
    - Logging settings
    - And more...

For detailed configuration options, see the sample config.yaml file.
""")
            return
        
        # If argument is provided and it's a file, use it as CSV file
        csv_path = Path(arg)
        if csv_path.exists() and csv_path.suffix.lower() == '.csv':
            csv_file = str(csv_path)
        elif not csv_path.exists():
            print(f"❌ Error: File not found: {arg}")
            print("   Use --help for usage information")
            sys.exit(1)
    
    # Validate dependencies
    logger.info("Validating dependencies")
    if not validate_dependencies():
        logger.error("Dependency validation failed. Please install missing packages.")
        print("❌ Dependency validation failed. Please install missing packages.")
        sys.exit(1)
    logger.info("Dependencies validated successfully")
    
    # Set up logging from YAML config with per-run timestamped files
    log_level = yaml_config.get('logging', {}).get('level', 'INFO') if yaml_config else 'INFO'
    base_log_file = yaml_config.get('logging', {}).get('file') if yaml_config else None
    
    # Create timestamped log file for this run
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if base_log_file:
        log_dir = Path(base_log_file).parent if Path(base_log_file).parent != Path('.') else Path('logs')
        log_dir.mkdir(exist_ok=True)
        log_name = Path(base_log_file).stem
        log_ext = Path(base_log_file).suffix or '.log'
        log_file = str(log_dir / f"{log_name}_{timestamp}{log_ext}")
    else:
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        log_file = str(log_dir / f"crawler_{timestamp}.log")
    
    # Save config file copy for this run
    config_backup_dir = Path('config_backups')
    config_backup_dir.mkdir(exist_ok=True)
    config_backup_file = config_backup_dir / f"config_{timestamp}.yaml"
    try:
        config_path = Path('config.yaml')
        if config_path.exists():
            shutil.copy2(config_path, config_backup_file)
            logger.info(f"Config backup saved to: {config_backup_file}")
    except Exception as e:
        logger.warning(f"Could not save config backup: {e}")
    
    logger = setup_logging(log_level, log_file)
    logger.info(f"Logging configured successfully - log file: {log_file}")
    logger.info(f"Config backup saved to: {config_backup_file}")
    
    # Validate configuration
    logger.debug("Validating configuration")
    config.validate()
    logger.info("Configuration validated successfully")
    
    # Print configuration
    print("=" * 60)
    print("Web Crawler Configuration")
    print("=" * 60)
    print(f"  CSV File:        {csv_file}")
    print(f"  CPUs:            {config.use_cpus}/{config.max_cpus}")
    print(f"  Output:          {config.output_base_dir}")
    print(f"  Max Pages:        {config.max_pages_per_website}")
    print(f"  Page Timeout:     {config.page_load_timeout}s")
    print(f"  Network Timeout: {config.network_timeout}s")
    print(f"  Browser Mode:    {'Headless' if config.browser_headless else 'Visible'}")
    print(f"  Log Level:       {log_level}")
    print("=" * 60)
    print()
    
    # Validate CSV file
    csv_path = Path(csv_file)
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_file}")
        print(f"❌ Error: CSV file not found: {csv_file}")
        print(f"   Create one with: python -m src.main --sample-csv")
        sys.exit(1)
    
    # Start crawling
    logger.info(f"Starting web crawl from CSV file: {csv_file}")
    try:
        print(f"🚀 Starting web crawl from: {csv_file}")
        print("-" * 60)
        
        logger.debug("Initializing multi-process crawler")
        crawler = MultiProcessCrawler(config)
        
        logger.info("Beginning crawling process")
        results = crawler.crawl_from_csv(str(csv_path))
        logger.info("Crawling process completed successfully")
        
        # Print summary
        logger.debug("Generating and displaying results summary")
        print()
        print_summary(results)
        
        # Save detailed results if configured
        save_json = yaml_config.get('results', {}).get('save_json') if yaml_config else None
        if save_json:
            logger.info(f"Saving detailed results to: {save_json}")
            save_results_to_json(results, save_json)
            logger.info("Results saved successfully")
            print(f"\n💾 Detailed results saved to: {save_json}")
    
    except KeyboardInterrupt:
        logger.warning("Crawling interrupted by user")
        print("\n⚠️  Crawling interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Crawling failed with error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    
    logger.info("Web crawler application completed")
    print("\n✅ Crawling completed successfully!")


if __name__ == '__main__':
    main()
