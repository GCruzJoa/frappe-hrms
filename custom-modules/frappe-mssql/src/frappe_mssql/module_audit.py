"""Inventory actual SQL Server coverage across installed modules.

Read-only schema/report smoke checks are deliberately distinct from verified
business workflows. Missing fixtures are reported, never counted as a pass.
"""
from collections import Counter
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import traceback

import frappe
import pyodbc

from .acceptance import COMPANY, _pilot_only
from .sql import UnsupportedSQL


def _declared_filters(report, values):
    """Use only filters declared by a report, without executing browser scripts."""
    declared = {field.fieldname for field in report.get("filters", []) if field.fieldname}
    path = Path(frappe.get_module_path(report.module, "report", frappe.scrub(report.name),
        frappe.scrub(report.name) + ".js"))
    script = path.read_text(encoding="utf-8") if path.is_file() else ""
    for shared in ("purchase_trends_filters", "sales_trends_filters"):
        if "erpnext." + shared in script:
            script += "\n" + Path(frappe.get_app_path("erpnext", "public", "js", shared + ".js")).read_text(encoding="utf-8")
    if "erpnext.get_stock_balance_report_settings" in script:
        script += "\n" + Path(frappe.get_app_path("erpnext", "public", "js", "stock_balance_report.js")).read_text(encoding="utf-8")
    matches = list(re.finditer(r'''["']?fieldname["']?\s*:\s*["']([^"']+)["']''', script))
    defaults = {}
    for index, match in enumerate(matches):
        key = match.group(1)
        declared.add(key)
        chunk = script[match.end():matches[index+1].start() if index+1 < len(matches) else len(script)]
        literal = re.search(r'''default\s*:\s*(?:__\()?"((?:[^"\\]|\\.)*)"''', chunk)
        if literal:
            defaults[key] = json.loads('"' + literal.group(1) + '"')
        if any(kind in chunk for kind in ("MultiSelectList", "MultiSelectPills")) and key in values and not isinstance(values[key], list):
            values[key] = [values[key]]
    if "erpnext.financial_statements" in script:
        declared.update(("company", "filter_based_on", "period_start_date", "period_end_date",
            "from_fiscal_year", "to_fiscal_year", "periodicity", "include_default_book_entries"))
    if declared:
        values = {key: value for key, value in values.items() if key in declared}
    else:
        # Query reports carry their parameters in SQL rather than browser code.
        if report.report_type == "Query Report":
            keys = set(re.findall(r"%\(([^)]+)\)s", report.query or ""))
            values = {key: value for key, value in values.items() if key in keys}
    values.update(defaults)
    return frappe._dict(values)


