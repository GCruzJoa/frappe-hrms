"""Translate SQL syntax without interpolating data or rewriting quoted literals.

Bind markers survive dialect translation, so a SQL AST rewrite can reorder or
duplicate expressions without binding the wrong value to an ODBC placeholder.
"""

from collections.abc import Mapping
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError


class UnsupportedSQL(NotImplementedError):
    """The experimental backend cannot represent this SQL statement safely."""


PREFIX = "__frappe_mssql_bind_"


def _render(expression, utc_offset_minutes=0):
    def clock(node):
        named_clock = isinstance(node, exp.Anonymous) and node.name.upper() in ("NOW", "SYSDATE", "UTC_TIMESTAMP")
        if isinstance(node, (exp.CurrentTimestamp, exp.CurrentDate, exp.CurrentTime)) or named_clock:
            if named_clock and node.expressions:
                raise UnsupportedSQL("Clock precision argument requires an explicit adaptation")
            value = exp.Anonymous(this="DATEADD", expressions=[exp.Var(this="MINUTE"), exp.Literal.number(int(utc_offset_minutes)), exp.Anonymous(this="SYSUTCDATETIME")])
            if named_clock and node.name.upper() == "UTC_TIMESTAMP":
                value = exp.Anonymous(this="SYSUTCDATETIME")
            if isinstance(node, exp.CurrentDate):
                value = exp.Cast(this=value, to=exp.DataType.build("DATE"))
            elif isinstance(node, exp.CurrentTime):
                value = exp.Cast(this=value, to=exp.DataType.build("TIME(6)", dialect="tsql"))
            return value
        return node
    expression = expression.transform(clock)
    # MySQL FOR UPDATE must retain its locking semantics, especially for tabSeries.
    for select in expression.find_all(exp.Select):
        if select.args.get("locks"):
            hints = [exp.Var(this="UPDLOCK"), exp.Var(this="HOLDLOCK")]
            for lock in select.args["locks"]:
                if not lock.args.get("update") or lock.args.get("wait") is False:
                    raise UnsupportedSQL("Unsupported locking read variant")
                if lock.args.get("wait") is True:
                    hints.append(exp.Var(this="NOWAIT"))
            select.set("locks", None)
            for table in select.find_all(exp.Table):
                table.set("hints", [exp.WithTableHint(expressions=[hint.copy() for hint in hints])])
    if isinstance(expression, exp.Insert) and (expression.args.get("conflict") or expression.args.get("ignore") or expression.args.get("overwrite")):
        return _render_upsert(expression)
    return expression.sql(dialect="tsql", identify=True, unsupported_level=ErrorLevel.RAISE)


def _render_upsert(expression):
    schema = expression.this
    rows = expression.args.get("expression")
    if not isinstance(schema, exp.Schema) or not isinstance(rows, exp.Values):
        raise UnsupportedSQL("Only VALUES-based upserts are implemented")
    table = schema.this.name
    columns = [column.name for column in schema.expressions]
    keys = {"__Auth": ["doctype", "name", "fieldname"], "__UserSettings": ["user", "doctype"], "tabSingles": ["doctype", "field"], "__global_search": ["doctype", "name"]}.get(table, ["name"])
    if not all(key in columns for key in keys):
        raise UnsupportedSQL("Upsert conflict key requires explicit adaptation")
    condition = " AND ".join(f"target.{quote_identifier(key)}=source.{quote_identifier(key)}" for key in keys)
    values = rows.sql(dialect="tsql")
    names = ",".join(quote_identifier(column) for column in columns)
    insert_values = ",".join("source." + quote_identifier(column) for column in columns)
    update_sql = ""
    conflict = expression.args.get("conflict")
    if conflict:
        assignments = []
        for assignment in conflict.expressions:
            if not isinstance(assignment, exp.EQ):
                raise UnsupportedSQL("Unexpected upsert assignment")
            def from_source(node):
                if isinstance(node, exp.Anonymous) and node.name.upper() == "VALUES":
                    return exp.column(node.expressions[0].name, table="source", quoted=True)
                return node
            value = assignment.expression.copy().transform(from_source).sql(dialect="tsql", identify=True)
            assignments.append(f"target.{quote_identifier(assignment.this.name)}={value}")
        if assignments:
            update_sql = " WHEN MATCHED THEN UPDATE SET " + ",".join(assignments)
    elif expression.args.get("overwrite"):
        raise UnsupportedSQL("REPLACE semantics require explicit adaptation")
    return (f"MERGE INTO {quote_identifier(table)} WITH (HOLDLOCK) AS target USING ({values}) AS source ({names}) ON {condition}"
            + update_sql + f" WHEN NOT MATCHED THEN INSERT ({names}) VALUES ({insert_values});")


