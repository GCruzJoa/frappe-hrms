"""Real ORM business workflows in the pilot, rolled back after each case."""
from datetime import datetime, timezone
import json
from pathlib import Path
import traceback

import frappe
from frappe.utils import today, add_days

from .acceptance import COMPANY, _pilot_only


def run():
    _pilot_only()
    if frappe.local.site != "mssql-qa.localhost":
        raise RuntimeError("Business workflow fixtures require the isolated QA site; pass --qa")
    prefix = "MSSQL-QA-" + datetime.now(timezone.utc).strftime("%H%M%S%f")
    previous_mute = frappe.flags.mute_emails
    frappe.flags.mute_emails = True
    created = []
    def insert(doctype, **values):
        set_name = values.pop("_set_name", None)
        doc = frappe.get_doc(dict(doctype=doctype, **values)).insert(set_name=set_name)
        created.append((doctype, doc.name))
        return doc
    cases = []
    try:
        department = insert("Department", department_name=prefix, company=COMPANY)
        designation = insert("Designation", designation_name=prefix)
        branch = insert("Branch", branch=prefix)
        employee = insert("Employee", first_name="María", middle_name="Integración", last_name="Peña",
            _set_name=prefix+"-EMPLOYEE", employee=prefix+"-EMPLOYEE",
            gender="Female", date_of_birth="1990-01-01", date_of_joining="2024-01-01",
            company=COMPANY, department=department.name, designation=designation.name, branch=branch.name,
            status="Active")
        holidays = insert("Holiday List", holiday_list_name=prefix,
            from_date=today()[:4]+"-01-01", to_date=today()[:4]+"-12-31")
        holiday_assignment = insert("Holiday List Assignment", applicable_for="Employee", assigned_to=employee.name,
            holiday_list=holidays.name, from_date=today()[:4]+"-01-01")
        holiday_assignment.submit()
        customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
        supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
        territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
        item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        assert customer_group and supplier_group and territory and item_group, "Leaf master groups are required"
        customer = insert("Customer", customer_name=prefix, customer_type="Company",
            customer_group=customer_group, territory=territory)
        supplier = insert("Supplier", supplier_name=prefix, supplier_type="Company",
            supplier_group=supplier_group)
        service = insert("Item", item_code=prefix+"-SERVICE", item_name=prefix+"-SERVICE",
            item_group=item_group, stock_uom="Nos", is_stock_item=0)
        stock = insert("Item", item_code=prefix+"-STOCK", item_name=prefix+"-STOCK",
            item_group=item_group, stock_uom="Nos", is_stock_item=1, valuation_rate=10)
        warehouse = frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 0}, "name")
        assert warehouse, "Company has no leaf warehouse"
        cost_center = frappe.db.get_value("Cost Center", {"company": COMPANY, "is_group": 0}, "name")

        def check(name, module, operation):
            frappe.db.savepoint("module_workflow")
            created_offset = len(created)
            row = dict(name=name, module=module, level="business-workflow")
            try:
                operation()
                row["status"] = "passed"
            except Exception as error:
                row.update(status="failed", exception=type(error).__name__, message=str(error)[:2000],
                    traceback=traceback.format_exc()[-10000:])
            finally:
                row["storage_modules"] = sorted({frappe.get_meta(doctype).module
                    for doctype, _ in created[created_offset:]} | ({"HR"} if module == "HR Setup" else set()))
                frappe.db.rollback(save_point="module_workflow")
            cases.append(row)
            print(json.dumps({key: row[key] for key in ("name", "module", "status")}), flush=True)

        def employee_edit_and_search():
            from frappe.desk.search import search_link
            employee.middle_name = "José"
            employee.save()
            assert frappe.db.get_value("Employee", employee.name, "middle_name") == "José"
            rows = search_link(doctype="Department", txt=prefix[:8], reference_doctype="Employee",
                filters={"company": COMPANY})
            assert rows, "Department link search did not find the fixture"
        check("employee-edit-and-link-search", "HR Setup", employee_edit_and_search)

        def attendance():
            doc = insert("Attendance", employee=employee.name, attendance_date=today(), status="Present", company=COMPANY)
            doc.submit()
            assert frappe.db.get_value("Attendance", doc.name, "docstatus") == 1
            doc.cancel()
            assert frappe.db.get_value("Attendance", doc.name, "docstatus") == 2
        check("attendance-submit-cancel", "Shift and Attendance", attendance)

        def shift_attendance_with_checkins():
            shift = insert("Shift Type", name=prefix, start_time="09:00:00", end_time="17:00:00",
                enable_auto_attendance=0)
            assigned = insert("Shift Assignment", employee=employee.name, shift_type=shift.name,
                company=COMPANY, start_date=today(), end_date=today())
            assigned.submit()
            doc = insert("Attendance", employee=employee.name, attendance_date=today(), status="Present",
                company=COMPANY, shift=shift.name, in_time=today()+" 09:00:00",
                out_time=today()+" 17:00:00", working_hours=8)
            doc.submit()
            for hour, log_type in (("09:00:00", "IN"), ("17:00:00", "OUT")):
                checkin = insert("Employee Checkin", employee=employee.name, time=today()+" "+hour,
                    log_type=log_type)
                checkin.attendance = doc.name
                checkin.save()
            from hrms.hr.report.shift_attendance.shift_attendance import execute
            _, rows, *_ = execute(frappe._dict(company=COMPANY, employee=employee.name,
                from_date=today(), to_date=today(), consider_grace_period=1))
            assert len(rows) == 1 and rows[0].name == doc.name and rows[0].working_hours == 8
        check("shift-attendance-nonempty-checkins", "Shift and Attendance", shift_attendance_with_checkins)

        def lead_opportunity():
            lead = insert("Lead", first_name=prefix, status="Lead")
            doc = insert("Opportunity", opportunity_from="Lead", party_name=lead.name,
                company=COMPANY, status="Open")
            assert frappe.get_doc("Opportunity", doc.name).party_name == lead.name
        check("lead-opportunity", "CRM", lead_opportunity)

        def recruitment():
            applicant = insert("Job Applicant", applicant_name=prefix,
                email_id=prefix.lower()+"@example.invalid")
            offer = insert("Job Offer", job_applicant=applicant.name, applicant_name=prefix,
                company=COMPANY, offer_date=today(), designation=designation.name, status="Awaiting Response")
            offer.submit()
            assert offer.docstatus == 1
            offer.cancel()
        check("job-applicant-offer-submit-cancel", "Recruitment", recruitment)

        def sales_order():
            doc = insert("Sales Order", customer=customer.name, company=COMPANY,
                transaction_date=today(), delivery_date=add_days(today(), 7),
                items=[dict(item_code=service.name, qty=1, rate=100, delivery_date=add_days(today(),7))])
            doc.submit()
            assert doc.docstatus == 1
            doc.cancel()
        check("sales-order-submit-cancel", "Selling", sales_order)

        def purchase_order():
            doc = insert("Purchase Order", supplier=supplier.name, company=COMPANY,
                transaction_date=today(), schedule_date=add_days(today(),7),
                items=[dict(item_code=service.name, qty=1, rate=100, schedule_date=add_days(today(),7))])
            doc.submit()
            assert doc.docstatus == 1
            doc.cancel()
        check("purchase-order-submit-cancel", "Buying", purchase_order)

        def journal():
            cash = frappe.db.get_value("Account", {"company": COMPANY, "is_group": 0, "account_type": "Cash"}, "name")
            expense = frappe.db.get_value("Account", {"company": COMPANY, "is_group": 0, "root_type": "Expense"}, "name")
            assert cash and expense, "Company needs cash and expense accounts"
            doc = insert("Journal Entry", company=COMPANY, posting_date=today(), voucher_type="Journal Entry",
                accounts=[dict(account=expense, cost_center=cost_center, debit_in_account_currency=100),
                    dict(account=cash, cost_center=cost_center, credit_in_account_currency=100)])
            doc.submit()
            assert frappe.db.count("GL Entry", {"voucher_no": doc.name}) >= 2
            balance = frappe.db.sql("SELECT SUM(debit)-SUM(credit) FROM `tabGL Entry` WHERE voucher_no=%s", (doc.name,))[0][0]
            assert balance == 0, "Journal is not balanced"
            doc.cancel()
        check("journal-post-cancel-balanced-ledger", "Accounts", journal)

        def stock_receipt():
            doc = insert("Stock Entry", company=COMPANY, stock_entry_type="Material Receipt",
                to_warehouse=warehouse, items=[dict(item_code=stock.name, qty=2, basic_rate=10, t_warehouse=warehouse)])
            doc.submit()
            assert frappe.db.count("Stock Ledger Entry", {"voucher_no": doc.name}) >= 1
            doc.cancel()
        check("stock-receipt-ledger-cancel", "Stock", stock_receipt)

        def bom():
            product = insert("Item", item_code=prefix+"-FG", item_name=prefix+"-FG",
                item_group=item_group, stock_uom="Nos", is_stock_item=1)
            doc = insert("BOM", item=product.name, quantity=1, company=COMPANY, currency="DOP",
                items=[dict(item_code=stock.name, qty=2, rate=10, uom="Nos", stock_uom="Nos")])
            doc.submit()
            from erpnext.manufacturing.report.bom_explorer.bom_explorer import execute
            _, data = execute(frappe._dict(bom=doc.name))
            assert len(data) == 1 and data[0]["item_code"] == stock.name and data[0]["qty"] == 2
        check("bom-submit-and-explorer", "Manufacturing", bom)

        def project_task():
            project = insert("Project", project_name=prefix, company=COMPANY)
            task = insert("Task", subject=prefix, project=project.name)
            task.status = "Completed"
            task.save()
            assert frappe.db.get_value("Task", task.name, "status") == "Completed"
        check("project-task-complete", "Projects", project_task)

        def leaves():
            leave_type = insert("Leave Type", leave_type_name=prefix, include_holiday=1)
            allocation = insert("Leave Allocation", employee=employee.name, company=COMPANY,
                leave_type=leave_type.name, from_date=today()[:4]+"-01-01", to_date=today()[:4]+"-12-31",
                new_leaves_allocated=5)
            allocation.submit()
            application = insert("Leave Application", employee=employee.name, company=COMPANY,
                leave_type=leave_type.name, from_date=today(), to_date=today(),
                leave_approver="Administrator", status="Approved")
            application.submit()
            assert application.total_leave_days == 1
            application.cancel()
            allocation.cancel()
        check("leave-allocation-application-cancel", "Leaves", leaves)

        def payroll():
            component = insert("Salary Component", salary_component=prefix, salary_component_abbr="MSQA",
                type="Earning", is_tax_applicable=0, depends_on_payment_days=0)
            structure = insert("Salary Structure", name=prefix, company=COMPANY, currency="DOP",
                payroll_frequency="Monthly", earnings=[dict(salary_component=component.name, amount=30000)])
            structure.submit()
            assigned = insert("Salary Structure Assignment", employee=employee.name, company=COMPANY,
                salary_structure=structure.name, from_date=today()[:4]+"-01-01", currency="DOP", base=30000)
            assigned.submit()
            start = today()[:7]+"-01"
            from frappe.utils import get_last_day
            slip = insert("Salary Slip", employee=employee.name, company=COMPANY,
                salary_structure=structure.name, start_date=start, end_date=str(get_last_day(start)),
                currency="DOP", exchange_rate=1)
            assert slip.gross_pay == 30000 and slip.net_pay == 30000
            slip.submit()
            slip.cancel()
        check("salary-structure-assignment-slip-cancel", "Payroll", payroll)

        def expenses():
            account = frappe.db.get_value("Account", {"company": COMPANY, "is_group": 0, "root_type": "Expense"}, "name")
            payable = frappe.db.get_value("Account", {"company": COMPANY, "is_group": 0, "account_type": "Payable"}, "name")
            expense_type = insert("Expense Claim Type", expense_type=prefix,
                accounts=[dict(company=COMPANY, default_account=account)])
            doc = insert("Expense Claim", employee=employee.name, company=COMPANY,
                approval_status="Approved", expense_approver="Administrator", payable_account=payable,
                cost_center=cost_center, currency="DOP", exchange_rate=1,
                expenses=[dict(expense_date=today(), expense_type=expense_type.name, amount=100,
                    sanctioned_amount=100, default_account=account, cost_center=cost_center)])
            doc.submit()
            assert frappe.db.count("GL Entry", {"voucher_no": doc.name}) >= 2
            doc.cancel()
        check("expense-claim-ledger-cancel", "Expenses", expenses)

        def onboarding():
            applicant = insert("Job Applicant", applicant_name=prefix, email_id=prefix.lower()+"@example.invalid")
            offer = insert("Job Offer", job_applicant=applicant.name, applicant_name=prefix, company=COMPANY,
                offer_date=today(), designation=designation.name, status="Accepted")
            offer.submit()
            doc = insert("Employee Onboarding", job_offer=offer.name, employee_name=prefix,
                company=COMPANY, date_of_joining=add_days(today(),7), boarding_begins_on=today(), holiday_list=holidays.name)
            doc.submit()
            doc.cancel()
        check("employee-onboarding-submit-cancel", "Tenure", onboarding)

        def performance():
            cycle = insert("Appraisal Cycle", cycle_name=prefix, start_date=today()[:4]+"-01-01",
                end_date=today()[:4]+"-12-31", company=COMPANY)
            cycle.description = "Descripción revisada de prueba"
            cycle.save()
            assert "revisada" in frappe.db.get_value("Appraisal Cycle", cycle.name, "description")
        check("appraisal-cycle-create-edit", "Performance", performance)

        def quality():
            goal = insert("Quality Goal", goal=prefix, frequency="None")
            assert frappe.get_doc("Quality Goal", goal.name).goal == prefix
            parameter = insert("Quality Inspection Parameter", parameter=prefix)
            doc = insert("Quality Inspection Template", quality_inspection_template_name=prefix,
                item_quality_inspection_parameter=[dict(specification=parameter.name, value="OK")])
            assert frappe.get_doc("Quality Inspection Template", doc.name).item_quality_inspection_parameter
        check("quality-goal-and-inspection-template", "Quality Management", quality)

        def assets():
            fixed = frappe.db.get_value("Account", {"company": COMPANY, "is_group": 0, "account_type": "Fixed Asset"}, "name")
            category = insert("Asset Category", asset_category_name=prefix,
                accounts=[dict(company_name=COMPANY, fixed_asset_account=fixed)])
            item = insert("Item", item_code=prefix+"-ASSET", item_name=prefix+"-ASSET",
                item_group=item_group, stock_uom="Nos", is_stock_item=0, is_fixed_asset=1,
                asset_category=category.name)
            location = insert("Location", location_name=prefix)
            doc = insert("Asset", asset_name=prefix, item_code=item.name, company=COMPANY,
                asset_category=category.name, asset_type="Existing Asset", asset_quantity=1,
                net_purchase_amount=1000, gross_purchase_amount=1000,
                purchase_date=today(), available_for_use_date=today(), calculate_depreciation=0, location=location.name)
            doc.submit()
            doc.cancel()
        check("existing-asset-submit-cancel", "Assets", assets)

        def maintenance():
            salesperson = insert("Sales Person", sales_person_name=prefix,
                parent_sales_person=frappe.db.get_value("Sales Person", {"is_group": 1}, "name"))
            doc = insert("Maintenance Visit", company=COMPANY, customer=customer.name, mntc_date=today(),
                completion_status="Fully Completed", maintenance_type="Unscheduled",
                purposes=[dict(item_code=stock.name, service_person=salesperson.name, work_done="Revisión ficticia")])
            doc.submit()
            doc.cancel()
        check("maintenance-visit-submit-cancel", "Maintenance", maintenance)

        def tax_benefits():
            period_name = frappe.db.get_value("Payroll Period", {"company": COMPANY,
                "start_date": today()[:4]+"-01-01", "end_date": today()[:4]+"-12-31"}, "name")
            period = frappe.get_doc("Payroll Period", period_name) if period_name else insert(
                "Payroll Period", name=prefix, company=COMPANY,
                start_date=today()[:4]+"-01-01", end_date=today()[:4]+"-12-31")
            category = insert("Employee Tax Exemption Category", name=prefix, max_amount=10000)
            subcategory = insert("Employee Tax Exemption Sub Category", name=prefix,
                exemption_category=category.name, max_amount=10000)
            doc = insert("Employee Tax Exemption Declaration", employee=employee.name, company=COMPANY,
                payroll_period=period.name, currency="DOP", declarations=[dict(
                    exemption_sub_category=subcategory.name, exemption_category=category.name, amount=5000)])
            assert doc.total_exemption_amount == 5000
            doc.submit()
            doc.cancel()
        check("synthetic-tax-exemption-declaration", "Tax and Benefits", tax_benefits)

        def support():
            doc = insert("Issue", subject=prefix, raised_by=prefix.lower()+"@example.invalid", customer=customer.name)
            doc.status = "Closed"
            doc.save()
            assert frappe.db.get_value("Issue", doc.name, "status") == "Closed"
        check("issue-create-close", "Support", support)

        def website():
            doc = insert("Web Page", title=prefix, route=prefix.lower(), published=0, content_type="Rich Text", main_section="Prueba de página ñ")
            doc.main_section = "Contenido actualizado: Peña"
            doc.save()
            assert "Peña" in frappe.get_doc("Web Page", doc.name).main_section
        check("unpublished-web-page-edit", "Website", website)

        def contacts():
            doc = insert("Contact", first_name="María", last_name="Peña", links=[dict(link_doctype="Customer", link_name=customer.name)])
            doc.designation = "Prueba SQL Server"
            doc.save()
            assert frappe.db.get_value("Contact", doc.name, "designation") == "Prueba SQL Server"
        check("contact-customer-link-edit", "Contacts", contacts)

        def email_template():
            doc = insert("Email Template", name=prefix, subject=prefix, response="Mensaje ficticio sin envío")
            doc.response = "Texto actualizado: niña"
            doc.save()
            assert "niña" in frappe.get_doc("Email Template", doc.name).response
        check("email-template-no-send", "Email", email_template)
    finally:
        frappe.db.rollback()
        for doctype, name in created:
            frappe.clear_document_cache(doctype, name)
            if doctype == "BOM":
                frappe.cache.hdel("bom_children", name)
        frappe.clear_cache()
        frappe.flags.mute_emails = previous_mute
    result = dict(prefix=prefix, cases=cases, passed=sum(row["status"] == "passed" for row in cases),
        failed=sum(row["status"] == "failed" for row in cases), fixtures="rolled-back")
    Path("/tmp/frappe-mssql-workflows.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {key: result[key] for key in ("passed", "failed", "fixtures")}
