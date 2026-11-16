"""
operations.py - Store operations: finding products, viewing stock and
sales, recording sales, receiving deliveries, logging waste, transferring
stock, and maintaining the product catalog.

The system assumes sales are normally recorded automatically by the
store's registers. record_sale is a manual backup (for example, when a
register is down) that writes a sale the same way a register would.

Every SQL statement that includes a user-supplied value uses ? placeholders.
Operations that change several tables run inside "with conn:", which
commits if every statement succeeds and rolls back all of them if any
statement (or a check in between) fails.
"""

import datetime

from db import AppError
from ui import (choose, print_table, prompt_date, prompt_int, prompt_money,
                prompt_text, prompt_yes_no)

# Allowed values come from the CHECK constraints in schema.sql. They are
# listed here only to build menus; the database still enforces them.
CATEGORIES = ["Beverages", "Snacks", "Grab-and-Go", "Frozen",
              "Household", "Health & Beauty"]
WASTE_REASONS = ["Expired", "Damaged", "Recalled", "Other"]
PAYMENT_METHODS = ["Meal Swipe", "Dining Dollars", "Card"]


def now_timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------
# Shared pickers: the user chooses from numbered lists, so nobody has to
# remember IDs or SKUs.
# ---------------------------------------------------------------------

def pick_location(conn, title="Select a location:", exclude_id=None):
    """Let the user choose an active location; returns (id, name)."""
    rows = conn.execute(
        """SELECT location_id, name, building
           FROM locations
           WHERE is_active = 1 AND location_id IS NOT ?
           ORDER BY name""",
        (exclude_id,),
    ).fetchall()
    if not rows:
        raise AppError("There are no other active locations to choose from.")
    options = [(f"{r['name']} ({r['building']})", (r["location_id"], r["name"]))
               for r in rows]
    return choose(title, options)


def pick_employee(conn, location_id, title="Who is recording this?"):
    """Let the user choose an active employee at a location; returns id."""
    rows = conn.execute(
        """SELECT employee_id, name, role
           FROM employees
           WHERE location_id = ? AND is_active = 1
           ORDER BY name""",
        (location_id,),
    ).fetchall()
    if not rows:
        raise AppError("No active employees are assigned to that location.")
    return choose(title, [(f"{r['name']} ({r['role']})", r["employee_id"])
                          for r in rows])


def pick_supplier(conn):
    """Let the user choose an active supplier that has products on file."""
    rows = conn.execute(
        """SELECT s.supplier_id, s.name, COUNT(sp.product_id) AS products
           FROM suppliers AS s
           JOIN supplier_products AS sp ON sp.supplier_id = s.supplier_id
           WHERE s.is_active = 1
           GROUP BY s.supplier_id
           ORDER BY s.name""",
    ).fetchall()
    if not rows:
        raise AppError("There are no active suppliers with products on file.")
    return choose("Which supplier is the delivery from?",
                  [(f"{r['name']} ({r['products']} products)",
                    (r["supplier_id"], r["name"])) for r in rows])


def pick_product(conn, title="Which product?", location_id=None,
                 carried_only=False, supplier_id=None, include_inactive=False):
    """
    Let the user type part of a product name (or press Enter to see every
    product) and choose from a numbered list.

    location_id      show stock at that location; with carried_only, list
                     only products that location carries
    supplier_id      list only products that supplier sells, with its cost
    include_inactive also list discontinued products
    """
    while True:
        text = prompt_text("Type part of the product name (or press Enter to list all)",
                           required=False, max_length=60)
        pattern = f"%{text}%" if text else "%"
        rows = conn.execute(
            """SELECT p.product_id, p.sku, p.name, p.category, p.unit_price,
                      p.unit_cost, p.meal_swipe_eligible, p.is_active,
                      li.quantity_on_hand, li.reorder_level,
                      sp.unit_cost AS supplier_cost
               FROM products AS p
               LEFT JOIN location_inventory AS li
                      ON li.product_id = p.product_id AND li.location_id = ?
               LEFT JOIN supplier_products AS sp
                      ON sp.product_id = p.product_id AND sp.supplier_id = ?
               WHERE (p.name LIKE ? OR p.sku LIKE ?)
                 AND (? = 1 OR p.is_active = 1)
                 AND (? = 0 OR li.product_id IS NOT NULL)
                 AND (? IS NULL OR sp.product_id IS NOT NULL)
               ORDER BY p.category, p.name""",
            (location_id, supplier_id, pattern, pattern, int(include_inactive),
             int(carried_only), supplier_id),
        ).fetchall()
        if not rows:
            print("  No products match. Try a different word.")
            continue
        options = [(_product_label(r, location_id, supplier_id), r) for r in rows]
        options.append(("(Search again)", None))
        product = choose(title, options)
        if product is not None:
            return product


