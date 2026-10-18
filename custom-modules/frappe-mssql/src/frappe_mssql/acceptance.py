"""End-to-end ORM acceptance checks, run only in the disposable pilot site."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import frappe

COMPANY = "Piloto SQL Server RD"
EMPLOYEE = "MSSQL-PILOT-EMPLOYEE"


def _pilot_only():
    if frappe.local.site != "mssql.localhost" or frappe.db.db_type != "mssql":
        raise RuntimeError("Acceptance fixtures may only run in the dedicated SQL Server pilot")


def _employee(name, first_name="María", last_name="Peña"):
    doc = frappe.get_doc(dict(doctype="Employee", name=name, first_name=first_name,
        last_name=last_name, gender="Female", date_of_birth="1990-01-01",
        date_of_joining="2024-01-01", status="Active", company=COMPANY))
    doc.insert(set_name=name)
    return doc


def run():
    _pilot_only()
    assert {"frappe", "erpnext", "hrms"} <= set(frappe.get_installed_apps())
    if not frappe.db.exists("Company", COMPANY):
        frappe.get_doc(dict(doctype="Company", company_name=COMPANY, abbr="MSP",
            default_currency="DOP", country="Dominican Republic",
            enable_perpetual_inventory=0)).insert()
    if not frappe.db.exists("Employee", EMPLOYEE):
        _employee(EMPLOYEE)
    employee = frappe.get_doc("Employee", EMPLOYEE)
    assert employee.first_name == "María" and employee.last_name == "Peña"
    employee.middle_name = "José"
    employee.save()
    frappe.db.commit()
    assert frappe.db.get_value("Employee", EMPLOYEE, "middle_name") == "José"
    page = frappe.get_list("Employee", filters={"last_name": ["like", "%Peña%"]},
        fields=["name", "last_name"], order_by="name", page_length=1, start=0)
    assert page and len(page) == 1

    frappe.db.savepoint("pilot_employee_rollback")
    frappe.db.set_value("Employee", EMPLOYEE, "middle_name", "ROLLBACK-MARKER")
    frappe.db.rollback(save_point="pilot_employee_rollback")
    assert frappe.db.get_value("Employee", EMPLOYEE, "middle_name") == "José"
    frappe.db.commit()

    username = "pilot-no-access@example.invalid"
    if not frappe.db.exists("User", username):
        frappe.get_doc(dict(doctype="User", email=username, first_name="Sin acceso",
            send_welcome_email=0, user_type="System User")).insert()
        frappe.db.commit()
    original_user = frappe.session.user
    try:
        frappe.set_user(username)
        try:
            rows = frappe.get_list("Employee", fields=["name"])
        except frappe.PermissionError:
            rows = []
        assert not rows, "Unprivileged user can list employee data"
        denied = False
        try:
            frappe.get_doc("Employee", EMPLOYEE).check_permission("read")
        except frappe.PermissionError:
            denied = True
        assert denied, "Unprivileged user can read an employee"
    finally:
        frappe.set_user(original_user)

    site, sites_path = frappe.local.site, frappe.local.sites_path
    def reserve(_):
        frappe.init(site=site, sites_path=sites_path)
        frappe.connect()
        try:
            from frappe.model.naming import getseries
            value = getseries("MSSQL-PILOT-SERIES-", 5)
            frappe.db.commit()
            return value
        finally:
            frappe.destroy()
    # Seed outside concurrency so we test locking the same existing series row.
    from frappe.model.naming import getseries
    getseries("MSSQL-PILOT-SERIES-", 5)
    frappe.db.commit()
    with ThreadPoolExecutor(max_workers=4) as executor:
        identifiers = list(executor.map(reserve, range(12)))
    assert len(set(identifiers)) == 12
    return dict(result="passed", employee=EMPLOYEE, concurrency_identifiers=12)


def assert_persistence():
    _pilot_only()
    assert frappe.db.get_value("Employee", EMPLOYEE, "middle_name") == "José"
    return dict(result="passed", employee=EMPLOYEE)
