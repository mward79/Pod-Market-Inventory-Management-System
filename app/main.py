"""
POD Market Inventory Management System - command-line application.

Usage (from the project root):
    python app/main.py             open pod_market.db in the project root
                                   (built from schema.sql and insert_data.sql
                                   if it doesn't exist yet)
    python app/main.py --reset     rebuild pod_market.db from the SQL files
    python app/main.py --db PATH   use a different database file
"""

import argparse
import os
import sqlite3
import sys

import db
import operations
import reports
from ui import Cancelled, choose, pause

MENU = [
    ("Find a product", operations.search_products),
    ("View stock at a location", operations.view_location_stock),
    ("View recent sales at a location", operations.view_recent_sales),
    ("Receive a delivery", operations.receive_delivery),
    ("Log expired or damaged items", operations.log_waste),
    ("Transfer stock between locations", operations.transfer_stock),
    ("Add a new product", operations.add_product),
    ("Edit a product (price, eligibility, status, reorder level)",
     operations.edit_product),
    ("Reports", reports.reports_menu),
]


def parse_args():
    parser = argparse.ArgumentParser(description="POD Market inventory app")
    parser.add_argument("--db", default=db.DEFAULT_DB_PATH,
                        help="path to the SQLite database file")
    parser.add_argument("--reset", action="store_true",
                        help="rebuild the database from schema.sql and insert_data.sql")
    return parser.parse_args()


def open_database(args):
    if args.reset or not os.path.exists(args.db):
        print("Building the database from schema.sql and insert_data.sql...")
        db.build_database(args.db)
    conn = db.connect(args.db)
    # Make sure the file really is this project's database.
    try:
        conn.execute("SELECT 1 FROM locations LIMIT 1")
    except sqlite3.Error:
        conn.close()
        raise db.AppError("The database file is missing the project tables. "
                          "Run: python app/main.py --reset")
    return conn


def run_action(conn, action):
    """Run one menu action and report any problem in plain language."""
    try:
        action(conn)
    except Cancelled:
        print("\nCancelled. No changes were made.")
    except db.AppError as exc:
        print(f"\n{exc}")
    except sqlite3.Error as exc:
        # Any open transaction was already rolled back by "with conn:".
        print(f"\n{db.friendly_error(exc)}")


def main():
    args = parse_args()
    try:
        conn = open_database(args)
    except db.AppError as exc:
        print(exc)
        sys.exit(1)
    except sqlite3.Error as exc:
        print(f"Could not open the database: {db.friendly_error(exc)}")
        sys.exit(1)

    try:
        print("\n=== POD Market Inventory Management ===")
        print("(Type q at any prompt to cancel and return to the menu.)")
        while True:
            options = [(label, fn) for label, fn in MENU] + [("Exit", None)]
            try:
                action = choose("Main menu:", options)
            except Cancelled:
                action = None
            if action is None:
                break
            run_action(conn, action)
            pause()
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        conn.close()
        print("Database connection closed. Goodbye.")


if __name__ == "__main__":
    main()