def _product_label(row, location_id, supplier_id):
    label = f"{row['name']:<28} {row['category']:<16}"
    if supplier_id is not None:
        label += f" ${row['supplier_cost']:.2f} each"
    elif location_id is not None:
        if row["quantity_on_hand"] is None:
            label += " not carried here"
        else:
            label += f" {row['quantity_on_hand']} in stock"
    else:
        label += f" ${row['unit_price']:.2f}"
    if not row["is_active"]:
        label += "  (discontinued)"
    return label.rstrip()


def collect_items(conn, location_id, action="remove", check_item=None):
    """
    Build a list of (product_row, quantity) taken from stock at a location.
    Only products the location carries, with stock on hand, can be chosen.
    check_item(product) may return a message to reject a product.
    """
    items = {}          # product_id -> [product_row, quantity]
    while True:
        product = pick_product(conn, f"Which product do you want to {action}?",
                               location_id, carried_only=True)
        already = items.get(product["product_id"], [None, 0])[1]
        available = product["quantity_on_hand"] - already
        problem = check_item(product) if check_item else None
        if problem:
            print(f"  {problem}")
        elif available <= 0:
            print(f"  There is no {product['name']} left in stock here.")
        else:
            qty = prompt_int(f"How many {product['name']}? (1-{available})",
                             1, available)
            items[product["product_id"]] = [product, already + qty]
            print(f"  Added {qty} x {product['name']}.")
        if items and not prompt_yes_no("Add another product?", default=False):
            return list(items.values())


def _remove_stock(conn, location_id, product, qty, timestamp):
    """
    Decrease stock, refusing if it would go below zero (for example, if
    the register sold the last units after the stock was checked).
    Raising inside "with conn:" rolls back the whole operation.
    """
    cur = conn.execute(
        """UPDATE location_inventory
           SET quantity_on_hand = quantity_on_hand - ?, updated_at = ?
           WHERE location_id = ? AND product_id = ? AND quantity_on_hand >= ?""",
        (qty, timestamp, location_id, product["product_id"], qty),
    )
    if cur.rowcount != 1:
        raise AppError(f"Not enough {product['name']} in stock. Nothing was saved.")


def _add_stock(conn, location_id, product_id, qty, timestamp):
    """
    Increase stock. If the location doesn't carry the product yet, it starts
    carrying it (reorder level 0 until a manager sets one).
    """
    conn.execute(
        """INSERT INTO location_inventory
               (location_id, product_id, quantity_on_hand, reorder_level, updated_at)
           VALUES (?, ?, ?, 0, ?)
           ON CONFLICT (location_id, product_id) DO UPDATE SET
               quantity_on_hand = quantity_on_hand + excluded.quantity_on_hand,
               updated_at = excluded.updated_at""",
        (location_id, product_id, qty, timestamp),
    )


# ---------------------------------------------------------------------
# 1. Find a product (search / browse, then details)
# ---------------------------------------------------------------------