def catalog():
    _pilot_only()
    installed = {row.name: row.module for row in frappe.get_all("DocType", fields=["name", "module"], limit_page_length=0)}
    expected = {}
    source_counts = {}
    for app in ("frappe", "erpnext", "hrms"):
        paths = Path(frappe.get_app_path(app)).glob("**/doctype/*/*.json")
        names = []
        for path in paths:
            item = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(item, dict) and item.get("doctype") == "DocType":
                expected[item["name"]] = dict(app=app, module=item["module"])
                names.append(item["name"])
        source_counts[app] = len(names)
    missing = {name: details for name, details in expected.items() if name not in installed}
    mismatch = {name: dict(expected=details["module"], installed=installed[name])
        for name, details in expected.items() if name in installed and installed[name] != details["module"]}
    result = dict(source_counts=source_counts, installed=len(installed), expected=len(expected),
        modules={name: app for app in ("frappe", "erpnext", "hrms") for name in frappe.get_module_list(app)},
        missing=missing, module_mismatches=mismatch,
        status="passed" if not missing and not mismatch else "failed")
    Path("/tmp/frappe-mssql-catalog-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def run(phase="schema", module=None):
    _pilot_only()
    if phase not in ("schema", "reports"):
        raise ValueError("Expected schema or reports audit")
    modules = {}
    for app in ("frappe", "erpnext", "hrms"):
        for name in frappe.get_module_list(app):
            modules[name] = app
    if module:
        if module not in modules:
            raise ValueError("Module is not part of the pinned applications")
        modules = {module: modules[module]}
    rows = []
    fixture_filters = {}
    if frappe.local.site == "mssql-qa.localhost":
        fixture_path = Path(frappe.get_site_path("private", "mssql-report-fixtures.json"))
        if fixture_path.exists():
            fixture_filters = json.loads(fixture_path.read_text())["filters"]
    frappe.db.native("SELECT 1")
    frappe.db.set_execution_timeout(20)
    if phase == "schema":
        targets = frappe.get_all("DocType", filters={"module": ["in", list(modules)]},
            fields=["name", "module", "issingle", "istable", "is_virtual"], order_by="module,name", limit_page_length=0)
    else:
        targets = frappe.get_all("Report", filters={"module": ["in", list(modules)],
            "is_standard": "Yes", "disabled": 0,
            "report_type": ["in", ["Script Report", "Query Report"]]},
            fields=["name", "module", "report_type"], order_by="module,name", limit_page_length=0)
    for index, target in enumerate(targets):
        row = dict(name=target.name, module=target.module, app=modules[target.module],
            level="schema-read" if phase == "schema" else "report-smoke")
        try:
            if phase == "schema":
                meta = frappe.get_meta(target.name)
                if target.is_virtual:
                    row.update(status="not-applicable", reason="virtual-doctype")
                elif target.issingle:
                    frappe.get_single(target.name).as_dict()
                    row.update(status="passed")
                else:
                    values = frappe.get_all(target.name, fields=["*"], limit_page_length=1,
                        order_by="modified desc")
                    row.update(status="passed", sample_rows=len(values))
            else:
                from frappe.desk.query_report import get_report_result
                today = date.today()
                filters = frappe._dict(company=COMPANY, from_date=f"{today.year}-01-01",
                    to_date=f"{today.year}-12-31", period_start_date=f"{today.year}-01-01",
                    period_end_date=f"{today.year}-12-31", from_fiscal_year=str(today.year),
                    to_fiscal_year=str(today.year), fiscal_year=str(today.year), year=str(today.year),
                    month=today.month, periodicity="Yearly", filter_based_on="Fiscal Year",
                    include_default_book_entries=1, currency="DOP", presentation_currency="DOP",
                    party_type="Customer", account_type="Receivable", value_quantity="Value",
                    tree_type="Customer", based_on="Item", group_by="Employee", ageing_based_on="Due Date",
                    report_date=today.isoformat(), range1=30, range2=60, range3=90, range4=120,
                    range="30,60,90,120", period="Monthly", date=today.isoformat(),
                    start_date=f"{today.year}-01-01", end_date=f"{today.year}-12-31",
                    parameter="Department", user="Administrator", doctype="Employee",
                    show_future_payments=0, show_net_values_in_party_account=0,
                    show_zero_values=1, consolidated=0, docstatus=1, payment_type="Pay",
                    employee_status="Active", summarize=0)
                report = frappe.get_doc("Report", target.name)
                report.disable_prepared_report_automation = 1
                filters.update(fixture_filters)
                filters = _declared_filters(report, dict(filters))
                if target.name == "Monthly Attendance Sheet":
                    filters.filter_based_on = "Month"
                    filters.group_by = "Department"
                if target.name in ("Item-wise Sales Register", "Item-wise Purchase Register"):
                    filters.group_by = "Item"
                if target.name == "Employee Birthday":
                    filters.month = today.strftime("%b")
                if target.name == "Salary Register":
                    filters.docstatus = "Submitted"
                output = get_report_result(report, filters)
                data = output[1] if isinstance(output, (list, tuple)) and len(output) > 1 else None
                row.update(status="passed", has_output=output is not None,
                    result_rows=len(data) if isinstance(data, (list, tuple)) else None,
                    fixtures="qa-postings" if fixture_filters else "baseline")
        except Exception as error:
            database_error = isinstance(error, (pyodbc.Error, UnsupportedSQL))
            region = {"IRS 1099": "United States", "UAE VAT 201": "United Arab Emirates", "VAT Audit Report": "South Africa"}.get(target.name)
            country_gate = (region and isinstance(error, frappe.ValidationError)
                and "only available" in str(error) and region in str(error)
                and frappe.db.get_value("Company", COMPANY, "country") == "Dominican Republic")
            status = "failed" if database_error or not isinstance(error, frappe.ValidationError) else "needs-fixtures-or-review"
            if country_gate:
                status = "not-applicable-country"
            row.update(status=status,
                exception=type(error).__name__, message=str(error)[:1500],
                traceback=traceback.format_exc()[-6500:])
            if database_error:
                row["last_sql"] = frappe.db.last_query
        finally:
            frappe.db.rollback()
        rows.append(row)
        if (index + 1) % 25 == 0:
            print(json.dumps(dict(progress=index+1, total=len(targets), phase=phase)), flush=True)
    result = dict(verified_at=datetime.now(timezone.utc).isoformat(), phase=phase,
        classification="smoke-coverage-not-business-certification",
        totals=dict(Counter(row["status"] for row in rows)),
        modules={name: dict(Counter(row["status"] for row in rows if row["module"] == name)) for name in modules},
        entries=rows)
    path = Path(f"/tmp/frappe-mssql-{phase}-audit.json")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(path=str(path), totals=result["totals"], modules=len(modules))
