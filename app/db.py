"""
db.py - Database connection and error handling for the POD Market app.

All database access goes through a single sqlite3 connection opened here.
Foreign-key enforcement is turned on for that connection, because SQLite
leaves it off by default.
"""

import os
import sqlite3

# The app lives in app/; the SQL files and the database file are in the
# project root, shared with run_queries.sh.
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)
DEFAULT_DB_PATH = os.path.join(PROJECT_DIR, "pod_market.db")
SCHEMA_FILE = os.path.join(PROJECT_DIR, "schema.sql")
DATA_FILE = os.path.join(PROJECT_DIR, "insert_data.sql")


class AppError(Exception):
    """An error with a message that is safe to show to the user."""


def connect(db_path):
    """Open the database and enable foreign keys for this connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row          # rows can be read by column name
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def build_database(db_path):
    """Create a fresh database from schema.sql and insert_data.sql."""
    for path in (SCHEMA_FILE, DATA_FILE):
        if not os.path.exists(path):
            raise AppError(f"Cannot build the database: {os.path.basename(path)} "
                           "is missing from the project folder.")
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    try:
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            conn.executescript(f.read())
        with open(DATA_FILE, encoding="utf-8") as f:
            conn.executescript(f.read())
    finally:
        conn.close()


def friendly_error(exc):
    """Turn a sqlite3 exception into a short message for the user."""
    text = str(exc)
    if isinstance(exc, sqlite3.IntegrityError):
        if "UNIQUE" in text:
            return "That record already exists (duplicate value)."
        if "FOREIGN KEY" in text:
            return "A related record does not exist, so the change was not saved."
        if "CHECK" in text:
            return "The change breaks a data rule (for example, stock cannot go below zero)."
        if "NOT NULL" in text:
            return "A required value was missing."
        return "The change conflicts with existing data and was not saved."
    if isinstance(exc, sqlite3.OperationalError):
        if "locked" in text:
            return "The database is busy. Please try again."
        return "The database could not complete that operation."
    return "A database error occurred. No changes were saved."
