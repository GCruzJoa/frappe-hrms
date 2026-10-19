"""Translate SQL syntax without interpolating data or rewriting quoted literals.

Bind markers survive dialect translation, so a SQL AST rewrite can reorder or
duplicate expressions without binding the wrong value to an ODBC placeholder.
"""

from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError


class UnsupportedSQL(NotImplementedError):
    """The experimental backend cannot represent this SQL statement safely."""


PREFIX = "__frappe_mssql_bind_"


def parse_unicode_literal(argument):
    """Decode a complete T-SQL Unicode literal as data for Frappe's parser.

    Return None for anything else so upstream field validation still applies.
    A decoded string is passed to the parameterized builder, never executed.
    """
    if re.fullmatch(r"[Nn]'(?:[^']|'')*'", argument):
        return argument[2:-1].replace("''", "'")
    return None


def ensure_read_only(query, values=None, *, native=False):
    """Enforce Frappe's read-only transaction contract at the adapter boundary."""
    try:
        marked, _ = _mark(str(query), values, native=native)
        statements = sqlglot.parse(marked, read="tsql" if native else "mysql", error_level=ErrorLevel.RAISE)
        forbidden = (exp.DML, exp.DDL, exp.Into, exp.NextValueFor, exp.Command)
        if len(statements) != 1 or not isinstance(statements[0], exp.Query):
            raise UnsupportedSQL("Read-only transactions only accept a single SELECT query")
        if any(isinstance(node, forbidden) for node in statements[0].walk()):
            raise UnsupportedSQL("Writing or advancing a sequence in a read-only transaction is forbidden")
    except SqlglotError as error:
        raise UnsupportedSQL("Cannot validate the read-only query") from error


def _parameter_type(value):
    if value is None or isinstance(value, str):
        return "nvarchar(max)"
    if isinstance(value, bool):
        return "bit"
    if isinstance(value, int):
        return "bigint" if -(2**63) <= value < 2**63 else "decimal(38,0)"
    if isinstance(value, Decimal):
        return f"decimal(38,{max(0, -value.as_tuple().exponent)})"
    if isinstance(value, float):
        return "float"
    if isinstance(value, datetime):
        return "datetime2(6)"
    if isinstance(value, date):
        return "date"
    if isinstance(value, (time, timedelta)):
        return "time(6)"
    if isinstance(value, bytes):
        return "varbinary(max)"
    raise UnsupportedSQL("Unsupported parameter type in a grouped expression")


