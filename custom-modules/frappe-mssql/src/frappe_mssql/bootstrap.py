"""Translate the pinned Frappe bootstrap schema without a framework import."""
from sqlglot import parse, exp
from .sql import quote_identifier as qi, UnsupportedSQL


def seed_statements(source):
    """Translate only the known core bootstrap DDL, preserving column metadata."""
    for statement in parse(source, read="mysql"):
        if statement is None or isinstance(statement, exp.Drop):
            continue
        if not isinstance(statement, exp.Create) or statement.args.get("kind") != "TABLE":
            raise UnsupportedSQL("Unexpected statement in the core bootstrap schema")
        schema = statement.this
        definitions = []
        for item in schema.expressions:
            if isinstance(item, exp.ColumnDef):
                kind = item.args["kind"]
                original = kind.sql(dialect="mysql").lower()
                if original.startswith("varchar"):
                    mapped = "n" + original
                elif original in ("text", "mediumtext", "longtext"):
                    mapped = "nvarchar(max)"
                elif original.startswith(("datetime", "timestamp")):
                    mapped = "datetime2(6)"
                elif original.startswith("tinyint"):
                    mapped = "smallint"
                elif original.startswith(("int", "bigint", "smallint", "decimal", "date", "time")):
                    mapped = original
                else:
                    raise UnsupportedSQL(f"Bootstrap type requires explicit adaptation: {original}")
                # The database supplies the SQL Server collation; MySQL column
                # collation names must never survive into the bootstrap DDL.
                constraints = " ".join(c.sql(dialect="tsql") for c in item.constraints
                                       if not isinstance(c.kind, exp.CollateColumnConstraint))
                definitions.append(f"{qi(item.name)} {mapped} {constraints}")
            elif isinstance(item, exp.PrimaryKey):
                columns = ",".join(qi(column.name) for column in item.expressions)
                definitions.append(f"PRIMARY KEY NONCLUSTERED ({columns})")
            elif isinstance(item, exp.IndexColumnConstraint):
                # Bootstrap secondary indexes are installed during the DocType sync.
                continue
            else:
                raise UnsupportedSQL(f"Unexpected bootstrap constraint: {type(item).__name__}")
        yield f"CREATE TABLE {qi(schema.this.name)} ({','.join(definitions)})"
