-- POD Market Inventory Management System
-- schema.sql  (SQLite)
PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS v_low_stock;
DROP VIEW  IF EXISTS v_delivery_summary;

DROP INDEX IF EXISTS idx_sales_location_sold_at;
DROP INDEX IF EXISTS idx_sale_items_product_id;
DROP INDEX IF EXISTS idx_delivery_items_expires_at;

DROP TABLE IF EXISTS waste_records;
DROP TABLE IF EXISTS transfer_items;
DROP TABLE IF EXISTS stock_transfers;
DROP TABLE IF EXISTS sale_items;
DROP TABLE IF EXISTS sales_transactions;
DROP TABLE IF EXISTS delivery_items;
DROP TABLE IF EXISTS deliveries;
DROP TABLE IF EXISTS supplier_products;
DROP TABLE IF EXISTS location_inventory;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS locations;

-- LOCATIONS: each POD Market on campus
CREATE TABLE locations (
    location_id INTEGER      PRIMARY KEY,
    name        TEXT         NOT NULL UNIQUE,
    building    TEXT         NOT NULL,
    is_active   INTEGER      NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- ---------------------------------------------------------------------
-- PRODUCTS: the shared catalog sold across all locations
-- unit_cost is the standard cost; actual costs per supplier and per
-- delivery are stored in supplier_products and delivery_items.
-- ---------------------------------------------------------------------
CREATE TABLE products (
    product_id          INTEGER       PRIMARY KEY,
    sku                 TEXT          NOT NULL UNIQUE,      -- alternate key
    name                TEXT          NOT NULL,
    category            TEXT          NOT NULL
                        CHECK (category IN ('Beverages', 'Snacks', 'Grab-and-Go',
                                            'Frozen', 'Household', 'Health & Beauty')),
    unit_price          REAL          NOT NULL CHECK (unit_price > 0),
    unit_cost           REAL          NOT NULL CHECK (unit_cost >= 0),
    meal_swipe_eligible INTEGER       NOT NULL DEFAULT 0 CHECK (meal_swipe_eligible IN (0, 1)),
    is_active           INTEGER       NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- ---------------------------------------------------------------------
-- SUPPLIERS: vendors that deliver to the POD Markets
-- Contact fields are optional; an email, when given, must look like one.
-- ---------------------------------------------------------------------
CREATE TABLE suppliers (
    supplier_id   INTEGER      PRIMARY KEY,
    name          TEXT         NOT NULL UNIQUE,
    contact_name  TEXT,
    contact_email TEXT        
                  CHECK (contact_email IS NULL OR contact_email LIKE '%_@_%._%'),
    is_active     INTEGER      NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- ---------------------------------------------------------------------
-- EMPLOYEES: staff assigned to a home location
-- ---------------------------------------------------------------------
CREATE TABLE employees (
    employee_id     INTEGER      PRIMARY KEY,
    location_id     INTEGER      NOT NULL,
    employee_number TEXT         NOT NULL UNIQUE,          -- alternate key
    name            TEXT         NOT NULL,
    role            TEXT         NOT NULL DEFAULT 'Associate'
                    CHECK (role IN ('Associate', 'Supervisor', 'Manager')),
    is_active       INTEGER      NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    FOREIGN KEY (location_id) REFERENCES locations (location_id)
);

-- ---------------------------------------------------------------------
-- LOCATION_INVENTORY: resolves the many-to-many relationship between
-- LOCATIONS and PRODUCTS. One row = current stock of one product at
-- one location.
-- ---------------------------------------------------------------------
CREATE TABLE location_inventory (
    location_id      INTEGER   NOT NULL,
    product_id       INTEGER   NOT NULL,
    quantity_on_hand INTEGER   NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
    reorder_level    INTEGER   NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
    updated_at       TEXT      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (location_id, product_id),
    FOREIGN KEY (location_id) REFERENCES locations (location_id),
    FOREIGN KEY (product_id)  REFERENCES products  (product_id)
);

-- ---------------------------------------------------------------------
-- SUPPLIER_PRODUCTS: resolves the many-to-many relationship between
-- SUPPLIERS and PRODUCTS, with each supplier's own SKU, cost, and
-- lead time for the product.
-- ---------------------------------------------------------------------
CREATE TABLE supplier_products (
    supplier_id    INTEGER       NOT NULL,
    product_id     INTEGER       NOT NULL,
    supplier_sku   TEXT,
    unit_cost      REAL          NOT NULL CHECK (unit_cost >= 0),
    lead_time_days INTEGER       CHECK (lead_time_days IS NULL OR lead_time_days >= 0),
    PRIMARY KEY (supplier_id, product_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers (supplier_id),
    FOREIGN KEY (product_id)  REFERENCES products  (product_id)
);

-- ---------------------------------------------------------------------
-- DELIVERIES: shipments from a supplier to a specific location
-- A supplier never reuses an invoice number (NULL invoices are allowed;
-- SQLite permits multiple NULLs under a UNIQUE constraint).
-- ---------------------------------------------------------------------
CREATE TABLE deliveries (
    delivery_id             INTEGER     PRIMARY KEY,
    supplier_id             INTEGER     NOT NULL,
    location_id             INTEGER     NOT NULL,
    received_by_employee_id INTEGER     NOT NULL,
    received_at             TEXT        NOT NULL,
    invoice_reference       TEXT,
    UNIQUE (supplier_id, invoice_reference),
    FOREIGN KEY (supplier_id)             REFERENCES suppliers (supplier_id),
    FOREIGN KEY (location_id)             REFERENCES locations (location_id),
    FOREIGN KEY (received_by_employee_id) REFERENCES employees (employee_id)
);

-- ---------------------------------------------------------------------
-- DELIVERY_ITEMS: the products and quantities received in a delivery.
-- expires_at is NULL for non-perishable items. Deleting a delivery
-- removes its line items.
-- ---------------------------------------------------------------------
CREATE TABLE delivery_items (
    delivery_item_id  INTEGER       PRIMARY KEY,
    delivery_id       INTEGER       NOT NULL,
    product_id        INTEGER       NOT NULL,
    quantity_received INTEGER       NOT NULL CHECK (quantity_received > 0),
    unit_cost         REAL          NOT NULL CHECK (unit_cost >= 0),
    lot_code          TEXT,
    expires_at        TEXT,
    FOREIGN KEY (delivery_id) REFERENCES deliveries (delivery_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id)  REFERENCES products   (product_id)
);

-- ---------------------------------------------------------------------
-- SALES_TRANSACTIONS: one customer purchase at one location
-- For meal-swipe sales, total_amount records the retail value of the
-- items covered by the swipe.
-- ---------------------------------------------------------------------
CREATE TABLE sales_transactions (
    sale_id                  INTEGER       PRIMARY KEY,
    location_id              INTEGER       NOT NULL,
    processed_by_employee_id INTEGER       NOT NULL,
    sold_at                  TEXT          NOT NULL,
    payment_method           TEXT          NOT NULL
                             CHECK (payment_method IN ('Meal Swipe', 'Dining Dollars', 'Card')),
    total_amount             REAL          NOT NULL CHECK (total_amount >= 0),
    FOREIGN KEY (location_id)              REFERENCES locations (location_id),
    FOREIGN KEY (processed_by_employee_id) REFERENCES employees (employee_id)
);

-- ---------------------------------------------------------------------
-- SALE_ITEMS: resolves the many-to-many relationship between
-- SALES_TRANSACTIONS and PRODUCTS. unit_price is the price charged at
-- the time of sale. A product appears at most once per sale.
-- ---------------------------------------------------------------------
CREATE TABLE sale_items (
    sale_item_id INTEGER       PRIMARY KEY,
    sale_id      INTEGER       NOT NULL,
    product_id   INTEGER       NOT NULL,
    quantity     INTEGER       NOT NULL CHECK (quantity > 0),
    unit_price   REAL          NOT NULL CHECK (unit_price >= 0),
    UNIQUE (sale_id, product_id),
    FOREIGN KEY (sale_id)    REFERENCES sales_transactions (sale_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products (product_id)
);

-- ---------------------------------------------------------------------
-- STOCK_TRANSFERS: stock moved from one location to another.
-- A transfer can't go from a location to itself.
-- transferred_at is when the transfer was created.
-- ---------------------------------------------------------------------
CREATE TABLE stock_transfers (
    transfer_id              INTEGER     PRIMARY KEY,
    from_location_id         INTEGER     NOT NULL,
    to_location_id           INTEGER     NOT NULL,
    requested_by_employee_id INTEGER     NOT NULL,
    transferred_at           TEXT        NOT NULL,
    status                   TEXT        NOT NULL DEFAULT 'Requested'
                             CHECK (status IN ('Requested', 'In Transit', 'Completed', 'Cancelled')),
    CHECK (from_location_id <> to_location_id),
    FOREIGN KEY (from_location_id)         REFERENCES locations (location_id),
    FOREIGN KEY (to_location_id)           REFERENCES locations (location_id),
    FOREIGN KEY (requested_by_employee_id) REFERENCES employees (employee_id)
);

-- ---------------------------------------------------------------------
-- TRANSFER_ITEMS: the products and quantities in a transfer.
-- A product appears at most once per transfer.
-- ---------------------------------------------------------------------
CREATE TABLE transfer_items (
    transfer_item_id INTEGER PRIMARY KEY,
    transfer_id      INTEGER NOT NULL,
    product_id       INTEGER NOT NULL,
    quantity         INTEGER NOT NULL CHECK (quantity > 0),
    UNIQUE (transfer_id, product_id),
    FOREIGN KEY (transfer_id) REFERENCES stock_transfers (transfer_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id)  REFERENCES products (product_id)
);

-- ---------------------------------------------------------------------
-- WASTE_RECORDS: items removed from stock at a location.
-- unit_cost is the cost at the time, so waste cost stays accurate even
-- if the product's cost later changes.
-- ---------------------------------------------------------------------
CREATE TABLE waste_records (
    waste_record_id         INTEGER       PRIMARY KEY,
    location_id             INTEGER       NOT NULL,
    product_id              INTEGER       NOT NULL,
    recorded_by_employee_id INTEGER       NOT NULL,
    quantity                INTEGER       NOT NULL CHECK (quantity > 0),
    reason                  TEXT          NOT NULL
                            CHECK (reason IN ('Expired', 'Damaged', 'Recalled', 'Other')),
    recorded_at             TEXT          NOT NULL,
    unit_cost               REAL          NOT NULL CHECK (unit_cost >= 0),
    FOREIGN KEY (location_id)             REFERENCES locations (location_id),
    FOREIGN KEY (product_id)              REFERENCES products  (product_id),
    FOREIGN KEY (recorded_by_employee_id) REFERENCES employees (employee_id)
);

-- ---------------------------------------------------------------------
-- VIEW: v_low_stock
-- Every active product at every active location whose quantity on hand
-- is at or below its reorder level, with the units needed to get back
-- to that level and the cheapest active supplier to reorder from.
-- Answers "what needs reordering, where, and from whom?"
-- ---------------------------------------------------------------------
CREATE VIEW v_low_stock AS
SELECT
    l.location_id,
    l.name                                 AS location_name,
    p.product_id,
    p.sku,
    p.name                                 AS product_name,
    p.category,
    li.quantity_on_hand,
    li.reorder_level,
    li.reorder_level - li.quantity_on_hand AS units_below_reorder,
    (SELECT s.name
       FROM supplier_products sp
       JOIN suppliers s ON s.supplier_id = sp.supplier_id
      WHERE sp.product_id = p.product_id
        AND s.is_active = 1
      ORDER BY sp.unit_cost, s.name
      LIMIT 1)                             AS preferred_supplier,
    li.updated_at
FROM location_inventory AS li
JOIN locations AS l ON l.location_id = li.location_id
JOIN products  AS p ON p.product_id  = li.product_id
WHERE li.quantity_on_hand <= li.reorder_level
  AND l.is_active = 1
  AND p.is_active = 1;

-- ---------------------------------------------------------------------
-- VIEW: v_delivery_summary
-- One row per delivery with supplier, location, and receiving employee
-- names, plus item count, units, and total cost computed from its line
-- items. Supports supplier-spending reports by location and period.
-- ---------------------------------------------------------------------
CREATE VIEW v_delivery_summary AS
SELECT
    d.delivery_id,
    d.received_at,
    d.invoice_reference,
    s.supplier_id,
    s.name                                      AS supplier_name,
    l.location_id,
    l.name                                      AS location_name,
    e.name                                      AS received_by,
    COUNT(di.delivery_item_id)                  AS line_items,
    SUM(di.quantity_received)                   AS total_units,
    ROUND(SUM(di.quantity_received * di.unit_cost), 2) AS total_cost
FROM deliveries AS d
JOIN suppliers  AS s ON s.supplier_id = d.supplier_id
JOIN locations  AS l ON l.location_id = d.location_id
JOIN employees  AS e ON e.employee_id = d.received_by_employee_id
JOIN delivery_items AS di ON di.delivery_id = d.delivery_id
GROUP BY d.delivery_id;

-- ---------------------------------------------------------------------
-- INDEXES
-- idx_sales_location_sold_at: sales reports filter by location and a
--   date range ("this week at the Library POD").
-- idx_sale_items_product_id: SQLite does not index foreign keys
--   automatically; best-seller reports join sale_items to products.
-- idx_delivery_items_expires_at: finds lots expiring within a date
--   range ("grab-and-go items expiring in the next 3 days").
-- ---------------------------------------------------------------------
CREATE INDEX idx_sales_location_sold_at
    ON sales_transactions (location_id, sold_at);

CREATE INDEX idx_sale_items_product_id
    ON sale_items (product_id);

CREATE INDEX idx_delivery_items_expires_at
    ON delivery_items (expires_at);
