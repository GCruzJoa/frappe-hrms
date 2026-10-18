"""SQL Server site provisioning; root credentials are only used at creation."""

from pathlib import Path

import frappe
from .bootstrap import seed_statements
from .database import MSSQLDatabase
from .sql import quote_identifier as qi, UnsupportedSQL


def get_root_connection():
    return MSSQLDatabase(host=frappe.conf.db_host, port=frappe.conf.db_port,
        user=frappe.flags.root_login or "sa", password=frappe.flags.root_password,
        cur_db_name="master")


def setup_database(force=False, verbose=False, *args):
    root = get_root_connection()
    name = frappe.conf.db_name
    user = frappe.conf.db_user or name
    password = frappe.conf.db_password
    try:
        exists = root.native("SELECT 1 FROM sys.databases WHERE name=%s", (name,))
        if exists:
            # A failed install must be inspected; force must not silently drop data.
            raise FileExistsError(f"SQL Server database {name!r} already exists")
        root.native(f"CREATE DATABASE {qi(name)} COLLATE Latin1_General_100_CI_AI_SC")
        root.native(f"ALTER DATABASE {qi(name)} SET COMPATIBILITY_LEVEL = 170")
        if root.native("SELECT 1 FROM sys.server_principals WHERE name=%s", (user,)):
            raise FileExistsError(f"SQL Server login {user!r} already exists")
        root.native(f"CREATE LOGIN {qi(user)} WITH PASSWORD = {root.escape(password)}, CHECK_POLICY = ON")
        site_db = MSSQLDatabase(host=frappe.conf.db_host, port=frappe.conf.db_port,
            user=frappe.flags.root_login or "sa", password=frappe.flags.root_password, cur_db_name=name)
        try:
            site_db.native(f"CREATE USER {qi(user)} FOR LOGIN {qi(user)}")
            site_db.native(f"ALTER ROLE db_owner ADD MEMBER {qi(user)}")
            site_db.commit()
        finally:
            site_db.close()
        frappe.local.session = frappe._dict(user="Administrator")
    finally:
        root.close()



def bootstrap_database(verbose=False, source_sql=None):
    if source_sql:
        raise UnsupportedSQL("Importing a different engine's SQL dump is unsupported")
    frappe.connect()
    seed = Path(frappe.__file__).parent / "database" / "mariadb" / "framework_mariadb.sql"
    for statement in seed_statements(seed.read_text()):
        frappe.db.native(statement)
    frappe.db.commit()


def drop_user_and_database(db_name, db_user):
    raise UnsupportedSQL("Database deletion must use the explicit pilot cleanup procedure")
