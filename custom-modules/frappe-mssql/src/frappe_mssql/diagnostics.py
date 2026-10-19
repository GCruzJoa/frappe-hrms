"""Native SQL Server diagnostics with the same report columns as Frappe."""
import frappe


def table_storage():
    return frappe.db.native("""SELECT t.name AS [table],
        SUM(p.used_page_count)/128.0 AS size,
        SUM(CASE WHEN p.index_id IN (0,1) THEN p.in_row_data_page_count
            + p.lob_used_page_count + p.row_overflow_used_page_count ELSE 0 END)/128.0 AS data_size,
        (SUM(p.used_page_count)-SUM(CASE WHEN p.index_id IN (0,1)
            THEN p.in_row_data_page_count+p.lob_used_page_count+p.row_overflow_used_page_count
            ELSE 0 END))/128.0 AS index_size
        FROM sys.tables t JOIN sys.dm_db_partition_stats p ON p.object_id=t.object_id
        WHERE t.schema_id=SCHEMA_ID('dbo') GROUP BY t.name ORDER BY size DESC""", as_dict=True)
