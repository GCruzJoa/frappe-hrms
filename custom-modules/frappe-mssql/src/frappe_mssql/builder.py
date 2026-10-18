"""A Frappe parameterized query builder with SQL Server rendering at execution."""

# Build the same parameterized intermediate SQL as the upstream MariaDB builder;
# compile_query converts its AST to the SQL Server dialect without interpolating values.
from frappe.query_builder.builder import MariaDB


class MSSQL(MariaDB):
    pass
