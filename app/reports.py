"""
reports.py - Summary reports. All filtering, joining, grouping, and
totals are done in SQL; Python only collects the options and prints.
"""

import datetime

from ui import choose, print_table, prompt_date, prompt_int, prompt_yes_no
from operations import pick_location


def default_report_date(conn):
    """
    Date of the most recent activity (sale, delivery, waste, or transfer),
    or today if there is none. The sample data ends on 2026-10-22, so this
    keeps date-based reports meaningful on the sample data, and moves
    forward on its own as new activity is recorded.
    """
    row = conn.execute(
        """SELECT date(MAX(at)) FROM (
               SELECT MAX(sold_at)        AS at FROM sales_transactions
               UNION ALL SELECT MAX(received_at)    FROM deliveries
               UNION ALL SELECT MAX(recorded_at)    FROM waste_records
               UNION ALL SELECT MAX(transferred_at) FROM stock_transfers)"""
    ).fetchone()
    return row[0] or datetime.date.today().isoformat()


def prompt_date_range(conn):
    end = prompt_date("End date", default_report_date(conn))
    default_start = (datetime.date.fromisoformat(end)
                     - datetime.timedelta(days=30)).isoformat()
    while True:
        start = prompt_date("Start date", default_start)
        if start <= end:
            return start, end
        print("  The start date must be on or before the end date.")


def optional_location(conn):
    """Returns a location_id, or None for all locations."""
    if prompt_yes_no("Limit to one location?", default=False):
        return pick_location(conn)[0]
    return None


# ---------------------------------------------------------------------

def reorder_list(conn):
    """Uses the v_low_stock view: items at or below reorder level."""
    location_id = optional_location(conn)
    rows = conn.execute(
        """SELECT COALESCE(preferred_supplier, '(none)') AS supplier,
                  location_name AS location, sku, product_name AS product,
                  quantity_on_hand AS on_hand, reorder_level,
                  units_below_reorder AS short_by
           FROM v_low_stock
           WHERE (? IS NULL OR location_id = ?)
           ORDER BY supplier, location, short_by DESC""",
        (location_id, location_id),
    ).fetchall()
    print("\nReorder list, grouped by cheapest active supplier:")
    print_table(rows, empty_message="Nothing needs reordering.")


def expiring_items(conn):
    as_of = prompt_date("Check as of", default_report_date(conn))
    days = prompt_int("Expiring within how many days?", 0, 365, default=3)
    grab_and_go_only = prompt_yes_no("Only grab-and-go items?", default=True)
    rows = conn.execute(
        """SELECT di.expires_at, l.name AS location, p.name AS product,
                  di.lot_code, di.quantity_received AS qty_received,
                  CAST(julianday(di.expires_at) - julianday(?) AS INTEGER)
                      AS days_left
           FROM delivery_items AS di
           JOIN deliveries AS d ON d.delivery_id = di.delivery_id
           JOIN locations  AS l ON l.location_id = d.location_id
           JOIN products   AS p ON p.product_id  = di.product_id
           WHERE di.expires_at BETWEEN ? AND date(?, '+' || ? || ' days')
             AND (? = 0 OR p.category = 'Grab-and-Go')
           ORDER BY di.expires_at, l.name, p.name""",
        (as_of, as_of, as_of, days, int(grab_and_go_only)),
    ).fetchall()
    print(f"\nLots expiring from {as_of} through {days} day(s) later:")
    print_table(rows, empty_message="No lots expire in that window.")


