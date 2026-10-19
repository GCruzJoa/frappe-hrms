"""Explicit SQL Server report adaptations that preserve result semantics."""
from collections import defaultdict

import frappe


def bom_exploded_items(root_bom):
    """Fetch each reachable BOM once, preserving UNION DISTINCT graph semantics.

    SQL Server recursive CTEs require UNION ALL. A visited frontier avoids both
    repeated sub-BOMs and cycles without changing the bill-of-material rows.
    """
    children = defaultdict(list)
    if not root_bom:
        return children
    pending, visited = {root_bom}, set()
    while pending:
        batch = sorted(pending - visited)[:128]
        if not batch:
            break
        visited.update(batch)
        pending.difference_update(batch)
        rows = frappe.db.native("""SELECT bi.parent,bi.qty,bi.stock_qty,bi.bom_no,
            bi.item_code,bi.item_name,bi.description,bi.uom,bi.idx,bi.is_phantom_item,
            b.quantity AS child_bom_qty FROM [tabBOM Item] bi
            LEFT JOIN [tabBOM] b ON bi.bom_no=b.name WHERE bi.parent IN %s""", (batch,), as_dict=True)
        for row in rows:
            for field in ("qty", "stock_qty", "child_bom_qty"):
                if row.get(field) is not None:
                    row[field] = float(row[field])
            children[row.parent].append(row)
            if row.bom_no and row.bom_no not in visited:
                pending.add(row.bom_no)
    return children


def task_reaches_self(name, select_field, filter_field):
    if (select_field, filter_field) not in (("task", "parent"), ("parent", "task")):
        raise ValueError("Invalid task edge direction")
    pending, visited = {name}, set()
    while pending:
        batch = sorted(pending - visited)[:128]
        if not batch:
            return False
        visited.update(batch)
        pending.difference_update(batch)
        rows = frappe.db.native(f"""SELECT [{select_field}] AS node,
            CASE WHEN [{select_field}]=%s THEN 1 ELSE 0 END AS is_target
            FROM [tabTask Depends On] WHERE [{filter_field}] IN %s""", (name, batch), as_dict=True)
        if any(row.is_target for row in rows):
            return True
        pending.update(row.node for row in rows if row.node and row.node not in visited)
    return False


def bom_graph_nodes(root, *, ancestors=False):
    pending, visited, found = {root}, set(), set()
    while pending:
        batch = sorted(pending - visited)[:128]
        if not batch:
            break
        visited.update(batch)
        pending.difference_update(batch)
        if ancestors:
            rows = frappe.db.native("""SELECT parent AS node FROM [tabBOM Item]
                WHERE bom_no IN %s AND parenttype='BOM' AND docstatus<2
                UNION SELECT parent AS node FROM [tabBOM Operation]
                WHERE bom_no IN %s AND parenttype='BOM' AND docstatus<2""", (batch,batch), pluck=True)
        else:
            rows = frappe.db.native("""SELECT DISTINCT bom_no FROM [tabBOM Item]
                WHERE parent IN %s AND parenttype='BOM' AND bom_no IS NOT NULL AND bom_no<>''""", (batch,), pluck=True)
        found.update(rows)
        pending.update(node for node in rows if node and node not in visited)
    if ancestors and root in found:
        frappe.throw(frappe._("BOM recursion: {0} cannot be an ancestor of itself").format(root))
    return sorted(found) if ancestors else [root, *sorted(found)]


def batch_ancestors_for_item(item_code):
    from erpnext.stock.doctype.company_restriction.company_restriction import get_allowed_masters_condition
    table = frappe.qb.DocType("Batch")
    def fetch(condition):
        query = frappe.qb.from_(table).select(table.name, table.parent_batch, table.reference_name).where(condition)
        if permission := get_allowed_masters_condition(table.item, "Item"):
            query = query.where(permission)
        return query.run(as_dict=True)
    rows = fetch(table.item == item_code)
    found, pending, attempted = set(), set(), set()
    while rows or pending:
        for row in rows:
            found.add(row.name)
            attempted.add(row.name)
            if row.reference_name and row.parent_batch and row.parent_batch not in attempted:
                pending.add(row.parent_batch)
        batch = sorted(pending - attempted)[:128]
        if not batch:
            break
        pending.difference_update(batch)
        attempted.update(batch)
        rows = fetch(table.name.isin(batch))
    return sorted(found)


def batch_children_map(roots):
    from erpnext.stock.doctype.company_restriction.company_restriction import remove_restricted_masters
    table = frappe.qb.DocType("Batch")
    fields = ["name", "parent_batch", "item", "item_name", "batch_qty", "stock_uom",
        "reference_doctype", "reference_name", "manufacturing_date", "creation"]
    children = defaultdict(dict)
    pending, visited = set(), set()
    rows = frappe.get_all("Batch", fields=fields, filters={"name": ["in", list(roots)]}, limit_page_length=0) if roots else []
    while rows or pending:
        for row in remove_restricted_masters(rows, "item", "Item"):
            children[row.parent_batch][row.name] = row
        visited.update(row.name for row in rows)
        pending.update(row.name for row in rows)
        batch = sorted(pending)[:128]
        pending.difference_update(batch)
        if not batch:
            break
        query = frappe.qb.from_(table).select(*(table[field] for field in fields)).where(
            table.parent_batch.isin(batch) & table.reference_name.isnotnull() & (table.reference_name != ""))
        rows = [row for row in query.run(as_dict=True) if row.name not in visited]
    return children
