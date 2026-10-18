"""DocType DDL for SQL Server; no truncation or destructive column drops."""

from decimal import Decimal
import hashlib

import frappe
from frappe.database.schema import DBTable, NOT_NULL_TYPES
from .sql import quote_identifier as qi, UnsupportedSQL


def ensure_queue_dedup_index(table, index, waiting_states):
    """Preserve PostgreSQL's partial uniqueness, including NULL key semantics."""
    definition = frappe.db.native("SELECT filter_definition FROM sys.indexes WHERE object_id=OBJECT_ID(%s) AND name=%s", (table, index))
    if definition and definition[0][0] and all(state in definition[0][0] for state in waiting_states):
        return
    if definition:
        frappe.db.native(f"DROP INDEX {qi(index)} ON {qi(table)}")
    states = ','.join(frappe.db.escape(state) for state in waiting_states)
    frappe.db.native(f"CREATE UNIQUE INDEX {qi(index)} ON {qi(table)} ([automation],[ref_doctype],[ref_name]) WHERE [status] IN ({states}) AND [resume_run] IS NULL AND [automation] IS NOT NULL AND [ref_doctype] IS NOT NULL AND [ref_name] IS NOT NULL")


class MSSQLTable(DBTable):
    def definition(self, column):
        typename, length = frappe.db.type_map[column.fieldtype]
        if typename == "nvarchar" and length != "max":
            length = int(column.length or length)
            if not 1 <= length <= 4000:
                raise ValueError("SQL Server nvarchar length must be 1–4000")
        sql = typename + (f"({length})" if length else "")
        nullable = not (column.not_nullable or column.fieldtype in NOT_NULL_TYPES)
        sql += " NULL" if nullable else " NOT NULL"
        default = column.default
        if default is not None and default != "" and not column.has_dynamic_default:
            if typename in ("decimal", "int", "bigint", "smallint"):
                default_sql = str(Decimal(str(default)))
            else:
                default_sql = frappe.db.escape(default)
            sql += " DEFAULT " + default_sql
        elif not nullable and typename in ("decimal", "int", "bigint", "smallint"):
            sql += " DEFAULT 0"
        return sql

    def create(self):
        name_type = "nvarchar(140)"
        if self.meta.autoname == "autoincrement":
            name_type = "bigint"
            frappe.db.create_sequence(self.doctype, check_not_exists=True)
        elif self.meta.autoname == "UUID":
            name_type = "uniqueidentifier"
        definitions = [f"[name] {name_type} NOT NULL PRIMARY KEY", "[creation] datetime2(6)", "[modified] datetime2(6)", "[modified_by] nvarchar(140)", "[owner] nvarchar(140)", "[docstatus] smallint NOT NULL DEFAULT 0", "[idx] bigint NOT NULL DEFAULT 0"]
        names = set(frappe.db.DEFAULT_COLUMNS)
        if self.meta.istable:
            for field in frappe.db.CHILD_TABLE_COLUMNS:
                definitions.append(f"{qi(field)} nvarchar(140)")
                names.add(field)
        for name, column in self.columns.items():
            if name not in names and column.fieldtype in frappe.db.type_map:
                definitions.append(f"{qi(name)} {self.definition(column)}")
        frappe.db.native(f"CREATE TABLE {qi(self.table_name)} ({', '.join(definitions)})")
        self.indexes()

    def alter(self):
        current = {item.name: item for item in frappe.db.get_table_columns_description(self.table_name)}
        for name, column in self.columns.items():
            if column.fieldtype not in frappe.db.type_map:
                continue
            if name not in current:
                frappe.db.native(f"ALTER TABLE {qi(self.table_name)} ADD {qi(name)} {self.definition(column)}")
            else:
                expected_type, expected_length = frappe.db.type_map[column.fieldtype]
                actual = current[name]
                # Existing data must never be silently truncated by a migration.
                if actual.type.lower() != expected_type:
                    raise UnsupportedSQL(f"Type migration for {self.doctype}.{name} requires an explicit migration")
                if expected_type == "nvarchar" and expected_length != "max":
                    required = int(column.length or expected_length)
                    actual_length = actual.max_length // 2 if actual.max_length > 0 else 4000
                    if required > actual_length:
                        frappe.db.native(f"ALTER TABLE {qi(self.table_name)} ALTER COLUMN {qi(name)} nvarchar({required}) " + ("NULL" if actual.nullable else "NOT NULL"))
        self.indexes()

    def indexes(self):
        for name, column in self.columns.items():
            typename = frappe.db.type_map.get(column.fieldtype)
            if not typename or typename == ("nvarchar", "max"):
                if column.unique:
                    raise UnsupportedSQL(f"A unique constraint on an unbounded field needs an explicit adaptation: {self.doctype}.{name}")
                # Upstream DBTable also excludes text fields from ordinary
                # search_index B-trees. This does not implement full-text search.
                continue
            if column.unique:
                frappe.db.add_unique(self.doctype, [name])
            elif column.set_index:
                frappe.db.add_index(self.doctype, [name])
        if self.meta.istable:
            frappe.db.add_index(self.doctype, ["parent"])
