-- POD Market Inventory Management System
.mode box
PRAGMA foreign_keys = ON;


-- Requirement 1: Filtering and Sorting
-- Proposal question: Which grab-and-go items will expire within the
-- next three days, and at which locations? Lists every delivered lot
-- expiring between the report date and three days later, soonest first.
SELECT
    l.name             AS location,
    p.name             AS product,
    di.lot_code,
    di.quantity_received,
    di.expires_at
FROM delivery_items AS di
JOIN deliveries AS d ON d.delivery_id = di.delivery_id
JOIN locations  AS l ON l.location_id = d.location_id
JOIN products   AS p ON p.product_id  = di.product_id
WHERE p.category = 'Grab-and-Go'
  AND di.expires_at BETWEEN '2026-10-22' AND date('2026-10-22', '+3 days')
ORDER BY di.expires_at, l.name, p.name;


-- Requirement 2: INNER JOIN
-- Waste log: every item removed from stock, with the product name and
-- the cost lost, most recent first.
SELECT
    w.recorded_at,
    p.name                            AS product,
    w.reason,
    w.quantity,
    w.unit_cost,
    ROUND(w.quantity * w.unit_cost, 2) AS cost_lost
FROM waste_records AS w
INNER JOIN products AS p ON p.product_id = w.product_id
ORDER BY w.recorded_at DESC;


-- Requirement 3: LEFT JOIN
-- Supplier activity: how many deliveries each supplier has made and
-- when the last one arrived. The LEFT JOIN keeps suppliers with no
-- deliveries (Summit Vending Supply shows 0 and no date), which helps
-- managers spot inactive vendor accounts.
SELECT
    s.name                    AS supplier,
    s.is_active,
    COUNT(d.delivery_id)      AS deliveries,
    MAX(d.received_at)        AS last_delivery
FROM suppliers AS s
LEFT JOIN deliveries AS d ON d.supplier_id = s.supplier_id
GROUP BY s.supplier_id
ORDER BY deliveries DESC, s.name;


-- Requirement 4: Three-Table Join
-- Proposal question: How much has each location spent with each
-- supplier this semester? Joins deliveries, delivery items, suppliers,
-- and locations to total cost per supplier and location.
SELECT
    l.name                                          AS location,
    s.name                                          AS supplier,
    COUNT(DISTINCT d.delivery_id)                   AS deliveries,
    ROUND(SUM(di.quantity_received * di.unit_cost), 2) AS total_spent
FROM deliveries AS d
JOIN delivery_items AS di ON di.delivery_id = d.delivery_id
JOIN suppliers      AS s  ON s.supplier_id  = d.supplier_id
JOIN locations      AS l  ON l.location_id  = d.location_id
WHERE d.received_at >= '2026-08-15'
GROUP BY l.location_id, s.supplier_id
ORDER BY l.name, total_spent DESC;


-- Requirement 5: Aggregate Query
-- October sales summary across all locations: number of sales, total
-- revenue, average sale, and smallest and largest sale.
SELECT
    COUNT(*)                   AS number_of_sales,
    ROUND(SUM(total_amount), 2) AS total_revenue,
    ROUND(AVG(total_amount), 2) AS average_sale,
    MIN(total_amount)          AS smallest_sale,
    MAX(total_amount)          AS largest_sale
FROM sales_transactions
WHERE sold_at >= '2026-10-01' AND sold_at < '2026-11-01';


-- Requirement 6: GROUP BY and HAVING
-- Proposal question: Which locations had the highest cost of wasted
-- product last month? Totals October waste cost per location and keeps
-- only locations that lost more than $8.00, the level where a manager
-- would review ordering.
SELECT
    l.name                                AS location,
    COUNT(*)                              AS waste_records,
    SUM(w.quantity)                       AS units_wasted,
    ROUND(SUM(w.quantity * w.unit_cost), 2) AS waste_cost
FROM waste_records AS w
JOIN locations AS l ON l.location_id = w.location_id
WHERE w.recorded_at >= '2026-10-01' AND w.recorded_at < '2026-11-01'
GROUP BY l.location_id
HAVING SUM(w.quantity * w.unit_cost) > 8.00
ORDER BY waste_cost DESC;


-- Requirement 7: Subquery
-- Proposal question: Which products have had no sales in the past 30
-- days? For the Hodges POD, the subquery finds every product sold
-- there since 2026-09-22; the outer query lists products the Library
-- stocks that are not in that set, with the stock sitting unsold, so
-- the manager can cut those items or transfer them to another POD.
SELECT
    p.sku,
    p.name              AS product,
    p.category,
    li.quantity_on_hand AS units_in_stock
FROM location_inventory AS li
JOIN products AS p ON p.product_id = li.product_id
WHERE li.location_id = 3
  AND p.is_active = 1
  AND li.product_id NOT IN (
        SELECT si.product_id
        FROM sale_items AS si
        JOIN sales_transactions AS st ON st.sale_id = si.sale_id
        WHERE st.location_id = 3
          AND st.sold_at >= date('2026-10-22', '-30 days')
      )
ORDER BY p.category, p.name;


-- Requirement 8: Set Operation
-- Stock movement history for the Turkey Club Sandwich (product 9):
-- combines deliveries received, units sold, units wasted, and transfer
-- requests into one timeline. Each SELECT is a different kind of
-- movement of the same product, so UNION ALL gives a complete audit
-- trail (ALL keeps rows that happen to match exactly).
SELECT d.received_at AS happened_at, l.name AS location,
       'Delivered' AS movement, di.quantity_received AS quantity
FROM delivery_items AS di
JOIN deliveries AS d ON d.delivery_id = di.delivery_id
JOIN locations  AS l ON l.location_id = d.location_id
WHERE di.product_id = 9

UNION ALL

SELECT st.sold_at, l.name, 'Sold', si.quantity
FROM sale_items AS si
JOIN sales_transactions AS st ON st.sale_id = si.sale_id
JOIN locations          AS l  ON l.location_id = st.location_id
WHERE si.product_id = 9

UNION ALL

SELECT w.recorded_at, l.name, 'Wasted (' || w.reason || ')', w.quantity
FROM waste_records AS w
JOIN locations AS l ON l.location_id = w.location_id
WHERE w.product_id = 9

UNION ALL

SELECT t.transferred_at, fl.name || ' -> ' || tl.name,
       'Transfer (' || t.status || ')', ti.quantity
FROM transfer_items AS ti
JOIN stock_transfers AS t  ON t.transfer_id  = ti.transfer_id
JOIN locations       AS fl ON fl.location_id = t.from_location_id
JOIN locations       AS tl ON tl.location_id = t.to_location_id
WHERE ti.product_id = 9

ORDER BY happened_at;


-- Requirement 9: View
-- Proposal operation: Generate a reorder list grouped by supplier.
-- v_low_stock already joins inventory, locations, products, and
-- supplier catalogs and picks the cheapest active supplier, so the
-- reorder list is a simple query on the view.
SELECT
    preferred_supplier,
    location_name,
    product_name,
    quantity_on_hand,
    reorder_level,
    units_below_reorder
FROM v_low_stock
ORDER BY preferred_supplier, location_name, units_below_reorder DESC;
