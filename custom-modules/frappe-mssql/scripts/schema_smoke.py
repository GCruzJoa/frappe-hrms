"""Emit a disposable SQL Server schema smoke check for sqlcmd -b."""
from pathlib import Path
import sys

from frappe_mssql.bootstrap import seed_statements


seed = Path(sys.argv[1]).read_text()
statements = list(seed_statements(seed))
lines = ["SET NOCOUNT ON;", "IF DB_ID(N'frappe_mssql_schema_smoke') IS NOT NULL THROW 51000, 'Smoke database already exists', 1;",
    "CREATE DATABASE [frappe_mssql_schema_smoke] COLLATE Latin1_General_100_CI_AI_SC;", "GO",
    "USE [frappe_mssql_schema_smoke];", *[statement + ";" for statement in statements],
    "IF (SELECT COUNT(*) FROM sys.tables) <> 11 THROW 51001, 'Core bootstrap table count differs', 1;",
    "CREATE TABLE [__unicode_test] ([name] nvarchar(140) PRIMARY KEY, [value] nvarchar(140));",
    "BEGIN TRANSACTION;", "INSERT INTO [__unicode_test] VALUES (N'José Peña',N'María');",
    "SAVE TRANSACTION [smoke_savepoint];", "UPDATE [__unicode_test] SET [value]=N'changed';",
    "ROLLBACK TRANSACTION [smoke_savepoint];",
    "IF NOT EXISTS (SELECT 1 FROM [__unicode_test] WHERE [name]=N'José Peña' AND [value]=N'María') THROW 51002, 'Unicode/savepoint check failed', 1;",
    "COMMIT TRANSACTION;", "GO", "USE [master];",
    "ALTER DATABASE [frappe_mssql_schema_smoke] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;",
    "DROP DATABASE [frappe_mssql_schema_smoke];", "SELECT 'Schema, Unicode and savepoint smoke checks passed' AS result;", "GO"]
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
