from frappe_mssql.bootstrap import seed_statements


def test_mysql_bootstrap_collations_and_engine_properties_do_not_leak():
    source = """CREATE TABLE `tabDocType` (
        `name` varchar(140) COLLATE utf8mb4_unicode_ci NOT NULL,
        `creation` datetime(6) DEFAULT NULL,
        `value` longtext,
        PRIMARY KEY (`name`), KEY `creation` (`creation`)
    ) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"""
    sql, = seed_statements(source)
    assert "utf8mb4" not in sql and "InnoDB" not in sql
    assert "nvarchar(140)" in sql and "nvarchar(max)" in sql
    assert "datetime2(6)" in sql
    assert "PRIMARY KEY NONCLUSTERED" in sql