def _normalize_single_values(expression, parameters):
    """VALUES infers one type per column; Singles intentionally stores text."""
    if not isinstance(expression, exp.Insert) or not isinstance(expression.this, exp.Schema):
        return
    if expression.this.this.name != "tabSingles":
        return
    columns = [column.name for column in expression.this.expressions]
    rows = expression.args.get("expression")
    if "value" not in columns or not isinstance(rows, exp.Values):
        raise UnsupportedSQL("Singles insertion requires explicit columns and VALUES")
    position = columns.index("value")
    for row in rows.expressions:
        value = row.expressions[position]
        if isinstance(value, exp.Parameter):
            match = re.fullmatch("@" + PREFIX + r"(\d+)", value.sql(dialect="mysql"))
            if not match:
                raise UnsupportedSQL("Unknown Singles value parameter")
            index = int(match.group(1))
            item = parameters[index]
            if item is None or isinstance(item, str):
                continue
            if isinstance(item, bool):
                item = int(item)
            if isinstance(item, datetime):
                item = item.isoformat(sep=" ")
            elif isinstance(item, (date, time)):
                item = item.isoformat()
            elif isinstance(item, bytes):
                item = item.decode("utf-8")
            parameters[index] = str(item)
        elif isinstance(value, exp.Literal) and value.is_number:
            value.replace(exp.Literal.string(value.this))
        elif not isinstance(value, (exp.Literal, exp.Null)):
            raise UnsupportedSQL("Computed Singles values require an explicit text representation")


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
    def compatible_function(node):
        if isinstance(node, exp.Coalesce) and not node.expressions:
            return node.this.copy()
        if isinstance(node, exp.Anonymous) and node.name.upper() == "UNIX_TIMESTAMP":
            if len(node.expressions) > 1:
                raise UnsupportedSQL("UNIX_TIMESTAMP expects at most one argument")
            instant = node.expressions[0].copy() if node.expressions else exp.Anonymous(this="SYSUTCDATETIME")
            if node.expressions:
                instant = exp.Cast(this=instant, to=exp.DataType.build("datetime2(6)", dialect="tsql"))
                instant = exp.Anonymous(this="DATEADD", expressions=[exp.Var(this="MINUTE"),
                    exp.Literal.number(-int(utc_offset_minutes)), instant])
            delta = exp.Anonymous(this="DATEDIFF_BIG", expressions=[exp.Var(this="MICROSECOND"),
                exp.Cast(this=exp.Literal.string("1970-01-01"), to=exp.DataType.build("datetime2(6)", dialect="tsql")), instant])
            if node.expressions:
                delta = exp.Cast(this=delta, to=exp.DataType.build("decimal(28,6)", dialect="tsql"))
            return exp.IntDiv(this=delta, expression=exp.Literal.number(1000000)) if not node.expressions else exp.Div(this=delta, expression=exp.Literal.number(1000000))
        if isinstance(node, exp.ConcatWs):
            return exp.Anonymous(this="CONCAT_WS", expressions=[item.copy() for item in node.expressions])
        return node
    expression = expression.transform(compatible_function)
    def row_predicate(node):
        if isinstance(node, exp.In) and not node.expressions and not node.args.get("query"):
            return exp.EQ(this=exp.Literal.number(1), expression=exp.Literal.number(0))
        if isinstance(node, exp.In) and isinstance(node.this.unnest(), exp.Tuple):
            if node.args.get("query"):
                raise UnsupportedSQL("Row IN subqueries require an explicit adaptation")
            left_tuple = node.this.unnest()
            alternatives = []
            for row in node.expressions:
                row = row.unnest()
                if not isinstance(row, exp.Tuple) or len(row.expressions) != len(left_tuple.expressions):
                    raise UnsupportedSQL("Row IN requires equally sized explicit tuples")
                alternatives.append(exp.and_(*(exp.EQ(this=left.copy(), expression=right.copy())
                    for left, right in zip(left_tuple.expressions, row.expressions))))
            return exp.or_(*alternatives)
        return node
    expression = expression.transform(row_predicate)
    def scalar_predicate(node):
        condition = node.this if isinstance(node, exp.Paren) else node
        if isinstance(condition, (exp.Predicate, exp.And, exp.Or, exp.Not)):
            return exp.Case().when(condition.copy(), exp.Literal.number(1)).when(
                exp.Not(this=condition.copy()), exp.Literal.number(0)).else_(exp.Null())
        return node
    for select in expression.find_all(exp.Select):
        for item in select.expressions:
            if isinstance(item, exp.Alias):
                item.set("this", scalar_predicate(item.this))
            else:
                replacement = scalar_predicate(item)
                if replacement is not item:
                    item.replace(replacement)
    for ordered in expression.find_all(exp.Ordered):
        ordered.set("this", scalar_predicate(ordered.this))
    for index, subquery in enumerate(expression.find_all(exp.Subquery)):
        if isinstance(subquery.parent, (exp.From, exp.Join)) and not subquery.alias:
            subquery.set("alias", exp.TableAlias(this=exp.to_identifier(f"__mssql_derived_{index}", quoted=True)))
    for select in expression.find_all(exp.Select):
        group = select.args.get("group")
        if not group:
            continue
        tables = {table.alias_or_name: table.name for table in select.find_all(exp.Table)
            if table.find_ancestor(exp.Select) is select}
        sole = next(iter(tables)) if len(tables) == 1 else None
        keyed = {field.table or sole for field in group.expressions
            if isinstance(field, exp.Column) and field.name == "name"
            and tables.get(field.table or sole, "").startswith("tab")}
        # Frappe DocTypes have name as their primary key. Adding columns of that
        # same row cannot split a group, and implements functional dependency
        # rules that MariaDB/Postgres accept but SQL Server does not infer.
        roots = list(select.expressions)
        if select.args.get("order"):
            roots.extend(select.args["order"].expressions)
        for root in roots:
            for column in root.find_all(exp.Column):
                if column.find_ancestor(exp.Select) is not select:
                    continue
                if (column.table or sole) not in keyed:
                    continue
                if column.find_ancestor(exp.AggFunc):
                    continue
                if not any(column == field for field in group.expressions):
                    group.append("expressions", column.copy())
    for update in expression.find_all(exp.Update):
        target = update.this
        if not isinstance(target, exp.Table):
            raise UnsupportedSQL("Unexpected UPDATE target")
        target_names = {target.name, target.alias_or_name}
        for assignment in update.expressions:
            column = assignment.this
            if isinstance(column, exp.Column) and column.table:
                if column.table not in target_names:
                    raise UnsupportedSQL("Updating multiple joined tables requires separate statements")
                column.set("table", None)
        if target.alias or target.args.get("joins"):
            if update.args.get("from_"):
                raise UnsupportedSQL("An aliased UPDATE with an existing FROM needs an explicit adaptation")
            update.set("from_", exp.From(this=target.copy()))
            update.set("this", exp.to_table(target.alias_or_name, quoted=True))
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


