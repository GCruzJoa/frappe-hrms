"""Inventory SQL portability candidates without claiming they are all failures."""
import argparse
import ast
import json
from pathlib import Path


def inventory(root):
    rows = []
    for path in Path(root).rglob("*.py"):
        if any(part in ("node_modules", ".git", "env", "tests") for part in path.parts) or path.name.startswith("test_"):
            continue
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            rows.append({"file": path.relative_to(root).as_posix(), "line": 1, "kind": "parse-error"})
            continue
        for node in ast.walk(tree):
            kind = None
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in ("sql", "sql_ddl", "multisql"):
                    kind = node.func.attr
            elif isinstance(node, ast.Compare):
                text = ast.get_source_segment(source, node) or ""
                if "db_type" in text and any(db in text for db in ("mariadb", "postgres", "sqlite")):
                    kind = "engine-specific-branch"
            if kind:
                rows.append({"file": path.relative_to(root).as_posix(), "line": node.lineno, "kind": kind})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("output")
    args = parser.parse_args()
    rows = inventory(args.root)
    Path(args.output).write_text(json.dumps({"classification": "portability-candidates-not-confirmed-defects", "entries": rows}, indent=2) + "\n")
    print(f"Recorded {len(rows)} SQL/engine portability candidates")
