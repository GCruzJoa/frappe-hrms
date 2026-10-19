"""Provision a separate SQL Server validation site without replacing the pilot."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shutil

import frappe

from .database import MSSQLDatabase
from .sql import quote_identifier as qi

QA_DATABASE = "frappe_mssql_qa"
QA_SITE = "mssql-qa.localhost"


def seed_reports():
    """Persist fictitious report prerequisites only in the marked QA copy."""
    if frappe.local.site != QA_SITE or frappe.conf.db_name != QA_DATABASE or frappe.db.db_type != "mssql":
        raise RuntimeError("Report fixtures require the isolated QA site")
    marker = Path(frappe.get_site_path(".frappe-mssql-qa.json"))
    if not marker.is_file():
        raise RuntimeError("The QA provisioning marker is missing")
    manifest = Path(frappe.get_site_path("private", "mssql-report-fixtures.json"))
    if manifest.exists():
        result = json.loads(manifest.read_text())
        if not frappe.db.exists("Employee", result["filters"]["employee"]):
            raise RuntimeError("The QA fixture manifest is stale")
        _add_synthetic_tax_slab(result)
        return result
    from .acceptance import COMPANY
    from frappe.utils import today, get_last_day
    prefix = "MSSQL-REPORT-" + datetime.now(timezone.utc).strftime("%H%M%S%f")
    start, end = today()[:4]+"-01-01", today()[:4]+"-12-31"
    previous_mute = frappe.flags.mute_emails
    frappe.flags.mute_emails = True

    def insert(doctype, **values):
        set_name = values.pop("_set_name", None)
        return frappe.get_doc(dict(doctype=doctype, **values)).insert(set_name=set_name)

    try:
        frappe.db.set_single_value("HR Settings", "standard_working_hours", 8)
        employee = insert("Employee", first_name="María", last_name="Peña QA",
            _set_name=prefix+"-EMPLOYEE", employee=prefix+"-EMPLOYEE", gender="Female",
            date_of_birth="1990-01-01", date_of_joining="2024-01-01", company=COMPANY, status="Active")
        holidays = insert("Holiday List", holiday_list_name=prefix, from_date=start, to_date=end)
        assigned = insert("Holiday List Assignment", applicable_for="Employee", assigned_to=employee.name,
            holiday_list=holidays.name, from_date=start)
        assigned.submit()
        component = insert("Salary Component", salary_component=prefix, salary_component_abbr="QAONLY",
            type="Earning", is_tax_applicable=0, depends_on_payment_days=0)
        structure = insert("Salary Structure", name=prefix, company=COMPANY, currency="DOP",
            payroll_frequency="Monthly", earnings=[dict(salary_component=component.name, amount=30000)])
        structure.submit()
        assignment = insert("Salary Structure Assignment", employee=employee.name, company=COMPANY,
            salary_structure=structure.name, from_date=start, currency="DOP", base=30000)
        slab = insert("Income Tax Slab", name=prefix+"-FICTIONAL-ZERO-TAX", company=COMPANY,
            currency="DOP", effective_from=start, slabs=[dict(from_amount=0, percent_deduction=0)])
        slab.submit()
        assignment.income_tax_slab = slab.name
        assignment.save()
        assignment.submit()
        slip = insert("Salary Slip", employee=employee.name, company=COMPANY, salary_structure=structure.name,
            start_date=today()[:7]+"-01", end_date=str(get_last_day(today())), currency="DOP", exchange_rate=1)
        slip.submit()
        period = frappe.db.get_value("Payroll Period", {"company": COMPANY, "start_date": start, "end_date": end}, "name")
        if not period:
            period = insert("Payroll Period", name=prefix, company=COMPANY, start_date=start, end_date=end).name
        attendance = insert("Attendance", employee=employee.name, attendance_date=today(), status="Present", company=COMPANY)
        attendance.submit()
        customer = insert("Customer", customer_name=prefix, customer_type="Company",
            customer_group=frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
            territory=frappe.db.get_value("Territory", {"is_group": 0}, "name"))
        supplier = insert("Supplier", supplier_name=prefix, supplier_type="Company",
            supplier_group=frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"))
        item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        item = insert("Item", item_code=prefix+"-STOCK", item_name=prefix+"-STOCK", item_group=item_group,
            stock_uom="Nos", is_stock_item=1, valuation_rate=10)
        warehouse = frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 0}, "name")
        receipt = insert("Stock Entry", company=COMPANY, stock_entry_type="Material Receipt", to_warehouse=warehouse,
            items=[dict(item_code=item.name, qty=10, basic_rate=10, t_warehouse=warehouse)])
        receipt.submit()
        # Exercise balances and receivable/payable reports with real postings.
        sale = insert("Sales Invoice", company=COMPANY, customer=customer.name,
            items=[dict(item_code=item.name, qty=1, rate=25, warehouse=warehouse)])
        sale.submit()
        purchase = insert("Purchase Invoice", company=COMPANY, supplier=supplier.name,
            bill_no=prefix, bill_date=today(), items=[dict(item_code=item.name, qty=1, rate=10, warehouse=warehouse)])
        purchase.submit()
        product = insert("Item", item_code=prefix+"-FG", item_name=prefix+"-FG", item_group=item_group,
            stock_uom="Nos", is_stock_item=1)
        bom = insert("BOM", item=product.name, quantity=1, company=COMPANY, currency="DOP",
            items=[dict(item_code=item.name, qty=2, rate=10, uom="Nos", stock_uom="Nos")])
        bom.submit()
        plan = insert("Production Plan", company=COMPANY, posting_date=today(), get_items_from="Sales Order",
            po_items=[dict(item_code=product.name, bom_no=bom.name, planned_qty=1,
                planned_start_date=today(), stock_uom="Nos", warehouse=warehouse, use_multi_level_bom=1)])
        plan.submit()
        stock_account = frappe.db.get_value("Account", {"company": COMPANY, "is_group": 0, "account_type": "Stock"}, "name")
        result = dict(site=QA_SITE, prefix=prefix, data="fictitious-qa-only", filters=dict(
            employee=employee.name, salary_structure_assignment=assignment.name, payroll_period=period,
            customer=customer.name, supplier=supplier.name, warehouse=warehouse, item_code=item.name,
            item=item.name, item_group=item_group, account=stock_account, stock_account=stock_account,
            production_plan=plan.name, bom=bom.name, days_since_last_order=30),
            postings=dict(salary_slip=slip.name, stock_entry=receipt.name, sales_invoice=sale.name,
                purchase_invoice=purchase.name))
        frappe.db.commit()
        manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        frappe.flags.mute_emails = previous_mute


def _add_synthetic_tax_slab(result):
    """Upgrade only our already-persisted QA fixtures; no country tax rules."""
    assignment = result["filters"]["salary_structure_assignment"]
    if frappe.db.get_value("Salary Structure Assignment", assignment, "income_tax_slab"):
        return
    from .acceptance import COMPANY
    slab = frappe.get_doc(dict(doctype="Income Tax Slab", name=result["prefix"]+"-FICTIONAL-ZERO-TAX",
        company=COMPANY, currency="DOP", effective_from=datetime.now().strftime("%Y-01-01"),
        slabs=[dict(from_amount=0, percent_deduction=0)])).insert()
    slab.submit()
    # This is a fixture upgrade in the guarded QA copy, never a payroll operation
    # exposed to users. Its existing submitted slip is deliberately unchanged.
    frappe.db.set_value("Salary Structure Assignment", assignment, "income_tax_slab", slab.name)
    frappe.db.commit()


def prepare(recover_unmarked=False):
    if frappe.local.site != "mssql.localhost" or frappe.conf.db_name != "frappe_pilot" or frappe.db.db_type != "mssql":
        raise RuntimeError("Create QA only from the dedicated SQL Server pilot")
    site = Path(frappe.local.sites_path).resolve() / QA_SITE
    config = json.loads(Path(frappe.get_site_path("site_config.json")).read_text())
    root = MSSQLDatabase(host="sqlserver", port=1433, user="sa",
        password=os.environ["MSSQL_SA_PASSWORD"], cur_db_name="master")
    try:
        exists = bool(root.native("SELECT 1 FROM sys.databases WHERE name=%s", (QA_DATABASE,)))
        recovering = exists and not site.exists() and recover_unmarked
        if recovering:
            paths = root.native("SELECT physical_name FROM sys.master_files WHERE database_id=DB_ID(%s)", (QA_DATABASE,), pluck=True)
            if not paths or not all(path.startswith("/var/opt/mssql/data/frappe_mssql_qa_") for path in paths):
                raise RuntimeError("Refusing to recover an unrecognized database")
        elif exists or site.exists():
            marker = site / ".frappe-mssql-qa.json"
            if not exists or not marker.is_file():
                raise FileExistsError("An incomplete or unmarked QA environment exists; inspect it instead of overwriting")
            config = json.loads((site / "site_config.json").read_text())
            if config.get("db_type") != "mssql" or config.get("db_name") != QA_DATABASE:
                raise RuntimeError("Existing QA configuration does not match")
            for directory in ("logs", "locks", "private/backups"):
                (site / directory).mkdir(parents=True, exist_ok=True)
            return dict(site=QA_SITE, database=QA_DATABASE, status="existing-preserved")
        if not recovering and root.native("SELECT 1 FROM sys.server_principals WHERE name=%s", (QA_DATABASE,)):
            raise FileExistsError("A QA login already exists without its marked site")
        if not recovering:
            root.native("BACKUP DATABASE [frappe_pilot] TO DISK=N'/var/opt/mssql/backup/qa-baseline.bak' WITH INIT,CHECKSUM")
            root.native("RESTORE VERIFYONLY FROM DISK=N'/var/opt/mssql/backup/qa-baseline.bak' WITH CHECKSUM")
            files = root.native("RESTORE FILELISTONLY FROM DISK=N'/var/opt/mssql/backup/qa-baseline.bak'", as_dict=True)
            moves = []
            for index, item in enumerate(files):
                extension = "ldf" if item.Type == "L" else "mdf"
                path = f"/var/opt/mssql/data/frappe_mssql_qa_{index}.{extension}"
                moves.append(f"MOVE {root.escape(item.LogicalName)} TO {root.escape(path)}")
            root.native("RESTORE DATABASE [frappe_mssql_qa] FROM DISK=N'/var/opt/mssql/backup/qa-baseline.bak' WITH CHECKSUM," + ",".join(moves))
        password = "Aa1!" + secrets.token_hex(24)
        operation = "ALTER" if recovering else "CREATE"
        root.native(f"{operation} LOGIN {qi(QA_DATABASE)} WITH PASSWORD={root.escape(password)},CHECK_POLICY=ON")
        connection = MSSQLDatabase(host="sqlserver", port=1433, user="sa",
            password=os.environ["MSSQL_SA_PASSWORD"], cur_db_name=QA_DATABASE)
        try:
            if not recovering:
                connection.native("ALTER ROLE db_owner DROP MEMBER [frappe_pilot]")
                connection.native("DROP USER [frappe_pilot]")
                connection.native("CREATE USER [frappe_mssql_qa] FOR LOGIN [frappe_mssql_qa]")
                connection.native("ALTER ROLE db_owner ADD MEMBER [frappe_mssql_qa]")
            elif not connection.native("SELECT 1 FROM sys.database_principals WHERE name='frappe_mssql_qa' AND sid=SUSER_SID('frappe_mssql_qa')"):
                raise RuntimeError("The recovered QA database has an unexpected principal")
            connection.commit()
        finally:
            connection.close()
        config.update(db_type="mssql", db_host="sqlserver", db_port=1433,
            db_name=QA_DATABASE, db_user=QA_DATABASE, db_password=password,
            pause_scheduler=1, enable_scheduler=0, mute_emails=1,
            mssql_trust_server_certificate=True)
        site.mkdir()
        (site / "site_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        for directory in ("public", "private"):
            source = Path(frappe.get_site_path(directory)).resolve()
            if source.exists():
                shutil.copytree(source, site / directory, symlinks=True)
        for directory in ("logs", "locks", "private/backups"):
            (site / directory).mkdir(parents=True, exist_ok=True)
        (site / ".frappe-mssql-qa.json").write_text(json.dumps(dict(source_database="frappe_pilot",
            created_at=datetime.now(timezone.utc).isoformat(), purpose="isolated-sqlserver-validation")), encoding="utf-8")
        return dict(site=QA_SITE, database=QA_DATABASE, status="created", scheduler="paused", emails="muted")
    finally:
        root.close()