def _pieces(sql, *, mysql_escapes=True):
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
                    if mysql_escapes and sql[i] == "\\" and ch in "'\"":
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


def _mark(query, values, *, native=False):
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
                     for protected, text in _pieces(query, mysql_escapes=not native))
    if not mapping and consumed != len(positional):
        raise ValueError("Unused positional SQL parameters")
    return marked, parameters


def compile_query(query, values=None, *, native=False, utc_offset_minutes=0):
    """Return SQL Server SQL and positional parameters for pyodbc.execute."""
    marked, params = _mark(str(query), values, native=native)
    grouped = False
    if native:
        rendered = marked
    else:
        try:
            expressions = sqlglot.parse(marked, read="mysql", error_level=ErrorLevel.RAISE)
            if len(expressions) != 1 or expressions[0] is None:
                raise UnsupportedSQL("Exactly one SQL statement is supported per execution")
            _normalize_single_values(expressions[0], params)
            grouped = expressions[0].find(exp.Group) is not None
            rendered = _render(expressions[0], utc_offset_minutes=utc_offset_minutes)
        except SqlglotError as exc:
            # Deliberately do not include query text or bound secrets in errors.
            raise UnsupportedSQL("SQL translation failed; add an explicit backend adaptation") from exc
    bound = []
    pattern = re.compile(r"@" + PREFIX + r"(\d+)\b")

    if grouped:
        # Repeated ODBC '?' markers become different SQL Server variables. The
        # engine then rejects identical parameterized SELECT/GROUP BY expressions.
        # Bind once to typed local variables so those expressions stay identical.
        indexes = []
        for protected, text in _pieces(rendered, mysql_escapes=False):
            if not protected:
                indexes.extend(int(match.group(1)) for match in pattern.finditer(text))
        canonical = {}
        replacements = {}
        for index in indexes:
            key = (_parameter_type(params[index]), params[index])
            replacements[index] = canonical.setdefault(key, index)
        normalized = [replacements[index] for index in indexes]
        if len(normalized) != len(set(normalized)):
            unique = list(dict.fromkeys(normalized))
            declarations = ", ".join(f"@{PREFIX}{index} {_parameter_type(params[index])} = ?" for index in unique)
            rendered = "".join(text if protected else pattern.sub(lambda match: f"@{PREFIX}{replacements[int(match.group(1))]}", text)
                for protected, text in _pieces(rendered, mysql_escapes=False))
            return "DECLARE " + declarations + "; " + rendered, [params[index] for index in unique]

    def replace(match):
        bound.append(params[int(match.group(1))])
        return "?"

    result = "".join(text if protected else pattern.sub(replace, text)
                     for protected, text in _pieces(rendered, mysql_escapes=False))
    return result, bound


def quote_identifier(name):
    if not isinstance(name, str) or not name or len(name) > 128 or "\x00" in name:
        raise ValueError("Invalid SQL Server identifier (1–128 characters required)")
    return "[" + name.replace("]", "]]") + "]"
