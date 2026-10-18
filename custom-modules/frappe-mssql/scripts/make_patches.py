"""Generate reviewed integration patches against the exact upstream source tree.

This writes patch artifacts, never the upstream checkout itself.
"""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError(f"Upstream integration anchor changed: {old[:100]!r}")
    return source.replace(old, new, 1)


def database_module(source):
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    inserts = []
    methods = {
        "get_db": "from frappe_mssql.database import MSSQLDatabase\n\t\treturn MSSQLDatabase(socket, host, user, password, port, cur_db_name)",
        "setup_database": "from frappe_mssql.setup_db import setup_database as setup_mssql\n\t\treturn setup_mssql(force, verbose, mariadb_user_host_login_scope)",
        "bootstrap_database": "from frappe_mssql.setup_db import bootstrap_database as bootstrap_mssql\n\t\treturn bootstrap_mssql(verbose, source_sql)",
        "drop_user_and_database": "from frappe_mssql.setup_db import drop_user_and_database as drop_mssql\n\t\treturn drop_mssql(db_name, db_user)",
        "get_command": "from frappe_mssql.sql import UnsupportedSQL\n\t\traise UnsupportedSQL('Use the pilot native SQL Server backup/restore scripts')",
    }
    found = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in methods:
            imports = [entry for entry in node.body if isinstance(entry, ast.Import) and any(alias.name == "frappe" for alias in entry.names)]
            if len(imports) != 1:
                raise RuntimeError(f"Cannot locate frappe import for {node.name}")
            position = sum(map(len, lines[:imports[0].end_lineno]))
            inserts.append((position, "\n\tif frappe.conf.db_type == \"mssql\":\n\t\t" + methods[node.name] + "\n"))
            found.add(node.name)
    if found != set(methods):
        raise RuntimeError(f"Missing database integration entrypoints: {set(methods) - found}")
    for position, text in sorted(inserts, reverse=True):
        source = source[:position] + text + source[position:]
    return source


