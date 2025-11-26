"""
Recursive directory discovery module.
Handles unlimited-depth recursive discovery of all subdirectories on a website.
"""

import asyncio
import logging
from typing import Set, List
from urllib.parse import urlparse, urljoin
from playwright.async_api import BrowserContext, Page

logger = logging.getLogger(__name__)


class RecursiveDirectoryDiscovery:
    """
    Handles recursive discovery of all directories on a website.
    Explores all nested subdirectories until no more are found.
    """

    def __init__(self, config, logger_instance: logging.Logger = None, url_store=None):
        """
        Initialize the recursive directory discovery.

        Args:
            config: CrawlerConfig instance
            logger_instance: Optional logger instance (uses module logger if not provided)
            url_store: Optional URLStore instance for persistent URL tracking
        """
        self.config = config
        self.logger = logger_instance or logger
        self.url_store = url_store

    async def discover_all_directories(self, context: BrowserContext, base_url: str) -> Set[str]:
        """
        Discover all directory-level pages on a website through unlimited-depth recursive traversal.

        This method:
        1. Starts from root URL
        2. Extracts all directory paths from links
        3. Recursively explores each directory (no depth limit)
        4. Continues until no new directories are found
        5. Returns comprehensive list of all directory URLs

        Args:
            context: Browser context
            base_url: Base URL of the website

        Returns:
            Set of unique directory URLs to scrape
        """
        self.logger.info(f"🔍 Starting recursive directory discovery from: {base_url}")

        discovered_directories = set([base_url])
        directories_to_explore = [base_url]
        explored_directories = set()
        
        # Write base URL to store if available
        if self.url_store:
            self.url_store.add_url(base_url)

        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc
        self.logger.debug(f"Base domain: {base_domain}")

        iteration = 0
        # No limit on recursive discovery - explore all directories until none remain
        while directories_to_explore:
            iteration += 1
            current_dir = directories_to_explore.pop(0)

            if current_dir in explored_directories:
                continue

            explored_directories.add(current_dir)
            
            # Calculate depth for logging (relative to base URL)
            # Count path segments, excluding empty strings and scheme/domain parts
            base_path_parts = [p for p in parsed_base.path.rstrip('/').split('/') if p]
            current_parsed = urlparse(current_dir)
            current_path_parts = [p for p in current_parsed.path.rstrip('/').split('/') if p]
            depth = len(current_path_parts) - len(base_path_parts)
            
            # Check depth limit from config
            max_depth = getattr(self.config, 'max_discovery_depth', 100)
            if depth > max_depth:
                self.logger.debug(f"⏹️  Skipping {current_dir} - depth {depth} exceeds max_depth {max_depth}")
                continue
            
            self.logger.info(f"📁 Exploring directory (depth {depth}/{max_depth}): {current_dir} ({len(discovered_directories)} total discovered, {len(directories_to_explore)} in queue)")

            try:
                page = await context.new_page()
                await page.goto(current_dir, timeout=self.config.page_load_timeout * 1000)

                # Wait for page to stabilize
                await asyncio.sleep(self.config.wait_after_load)

                # NO popup handling in Phase 1 - each Phase 2 browser handles its own popups independently

                # Extract all links and identify directory paths
                directory_paths = await self._extract_directory_paths(page, current_dir, base_domain)

                # Add new directories to exploration queue
                new_directories = 0
                added_to_queue = 0
                added_to_store = 0
                for dir_path in directory_paths:
                    if dir_path not in discovered_directories:
                        discovered_directories.add(dir_path)
                        new_directories += 1
                        
                        # Write to SQLite store if available (for persistent tracking)
                        if self.url_store:
                            if self.url_store.add_url(dir_path):
                                added_to_store += 1
                        
                        if dir_path not in explored_directories:
                            directories_to_explore.append(dir_path)
                            added_to_queue += 1
                            self.logger.debug(f"   ➕ Added directory to queue: {dir_path}")

                if new_directories > 0:
                    store_msg = f", {added_to_store} saved to store" if self.url_store else ""
                    self.logger.info(f"   ✅ Found {new_directories} new directories on this page ({added_to_queue} added to queue, {new_directories - added_to_queue} already explored{store_msg})")

                await page.close()

            except Exception as e:
                self.logger.warning(f"⚠️ Error exploring directory {current_dir}: {e}")
                continue

        self.logger.info(f"✅ No more directories to explore. Discovery complete.")

        self.logger.info(f"📂 Recursive directory discovery completed: {len(discovered_directories)} directories found")
        return discovered_directories

    async def _extract_directory_paths(self, page: Page, current_url: str, base_domain: str) -> Set[str]:
        """
        Extract directory paths from all links on a page.

        Focuses on identifying directory structures rather than individual pages.
        No depth limit - extracts all valid directory paths.

        Args:
            page: Playwright page object
            current_url: Current directory URL being explored
            base_domain: Base domain to stay within

        Returns:
            Set of directory URLs found on this page
        """
        directory_paths = set()

        try:
            # Get all links on the page
            links = await page.query_selector_all('a[href]')
            self.logger.info(f"🔗 Found {len(links)} total links on {current_url}")

            for link in links:
                try:
                    href = await link.get_attribute('href')
                    if not href:
                        continue

                    full_url = urljoin(current_url, href)
                    parsed_url = urlparse(full_url)

                    # Only process URLs from the same domain
                    if parsed_url.netloc != base_domain or parsed_url.scheme not in ['http', 'https']:
                        continue

                    # Normalize the URL path
                    normalized_url = self._normalize_url(parsed_url)

                    # Only add if it's a valid directory path (not a file)
                    if normalized_url and self._is_valid_directory(normalized_url, current_url):
                        directory_paths.add(normalized_url)
                        self.logger.debug(f"      ✓ Valid directory: {normalized_url}")
                    else:
                        self.logger.debug(f"      ✗ Skipped (not valid directory): {normalized_url or full_url}")

                except Exception as e:
                    # Skip problematic links
                    self.logger.debug(f"   Skipping link due to error: {e}")
                    continue

            self.logger.info(f"📁 Extracted {len(directory_paths)} directory paths from {current_url}")

        except Exception as e:
            self.logger.error(f"❌ Error extracting directory paths from {current_url}: {e}")

        return directory_paths

    def _normalize_url(self, parsed_url) -> str:
        """
        Normalize a URL to represent a directory structure.

        Removes file extensions, query parameters, and fragments to focus on directory paths.
        Ensures consistent trailing slash format.

        Args:
            parsed_url: Parsed URL object

        Returns:
            Normalized directory URL string, or None if invalid
        """
        path = parsed_url.path

        # Remove query parameters and fragments
        # (already handled by urlparse, but ensure clean path)
        path = path.split('?')[0].split('#')[0]

        # Remove common file extensions
        file_extensions = [
            '.html', '.htm', '.php', '.jsp', '.asp', '.aspx', 
            '.py', '.js', '.css', '.json', '.xml',
            '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.zip', '.tar', '.gz', '.rar',
            '.mp4', '.mp3', '.avi', '.mov', '.wmv',
            '.woff', '.woff2', '.ttf', '.eot'
        ]
        
        path_lower = path.lower()
        for ext in file_extensions:
            if path_lower.endswith(ext):
                path = path[:-len(ext)]
                break

        # Handle root path
        if not path or path == '/':
            path = '/'
        else:
            # Ensure it ends with / for directories (except root)
            if not path.endswith('/'):
                path += '/'

        # Construct full directory URL
        dir_url = f"{parsed_url.scheme}://{parsed_url.netloc}{path}"
        return dir_url

    def _is_valid_directory(self, url: str, base_url: str) -> bool:
        """
        Determine if a URL represents a valid directory path worth exploring.

        NO DEPTH LIMIT - explores all nested directories.
        Only filters out obvious files and sensitive paths.

        Args:
            url: URL to check
            base_url: Base URL for comparison

        Returns:
            True if URL represents a valid directory path
        """
        parsed_url = urlparse(url)

        # Always include the base URL
        if url.rstrip('/') == base_url.rstrip('/'):
            return True

        # NO DEPTH LIMIT - removed the len(path_parts) > 5 check
        # Explore all nested directories

        # Skip obvious file paths (check last path segment)
        path_parts = [p for p in parsed_url.path.strip('/').split('/') if p]
        if path_parts:
            last_part = path_parts[-1]
            # Check if last part looks like a file (has extension)
            if '.' in last_part:
                extension = last_part.split('.')[-1].lower()
                # Common file extensions (already handled in _normalize_url, but double-check)
                file_extensions = ['html', 'htm', 'php', 'jsp', 'asp', 'aspx', 'py', 'js', 'css', 
                                 'jpg', 'jpeg', 'png', 'gif', 'pdf', 'doc', 'docx', 'zip', 'tar', 'gz']
                if extension in file_extensions and len(extension) <= 4:
                    return False

        # Skip common non-directory paths (sensitive areas)
        skip_patterns = [
            'search', 'login', 'register', 'signin', 'signup', 'sign-in', 'sign-up',
            'cart', 'checkout', 'payment', 'billing',
            'admin', 'wp-admin', 'administrator', 'dashboard',
            'api', 'feed', 'rss', 'atom',
            'logout', 'log-out', 'signout', 'sign-out',
            'profile', 'account', 'settings', 'preferences'
        ]
        
        url_lower = url.lower()
        for pattern in skip_patterns:
            # Only skip if pattern is a complete path segment, not just part of a word
            if f'/{pattern}/' in url_lower or url_lower.endswith(f'/{pattern}') or url_lower.startswith(f'{pattern}/'):
                return False

        return True


