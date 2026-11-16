-- select_all.sql: show every row in every table (parents first)
.mode box

SELECT * FROM locations;
SELECT * FROM products;
SELECT * FROM suppliers;
SELECT * FROM employees;
SELECT * FROM location_inventory;
SELECT * FROM supplier_products;
SELECT * FROM deliveries;
SELECT * FROM delivery_items;
SELECT * FROM sales_transactions;
SELECT * FROM sale_items;
SELECT * FROM stock_transfers;
SELECT * FROM transfer_items;
SELECT * FROM waste_records;