def search_products(conn):
    keyword = prompt_text("Type part of the product name (or press Enter for all)",
                          required=False, max_length=60)
    category = choose("Category:", [("All categories", None)] +
                      [(c, c) for c in CATEGORIES])
    include_inactive = prompt_yes_no("Include discontinued products?", default=False)

    pattern = f"%{keyword}%" if keyword else "%"
    rows = conn.execute(
        """SELECT ROW_NUMBER() OVER (ORDER BY p.category, p.name) AS "#",
                  p.product_id,
                  p.name                                  AS product,
                  p.category,
                  p.unit_price                            AS price,
                  CASE p.meal_swipe_eligible WHEN 1 THEN 'Yes' ELSE 'No' END
                                                          AS meal_swipe,
                  CASE p.is_active WHEN 1 THEN 'Active' ELSE 'Discontinued' END
                                                          AS status,
                  COUNT(li.location_id)                   AS locations,
                  COALESCE(SUM(li.quantity_on_hand), 0)   AS total_stock
           FROM products AS p
           LEFT JOIN location_inventory AS li ON li.product_id = p.product_id
           WHERE (p.name LIKE ? OR p.sku LIKE ?)
             AND (? IS NULL OR p.category = ?)
             AND (? = 1 OR p.is_active = 1)
           GROUP BY p.product_id
           ORDER BY p.category, p.name""",
        (pattern, pattern, category, category, int(include_inactive)),
    ).fetchall()
    columns = ["#", "product", "category", "price", "meal_swipe", "status",
               "locations", "total_stock"]
    print_table([[r[c] for c in columns] for r in rows], columns,
                empty_message="No products match that search.")

    if rows:
        number = prompt_int("\nEnter a # to see that product's details "
                            "(or press Enter to go back)", 1, len(rows),
                            allow_blank=True)
        if number is not None:
            show_product_details(conn, rows[number - 1]["product_id"])


