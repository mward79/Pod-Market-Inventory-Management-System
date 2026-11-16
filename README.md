# POD Market Inventory Management System

A database-backed inventory system for the POD Market convenience stores on
campus, with an interactive Python command-line application.

## Project Overview

**What it does.** Each of the five POD Market locations (Hess, Hodges,
Laurel, Rocky Top, and Zeanah) sells largely the same catalog of
snacks, drinks, grab-and-go meals, and everyday items, but keeps its own
stock. The system tracks products, stock at each location, supplier
catalogs and deliveries (with lot codes and expiration dates), sales
(including meal swipes and dining dollars), stock transfers between
locations, and items removed as expired or damaged. It answers questions
such as what needs reordering, what is about to expire, what sells best,
how customers pay, and how much product is being wasted.

**Intended users.**
- *Store employees* receive deliveries, log expired or damaged items, and
  check stock at their location.
- *Store managers* move stock between locations, maintain the product
  catalog, and use reports to make reordering decisions.

**Major functionality.** Finding products, stock and recent sales by
location, recording sales, receiving deliveries, logging waste, transferring stock, adding
and editing products, and six reports (see
[Major Application Operations](#major-application-operations)).

The system assumes sales are recorded automatically by the store's
registers (`transaction.sql` shows the SQL a register would run for one
sale). The app displays sales, uses them in reports, and includes a manual
"record a sale" option as a backup, for example when a register is down.

Users never need to remember IDs or SKUs: they choose locations, people,
suppliers, and products from numbered lists, and can narrow a product list
by typing part of the name.

## Repository Contents

| File | Purpose |
|---|---|
| `erd.pdf`, `erd.png` | Final ER diagram (13 tables) |
| `schema.sql` | Creates all tables, constraints, 2 views, and 3 indexes |
| `insert_data.sql` | Synthetic sample data (294 rows) |
| `queries.sql` | The 9 required SQL queries, each labeled |
| `transaction.sql` | Transaction example (records a sale, then rolls back) |
| `run_queries.sh` | Rebuilds the database and runs `queries.sql` and `transaction.sql` |
| `select_all.sql` | Shows every row in every table (optional, for checking data) |
| `app/main.py` | Application entry point and main menu |
| `app/db.py` | Database connection, database build, friendly error messages |
| `app/ui.py` | Validated input prompts and table output |
| `app/operations.py` | Store operations (find products, stock, sales, deliveries, waste, transfers, products) |
| `app/reports.py` | Summary reports |
| `.gitignore` | Keeps the generated database file out of the repository |
| `.gitattributes` | Keeps Unix line endings so `run_queries.sh` works on every system |

## DBMS

**SQLite 3.** The database is a single local file (`pod_market.db`) created
from the SQL files in this repository. No server, hosted service, account,
password, or connection string is used, so there are no credentials and no
configuration template is needed.

## Database Setup

**Required software:** the `sqlite3` command-line program (SQLite 3.33 or
later, for `.mode box` output) and Bash, to run the SQL files directly. The application can also
build the database by itself without the `sqlite3` program (see
[Application Setup](#application-setup)).

**File order:** `schema.sql`, then `insert_data.sql`. `schema.sql` drops
every object first, so running it again rebuilds the database from scratch.

**Option A - build the database and run all required SQL (recommended):**

```bash
bash run_queries.sh
```

This deletes any old `pod_market.db`, runs `schema.sql` and
`insert_data.sql`, runs `queries.sql` and displays the results, then runs
`transaction.sql`.

**Option B - build the database only:**

```bash
sqlite3 pod_market.db ".read schema.sql" ".read insert_data.sql"
```

To see every row in every table afterward:

```bash
sqlite3 pod_market.db ".read select_all.sql"
```

**SQLite-specific notes:**
- Foreign keys are only enforced when `PRAGMA foreign_keys = ON;` is run on
  a connection. All the SQL files and the application turn it on.
- Column types are SQLite types: `INTEGER`, `TEXT`, and `REAL`. Booleans are
  `INTEGER` 0/1, enforced by `CHECK` constraints. Timestamps are `TEXT`
  (`YYYY-MM-DD HH:MM:SS`) and dates are `TEXT` (`YYYY-MM-DD`).
- `transaction.sql` ends with `ROLLBACK`, so running it leaves the sample
  data unchanged.

## Application Setup

- **Language:** Python 3.8 or later (tested with Python 3.13).
- **Packages:** Python standard library only (`sqlite3`, `argparse`,
  `datetime`, `os`). Nothing needs to be installed with pip, so there is no
  `requirements.txt`.
- **Database connection:** the app uses `pod_market.db` in the repository
  root, the same file `run_queries.sh` creates. If the file doesn't exist,
  the app builds it from `schema.sql` and `insert_data.sql`.

Start the app from the repository root:

```bash
python app/main.py
```

(Use `python3` if that is how Python 3 is run on your system.)

Other options:

```bash
python app/main.py --reset          # rebuild the database with fresh sample data
python app/main.py --db other.db    # use a different database file
```

Choose operations by number. Type `q` at any prompt to cancel the current
operation without saving anything. Choose **11 Exit** (or type `q` at the main
menu) to quit; the database connection is closed on exit.

## Major Application Operations

| Menu | Operation | Database work |
|---|---|---|
| 1 | **Find a product** - filter by part of the name, category, and status; pick a result by number to see its stock at every location and its suppliers | Search (`LIKE`, `LEFT JOIN`, `GROUP BY`); related data (joins across 5 tables) |
| 2 | **View stock at a location**, optionally only low-stock items | Join of `location_inventory` and `products` |
| 3 | **View recent sales at a location** - each sale with its cashier, payment method, and items | Join of `sales_transactions`, `employees`, `sale_items`, and `products` |
| 4 | **Record a sale manually** - a backup for when a register is down: choose the store, cashier, and payment method, then pick the products sold; meal swipes only accept swipe-eligible products | `INSERT` sale and line items, `UPDATE` stock, in one transaction |
| 5 | **Receive a delivery** - choose the supplier, then pick the products that arrived from that supplier's catalog, with quantities, costs, lot codes, and expiration dates | `INSERT` delivery and line items, `UPDATE` stock, in one transaction |
| 6 | **Log expired or damaged items** | `INSERT` waste records, `UPDATE` stock, in one transaction |
| 7 | **Transfer stock between locations** | `INSERT` transfer and items, `UPDATE` both locations' stock, in one transaction |
| 8 | **Add a new product** and set it up at every location (the next SKU is suggested) | `INSERT` product and inventory rows, in one transaction |
| 9 | **Edit a product** - price, cost, meal-swipe eligibility, active status, or a location's reorder level | `UPDATE` |
| 10 | **Reports** (below) | Joins, aggregates, `GROUP BY`, views |

Reports (menu 10):
1. **Reorder list** - items at or below reorder level, grouped by the cheapest
   active supplier (`v_low_stock` view)
2. **Items expiring soon** - delivered lots expiring within N days
3. **Best-selling products** in a date range
4. **Sales by payment method** - meal swipe, dining dollars, and card as a
   share of each location's sales
5. **Waste cost** by location and category
6. **Spending with each supplier** (`v_delivery_summary` view)

**Mapping to the required operation types:** search = 1; related data = 1
(product details), 2, and 3; add = 4, 5, and 8; update = 9; report = 10;
additional = 6 and 7.

**Safety and validation.** Every SQL statement with user input uses `?`
placeholders. Input is validated (menu numbers, quantities, prices, dates,
duplicate SKUs and invoice numbers, stock available, meal-swipe eligibility,
expiration dates that have already passed, a transfer to the same location). Database errors are shown as short
messages instead of raw errors. Multi-table changes run inside a
transaction, so a failure rolls back the whole operation.

### Checking that changes are saved

After receiving a delivery in the app, confirm it is in the database:

```bash
sqlite3 -header -column pod_market.db \
  "SELECT * FROM v_delivery_summary ORDER BY delivery_id DESC LIMIT 1;"
```

The app's own screens also read from the database each time, so option 2
(stock at a location) shows the increased stock right away.

## Database Design Summary

- **Many-to-many relationships**, each resolved by a junction table:
  Locations-Products (`location_inventory`), Suppliers-Products
  (`supplier_products`), Sales-Products (`sale_items`), and
  Transfers-Products (`transfer_items`).
- **Views:** `v_low_stock` (what needs reordering, where, and from whom) and
  `v_delivery_summary` (each delivery's totals calculated from its line items).
- **Indexes:** `sales_transactions(location_id, sold_at)` for sales reports
  by location and date; `sale_items(product_id)` for best-seller joins;
  `delivery_items(expires_at)` for expiration lookups.
- **Constraints** include allowed values for payment method, transfer status,
  waste reason, category, and role; non-negative stock; positive quantities;
  unique SKUs, employee numbers, and supplier invoice numbers; and a rule
  that a transfer's two locations must differ.

## Known Limitations

- **Sample dates.** The sample data runs from 2026-09-08 to 2026-10-22.
  `queries.sql` uses 2026-10-22 as a fixed report date so results don't
  change. The app's report date prompts default to the date of the most
  recent activity in the database (sale, delivery, waste, or transfer), so
  after something new is recorded, the defaults move to that date. Type a
  date in the sample range to report on the sample data.
- **Stock is a snapshot.** `location_inventory` holds counted stock as of
  October 21-22, so in the sample data it is not exactly deliveries minus
  sales, waste, and transfers. Changes made through the app keep it
  consistent from then on.
- **Sales are assumed to come from the registers.** The system is designed
  for sales to be recorded automatically by the store's registers, but this
  project has no connection to real registers. The manual "Record a sale"
  option stands in for them and writes sales the same way a register would.
- **Supplier catalogs** are in the database but are not edited through the
  app. Transfers made in the app are completed immediately; the Requested
  and In Transit statuses appear only in the sample data.
- **Expiring-items report** lists delivered lots by expiration date. It does
  not track how many units of each lot are still on the shelf.
- **Single user.** SQLite is a local file, so the app is meant for one user
  at a time. There is no login; any employee in the list can be chosen.
- **Money is stored as REAL.** Amounts are rounded to cents when stored and
  reported.
