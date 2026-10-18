"""Experimental SQL Server implementation of Frappe's Database contract."""

from contextlib import contextmanager
from contextlib import suppress
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import itertools
import re
from zoneinfo import ZoneInfo

import pyodbc
import frappe
from frappe.database.database import Database
from frappe.utils import get_table_name

from .sql import compile_query, quote_identifier as qi, UnsupportedSQL


def _error_number(exc, *numbers):
    return any(re.search(r"\(" + str(number) + r"\)", str(exc)) for number in numbers)


def _odbc_parameters(values):
    # SQL_TIME_STRUCT has no fractional seconds. Bind ISO text so SQL Server's
    # time(6) conversion retains the full microsecond precision.
    return [value.isoformat() if isinstance(value, time) else value for value in values]


class MSSQLDatabase(Database):
    MAX_COLUMN_LENGTH = 128
    default_port = 1433
    REGEX_CHARACTER = "REGEXP"
    ProgrammingError = pyodbc.ProgrammingError
    TableMissingError = pyodbc.ProgrammingError
    OperationalError = pyodbc.OperationalError
    InternalError = pyodbc.InternalError
    SQLError = pyodbc.ProgrammingError
    DataError = pyodbc.DataError
    InterfaceError = pyodbc.InterfaceError
    SequenceGeneratorLimitExceeded = pyodbc.DataError

    is_deadlocked = staticmethod(lambda e: _error_number(e, 1205, 3960))
    is_timedout = staticmethod(lambda e: str(e.args[0]) in ("HYT00", "HYT01") or _error_number(e, 1222))
    is_statement_timeout = is_timedout
    is_table_missing = staticmethod(lambda e: _error_number(e, 208))
    is_missing_table = is_table_missing
    is_missing_column = staticmethod(lambda e: _error_number(e, 207))
    is_duplicate_entry = staticmethod(lambda e: _error_number(e, 2601, 2627))
    is_primary_key_violation = staticmethod(lambda e: _error_number(e, 2627) and "PRIMARY" in str(e))
    is_unique_key_violation = is_duplicate_entry
    is_duplicate_fieldname = staticmethod(lambda e: _error_number(e, 2705))
    cant_drop_field_or_key = staticmethod(lambda e: _error_number(e, 3701, 3728))
    is_read_only_mode_error = staticmethod(lambda e: _error_number(e, 3906))
    is_access_denied = staticmethod(lambda e: _error_number(e, 18456, 229))
    is_data_too_long = staticmethod(lambda e: _error_number(e, 8152, 2628))
    is_data_truncated = staticmethod(lambda e: _error_number(e, 245, 8114, 8115))
    is_db_table_size_limit = staticmethod(lambda e: _error_number(e, 1105))
    is_interface_error = staticmethod(lambda e: isinstance(e, pyodbc.InterfaceError))
    # Let the SQL Server exception propagate without Frappe logging bound values.
    is_syntax_error = staticmethod(lambda e: False)

    def setup_type_map(self):
        self.db_type = "mssql"
        self.type_map = {}
        for field in ("Data", "Link", "Dynamic Link", "Select", "Read Only", "Color", "Icon", "Phone", "Autocomplete"):
            self.type_map[field] = ("nvarchar", self.VARCHAR_LEN)
        for field in ("Small Text", "Long Text", "Code", "Text Editor", "Markdown Editor", "HTML Editor", "Text", "Password", "Attach", "Attach Image", "Signature", "Barcode", "Geolocation", "JSON"):
            self.type_map[field] = ("nvarchar", "max")
        for field in ("Currency", "Float", "Percent", "Duration"):
            self.type_map[field] = ("decimal", "21,9")
        self.type_map.update({"Int": ("int", None), "Long Int": ("bigint", None), "Check": ("smallint", None), "Date": ("date", None), "Datetime": ("datetime2", "6"), "Time": ("time", "6"), "Rating": ("decimal", "3,2")})

    @property
    def db_schema(self):
        return "dbo"

    def get_connection(self):
        def odbc(value):
            return "{" + str(value).replace("}", "}}") + "}"
        settings = {
            "DRIVER": "ODBC Driver 18 for SQL Server",
            "SERVER": f"{self.host or 'sqlserver'},{self.port or 1433}",
            "DATABASE": self.cur_db_name or "master",
            "UID": self.user,
            "PWD": self.password,
            "Encrypt": "yes",
            "LongAsMax": "yes",
            "TrustServerCertificate": "yes" if frappe.conf.get("mssql_trust_server_certificate") else "no",
            "APP": "Frappe MSSQL Pilot",
        }
        connection = pyodbc.connect(";".join(f"{key}={odbc(value)}" for key, value in settings.items()), autocommit=True, timeout=15)
        connection.execute("SET QUOTED_IDENTIFIER ON")
        connection.execute("SET ANSI_NULLS ON")
        for setting in ("ANSI_PADDING ON", "ANSI_WARNINGS ON", "ARITHABORT ON", "CONCAT_NULL_YIELDS_NULL ON", "NUMERIC_ROUNDABORT OFF"):
            connection.execute("SET " + setting)
        connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        # Use the driver's transaction API. Mixing autocommit with explicit
        # BEGIN/COMMIT can retain nested transactions in pooled connections.
        # RCSI supplies nonblocking ordinary reads; FOR UPDATE remains locked.
        if self.cur_db_name and self.cur_db_name.lower() != "master":
            connection.autocommit = False
            connection.rollback()
        return connection

    def close(self):
        if self._conn:
            with suppress(pyodbc.Error):
                self._conn.rollback()
        super().close()

    def _clear_cursor(self):
        if self._cursor:
            self._cursor.close()
        self._cursor = self._conn.cursor()

    def set_execution_timeout(self, seconds):
        self._conn.timeout = max(0, int(seconds))

    def get_execution_timeout(self):
        return self._conn.timeout

    def set_session_time_zone(self, timezone):
        ZoneInfo(timezone)  # Validate instead of silently choosing another zone.
        self._session_time_zone = timezone

    def _utc_offset_minutes(self):
        timezone = ZoneInfo(getattr(self, "_session_time_zone", "UTC"))
        return int(datetime.now(timezone).utcoffset().total_seconds() // 60)

    def _transform_query(self, query, values):
        return query, values

    def execute_query(self, query, values=None):
        statement = re.sub(r"\s*/\*\s*FRAPPE_TRACE_ID:\s*[0-9a-f]+\s*\*/\s*$", "", query, flags=re.I).strip().rstrip(";")
        command = statement.lower()
        if command.startswith("start transaction"):
            if "read only" in command:
                raise UnsupportedSQL("Read-only transactions are not implemented")
            self._clear_cursor()
            self._last_query = statement
            return
        elif command in ("commit", "commit and chain", "rollback", "rollback and chain"):
            if command.startswith("commit"):
                self._conn.commit()
            else:
                self._conn.rollback()
            self._clear_cursor()
            self._last_query = statement
            return
        elif command.startswith("savepoint "):
            sql, args = "SAVE TRANSACTION " + qi(statement.split()[-1]), []
        elif command.startswith("rollback to savepoint "):
            savepoint = qi(statement.split()[-1])
            # SQL Server consumes the target savepoint; Frappe may reuse it.
            sql, args = f"ROLLBACK TRANSACTION {savepoint}; SAVE TRANSACTION {savepoint}", []
        elif command.startswith("release savepoint "):
            return
        else:
            sql, args = compile_query(query, values, utc_offset_minutes=self._utc_offset_minutes())
        self._last_query = sql
        return self._cursor.execute(sql, _odbc_parameters(args))

    def native(self, query, values=None, *, as_dict=False, pluck=False):
        """Internal T-SQL; retain values as parameters and never dialect-translate."""
        if not self._conn:
            self.connect()
        sql, args = compile_query(query, values, native=True)
        self._last_query = sql
        self._cursor.execute(sql, _odbc_parameters(args))
        while self._cursor.description is None:
            if not self._cursor.nextset():
                return []
        rows = [tuple(row) for row in self._cursor.fetchall()]
        if pluck:
            return [row[0] for row in rows]
        return self.fetch_as_dict(rows) if as_dict else rows

    def _transform_result(self, result):
        return tuple(tuple(row) for row in result)

    @property
    def last_query(self):
        return getattr(self, "_last_query", "")

    def lazy_mogrify(self, query, values=None):
        return self.last_query or str(query)

    def mogrify(self, query, values=None):
        return compile_query(query, values)[0]

    @staticmethod
    def escape(value, percent=True):
        value = "" if value is None else value.decode() if isinstance(value, bytes) else str(value)
        return "N'" + value.replace("'", "''") + "'"

    @staticmethod
    def is_type_number(code):
        return code in (int, float, Decimal)

    @staticmethod
    def is_type_datetime(code):
        return code in (date, datetime, time)

    def check_implicit_commit(self, query, query_type):
        return

    def get_tables(self, cached=True):
        return self.native("SELECT name FROM sys.tables WHERE schema_id=SCHEMA_ID('dbo')", pluck=True)

    def get_table_counts(self):
        rows = self.native("""SELECT t.[name] AS [name],COALESCE(SUM(p.[rows]),0) AS [count]
            FROM sys.tables t LEFT JOIN sys.partitions p
            ON p.object_id=t.object_id AND p.index_id IN (0,1)
            WHERE t.schema_id=SCHEMA_ID('dbo') GROUP BY t.[name]""", as_dict=True)
        return {row.name.removeprefix("tab"): int(row.count) for row in rows}

    def get_db_table_columns(self, table):
        return self.native("SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(%s) ORDER BY column_id", (f"dbo.{qi(table)}",), pluck=True)

    def get_table_columns_description(self, table):
        return self.native("""SELECT c.name AS name, t.name AS type, c.max_length AS max_length,
            c.precision AS precision, c.scale AS scale, c.is_nullable AS nullable,
            d.definition AS [default]
            FROM sys.columns c JOIN sys.types t ON c.user_type_id=t.user_type_id
            LEFT JOIN sys.default_constraints d ON c.default_object_id=d.object_id
            WHERE c.object_id=OBJECT_ID(%s) ORDER BY c.column_id""", (f"dbo.{qi(table)}",), as_dict=True)

    def get_column_type(self, doctype, column):
        for item in self.get_table_columns_description(get_table_name(doctype)):
            if item.name == column:
                return item.type

    def describe(self, doctype):
        return [(column,) for column in self.get_db_table_columns(get_table_name(doctype))]

    def get_database_size(self):
        return self.native("SELECT SUM(size)*8.0/1024 FROM sys.database_files")[0][0]

    def get_database_list(self):
        return self.native("SELECT name FROM sys.databases", pluck=True)

    def updatedb(self, doctype, meta=None):
        from .schema import MSSQLTable
        meta = meta or frappe.get_meta(doctype)
        if meta.issingle or meta.is_virtual:
            return
        table = MSSQLTable(doctype, meta)
        table.sync()
        self.commit()

    def has_index(self, table_name, index_name):
        return bool(self.native("SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(%s) AND name=%s", (f"dbo.{qi(table_name)}", index_name)))

    def add_index(self, doctype, fields, index_name=None, using=None, where=None, include=None):
        if using not in (None, "btree") or where or include:
            raise UnsupportedSQL("Special index methods require an explicit SQL Server adaptation")
        table = get_table_name(doctype)
        index_name = index_name or "idx_" + hashlib.sha256((table + "|" + "|".join(fields)).encode()).hexdigest()[:32]
        if not self.has_index(table, index_name):
            index_fields = []
            for field in fields:
                if prefix := re.fullmatch(r"(.+)\((\d+)\)", field):
                    column, length = prefix.group(1), int(prefix.group(2))
                    if not 1 <= length <= 850:
                        raise UnsupportedSQL("Unicode index prefixes must fit SQL Server's index key limit")
                    computed = "_mssql_prefix_" + hashlib.sha256(field.encode()).hexdigest()[:24]
                    if computed not in self.get_db_table_columns(table):
                        self.native(f"ALTER TABLE {qi(table)} ADD {qi(computed)} AS CONVERT(nvarchar({length}),LEFT({qi(column)},{length})) PERSISTED")
                    index_fields.append(computed)
                else:
                    index_fields.append(field)
            self.native(f"CREATE INDEX {qi(index_name)} ON {qi(table)} ({','.join(qi(field) for field in index_fields)})")

    def add_unique(self, doctype, fields, constraint_name=None):
        table = get_table_name(doctype)
        name = constraint_name or "uq_" + hashlib.sha256((table + "|" + "|".join(fields)).encode()).hexdigest()[:32]
        if not self.has_index(table, name):
            # Filtered unique indexes preserve MariaDB's multiple-NULL behavior.
            predicate = " AND ".join(f"{qi(field)} IS NOT NULL" for field in fields)
            self.native(f"CREATE UNIQUE INDEX {qi(name)} ON {qi(table)} ({','.join(qi(field) for field in fields)}) WHERE {predicate}")

    def get_column_index(self, table_name, fieldname, unique=False):
        rows = self.native("""SELECT i.name AS Key_name, NULL AS Constraint_name FROM sys.indexes i
            JOIN sys.index_columns ic ON i.object_id=ic.object_id AND i.index_id=ic.index_id
            JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
            WHERE i.object_id=OBJECT_ID(%s) AND c.name=%s AND ic.key_ordinal=1 AND i.is_unique=%s""", (f"dbo.{qi(table_name)}", fieldname, int(unique)), as_dict=True)
        return rows[0] if rows else None

    def get_row_size(self, doctype):
        # Estimate declared storage; SQL Server may move variable-length data to
        # row-overflow pages. The engine enforces the actual physical row limit.
        return int(self.native("""SELECT COALESCE(SUM(CASE WHEN max_length=-1 THEN 24 ELSE max_length END),0)
            FROM sys.columns WHERE object_id=OBJECT_ID(%s)""", (f"dbo.{qi(get_table_name(doctype))}",))[0][0])

    def estimate_count(self, doctype):
        return self.count(doctype)

    def bulk_insert(self, doctype, fields, values, ignore_duplicates=False, *, chunk_size=1000):
        # SQL Server accepts at most 2100 parameters in a request.
        chunk_size = min(chunk_size, 1000, max(1, 2000 // max(1, len(fields))))
        iterator = iter(values)
        while chunk := tuple(itertools.islice(iterator, chunk_size)):
            query = self.qb.into(self.qb.DocType(doctype)).columns(fields).insert(*chunk)
            if ignore_duplicates:
                query = query.ignore()
            self._run_query(query)

    def create_auth_table(self):
        self.native("""IF OBJECT_ID('__Auth') IS NULL CREATE TABLE [__Auth] (
            doctype nvarchar(140) NOT NULL, name nvarchar(255) NOT NULL,
            fieldname nvarchar(140) NOT NULL, password nvarchar(max) NOT NULL,
            encrypted int NOT NULL DEFAULT 0,
            CONSTRAINT PK_Auth PRIMARY KEY NONCLUSTERED (doctype,name,fieldname))""")

    def create_user_settings_table(self):
        self.native("""IF OBJECT_ID('__UserSettings') IS NULL CREATE TABLE [__UserSettings] (
            [user] nvarchar(180) NOT NULL, doctype nvarchar(180) NOT NULL,
            data nvarchar(max), CONSTRAINT PK_UserSettings PRIMARY KEY ([user],doctype))""")

    def create_global_search_table(self):
        self.native("""IF OBJECT_ID('__global_search') IS NULL CREATE TABLE [__global_search] (
            doctype nvarchar(100) NOT NULL, name nvarchar(140) NOT NULL,
            title nvarchar(140), content nvarchar(max), route nvarchar(140),
            published int NOT NULL DEFAULT 0, CONSTRAINT PK_GlobalSearch PRIMARY KEY (doctype,name))""")

    def get_on_duplicate_update(self, *args, **kwargs):
        raise UnsupportedSQL("ON DUPLICATE KEY requires an explicit SQL Server upsert")

    def create_sequence(self, name, check_not_exists=False, **kwargs):
        if set(kwargs) - {"start_value", "increment_by", "min_value", "max_value", "cycle", "cache", "slug", "temporary"}:
            raise UnsupportedSQL("Unknown sequence options")
        if kwargs.get("temporary") or kwargs.get("slug", "_id_seq") != "_id_seq":
            raise UnsupportedSQL("Temporary or custom-slug sequences require an explicit adaptation")
        sequence = self.get_sequence_name(name)
        exists = self.native("SELECT 1 FROM sys.sequences WHERE name=%s", (sequence,))
        if exists and not check_not_exists:
            raise FileExistsError(f"Sequence already exists for {name}")
        if not exists:
            options = f"START WITH {int(kwargs.get('start_value') or 1)} INCREMENT BY {int(kwargs.get('increment_by') or 1)}"
            options += f" MINVALUE {int(kwargs.get('min_value') or 1)}"
            if kwargs.get("max_value"):
                options += f" MAXVALUE {int(kwargs['max_value'])}"
            options += " CYCLE" if kwargs.get("cycle") else " NO CYCLE"
            options += f" CACHE {int(kwargs['cache'])}" if kwargs.get("cache") else " NO CACHE"
            self.native(f"CREATE SEQUENCE {qi(sequence)} AS bigint {options}")
        return sequence

    def set_next_sequence_val(self, name, value, *, slug="_id_seq", is_val_used=False):
        if slug != "_id_seq":
            raise UnsupportedSQL("Custom-slug sequences require an explicit adaptation")
        sequence = self.get_sequence_name(name)
        increment = self.native("SELECT CAST(increment AS bigint) FROM sys.sequences WHERE name=%s", (sequence,))[0][0]
        self.native(f"ALTER SEQUENCE {qi(sequence)} RESTART WITH {int(value) + (int(increment) if is_val_used else 0)}")

    def get_next_sequence_val(self, name, slug="_id_seq"):
        if slug != "_id_seq":
            raise UnsupportedSQL("Custom-slug sequences require an explicit adaptation")
        sequence = self.get_sequence_name(name)
        return self.native(f"SELECT NEXT VALUE FOR {qi(sequence)}")[0][0]

    def get_sequence_name(self, name):
        return "seq_" + hashlib.sha256(name.encode()).hexdigest()[:32]

    @contextmanager
    def advisory_lock(self, name, timeout=10):
        resource = "frappe:" + str(name)
        result = self.native("""DECLARE @result int; EXEC @result=sys.sp_getapplock
            @Resource=%s,@LockMode='Exclusive',@LockOwner='Session',@LockTimeout=%s;
            SELECT @result""", (resource, int(timeout * 1000)))[0][0]
        if result < 0:
            raise frappe.QueryTimeoutError("SQL Server advisory lock could not be acquired")
        try:
            yield
        finally:
            self.native("EXEC sys.sp_releaseapplock @Resource=%s,@LockOwner='Session'", (resource,))