def show_product_details(conn, product_id):
    """Related data: a product with its stock by location and its suppliers."""
    product = conn.execute(
        "SELECT * FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()
    if product is None:
        raise AppError("That product no longer exists.")

    print(f"\n{product['name']}  ({product['category']}, SKU {product['sku']})")
    print(f"Price ${product['unit_price']:.2f}   Standard cost "
          f"${product['unit_cost']:.2f}   Meal swipe: "
          f"{'Yes' if product['meal_swipe_eligible'] else 'No'}   "
          f"{'Active' if product['is_active'] else 'Discontinued'}")

    print("\nStock by location:")
    print_table(conn.execute(
        """SELECT l.name AS location, li.quantity_on_hand AS on_hand,
                  li.reorder_level,
                  CASE WHEN li.quantity_on_hand <= li.reorder_level
                       THEN 'LOW' ELSE '' END AS alert,
                  li.updated_at
           FROM location_inventory AS li
           JOIN locations AS l ON l.location_id = li.location_id
           WHERE li.product_id = ?
           ORDER BY l.name""",
        (product_id,),
    ).fetchall(), empty_message="Not stocked at any location.")

    print("\nSuppliers:")
    print_table(conn.execute(
        """SELECT s.name AS supplier, sp.unit_cost, sp.lead_time_days,
                  CASE s.is_active WHEN 1 THEN 'Active' ELSE 'Inactive' END
                      AS supplier_status
           FROM supplier_products AS sp
           JOIN suppliers AS s ON s.supplier_id = sp.supplier_id
           WHERE sp.product_id = ?
           ORDER BY sp.unit_cost""",
        (product_id,),
    ).fetchall(), empty_message="No suppliers on file.")


# ---------------------------------------------------------------------
# 2. Stock at a location (related data)
# ---------------------------------------------------------------------

def view_location_stock(conn):
    location_id, location_name = pick_location(conn)
    low_only = prompt_yes_no("Show only items at or below reorder level?",
                             default=False)
    rows = conn.execute(
        """SELECT p.name AS product, p.category,
                  li.quantity_on_hand AS on_hand, li.reorder_level,
                  CASE WHEN li.quantity_on_hand = 0 THEN 'OUT'
                       WHEN li.quantity_on_hand <= li.reorder_level THEN 'LOW'
                       ELSE '' END AS alert,
                  li.updated_at
           FROM location_inventory AS li
           JOIN products AS p ON p.product_id = li.product_id
           WHERE li.location_id = ?
             AND p.is_active = 1
             AND (? = 0 OR li.quantity_on_hand <= li.reorder_level)
           ORDER BY p.category, p.name""",
        (location_id, int(low_only)),
    ).fetchall()
    print(f"\nStock at {location_name}:")
    print_table(rows, empty_message="Nothing to show for this location.")


# ---------------------------------------------------------------------
# 3. Recent sales at a location (related data)
# ---------------------------------------------------------------------

def view_recent_sales(conn):
    location_id, location_name = pick_location(conn)
    limit = prompt_int("How many recent sales to show?", 1, 100, default=10)
    rows = conn.execute(
        """SELECT st.sale_id, st.sold_at, e.name AS cashier, st.payment_method,
                  st.total_amount,
                  GROUP_CONCAT(si.quantity || ' x ' || p.name, ', ') AS items
           FROM sales_transactions AS st
           JOIN employees  AS e  ON e.employee_id = st.processed_by_employee_id
           JOIN sale_items AS si ON si.sale_id    = st.sale_id
           JOIN products   AS p  ON p.product_id  = si.product_id
           WHERE st.location_id = ?
           GROUP BY st.sale_id
           ORDER BY st.sold_at DESC
           LIMIT ?""",
        (location_id, limit),
    ).fetchall()
    print(f"\nMost recent sales at {location_name}:")
    print_table(rows, empty_message="No sales recorded at this location.")


# ---------------------------------------------------------------------
# 4. Record a sale manually (transaction)
# Sales normally come from the registers automatically; this is the
# backup for when a register is down. It writes the sale exactly the way
# a register would: the sale, its line items, and the stock decrease.
# ---------------------------------------------------------------------

def record_sale(conn):
    print("\nSales are normally recorded by the registers automatically.")
    print("Use this only to enter a sale by hand, such as when a register is down.")
    location_id, location_name = pick_location(conn, "Where was the sale?")
    employee_id = pick_employee(conn, location_id, "Cashier:")
    payment = choose("Payment method:", [(m, m) for m in PAYMENT_METHODS])

    def swipe_rule(product):
        if payment == "Meal Swipe" and not product["meal_swipe_eligible"]:
            return f"{product['name']} can't be paid for with a meal swipe."
        return None

    items = collect_items(conn, location_id, "sell", swipe_rule)

    total = round(sum(p["unit_price"] * qty for p, qty in items), 2)
    print(f"\nSale at {location_name} - {payment}")
    for p, qty in items:
        print(f"  {qty} x {p['name']} @ ${p['unit_price']:.2f}")
    print(f"  Total: ${total:.2f}")
    if not prompt_yes_no("Record this sale?", default=True):
        print("Sale not recorded.")
        return

    sold_at = now_timestamp()
    # The sale, its line items, and the stock decreases succeed or fail
    # together, so inventory always matches recorded sales.
    with conn:
        sale_id = conn.execute(
            """INSERT INTO sales_transactions
                   (location_id, processed_by_employee_id, sold_at,
                    payment_method, total_amount)
               VALUES (?, ?, ?, ?, ?)""",
            (location_id, employee_id, sold_at, payment, total),
        ).lastrowid
        for product, qty in items:
            conn.execute(
                """INSERT INTO sale_items (sale_id, product_id, quantity, unit_price)
                   VALUES (?, ?, ?, ?)""",
                (sale_id, product["product_id"], qty, product["unit_price"]),
            )
            _remove_stock(conn, location_id, product, qty, sold_at)
    print(f"Sale #{sale_id} recorded. Stock at {location_name} updated.")


# ---------------------------------------------------------------------
# 5. Receive a delivery (transaction)
# ---------------------------------------------------------------------

def receive_delivery(conn):
    location_id, location_name = pick_location(conn, "Where is the delivery?")
    employee_id = pick_employee(conn, location_id, "Who is receiving it?")
    supplier_id, supplier_name = pick_supplier(conn)

    while True:
        invoice = prompt_text("Invoice number (press Enter if none)",
                              required=False, max_length=80)
        if invoice is None or conn.execute(
                """SELECT 1 FROM deliveries
                   WHERE supplier_id = ? AND invoice_reference = ?""",
                (supplier_id, invoice)).fetchone() is None:
            break
        print(f"  Invoice {invoice} from {supplier_name} was already received.")

    today = datetime.date.today().isoformat()
    items = []
    print(f"\nEnter what arrived from {supplier_name}.")
    while True:
        product = pick_product(conn, "Which product arrived?",
                               supplier_id=supplier_id)
        qty = prompt_int(f"How many {product['name']} arrived?", 1, 10000)
        cost = prompt_money("Cost per unit", default=product["supplier_cost"])
        # Grab-and-go food must have an expiration date; other items may.
        must_expire = product["category"] == "Grab-and-Go"
        while True:
            expires = prompt_date(
                "Expiration date" + ("" if must_expire else " (press Enter if none)"),
                allow_blank=not must_expire)
            if expires is None or expires >= today:
                break
            print("  That date has already passed.")
        lot = prompt_text("Lot code (press Enter if none)", required=False,
                          max_length=60)
        items.append((product, qty, cost, lot, expires))
        print(f"  Added {qty} x {product['name']}.")
        if not prompt_yes_no("Add another product?", default=False):
            break

    total = round(sum(qty * cost for _p, qty, cost, _l, _e in items), 2)
    print(f"\nDelivery from {supplier_name} to {location_name}:")
    for p, qty, cost, _lot, expires in items:
        print(f"  {qty} x {p['name']} @ ${cost:.2f}"
              + (f"  (expires {expires})" if expires else ""))
    print(f"  Total cost: ${total:.2f}")
    if not prompt_yes_no("Save this delivery and add it to stock?", default=True):
        print("Delivery not saved.")
        return

    received_at = now_timestamp()
    # The delivery, its line items, and the stock increases are saved
    # together, so stock always matches what was received.
    with conn:
        delivery_id = conn.execute(
            """INSERT INTO deliveries
                   (supplier_id, location_id, received_by_employee_id,
                    received_at, invoice_reference)
               VALUES (?, ?, ?, ?, ?)""",
            (supplier_id, location_id, employee_id, received_at, invoice),
        ).lastrowid
        for product, qty, cost, lot, expires in items:
            conn.execute(
                """INSERT INTO delivery_items
                       (delivery_id, product_id, quantity_received, unit_cost,
                        lot_code, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (delivery_id, product["product_id"], qty, cost, lot, expires),
            )
            _add_stock(conn, location_id, product["product_id"], qty, received_at)
    print(f"Delivery #{delivery_id} saved. Stock at {location_name} updated.")


# ---------------------------------------------------------------------
# 6. Log expired or damaged items (transaction)
# ---------------------------------------------------------------------

def log_waste(conn):
    location_id, location_name = pick_location(conn, "Where were items removed?")
    employee_id = pick_employee(conn, location_id)
    reason = choose("Reason:", [(r, r) for r in WASTE_REASONS])

    items = collect_items(conn, location_id, "remove")

    total_cost = round(sum(p["unit_cost"] * qty for p, qty in items), 2)
    print(f"\nRemove from {location_name} ({reason}):")
    for p, qty in items:
        print(f"  {qty} x {p['name']}  (cost ${p['unit_cost'] * qty:.2f})")
    print(f"  Total cost lost: ${total_cost:.2f}")
    if not prompt_yes_no("Record this waste?", default=True):
        print("Nothing recorded.")
        return

    recorded_at = now_timestamp()
    # Each waste record and its stock decrease are saved together.
    with conn:
        for product, qty in items:
            conn.execute(
                """INSERT INTO waste_records
                       (location_id, product_id, recorded_by_employee_id,
                        quantity, reason, recorded_at, unit_cost)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (location_id, product["product_id"], employee_id, qty,
                 reason, recorded_at, product["unit_cost"]),
            )
            _remove_stock(conn, location_id, product, qty, recorded_at)
    print(f"Logged {len(items)} waste record(s) and updated stock.")


# ---------------------------------------------------------------------
# 7. Transfer stock between locations (transaction)
# ---------------------------------------------------------------------

def transfer_stock(conn):
    from_id, from_name = pick_location(conn, "Send stock FROM:")
    to_id, to_name = pick_location(conn, "Send stock TO:", exclude_id=from_id)
    employee_id = pick_employee(conn, from_id, "Who is sending it?")

    items = collect_items(conn, from_id, "send")

    print(f"\nTransfer {from_name} -> {to_name}:")
    for p, qty in items:
        print(f"  {qty} x {p['name']}")
    if not prompt_yes_no("Complete this transfer?", default=True):
        print("Transfer not recorded.")
        return

    moved_at = now_timestamp()
    # The transfer record, its items, the decrease at the sender, and the
    # increase at the receiver must all happen, or none of them.
    with conn:
        transfer_id = conn.execute(
            """INSERT INTO stock_transfers
                   (from_location_id, to_location_id, requested_by_employee_id,
                    transferred_at, status)
               VALUES (?, ?, ?, ?, 'Completed')""",
            (from_id, to_id, employee_id, moved_at),
        ).lastrowid
        for product, qty in items:
            conn.execute(
                """INSERT INTO transfer_items (transfer_id, product_id, quantity)
                   VALUES (?, ?, ?)""",
                (transfer_id, product["product_id"], qty),
            )
            _remove_stock(conn, from_id, product, qty, moved_at)
            _add_stock(conn, to_id, product["product_id"], qty, moved_at)
    print(f"Transfer #{transfer_id} completed. Stock updated at both locations.")


# ---------------------------------------------------------------------
# 8. Add a new product (transaction when stocking locations)
# ---------------------------------------------------------------------

def _next_sku(conn, category):
    """Suggest the next SKU in a category's series, e.g. SNK-006."""
    prefix = conn.execute(
        """SELECT substr(sku, 1, instr(sku, '-')) FROM products
           WHERE category = ? AND instr(sku, '-') > 0 LIMIT 1""",
        (category,),
    ).fetchone()
    prefix = prefix[0] if prefix else category[:3].upper() + "-"
    highest = conn.execute(
        """SELECT MAX(CAST(substr(sku, length(?) + 1) AS INTEGER))
           FROM products WHERE sku LIKE ? || '%'""",
        (prefix, prefix),
    ).fetchone()[0] or 0
    return f"{prefix}{highest + 1:03d}"


def add_product(conn):
    name = prompt_text("Product name", max_length=160)
    category = choose("Category:", [(c, c) for c in CATEGORIES])
    suggested = _next_sku(conn, category)
    while True:
        sku = prompt_text("SKU", default=suggested, max_length=40).upper()
        if conn.execute("SELECT 1 FROM products WHERE sku = ?",
                        (sku,)).fetchone() is None:
            break
        print(f"  SKU {sku} is already in use. Enter a different one.")
    price = prompt_money("Selling price", allow_zero=False)
    while True:
        cost = prompt_money("Unit cost")
        if cost <= price:
            break
        print("  Cost is higher than the selling price. Please re-enter.")
    swipe_ok = prompt_yes_no("Can it be bought with a meal swipe?", default=False)

    stock_everywhere = prompt_yes_no(
        "Add it to inventory at every location (starting at 0 units)?",
        default=True)
    reorder_level = (prompt_int("Reorder level at each location", 0, 1000)
                     if stock_everywhere else None)

    # The product and its inventory rows are saved together.
    with conn:
        product_id = conn.execute(
            """INSERT INTO products
                   (sku, name, category, unit_price, unit_cost,
                    meal_swipe_eligible, is_active)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (sku, name, category, price, cost, int(swipe_ok)),
        ).lastrowid
        stocked = 0
        if stock_everywhere:
            stocked = conn.execute(
                """INSERT INTO location_inventory
                       (location_id, product_id, quantity_on_hand,
                        reorder_level, updated_at)
                   SELECT location_id, ?, 0, ?, ?
                   FROM locations WHERE is_active = 1""",
                (product_id, reorder_level, now_timestamp()),
            ).rowcount
    print(f"Added {name} ({sku})" +
          (f" and set it up at {stocked} location(s)." if stocked else "."))


# ---------------------------------------------------------------------
# 9. Edit a product (UPDATE)
# ---------------------------------------------------------------------

def edit_product(conn):
    product = pick_product(conn, "Which product do you want to edit?",
                           include_inactive=True)
    print(f"\n{product['name']}: price ${product['unit_price']:.2f}, "
          f"cost ${product['unit_cost']:.2f}, meal swipe "
          f"{'yes' if product['meal_swipe_eligible'] else 'no'}, "
          f"{'active' if product['is_active'] else 'discontinued'}")

    field = choose("What do you want to change?", [
        ("Selling price", "price"),
        ("Unit cost", "cost"),
        ("Meal-swipe eligibility", "swipe"),
        ("Active / discontinued status", "active"),
        ("Reorder level at a location", "reorder"),
    ])
    pid = product["product_id"]

    if field == "price":
        new_price = prompt_money("New selling price", allow_zero=False,
                                 default=product["unit_price"])
        if new_price < product["unit_cost"] and not prompt_yes_no(
                "That is below the unit cost. Save anyway?", default=False):
            return
        _update(conn, "UPDATE products SET unit_price = ? WHERE product_id = ?",
                (new_price, pid))
        print(f"Price changed to ${new_price:.2f}. Past sales keep the price "
              "they were sold at.")
    elif field == "cost":
        new_cost = prompt_money("New unit cost", default=product["unit_cost"])
        _update(conn, "UPDATE products SET unit_cost = ? WHERE product_id = ?",
                (new_cost, pid))
        print(f"Unit cost changed to ${new_cost:.2f}.")
    elif field == "swipe":
        eligible = prompt_yes_no("Allow meal swipes for this product?",
                                 default=bool(product["meal_swipe_eligible"]))
        _update(conn, "UPDATE products SET meal_swipe_eligible = ? WHERE product_id = ?",
                (int(eligible), pid))
        print("Meal-swipe eligibility updated.")
    elif field == "active":
        active = prompt_yes_no("Should this product be active?",
                               default=bool(product["is_active"]))
        _update(conn, "UPDATE products SET is_active = ? WHERE product_id = ?",
                (int(active), pid))
        print("Product is now " + ("active." if active else "discontinued."))
    else:
        location_id, location_name = pick_location(conn)
        current = conn.execute(
            """SELECT reorder_level FROM location_inventory
               WHERE location_id = ? AND product_id = ?""",
            (location_id, pid),
        ).fetchone()
        if current is None:
            raise AppError(f"{location_name} does not carry {product['name']}.")
        level = prompt_int("New reorder level", 0, 1000,
                           default=current["reorder_level"])
        _update(conn,
                """UPDATE location_inventory
                   SET reorder_level = ?, updated_at = ?
                   WHERE location_id = ? AND product_id = ?""",
                (level, now_timestamp(), location_id, pid))
        print(f"Reorder level at {location_name} set to {level}.")


def _update(conn, sql, params):
    """Run a single UPDATE and make sure it changed exactly one row."""
    with conn:
        if conn.execute(sql, params).rowcount != 1:
            raise AppError("That record no longer exists. Nothing was changed.")
