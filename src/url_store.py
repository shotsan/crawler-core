"""
URL Store module using SQLite for persistent URL tracking and duplicate prevention.
Handles concurrent read/write operations safely using SQLite's built-in locking.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class URLStore:
    """
    SQLite-based URL store for tracking discovered and scraped URLs.
    Prevents duplicates and handles concurrent access safely.
    """

    def __init__(self, db_path: str, domain: str):
        """
        Initialize URL store for a specific domain.

        Args:
            db_path: Path to SQLite database file
            domain: Domain name for this store
        """
        self.db_path = Path(db_path)
        self.domain = domain
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database and create table if it doesn't exist."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
        conn.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                url TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                domain TEXT NOT NULL,
                discovered_at TIMESTAMP,
                scraped_at TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status_domain ON urls(status, domain)")
        conn.commit()
        conn.close()
        logger.debug(f"Initialized URL store database: {self.db_path}")

    def add_url(self, url: str) -> bool:
        """
        Add URL to store with status='pending'.
        Uses INSERT OR IGNORE to prevent duplicates.

        Args:
            url: URL to add

        Returns:
            True if URL was added (new), False if it already existed
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO urls (url, status, domain, discovered_at)
                VALUES (?, 'pending', ?, ?)
            """, (url, self.domain, datetime.now()))
            was_added = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return was_added
        except sqlite3.Error as e:
            logger.error(f"Error adding URL to store: {e}")
            return False

    def get_pending_count(self) -> int:
        """
        Get count of pending URLs for this domain.

        Returns:
            Number of pending URLs
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM urls
                WHERE status = 'pending' AND domain = ?
            """, (self.domain,))
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except sqlite3.Error as e:
            logger.error(f"Error getting pending count: {e}")
            return 0

    def get_next_pending_url(self) -> Optional[str]:
        """
        Atomically get and mark one pending URL as 'processing'.
        This prevents duplicate processing across multiple workers.

        Returns:
            URL string if found, None if no pending URLs
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.execute("BEGIN IMMEDIATE")  # Start transaction with immediate lock
            cursor = conn.cursor()
            # Get one pending URL
            cursor.execute("""
                SELECT url FROM urls
                WHERE status = 'pending' AND domain = ?
                LIMIT 1
            """, (self.domain,))
            result = cursor.fetchone()
            if result:
                url = result[0]
                # Mark it as processing
                cursor.execute("""
                    UPDATE urls
                    SET status = 'processing'
                    WHERE url = ?
                """, (url,))
                conn.commit()
                conn.close()
                return url
            else:
                conn.commit()
                conn.close()
                return None
        except sqlite3.Error as e:
            logger.error(f"Error getting next pending URL: {e}")
            try:
                conn.rollback()
                conn.close()
            except:
                pass
            return None

    def mark_completed(self, url: str):
        """
        Mark URL as completed with timestamp.

        Args:
            url: URL to mark as completed
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.execute("""
                UPDATE urls
                SET status = 'completed', scraped_at = ?
                WHERE url = ?
            """, (datetime.now(), url))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error marking URL as completed: {e}")

    def mark_failed(self, url: str):
        """
        Mark URL as failed (reset to pending for retry, or keep as processing).

        Args:
            url: URL that failed
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            # Reset to pending so it can be retried
            conn.execute("""
                UPDATE urls
                SET status = 'pending'
                WHERE url = ?
            """, (url,))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error marking URL as failed: {e}")

    def get_all_pending_urls(self) -> list:
        """
        Get all pending URLs (for batch operations if needed).
        Note: This doesn't mark them as processing - use get_next_pending_url() for that.

        Returns:
            List of pending URL strings
        """
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT url FROM urls
                WHERE status = 'pending' AND domain = ?
            """, (self.domain,))
            urls = [row[0] for row in cursor.fetchall()]
            conn.close()
            return urls
        except sqlite3.Error as e:
            logger.error(f"Error getting all pending URLs: {e}")
            return []

