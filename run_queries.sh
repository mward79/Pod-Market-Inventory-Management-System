#!/bin/bash
# POD Market Inventory Management System
# Recreates the database from scratch, runs the queries, then runs the
# transaction example. Run from the folder containing the SQL files:
#     bash run_queries.sh

DB="pod_market.db"

echo "Recreating database..."
rm -f "$DB"

sqlite3 -bail "$DB" < schema.sql || { echo "schema.sql failed."; exit 1; }
sqlite3 -bail "$DB" < insert_data.sql || { echo "insert_data.sql failed."; exit 1; }

echo
echo "Running queries..."
sqlite3 -header -column "$DB" < queries.sql

echo
echo "Running transaction..."
sqlite3 -bail -header -column "$DB" < transaction.sql
status=$?

if [ "$status" -eq 0 ]; then
    echo "Transaction completed successfully."
else
    echo "Transaction failed."
    echo "Uncommitted changes were rolled back."
fi

echo
echo "Done."
