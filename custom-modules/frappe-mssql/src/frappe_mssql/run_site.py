"""Run the standalone adapter's operational helpers in the dedicated site."""
import argparse
from contextlib import suppress
import importlib
import json
import os
from pathlib import Path

import frappe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("method", choices=("acceptance.prepare_setup", "acceptance.run",
        "acceptance.assert_persistence", "backup.run"))
    parser.add_argument("--kwargs", default="{}")
    args = parser.parse_args()
    kwargs = json.loads(args.kwargs)
    if not isinstance(kwargs, dict):
        raise TypeError("Operational keyword arguments must be a JSON object")
    sites = Path("/home/frappe/frappe-bench/sites")
    os.chdir(sites)
    frappe.init("mssql.localhost", sites_path=str(sites))
    try:
        if frappe.conf.db_type != "mssql" or frappe.conf.db_name != "frappe_pilot":
            raise RuntimeError("Operational helpers are restricted to the SQL Server pilot")
        frappe.connect()
        module, method = args.method.rsplit(".", 1)
        result = getattr(importlib.import_module("frappe_mssql." + module), method)(**kwargs)
        frappe.db.commit()
        print(json.dumps(result, ensure_ascii=False))
    except BaseException:
        with suppress(Exception):
            if frappe.db:
                frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