def explicit_dialect_entries(source):
    """Add a reviewed intermediate SQL branch; actual execution uses T-SQL."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    entries = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        string_keys = {key.value for key in node.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)}
        enum_keys = {key.attr for key in node.keys if isinstance(key, ast.Attribute) and isinstance(key.value, ast.Name) and key.value.id == "db_type_is"}
        for key, value in zip(node.keys, node.values):
            if (isinstance(key, ast.Constant) and key.value == "mariadb" and "mssql" not in string_keys and "postgres" in string_keys):
                new_key = '"mssql"'
            elif isinstance(key, ast.Attribute) and key.attr == "MARIADB" and "MSSQL" not in enum_keys and "POSTGRES" in enum_keys:
                new_key = "db_type_is.MSSQL"
            else:
                continue
            expression = ast.get_source_segment(source, value)
            position = offsets[key.lineno - 1] + key.col_offset
            entries.append((position, f"{new_key}: {expression}, "))
    for position, text in sorted(entries, reverse=True):
        source = source[:position] + text + source[position:]
    return source


def sequence_module(source):
    bodies = {
        "create_sequence": "return db.create_sequence(doctype_name, slug=slug, temporary=temporary, check_not_exists=check_not_exists, cycle=cycle, cache=cache, start_value=start_value, increment_by=increment_by, min_value=min_value, max_value=max_value)",
        "get_next_val": "return db.get_next_sequence_val(doctype_name, slug=slug)",
        "set_next_val": "return db.set_next_sequence_val(doctype_name, next_val, slug=slug, is_val_used=is_val_used)",
        "_get_existing_sequences": "return set(db.native(\"SELECT name FROM sys.sequences WHERE schema_id=SCHEMA_ID('dbo')\", pluck=True))",
    }
    lines = source.splitlines(keepends=True)
    inserts = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in bodies:
            position = sum(map(len, lines[:node.body[0].lineno - 1]))
            inserts.append((position, '\tif db.db_type == "mssql":\n\t\t' + bodies[node.name] + '\n\n'))
    if len(inserts) != len(bodies):
        raise RuntimeError("Sequence integration entrypoints changed")
    for position, text in sorted(inserts, reverse=True):
        source = source[:position] + text + source[position:]
    return replace_once(source, '\t\tif scrub(f"{doctype}_id_seq") in existing:', '\t\tsequence_name = db.get_sequence_name(doctype) if db.db_type == "mssql" else scrub(f"{doctype}_id_seq")\n\t\tif sequence_name in existing:')


def generate(upstream, output, app="frappe"):
    root = Path(upstream)
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    changed = {}
    for path in (root / app).rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        original = path.read_text(encoding="utf-8")
        source = original
        if relative == "frappe/database/__init__.py":
            source = database_module(source)
        elif relative == "frappe/database/sequence.py":
            source = sequence_module(source)
        elif relative == "frappe/commands/site.py":
            source = replace_once(source, 'click.Choice(["mariadb", "postgres", "sqlite"])', 'click.Choice(["mariadb", "postgres", "sqlite", "mssql"])')
        elif relative == "frappe/config.py":
            source = replace_once(source, '\t\traise ValueError(f"Unsupported db_type={db_type}")', '\t\telif db_type == "mssql":\n\t\t\treturn 1433\n\n\t\traise ValueError(f"Unsupported db_type={db_type}")')
            source = replace_once(source, 'config["db_type"] in ("mariadb", "postgres")', 'config["db_type"] in ("mariadb", "postgres", "mssql")')
        elif relative == "frappe/cache_manager.py":
            anchor = '\tif frappe.db.db_type != "sqlite":\n\t\ttable_name ='
            source = replace_once(source, anchor, '\tif frappe.db.db_type == "mssql":\n\t\tcounts = frappe.db.get_table_counts()\n\t\tfrappe.cache.set_value("information_schema:counts", counts)\n\t\treturn counts\n\n' + anchor)
        elif relative == "frappe/database/query.py":
            source = replace_once(source, 'db_type in ("mariadb", "postgres", "sqlite")', 'db_type in ("mariadb", "postgres", "sqlite", "mssql")')
            source = replace_once(source, 'self.is_mariadb = db_type == "mariadb"', 'self.is_mariadb = db_type in ("mariadb", "mssql")  # intermediate query syntax')
            source = replace_once(source, 'self.query.limit(-1 if self.is_sqlite else MAX_LIMIT)', 'self.query.limit(-1 if self.is_sqlite else (9223372036854775807 if db_type == "mssql" else MAX_LIMIT))')
            source = replace_once(source, '\t\t\t\tself.is_postgres\n\t\t\t\tand is_select\n\t\t\t\tand distinct', '\t\t\t\t(self.is_postgres or db_type == "mssql")\n\t\t\t\tand is_select\n\t\t\t\tand distinct')
            source = source.replace('because PostgreSQL requires them to ', 'because this SQL dialect requires them to ')
        elif relative == "frappe/database/database.py":
            source = replace_once(source, '\t\tquery = IFNULL_PATTERN.sub("coalesce(", query.strip())', '\t\tquery = query.strip() if self.db_type == "mssql" else IFNULL_PATTERN.sub("coalesce(", query.strip())')
        elif relative == "frappe/query_builder/utils.py":
            source = replace_once(source, '\tSQLITE = "sqlite"', '\tSQLITE = "sqlite"\n\tMSSQL = "mssql"')
            source = replace_once(source, '\tdb_type_is.SQLITE: SQLite,', '\tdb_type_is.SQLITE: SQLite,\n\tdb_type_is.MSSQL: MariaDB,')
            source = replace_once(source, '\treturn DB_TYPE_MAP[db_type_is(type_of_db)]', '\tif type_of_db == "mssql":\n\t\tfrom frappe_mssql.builder import MSSQL\n\t\treturn MSSQL\n\treturn DB_TYPE_MAP[db_type_is(type_of_db)]')
        elif relative == "frappe/model/base_document.py":
            source = replace_once(source, 'if column_type == "varchar":', 'if column_type == "varchar" or (column_type == "nvarchar" and type_map[df.fieldtype][1] != "max"):')
            source = replace_once(source, 'frappe.db.db_type == "mariadb" and isinstance(docname, str)', 'frappe.db.db_type in ("mariadb", "mssql") and isinstance(docname, str)')
        elif relative == "frappe/model/document.py":
            for variable in ("row.name", "name"):
                source = replace_once(source, f'frappe.db.db_type == "mariadb" and isinstance({variable}, str)', f'frappe.db.db_type in ("mariadb", "mssql") and isinstance({variable}, str)')
        elif relative == "frappe/model/db_query.py":
            source = source.replace('quote_char = "`" if frappe.db.db_type == "mariadb" else', 'quote_char = "`" if frappe.db.db_type in ("mariadb", "mssql") else')
        elif relative == "frappe/utils/password.py":
            source = source.replace('frappe.db.db_type == "mariadb"', 'frappe.db.db_type in ("mariadb", "mssql")')
            source = source.replace('("mariadb", "sqlite", "postgres")', '("mariadb", "sqlite", "postgres", "mssql")')
        elif relative == "frappe/utils/connections.py":
            source = replace_once(source, '("redis", "rediss", "postgres", "mariadb")', '("redis", "rediss", "postgres", "mariadb", "mssql")')
            source = replace_once(source, '3306 if db_type == "mariadb" else 5432', '1433 if db_type == "mssql" else (3306 if db_type == "mariadb" else 5432)')
        elif relative == "frappe/automation/doctype/automation_trigger_queue/automation_trigger_queue.py":
            source = replace_once(source, '\tif frappe.db.db_type == "mariadb":', '\tif frappe.db.db_type == "mssql":\n\t\tfrom frappe_mssql.schema import ensure_queue_dedup_index\n\t\tensure_queue_dedup_index(TABLE, DEDUP_INDEX, WAITING_STATES)\n\telif frappe.db.db_type == "mariadb":')
        # Reviewable per-call branches, never a runtime fallback to another engine.
        source = explicit_dialect_entries(source)
        if source != original:
            ast.parse(source)
            changed[relative] = (original, source)
    patch = "".join("".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile="a/" + name, tofile="b/" + name)) for name, (before, after) in sorted(changed.items()))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{app}.patch").write_text(patch, encoding="utf-8", newline="\n")
    manifest = {"commit": commit, "files": {name: hashlib.sha256(before.encode()).hexdigest() for name, (before, _) in changed.items()}}
    (output / f"{app}-preimages.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Generated integration patch for {commit}: {len(changed)} files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream")
    parser.add_argument("output")
    parser.add_argument("--app", default="frappe", choices=["frappe", "erpnext", "hrms"])
    args = parser.parse_args()
    generate(args.upstream, args.output, args.app)