def best_sellers(conn):
    start, end = prompt_date_range(conn)
    location_id = optional_location(conn)
    top_n = prompt_int("How many products to show?", 1, 100, default=10)
    rows = conn.execute(
        """SELECT p.name AS product, p.category,
                  SUM(si.quantity)                          AS units_sold,
                  ROUND(SUM(si.quantity * si.unit_price), 2) AS revenue,
                  COUNT(DISTINCT st.sale_id)                AS sales
           FROM sale_items AS si
           JOIN sales_transactions AS st ON st.sale_id = si.sale_id
           JOIN products           AS p  ON p.product_id = si.product_id
           WHERE date(st.sold_at) BETWEEN ? AND ?
             AND (? IS NULL OR st.location_id = ?)
           GROUP BY p.product_id
           ORDER BY units_sold DESC, revenue DESC
           LIMIT ?""",
        (start, end, location_id, location_id, top_n),
    ).fetchall()
    print(f"\nBest sellers, {start} to {end}:")
    print_table(rows, empty_message="No sales in that period.")


def payment_mix(conn):
    start, end = prompt_date_range(conn)
    # The window function computes each location's total so each payment
    # method can be shown as a percentage of that location's sales.
    rows = conn.execute(
        """SELECT location, payment_method, sales, revenue,
                  ROUND(100.0 * revenue / SUM(revenue) OVER (PARTITION BY location), 1)
                      AS pct_of_location
           FROM (SELECT l.name AS location, st.payment_method,
                        COUNT(*) AS sales,
                        ROUND(SUM(st.total_amount), 2) AS revenue
                 FROM sales_transactions AS st
                 JOIN locations AS l ON l.location_id = st.location_id
                 WHERE date(st.sold_at) BETWEEN ? AND ?
                 GROUP BY l.location_id, st.payment_method)
           ORDER BY location, revenue DESC""",
        (start, end),
    ).fetchall()
    print(f"\nSales by payment method, {start} to {end}:")
    print_table(rows, empty_message="No sales in that period.")


def waste_report(conn):
    start, end = prompt_date_range(conn)
    rows = conn.execute(
        """SELECT l.name AS location, p.category,
                  COUNT(*)                                AS records,
                  SUM(w.quantity)                         AS units,
                  ROUND(SUM(w.quantity * w.unit_cost), 2) AS cost_lost
           FROM waste_records AS w
           JOIN locations AS l ON l.location_id = w.location_id
           JOIN products  AS p ON p.product_id  = w.product_id
           WHERE date(w.recorded_at) BETWEEN ? AND ?
           GROUP BY l.location_id, p.category
           ORDER BY cost_lost DESC""",
        (start, end),
    ).fetchall()
    print(f"\nWaste cost by location and category, {start} to {end}:")
    print_table(rows, empty_message="No waste recorded in that period.")
    if rows:
        total = conn.execute(
            """SELECT ROUND(SUM(quantity * unit_cost), 2) FROM waste_records
               WHERE date(recorded_at) BETWEEN ? AND ?""",
            (start, end),
        ).fetchone()[0]
        print(f"  Total cost lost: ${total:.2f}")


def supplier_spending(conn):
    start, end = prompt_date_range(conn)
    rows = conn.execute(
        """SELECT supplier_name AS supplier, location_name AS location,
                  COUNT(*)               AS deliveries,
                  SUM(total_units)       AS units,
                  ROUND(SUM(total_cost), 2) AS total_spent
           FROM v_delivery_summary
           WHERE date(received_at) BETWEEN ? AND ?
           GROUP BY supplier_id, location_id
           ORDER BY supplier, total_spent DESC""",
        (start, end),
    ).fetchall()
    print(f"\nSupplier spending by location, {start} to {end}:")
    print_table(rows, empty_message="No deliveries in that period.")


REPORTS = [
    ("Reorder list (low stock, by supplier)", reorder_list),
    ("Items expiring soon", expiring_items),
    ("Best-selling products", best_sellers),
    ("Sales by payment method (meal swipe / dining dollars / card)", payment_mix),
    ("Waste cost by location and category", waste_report),
    ("Spending with each supplier", supplier_spending),
]


def reports_menu(conn):
    report = choose("Reports:", [(label, fn) for label, fn in REPORTS])
    report(conn)
