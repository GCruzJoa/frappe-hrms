from decimal import Decimal
from datetime import datetime

import pytest

from frappe_mssql.sql import UnsupportedSQL, compile_query, quote_identifier, parse_unicode_literal, ensure_read_only


@pytest.mark.parametrize("query", ["UPDATE t SET a=1", "SELECT * INTO t FROM source", "SELECT 1; DELETE FROM t", "WITH a AS (SELECT 1) DELETE FROM t"])
def test_read_only_mode_rejects_writes(query):
    with pytest.raises(UnsupportedSQL):
        ensure_read_only(query)


def test_read_only_mode_accepts_parameterized_select_and_cte():
    ensure_read_only("WITH a AS (SELECT name FROM tabUser WHERE name=%s) SELECT * FROM a", ("Administrator",))


def test_grouped_expressions_reuse_one_server_parameter():
    sql, values = compile_query("SELECT COALESCE(name,%s),SUM(amount) FROM t GROUP BY COALESCE(name,%s)", ("Peña", "Peña"))
    assert sql.startswith("DECLARE ") and sql.count("?") == 1
    assert sql.count("@__frappe_mssql_bind_0") == 3
    assert values == ["Peña"]


def test_primary_key_group_preserves_functionally_dependent_columns():
    sql, _ = compile_query("SELECT t.name,t.employee_name,SUM(c.amount) FROM `tabEmployee` t JOIN `tabExpense Claim` c ON c.employee=t.name GROUP BY t.name ORDER BY t.creation")
    assert "GROUP BY [t].[name], [t].[employee_name], [t].[creation]" in sql
    assert "GROUP BY [t].[name], [t].[employee_name], [t].[creation], [c].[amount]" not in sql


def test_non_primary_group_is_not_expanded_to_change_totals():
    sql, _ = compile_query("SELECT company,SUM(amount) FROM `tabExpense Claim` GROUP BY company")
    assert sql.endswith("GROUP BY [company]")


def test_derived_union_has_a_required_sql_server_alias():
    sql, _ = compile_query("SELECT name FROM (SELECT name FROM a UNION SELECT name FROM b)")
    assert "AS [__mssql_derived_0]" in sql


def test_unix_timestamp_uses_epoch_and_explicit_timezone():
    sql, values = compile_query("SELECT UNIX_TIMESTAMP(%s)", ("1970-01-01 00:00:00",), utc_offset_minutes=-240)
    assert "UNIX_TIMESTAMP" not in sql and "DATEDIFF_BIG(MICROSECOND" in sql
    assert "DATEADD(MINUTE, 240" in sql
    assert values == ["1970-01-01 00:00:00"]


def test_concat_ws_keeps_skip_null_semantics():
    sql, _ = compile_query("SELECT CONCAT_WS(' ',first_name,last_name) FROM t")
    assert "CONCAT_WS" in sql and "CASE WHEN" not in sql


def test_single_argument_coalesce_is_the_expression_itself():
    sql, values = compile_query("SELECT COALESCE(%s) AS voucher_type", ("Stock Entry",))
    assert "COALESCE" not in sql and values == ["Stock Entry"]


def test_boolean_ordering_and_projection_use_scalar_cases():
    sql, _ = compile_query("SELECT name IS NULL AS absent FROM t ORDER BY name IS NULL")
    assert sql.count("CASE WHEN") == 2 and "ELSE NULL END" in sql


def test_row_in_expands_to_equivalent_scalar_conditions_with_bound_values():
    sql, values = compile_query("SELECT name FROM t WHERE (item,warehouse) IN ((%s,%s),(%s,%s))", ("uno", "ñ", "dos", "é"))
    assert "([item] = ? AND [warehouse] = ?) OR ([item] = ? AND [warehouse] = ?)" in sql
    assert values == ["uno", "ñ", "dos", "é"]


@pytest.mark.parametrize("literal,value", [("N'T'", "T"), ("N''", ""), ("n'Niña Peña'", "Niña Peña"), ("N'O''Connor'", "O'Connor"), ("N'C:\\'", "C:\\")])
def test_unicode_literals_are_decoded_as_data(literal, value):
    assert parse_unicode_literal(literal) == value
    sql, values = compile_query("SELECT %s", (parse_unicode_literal(literal),))
    assert sql == "SELECT ?" and values == [value]


@pytest.mark.parametrize("value", ["N'T'; DROP TABLE x", "N'T' OR 1=1", "N'open", "name", "N'bad'quote'", 'N"value"'])
def test_unicode_literal_parser_does_not_accept_expressions(value):
    assert parse_unicode_literal(value) is None


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


def test_empty_literal_in_is_false_and_not_in_is_true_even_for_null():
    sql, values = compile_query("SELECT 1 WHERE NULL NOT IN () AND name IN ()")
    assert "IN ()" not in sql and "1 = 0" in sql and values == []


def test_wrapped_row_tuple_in_preserves_bound_values():
    sql, values = compile_query("SELECT 1 WHERE ((a,b)) IN ((%s,%s),(%s,%s))", ("Sales Invoice", "A", "Purchase Invoice", "B"))
    assert " IN " not in sql and " OR " in sql and " AND " in sql
    assert values == ["Sales Invoice", "A", "Purchase Invoice", "B"]


def test_row_in_subquery_fails_explicitly_instead_of_emitting_invalid_tsql():
    with pytest.raises(UnsupportedSQL, match="Row IN subqueries"):
        compile_query("SELECT 1 WHERE (a,b) IN (SELECT c,d FROM t)")


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
