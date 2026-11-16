-- POD Market Inventory Management System
-- transaction.sql  (SQLite)
--
-- Records a sale at the Library POD: a customer buys 2 Cold Brew
-- Coffees and 1 Fresh Fruit Cup with dining dollars.
--
-- A sale changes three things: the sale header, its line items, and
-- the stock at that location. These must succeed or fail together. If
-- the sale were saved but the stock update failed (for example, the
-- CHECK quantity_on_hand >= 0 rejects selling more than is in stock),
-- inventory would no longer match sales.
--
-- The example ends with ROLLBACK so the sample data is unchanged after
-- it runs. In the application, the last step would be COMMIT.

.mode columns
PRAGMA foreign_keys = ON;

SELECT 'Library stock before the sale:' AS step;
SELECT p.name AS product, li.quantity_on_hand
FROM location_inventory AS li
JOIN products AS p ON p.product_id = li.product_id
WHERE li.location_id = 3 AND li.product_id IN (2, 11);

BEGIN TRANSACTION;

-- 1. Sale header (2 x 4.49 + 1 x 4.29 = 13.27)
INSERT INTO sales_transactions
    (location_id, processed_by_employee_id, sold_at, payment_method, total_amount)
VALUES (3, 5, '2026-10-22 12:15:00', 'Dining Dollars', 13.27);

-- 2. Line items for the new sale
INSERT INTO sale_items (sale_id, product_id, quantity, unit_price)
VALUES ((SELECT MAX(sale_id) FROM sales_transactions), 2, 2, 4.49);

INSERT INTO sale_items (sale_id, product_id, quantity, unit_price)
VALUES ((SELECT MAX(sale_id) FROM sales_transactions), 11, 1, 4.29);

-- 3. Remove the sold units from the Library's stock
UPDATE location_inventory
SET quantity_on_hand = quantity_on_hand - 2,
    updated_at = '2026-10-22 12:15:00'
WHERE location_id = 3 AND product_id = 2;

UPDATE location_inventory
SET quantity_on_hand = quantity_on_hand - 1,
    updated_at = '2026-10-22 12:15:00'
WHERE location_id = 3 AND product_id = 11;

SELECT 'Inside the transaction, after the sale:' AS step;
SELECT st.sale_id, st.payment_method, st.total_amount,
       COUNT(si.sale_item_id) AS line_items
FROM sales_transactions AS st
JOIN sale_items AS si ON si.sale_id = st.sale_id
WHERE st.sale_id = (SELECT MAX(sale_id) FROM sales_transactions);

SELECT p.name AS product, li.quantity_on_hand
FROM location_inventory AS li
JOIN products AS p ON p.product_id = li.product_id
WHERE li.location_id = 3 AND li.product_id IN (2, 11);

-- Undo every change above as one unit.
ROLLBACK;

SELECT 'After ROLLBACK, the sale is gone and stock is restored:' AS step;
SELECT COUNT(*) AS total_sales FROM sales_transactions;

SELECT p.name AS product, li.quantity_on_hand
FROM location_inventory AS li
JOIN products AS p ON p.product_id = li.product_id
WHERE li.location_id = 3 AND li.product_id IN (2, 11);