def _pieces(sql):
    """Yield (protected, text) for strings, identifiers and SQL comments."""
    i = start = 0
    while i < len(sql):
        ch = sql[i]
        if ch in "'\"`[" or sql.startswith("--", i) or sql.startswith("/*", i):
            if start < i:
                yield False, sql[start:i]
            begin = i
            if sql.startswith("--", i):
                end = sql.find("\n", i)
                i = len(sql) if end < 0 else end + 1
            elif sql.startswith("/*", i):
                depth = 1
                i += 2
                while i < len(sql) and depth:
                    if sql.startswith("/*", i):
                        depth += 1
                        i += 2
                    elif sql.startswith("*/", i):
                        depth -= 1
                        i += 2
                    else:
                        i += 1
                if depth:
                    raise ValueError("Unterminated SQL comment")
            else:
                close = "]" if ch == "[" else ch
                i += 1
                while i < len(sql):
                    if sql[i] == close:
                        if i + 1 < len(sql) and sql[i + 1] == close:
                            i += 2
                            continue
                        i += 1
                        break
                    if sql[i] == "\\" and ch in "'\"":
                        i += 2
                    else:
                        i += 1
                else:
                    raise ValueError("Unterminated SQL quote")
            yield True, sql[begin:i]
            start = i
        else:
            i += 1
    if start < len(sql):
        yield False, sql[start:]


def _mark(query, values):
    if PREFIX in query:
        raise ValueError("SQL contains a reserved backend marker")
    parameters = []
    mapping = isinstance(values, Mapping)
    positional = tuple(values or ()) if not mapping else ()
    consumed = 0

    def marker(value):
        if isinstance(value, (list, tuple, set, frozenset)):
            if not value:
                return "(SELECT NULL WHERE 1=0)"
            return "(" + ", ".join(marker(item) for item in value) + ")"
        parameters.append(value)
        return f"@{PREFIX}{len(parameters) - 1}"

    def substitute(match):
        nonlocal consumed
        if match.group(0) == "%%":
            return "%"
        key = match.group(1)
        if key is not None:
            if not mapping:
                raise ValueError("Named SQL parameter requires a mapping")
            return marker(values[key])
        if mapping or consumed >= len(positional):
            raise ValueError("Missing positional SQL parameter")
        result = marker(positional[consumed])
        consumed += 1
        return result

    pattern = re.compile(r"%%|%\(([^)]+)\)s|%s")
    marked = "".join(text if protected else pattern.sub(substitute, text)
                     for protected, text in _pieces(query))
    if not mapping and consumed != len(positional):
        raise ValueError("Unused positional SQL parameters")
    return marked, parameters


def compile_query(query, values=None, *, native=False, utc_offset_minutes=0):
    """Return SQL Server SQL and positional parameters for pyodbc.execute."""
    marked, params = _mark(str(query), values)
    if native:
        rendered = marked
    else:
        try:
            expressions = sqlglot.parse(marked, read="mysql", error_level=ErrorLevel.RAISE)
            if len(expressions) != 1 or expressions[0] is None:
                raise UnsupportedSQL("Exactly one SQL statement is supported per execution")
            rendered = _render(expressions[0], utc_offset_minutes=utc_offset_minutes)
        except SqlglotError as exc:
            # Deliberately do not include query text or bound secrets in errors.
            raise UnsupportedSQL("SQL translation failed; add an explicit backend adaptation") from exc
    bound = []
    pattern = re.compile(r"@" + PREFIX + r"(\d+)\b")

    def replace(match):
        bound.append(params[int(match.group(1))])
        return "?"

    result = "".join(text if protected else pattern.sub(replace, text)
                     for protected, text in _pieces(rendered))
    return result, bound


def quote_identifier(name):
    if not isinstance(name, str) or not name or len(name) > 128 or "\x00" in name:
        raise ValueError("Invalid SQL Server identifier (1–128 characters required)")
    return "[" + name.replace("]", "]]") + "]"
