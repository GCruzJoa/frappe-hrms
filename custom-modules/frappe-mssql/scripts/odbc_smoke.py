"""Exercise the actual Database adapter against the disposable SQL Server."""
from pathlib import Path
import os
from datetime import datetime, time, timedelta
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
    db.begin(read_only=True)
    assert db.sql("SELECT name FROM tabSeries WHERE name=%s", ("readonly",)) == ()
    for operation in (lambda: db.sql("INSERT INTO tabSeries (name,current) VALUES (%s,%s)", ("readonly", 1)),
            lambda: db.native("INSERT INTO tabSeries (name,current) VALUES (%s,%s)", ("readonly", 1))):
        try:
            operation()
        except NotImplementedError:
            pass
        else:
            raise AssertionError("Read-only mode allowed a write")
    db.rollback()
    grouped = "SELECT COALESCE(label,%s),SUM(amount) FROM (SELECT CAST(NULL AS CHAR) AS label,1 AS amount UNION ALL SELECT CAST(NULL AS CHAR),2) g GROUP BY COALESCE(label,%s)"
    assert db.sql(grouped, ("fallback", "fallback")) == (("fallback", 3),)
    db.set_session_time_zone("UTC")
    assert Decimal(str(db.sql("SELECT UNIX_TIMESTAMP(%s)", ("1970-01-01 00:00:00.123456",))[0][0])) == Decimal("0.123456")
    db.set_session_time_zone("America/Santo_Domingo")
    assert Decimal(str(db.sql("SELECT UNIX_TIMESTAMP(%s)", ("1969-12-31 20:00:00.123456",))[0][0])) == Decimal("0.123456")
    db.set_session_time_zone("UTC")
    assert db.sql("SELECT CONCAT_WS(' ', %s, NULL, %s)", ("María", "Peña"))[0][0] == "María Peña"
    with db.unbuffered_cursor():
        iterator = db.sql("SELECT %s AS name UNION ALL SELECT %s", ("uno", "dos"), as_iterator=True, as_dict=True)
        assert [row.name for row in iterator] == ["uno", "dos"]
    db.rollback()
    assert db.native(r"SELECT N'C:\', %s", ("Niña",)) == [("C:\\", "Niña")]
    db.native("CREATE TABLE [tabBOM] (name nvarchar(140) PRIMARY KEY,quantity decimal(21,9))")
    db.native("CREATE TABLE [tabBOM Item] (parent nvarchar(140),qty decimal(21,9),stock_qty decimal(21,9),bom_no nvarchar(140),item_code nvarchar(140),item_name nvarchar(140),description nvarchar(max),uom nvarchar(140),idx int,is_phantom_item int)")
    db.native("INSERT INTO [tabBOM] (name,quantity) VALUES ('root',1),('shared',2)")
    db.native("INSERT INTO [tabBOM Item] (parent,qty,stock_qty,bom_no,item_code,idx) VALUES ('root',2,2,'shared','part-a',1),('root',3,3,'shared','part-b',2),('shared',1,1,'','leaf',1)")
    from frappe_mssql.reports import bom_exploded_items
    graph = bom_exploded_items("root")
    assert set(graph) == {"root", "shared"} and len(graph["root"]) == 2 and len(graph["shared"]) == 1
    assert graph["root"][0].child_bom_qty == Decimal("2")
    db.native("UPDATE [tabBOM Item] SET bom_no='root' WHERE item_code='leaf'")
    assert len(bom_exploded_items("root")["shared"]) == 1
    db.native("UPDATE [tabBOM Item] SET bom_no='' WHERE item_code='leaf'")
    db.native("ALTER TABLE [tabBOM Item] ADD parenttype nvarchar(140) NOT NULL DEFAULT 'BOM',docstatus int NOT NULL DEFAULT 0")
    db.native("CREATE TABLE [tabBOM Operation] (parent nvarchar(140),bom_no nvarchar(140),parenttype nvarchar(140),docstatus int)")
    from frappe_mssql.reports import bom_graph_nodes
    assert bom_graph_nodes("root") == ["root", "shared"]
    assert bom_graph_nodes("shared", ancestors=True) == ["root"]
    db.native("INSERT INTO [tabBOM Operation] VALUES ('top','root','BOM',0)")
    assert bom_graph_nodes("shared", ancestors=True) == ["root", "top"]
    db.native("INSERT INTO [tabBOM Operation] VALUES ('shared','root','BOM',0)")
    try:
        bom_graph_nodes("root", ancestors=True)
    except frappe.ValidationError:
        pass
    else:
        raise AssertionError("An ancestor BOM cycle was not rejected")
    db.rollback()
    assert db.sql("SELECT NULL IS NULL AS absent")[0][0] == 1
    assert db.sql("SELECT 1 WHERE (%s,%s) IN ((%s,%s))", ("item", "warehouse", "item", "warehouse")) == ((1,),)
    assert db.sql("SELECT 1 WHERE ((%s,%s)) IN ((%s,%s))", ("item", "warehouse", "item", "warehouse")) == ((1,),)
    assert not db.sql("SELECT 1 WHERE NULL IN ()")
    assert db.sql("SELECT 1 WHERE NULL NOT IN ()") == ((1,),)
    db.native("CREATE TABLE [tabTask Depends On] (parent nvarchar(140),task nvarchar(140))")
    db.native("INSERT INTO [tabTask Depends On] (parent,task) VALUES ('a','b'),('b','c')")
    from frappe_mssql.reports import task_reaches_self
    assert not task_reaches_self("a", "task", "parent")
    db.native("INSERT INTO [tabTask Depends On] (parent,task) VALUES ('c','a')")
    assert task_reaches_self("a", "task", "parent") and task_reaches_self("a", "parent", "task")
    db.rollback()
    db.native("CREATE TABLE [tabRename Smoke] ([old_name] nvarchar(140))")
    db.rename_column("Rename Smoke", "old_name", "new_name")
    assert db.get_db_table_columns("tabRename Smoke") == ["new_name"]
    assert db._estimate_count("tabRename Smoke") == 0
    db.rollback()
    lock_key = ["stock", "Niña", "warehouse"]
    db.transaction_advisory_lock(lock_key, timeout=0)
    contender = MSSQLDatabase(**settings, cur_db_name=name)
    try:
        try:
            contender.transaction_advisory_lock(lock_key, timeout=0)
        except frappe.QueryTimeoutError:
            pass
        else:
            raise AssertionError("A conflicting transaction application lock was acquired")
        contender.rollback()
        db.rollback()
        contender.transaction_advisory_lock(lock_key, timeout=0)
        contender.commit()
        db.transaction_advisory_lock(lock_key, timeout=0)
        db.commit()
    finally:
        contender.close()
    precise = (Decimal("123456789012.123456789"), datetime(2026,10,18,20,30,40,123456), time(20,30,40,987654))
    db.sql("INSERT INTO __PrecisionSmoke (amount,moment,clock) VALUES (%s,%s,%s)", precise)
    observed = db.native("SELECT amount,moment,clock FROM __PrecisionSmoke")
    assert observed == [precise], f"Numeric or temporal precision was lost: {observed!r}"
    assert isinstance(db.sql("SELECT amount FROM __PrecisionSmoke")[0][0], float)
    clock = timedelta(hours=20, minutes=30, seconds=40, microseconds=987654)
    assert db.sql("SELECT clock FROM __PrecisionSmoke")[0][0] == clock
    db.sql("UPDATE __PrecisionSmoke SET clock=%s", (clock,))
    assert db.native("SELECT clock FROM __PrecisionSmoke")[0][0] == precise[2]
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
