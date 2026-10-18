"""Exercise the actual Database adapter against the disposable SQL Server."""
from pathlib import Path
import os
from datetime import datetime, time
from decimal import Decimal

import frappe
from frappe_mssql.database import MSSQLDatabase
from frappe_mssql.bootstrap import seed_statements

name = "frappe_mssql_odbc_smoke"
frappe.init(site="mssql.localhost", sites_path="/home/frappe/frappe-bench/sites", new_site=True)
os.chdir("/home/frappe/frappe-bench/sites")
# Frappe namespaces Redis by conf.db_name. Never cache the empty smoke schema
# under the actual site's key prefix, even though we reuse its bench settings.
frappe.conf.update(db_type="mssql", db_name=name, mssql_trust_server_certificate=True, developer_mode=0)
assert frappe.cache.make_key("smoke-isolation") == (name + "|smoke-isolation").encode()
settings = dict(host="sqlserver", port=1433, user="sa", password=os.environ["MSSQL_SA_PASSWORD"])
root = MSSQLDatabase(**settings, cur_db_name="master")
frappe.local.db = root
if root.native("SELECT 1 FROM sys.databases WHERE name=%s", (name,)):
    raise RuntimeError("Smoke database already exists; inspect it before removing it")
root.native(f"CREATE DATABASE [{name}] COLLATE Latin1_General_100_CI_AI_SC")
root.native(f"ALTER DATABASE [{name}] SET READ_COMMITTED_SNAPSHOT ON")
db = MSSQLDatabase(**settings, cur_db_name=name)
frappe.local.db = db
try:
    seed = Path(frappe.__file__).parent / "database/mariadb/framework_mariadb.sql"
    for statement in seed_statements(seed.read_text()):
        db.native(statement)
    db.create_user_settings_table()
    db.native("CREATE TABLE [__PrecisionSmoke] ([amount] decimal(21,9),[moment] datetime2(6),[clock] time(6))")
    db.commit()
    assert db.native(r"SELECT N'C:\', %s", ("Niña",)) == [("C:\\", "Niña")]
    precise = (Decimal("123456789012.123456789"), datetime(2026,10,18,20,30,40,123456), time(20,30,40,987654))
    db.sql("INSERT INTO __PrecisionSmoke (amount,moment,clock) VALUES (%s,%s,%s)", precise)
    observed = db.sql("SELECT amount,moment,clock FROM __PrecisionSmoke")
    assert observed == (precise,), f"Numeric or temporal precision was lost: {observed!r}"
    db.rollback()
    for index in range(8):
        pooled = MSSQLDatabase(**settings, cur_db_name=name)
        try:
            pooled.native("SET LOCK_TIMEOUT 3000")
            assert pooled.native("SELECT @@TRANCOUNT")[0][0] == 1
            pooled.sql("INSERT INTO tabSeries (name,current) VALUES (%s,%s)", ("pool-cleanup", index))
        finally:
            pooled.close()
    assert not db.sql("SELECT name FROM tabSeries WHERE name=%s", ("pool-cleanup",))
    from frappe.database.sequence import create_sequence, get_next_val, set_next_val, _get_existing_sequences
    sequence = create_sequence("MSSQL Sequence Smoke", check_not_exists=True, start_value=7)
    assert sequence in _get_existing_sequences()
    assert get_next_val("MSSQL Sequence Smoke") == 7
    assert get_next_val("MSSQL Sequence Smoke") == 8
    set_next_val("MSSQL Sequence Smoke", 20)
    assert get_next_val("MSSQL Sequence Smoke") == 20
    set_next_val("MSSQL Sequence Smoke", 20, is_val_used=True)
    assert get_next_val("MSSQL Sequence Smoke") == 21
    assert create_sequence("MSSQL Sequence Smoke", check_not_exists=True, start_value=1) == sequence
    assert get_next_val("MSSQL Sequence Smoke") == 22
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
    db.sql("UPDATE `tabSeries` AS s SET s.current=(SELECT MAX(t.current)+1 FROM `tabSeries` AS t WHERE t.name=s.name) WHERE s.name=%s", ("José Peña",))
    assert db.sql("SELECT current FROM `tabSeries` WHERE name=%s", ("José Peña",)) == ((2,),)
    db.rollback(save_point="smoke_savepoint")
    db.sql("INSERT INTO `__Auth` (doctype,name,fieldname,password,encrypted) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE password=%s", ("User", "José Peña", "password", "hash-one", 0, "hash-two"))
    db.sql("INSERT INTO `__Auth` (doctype,name,fieldname,password,encrypted) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE password=%s", ("User", "José Peña", "password", "hash-one", 0, "hash-two"))
    assert db.sql("SELECT password FROM `__Auth` WHERE name=%s", ("José Peña",), pluck=True) == ["hash-two"]
    assert db.sql("SELECT name FROM `tabSeries` WHERE name NOT IN %s", ((),), pluck=True) == ["José Peña"]
    db.sql("INSERT INTO tabSingles (doctype,field,value) VALUES (%s,%s,%s),(%s,%s,%s)", ("Smoke", "enabled", 1, "Smoke", "modified", "2026-10-18 20:30:40.123456"))
    assert db.sql("SELECT value FROM tabSingles WHERE doctype=%s ORDER BY field", ("Smoke",), pluck=True) == ["1", "2026-10-18 20:30:40.123456"]
    long_text = "María Peña 🏝 " * 1000
    db.sql("INSERT INTO `__UserSettings` (`user`,doctype,data) VALUES (%s,%s,%s)", ("test", "Employee", long_text))
    assert db.sql("SELECT data FROM `__UserSettings` WHERE `user`=%s", ("test",), pluck=True) == [long_text]
    db.rollback(chain=True)
    db.savepoint("after_chained_rollback")
    db.commit()
    print("ODBC adapter: isolated cache, Unicode, numeric/time precision, parameters, chained transactions, reusable savepoints, NOWAIT, correlated UPDATE and composite-key upsert passed")
finally:
    db.close()
    root.native(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
    root.native(f"DROP DATABASE [{name}]")
    root.close()
    frappe.local.db = None
    frappe.destroy()
