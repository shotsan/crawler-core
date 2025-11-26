#!/usr/bin/env python3
"""
Script to view and export SQLite database contents from the crawler.
"""

import sqlite3
import json
import csv
import sys
from pathlib import Path
from datetime import datetime


def view_database(db_path: str, output_format: str = 'text', output_file: str = None):
    """
    View database contents in various formats.

    Args:
        db_path: Path to SQLite database
        output_format: 'text', 'json', or 'csv'
        output_file: Optional output file path
    """
    if not Path(db_path).exists():
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all data
    cursor.execute("""
        SELECT url, status, domain, discovered_at, scraped_at
        FROM urls
        ORDER BY discovered_at
    """)
    rows = cursor.fetchall()

    # Get stats
    cursor.execute("SELECT COUNT(*) FROM urls")
    total_count = cursor.fetchone()[0]

    cursor.execute("SELECT status, COUNT(*) FROM urls GROUP BY status")
    status_counts = dict(cursor.fetchall())

    conn.close()

    if output_format == 'text':
        output = f"""Database: {db_path}
Total URLs: {total_count}

Status Summary:
"""

        for status, count in status_counts.items():
            output += f"  {status}: {count}\n"

        output += "\nURLs:\n"
        for row in rows:
            url, status, domain, discovered, scraped = row
            discovered_str = discovered or 'N/A'
            scraped_str = scraped or 'N/A'
            output += f"  URL: {url}\n"
            output += f"  Status: {status}\n"
            output += f"  Domain: {domain}\n"
            output += f"  Discovered: {discovered_str}\n"
            output += f"  Scraped: {scraped_str}\n"
            output += "-" * 80 + "\n"

    elif output_format == 'json':
        data = {
            'database': str(db_path),
            'total_urls': total_count,
            'status_counts': status_counts,
            'urls': [
                {
                    'url': row[0],
                    'status': row[1],
                    'domain': row[2],
                    'discovered_at': row[3],
                    'scraped_at': row[4]
                } for row in rows
            ]
        }
        output = json.dumps(data, indent=2, default=str)

    elif output_format == 'csv':
        output = "url,status,domain,discovered_at,scraped_at\n"
        for row in rows:
            # Escape commas in URLs if needed
            url = f'"{row[0]}"' if ',' in row[0] else row[0]
            line = f"{url},{row[1]},{row[2]},{row[3] or ''},{row[4] or ''}\n"
            output += line

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Exported to: {output_file}")
    else:
        print(output)


def main():
    if len(sys.argv) < 2:
        print("Usage: python view_db.py <db_path> [format] [output_file]")
        print("Formats: text (default), json, csv")
        print("Example: python view_db.py crawled_data/zerodha_2025_11_21_22_49/urls.db json urls.json")
        return

    db_path = sys.argv[1]
    output_format = sys.argv[2] if len(sys.argv) > 2 else 'text'
    output_file = sys.argv[3] if len(sys.argv) > 3 else None

    if output_format not in ['text', 'json', 'csv']:
        print("Invalid format. Use: text, json, or csv")
        return

    view_database(db_path, output_format, output_file)


if __name__ == '__main__':
    main()

