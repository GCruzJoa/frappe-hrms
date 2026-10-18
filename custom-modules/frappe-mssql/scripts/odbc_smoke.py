"""Exercise the actual Database adapter against the disposable SQL Server."""
from pathlib import Path
import os

import frappe
from frappe_mssql.database import MSSQLDatabase
from frappe_mssql.bootstrap import seed_statements

frappe.init(site="mssql.localhost", sites_path="/home/frappe/frappe-bench/sites", new_site=True)
os.chdir("/home/frappe/frappe-bench/sites")
frappe.conf.update(db_type="mssql", mssql_trust_server_certificate=True, developer_mode=0)
settings = dict(host="sqlserver", port=1433, user="sa", password=os.environ["MSSQL_SA_PASSWORD"])
root = MSSQLDatabase(**settings, cur_db_name="master")
frappe.local.db = root
name = "frappe_mssql_odbc_smoke"
if root.native("SELECT 1 FROM sys.databases WHERE name=%s", (name,)):
    raise RuntimeError("Smoke database already exists; inspect it before removing it")
root.native(f"CREATE DATABASE [{name}] COLLATE Latin1_General_100_CI_AI_SC")
db = MSSQLDatabase(**settings, cur_db_name=name)
frappe.local.db = db
try:
    seed = Path(frappe.__file__).parent / "database/mariadb/framework_mariadb.sql"
    for statement in seed_statements(seed.read_text()):
        db.native(statement)
    db.create_user_settings_table()
    db.commit()
    db.sql("INSERT INTO `tabSeries` (name,current) VALUES (%s,%s)", ("José Peña", 1))
    assert db.sql("SELECT current FROM `tabSeries` WHERE name=%s", ("José Peña",)) == ((1,),)
    db.rollback()
    assert not db.sql("SELECT current FROM `tabSeries` WHERE name=%s", ("José Peña",))
    db.sql("INSERT INTO `tabSeries` (name,current) VALUES (%s,%s)", ("José Peña", 1))
    db.commit()
    db.commit(chain=True)
    db.savepoint("smoke_savepoint")
    db.sql("UPDATE `tabSeries` SET current=%s WHERE name=%s", (2, "José Peña"))
    db.rollback(save_point="smoke_savepoint")
    assert db.sql("SELECT current FROM `tabSeries` WHERE name=%s FOR UPDATE", ("José Peña",)) == ((1,),)
    contender = MSSQLDatabase(**settings, cur_db_name=name)
    try:
        try:
            contender.sql("SELECT current FROM `tabSeries` WHERE name=%s FOR UPDATE NOWAIT", ("José Peña",))
        except frappe.QueryTimeoutError:
            pass
        else:
            raise AssertionError("NOWAIT did not reject a conflicting lock")
    finally:
        contender.close()
    db.sql("INSERT INTO `__Auth` (doctype,name,fieldname,password,encrypted) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE password=%s", ("User", "José Peña", "password", "hash-one", 0, "hash-two"))
    db.sql("INSERT INTO `__Auth` (doctype,name,fieldname,password,encrypted) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE password=%s", ("User", "José Peña", "password", "hash-one", 0, "hash-two"))
    assert db.sql("SELECT password FROM `__Auth` WHERE name=%s", ("José Peña",), pluck=True) == ["hash-two"]
    assert db.sql("SELECT name FROM `tabSeries` WHERE name NOT IN %s", ((),), pluck=True) == ["José Peña"]
    long_text = "María Peña 🏝 " * 1000
    db.sql("INSERT INTO `__UserSettings` (`user`,doctype,data) VALUES (%s,%s,%s)", ("test", "Employee", long_text))
    assert db.sql("SELECT data FROM `__UserSettings` WHERE `user`=%s", ("test",), pluck=True) == [long_text]
    db.rollback(chain=True)
    db.savepoint("after_chained_rollback")
    db.commit()
    print("ODBC adapter: Unicode (including long text), parameters, chained transactions, savepoint, locking, composite-key upsert and empty NOT IN passed")
finally:
    db.close()
    root.native(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
    root.native(f"DROP DATABASE [{name}]")
    root.close()
    frappe.local.db = None
    frappe.destroy()
