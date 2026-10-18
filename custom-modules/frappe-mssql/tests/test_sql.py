from decimal import Decimal
from datetime import datetime

import pytest

from frappe_mssql.sql import UnsupportedSQL, compile_query, quote_identifier


def test_untrusted_value_is_bound_separately():
    attack = "O'Connor; DROP TABLE [tabEmployee]; --"
    sql, values = compile_query("select name from `tabEmployee` where name=%s", (attack,))
    assert attack not in sql
    assert values == [attack]
    assert "?" in sql


def test_placeholders_inside_strings_identifiers_and_comments_are_not_parameters():
    sql, values = compile_query("SELECT '%s', [%(secret)s], %s -- %(secret)s\n", ("Niña",), native=True)
    assert "'%s'" in sql and "[%(secret)s]" in sql and "-- %(secret)s" in sql
    assert values == ["Niña"]


def test_native_tsql_does_not_treat_backslash_as_a_quote_escape():
    sql, values = compile_query(r"SELECT N'C:\', %s", ("Niña",), native=True)
    assert sql == "SELECT N'C:\\', ?" and values == ["Niña"]


def test_mysql_backslash_literal_is_valid_after_tsql_translation():
    sql, values = compile_query(r"SELECT 'C:\\', %s", ("Niña",))
    assert "'C:\\'" in sql and values == ["Niña"]


def test_named_parameters_are_repeated_in_correct_order():
    sql, values = compile_query("select %(b)s, %(a)s, %(b)s", {"a": 1, "b": Decimal("1.23")})
    assert sql.count("?") == 3
    assert values == [Decimal("1.23"), 1, Decimal("1.23")]


def test_tuple_parameter_expands_in_list():
    sql, values = compile_query("select name from `tabEmployee` where name in %(names)s", {"names": ("José", "Peña")})
    assert "IN (?, ?)" in sql
    assert values == ["José", "Peña"]


def test_empty_tuple_has_no_invalid_empty_in_clause():
    sql, values = compile_query("select name from t where name in %s", ((),))
    assert "IN (SELECT NULL WHERE 1 = 0)" in sql and values == []


@pytest.mark.parametrize("query,values", [("select %s", ()), ("select 1", (1,)), ("select %(x)s", ())])
def test_bad_parameters_fail(query, values):
    with pytest.raises((ValueError, KeyError)):
        compile_query(query, values)


def test_sql_server_limit_syntax():
    sql, values = compile_query("select name from `tabEmployee` order by name limit 5 offset 10")
    assert "LIMIT" not in sql and "OFFSET 10" in sql
    assert values == []


def test_multiple_statements_fail():
    with pytest.raises(UnsupportedSQL):
        compile_query("select 1; select 2")


def test_identifiers_are_escaped_and_length_checked():
    assert quote_identifier("tabEmployee") == "[tabEmployee]"
    assert quote_identifier("a]b") == "[a]]b]"
    with pytest.raises(ValueError):
        quote_identifier("x" * 129)


def test_for_update_keeps_a_lock_in_sql_server():
    sql, values = compile_query("select current from `tabSeries` where name=%s for update", ("EMP-",))
    assert "UPDLOCK" in sql and "HOLDLOCK" in sql
    assert values == ["EMP-"]


def test_nowait_lock_does_not_silently_wait():
    sql, values = compile_query("select name from t where name=%s for update nowait", ("locked",))
    assert "UPDLOCK" in sql and "HOLDLOCK" in sql and "NOWAIT" in sql
    assert values == ["locked"]


def test_skip_locked_requires_its_own_explicit_adaptation():
    with pytest.raises(UnsupportedSQL):
        compile_query("select name from t for update skip locked")


def test_correlated_update_alias_uses_sql_server_from_syntax():
    sql, values = compile_query("UPDATE `tabLeave Ledger Entry` AS lle SET lle.company=(SELECT company FROM `tabEmployee` WHERE employee=lle.employee) WHERE lle.company IS NULL")
    assert "UPDATE [lle] SET [company]" in sql
    assert "FROM [tabLeave Ledger Entry] AS [lle]" in sql
    assert values == []


def test_single_values_remain_text_without_losing_numeric_or_temporal_precision():
    instant = datetime(2026, 10, 18, 20, 30, 40, 123456)
    sql, values = compile_query("INSERT INTO tabSingles (doctype,field,value) VALUES (%s,%s,%s),(%s,%s,%s),(%s,%s,%s)",
        ("Settings", "enabled", True, "Settings", "modified", instant,
         "Settings", "rate", Decimal("123456789.123456789")))
    assert values[2] == "1"
    assert values[5] == "2026-10-18 20:30:40.123456"
    assert values[8] == "123456789.123456789"
    assert sql.count("?") == 9


def test_password_upsert_updates_the_same_composite_key_and_keeps_hash_bound():
    sql, values = compile_query("insert into `__Auth` (doctype,name,fieldname,password,encrypted) values (%s,%s,%s,%s,%s) on duplicate key update password=%s,encrypted=0", ("User", "Administrator", "password", "secret-hash", 0, "new-secret-hash"))
    assert "MERGE" in sql and "HOLDLOCK" in sql
    assert "target.[doctype]=source.[doctype]" in sql
    assert "target.[fieldname]=source.[fieldname]" in sql
    assert "secret-hash" not in sql
    assert values[-1] == "new-secret-hash"


def test_upsert_values_function_is_source_column():
    sql, values = compile_query("insert into `tabSeries` (name,current) values (%s,%s) on duplicate key update current=values(current)", ("EMP-", 42))
    assert "[source].[current]" in sql
    assert values == ["EMP-", 42]


def test_clock_functions_follow_the_application_timezone():
    sql, values = compile_query("select now(), current_date, current_time", utc_offset_minutes=-240)
    assert sql.count("SYSUTCDATETIME()") == 3
    assert "DATEADD(MINUTE, -240" in sql
    assert " AS DATE)" in sql and " AS TIME(6))" in sql
    assert values == []


def test_unquoted_mysql_column_that_is_reserved_in_sql_server_gets_quoted():
    sql, values = compile_query("insert into `tabSeries` (name,current) values (%s,%s)", ("EMP-", 1))
    assert "[current]" in sql and "[name]" in sql
    assert values == ["EMP-", 1]
