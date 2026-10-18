"""Native .bak backup and isolated restore verification for the pilot."""
import os
import hashlib
from pathlib import Path
import tarfile
import tempfile

import frappe
from .database import MSSQLDatabase


def run(verify_restore=False):
    if frappe.local.site != "mssql.localhost" or frappe.db.db_type != "mssql":
        raise RuntimeError("Native backup helper is restricted to the SQL Server pilot")
    root = MSSQLDatabase(host="sqlserver", port=1433, user="sa",
        password=os.environ["MSSQL_SA_PASSWORD"], cur_db_name="master")
    try:
        root.native("BACKUP DATABASE [frappe_pilot] TO DISK=N'/var/opt/mssql/backup/pilot.bak' WITH INIT,CHECKSUM")
        root.native("RESTORE VERIFYONLY FROM DISK=N'/var/opt/mssql/backup/pilot.bak' WITH CHECKSUM")
        if verify_restore:
            if root.native("SELECT 1 FROM sys.databases WHERE name=N'frappe_pilot_restore'"):
                raise FileExistsError("The isolated restore database already exists; inspect it before another verification")
            files = root.native("RESTORE FILELISTONLY FROM DISK=N'/var/opt/mssql/backup/pilot.bak'", as_dict=True)
            moves = []
            for index, item in enumerate(files):
                extension = "ldf" if item.Type == "L" else "mdf"
                path = f"/var/opt/mssql/data/frappe_pilot_restore_{index}.{extension}"
                moves.append(f"MOVE {root.escape(item.LogicalName)} TO {root.escape(path)}")
            root.native("RESTORE DATABASE [frappe_pilot_restore] FROM DISK=N'/var/opt/mssql/backup/pilot.bak' WITH CHECKSUM," + ",".join(moves))
            restored = root.native("SELECT [middle_name] FROM [frappe_pilot_restore].[dbo].[tabEmployee] WHERE [name]=%s", ("MSSQL-PILOT-EMPLOYEE",))
            assert restored == [("José",)], "Restored employee differs from the acceptance fixture"
            root.native("ALTER DATABASE [frappe_pilot_restore] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            root.native("DROP DATABASE [frappe_pilot_restore]")
        destination = Path("/tmp/frappe-mssql-site-files.tar.gz")
        with tarfile.open(destination, "w:gz") as archive:
            site = Path(frappe.get_site_path()).resolve()
            for item in (site / "public", site / "private", site / "site_config.json"):
                archive.add(item, arcname=item.relative_to(site))
        restored_files = 0
        if verify_restore:
            with tempfile.TemporaryDirectory(prefix="frappe-mssql-files-restore-") as restored:
                with tarfile.open(destination, "r:gz") as archive:
                    archive.extractall(restored, filter="data")
                    for member in archive.getmembers():
                        if member.isfile():
                            original = (site / member.name).read_bytes()
                            recovered = (Path(restored) / member.name).read_bytes()
                            assert hashlib.sha256(original).digest() == hashlib.sha256(recovered).digest(), "Restored site file differs"
                            restored_files += 1
                assert (Path(restored) / "site_config.json").is_file()
        return dict(backup="/var/opt/mssql/backup/pilot.bak", site_files=str(destination), restore_verified=bool(verify_restore), restored_files=restored_files)
    finally:
        root.close()
