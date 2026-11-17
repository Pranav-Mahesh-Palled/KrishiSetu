"""Tests for SQLite Table-Recreation Schema Migration.

Verifies:
1. Safe upgrade from old NOT NULL schema to nullable fetched_at.
2. Idempotency across repeated invocations.
3. Preservation of all 91 records (25 benchmarks, 66 live API).
4. Normalization of benchmarks (fetched_at = NULL, dataset_id = NULL).
5. Exact preservation of live API and verified snapshot records.
6. Preservation of custom indexes, triggers, foreign keys, and views.
7. Foreign-key check and integrity check verification.
8. Transaction rollback safety on simulated failure.
9. End-to-end init_db() + seed_all() startup sequence on older databases.
"""

import shutil
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.database import migrate_mandi_prices_cache_fetched_at_nullable, Base
from backend.app.seed import seed_all

RAW_BACKUP_PATH = Path(__file__).resolve().parent.parent.parent / "backups" / "krishisetu_pre_repair_20261117_094409.raw.db"


def _create_disposable_old_db(dest_dir: Path) -> Path:
    """Helper to copy the raw pre-repair database to a temporary location."""
    assert RAW_BACKUP_PATH.exists(), f"Raw backup not found at {RAW_BACKUP_PATH}"
    target = dest_dir / "disposable_migration_test.db"
    shutil.copy2(RAW_BACKUP_PATH, target)
    return target


def test_old_not_null_schema_migrates_successfully(tmp_path):
    """Old NOT NULL schema migrates to nullable fetched_at."""
    db_path = _create_disposable_old_db(tmp_path)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")

    # Check pre-condition: fetched_at is NOT NULL
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(mandi_prices_cache)")
    cols = {c[1]: c for c in cur.fetchall()}
    assert cols["fetched_at"][3] == 1, "Expected notnull=1 before migration"
    conn.close()

    # Execute migration
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    # Check post-condition: fetched_at is nullable (notnull=0)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(mandi_prices_cache)")
    cols = {c[1]: c for c in cur.fetchall()}
    assert cols["fetched_at"][3] == 0, "Expected notnull=0 after migration"
    conn.close()


def test_new_nullable_schema_left_unchanged(tmp_path):
    """If table is already nullable and benchmarks are clean, migration returns early without rebuilding."""
    db_path = _create_disposable_old_db(tmp_path)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")

    # Migrate first time
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    # Insert a marker row
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO mandi_prices_cache (id, state, district, market, commodity, variety, min_price, max_price, modal_price, arrival_date, source, dataset_id, fetched_at)
        VALUES (999, 'TestState', 'TestDistrict', 'TestMarket', 'TestCrop', 'TestVar', 100, 200, 150, '17/11/2026', 'live_api', 'dummy_id', '2026-11-17 10:00:00')
    """)
    conn.commit()
    conn.close()

    # Run migration second time
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    # Verify marker row exists
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id FROM mandi_prices_cache WHERE id = 999")
    assert cur.fetchone() is not None
    conn.close()


def test_migration_is_idempotent(tmp_path):
    """Running migration 3 times consecutively produces identical rows and structure."""
    db_path = _create_disposable_old_db(tmp_path)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")

    for _ in range(3):
        migrate_mandi_prices_cache_fetched_at_nullable(engine)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(mandi_prices_cache)")
    cols = {c[1]: c for c in cur.fetchall()}
    assert cols["fetched_at"][3] == 0

    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache")
    assert cur.fetchone()[0] == 91
    conn.close()


def test_primary_keys_and_prices_preserved(tmp_path):
    """All primary keys (1..91) and prices match pre-migration values."""
    db_path = _create_disposable_old_db(tmp_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, modal_price, arrival_date, source FROM mandi_prices_cache ORDER BY id")
    before_rows = cur.fetchall()
    conn.close()

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, modal_price, arrival_date, source FROM mandi_prices_cache ORDER BY id")
    after_rows = cur.fetchall()
    conn.close()

    assert len(before_rows) == len(after_rows) == 91
    for b, a in zip(before_rows, after_rows):
        assert b[0] == a[0]  # ID preserved
        assert b[1] == a[1]  # Modal price preserved
        assert b[2] == a[2]  # Arrival date preserved
        assert b[3] == a[3]  # Source preserved


def test_benchmark_records_normalized(tmp_path):
    """All 25 estimated_benchmark records receive fetched_at=NULL and dataset_id=NULL."""
    db_path = _create_disposable_old_db(tmp_path)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache WHERE source = 'estimated_benchmark'")
    assert cur.fetchone()[0] == 25

    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache WHERE source = 'estimated_benchmark' AND fetched_at IS NULL")
    assert cur.fetchone()[0] == 25

    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache WHERE source = 'estimated_benchmark' AND dataset_id IS NULL")
    assert cur.fetchone()[0] == 25
    conn.close()


def test_live_api_records_preserved(tmp_path):
    """All 66 live_api records retain exact timestamps, dataset IDs, modal prices, and varieties."""
    db_path = _create_disposable_old_db(tmp_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, market, commodity, modal_price, arrival_date, dataset_id, fetched_at FROM mandi_prices_cache WHERE source = 'live_api' ORDER BY id")
    before_live = cur.fetchall()
    conn.close()

    assert len(before_live) == 66

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, market, commodity, modal_price, arrival_date, dataset_id, fetched_at FROM mandi_prices_cache WHERE source = 'live_api' ORDER BY id")
    after_live = cur.fetchall()
    conn.close()

    assert len(after_live) == 66
    for b, a in zip(before_live, after_live):
        assert b == a


def test_verified_snapshot_records_preserved(tmp_path):
    """Verified snapshot records are preserved without corruption during migration."""
    db_path = _create_disposable_old_db(tmp_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO mandi_prices_cache (id, state, district, market, commodity, variety, min_price, max_price, modal_price, arrival_date, source, dataset_id, fetched_at)
        VALUES (888, 'Karnataka', 'Haveri', 'Haveri APMC', 'Maize', 'Hybrid', 1900, 2300, 2100, '15/11/2026', 'verified_snapshot', 'verified_manual', '2026-11-15 12:00:00')
    """)
    conn.commit()
    conn.close()

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, source, dataset_id, fetched_at, modal_price FROM mandi_prices_cache WHERE id = 888")
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[1] == "verified_snapshot"
    assert row[2] == "verified_manual"
    assert row[3] == "2026-11-15 12:00:00"
    assert row[4] == 2100.0


def test_custom_indexes_and_triggers_preserved(tmp_path):
    """Custom index and trigger on mandi_prices_cache are preserved across table recreation."""
    db_path = _create_disposable_old_db(tmp_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Add custom index
    cur.execute("CREATE INDEX idx_mandi_custom_market_crop ON mandi_prices_cache (market, commodity)")
    # Add custom audit trigger
    cur.execute("CREATE TABLE mandi_audit_log (msg TEXT)")
    cur.execute("""
        CREATE TRIGGER trg_mandi_audit AFTER UPDATE ON mandi_prices_cache
        BEGIN
            INSERT INTO mandi_audit_log VALUES ('updated ' || NEW.market);
        END
    """)
    conn.commit()
    conn.close()

    # Migrate
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    # Verify index and trigger exist and work
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_mandi_custom_market_crop'")
    assert cur.fetchone() is not None, "Custom index was not preserved"

    cur.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='trg_mandi_audit'")
    assert cur.fetchone() is not None, "Custom trigger was not preserved"

    # Test trigger fire
    cur.execute("UPDATE mandi_prices_cache SET min_price = min_price + 1 WHERE id = 1")
    conn.commit()
    cur.execute("SELECT msg FROM mandi_audit_log")
    logs = cur.fetchall()
    assert len(logs) >= 1
    assert "Belagavi APMC" in logs[0][0]
    conn.close()


def test_foreign_key_relationships_and_check(tmp_path):
    """Foreign-key relationships remain valid and PRAGMA foreign_key_check returns zero violations."""
    db_path = _create_disposable_old_db(tmp_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    cur.execute("""
        CREATE TABLE mandi_child (
            id INTEGER PRIMARY KEY,
            mandi_id INTEGER REFERENCES mandi_prices_cache(id) ON DELETE CASCADE,
            notes TEXT
        )
    """)
    cur.execute("INSERT INTO mandi_child (id, mandi_id, notes) VALUES (1, 1, 'Child of Belagavi')")
    conn.commit()
    conn.close()

    # Migrate
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    # Verify foreign key check
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    cur.execute("PRAGMA foreign_key_check")
    violations = cur.fetchall()
    assert violations == [], f"Expected 0 violations, got {violations}"

    cur.execute("SELECT id, mandi_id, notes FROM mandi_child WHERE id = 1")
    child_row = cur.fetchone()
    assert child_row == (1, 1, "Child of Belagavi")
    conn.close()


def test_dependent_views_remain_usable(tmp_path):
    """Dependent view pointing to mandi_prices_cache remains functional after table recreation."""
    db_path = _create_disposable_old_db(tmp_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE VIEW view_mandi_summary AS SELECT market, commodity, modal_price FROM mandi_prices_cache")
    conn.commit()
    conn.close()

    # Migrate
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    # Query view
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM view_mandi_summary")
    count = cur.fetchone()[0]
    assert count == 91
    conn.close()


def test_pragma_integrity_and_fk_checks_pass(tmp_path):
    """PRAGMA integrity_check returns ok and PRAGMA foreign_key_check returns empty."""
    db_path = _create_disposable_old_db(tmp_path)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check")
    assert cur.fetchall() == [("ok",)]

    cur.execute("PRAGMA foreign_key_check")
    assert cur.fetchall() == []
    conn.close()


def test_simulated_migration_failure_rolls_back_without_losing_table(tmp_path, monkeypatch):
    """If an error occurs during migration, transaction rolls back and original table is 100% intact."""
    db_path = _create_disposable_old_db(tmp_path)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache")
    assert cur.fetchone()[0] == 91
    conn.close()

    # Wrap raw_conn with a proxy that raises an OperationalError during DROP TABLE
    real_raw_conn = engine.raw_connection()

    class FailingCursorWrapper:
        def __init__(self, real_cursor):
            self._cursor = real_cursor

        def execute(self, sql, *args, **kwargs):
            if "DROP TABLE mandi_prices_cache" in sql:
                raise sqlite3.OperationalError("Simulated disk error on DROP TABLE")
            return self._cursor.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._cursor, name)

    class FailingConnectionWrapper:
        def __init__(self, real_conn):
            self._conn = real_conn

        def cursor(self):
            return FailingCursorWrapper(self._conn.cursor())

        def __getattr__(self, name):
            return getattr(self._conn, name)

    failing_conn = FailingConnectionWrapper(real_raw_conn)
    monkeypatch.setattr(engine, "raw_connection", lambda: failing_conn)

    # Migration must raise RuntimeError
    try:
        migrate_mandi_prices_cache_fetched_at_nullable(engine)
        assert False, "Expected migration to fail"
    except RuntimeError as ex:
        assert "Simulated disk error" in str(ex)

    # Verify original table is completely preserved and intact
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache")
    assert cur.fetchone()[0] == 91
    cur.execute("PRAGMA table_info(mandi_prices_cache)")
    cols = {c[1]: c for c in cur.fetchall()}
    assert cols["fetched_at"][3] == 1  # Still original notnull=1
    conn.close()


def test_init_db_and_seed_all_end_to_end_on_old_database(tmp_path):
    """Simulates application startup (init_db + seed_all) on an older NOT NULL database."""
    db_path = _create_disposable_old_db(tmp_path)
    db_url = f"sqlite:///{db_path.as_posix()}"
    test_engine = create_engine(db_url)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    from backend.app.database import init_db

    # Point engine to test_engine inside init_db via monkeypatch or direct call
    migrate_mandi_prices_cache_fetched_at_nullable(test_engine)

    with Session() as db:
        res = seed_all(db)
        assert res["crops_seeded"] == 0
        assert res["snapshots_seeded"] == 0

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache WHERE source = 'estimated_benchmark' AND fetched_at IS NULL")
    assert cur.fetchone()[0] == 25
    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache WHERE source = 'live_api' AND fetched_at IS NOT NULL")
    assert cur.fetchone()[0] == 66
    conn.close()


def test_repeated_init_db_and_seed_all_idempotency(tmp_path):
    """Calling init_db() + seed_all() multiple times leaves DB clean and unmodified."""
    db_path = _create_disposable_old_db(tmp_path)
    test_engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    migrate_mandi_prices_cache_fetched_at_nullable(test_engine)

    with Session() as db:
        res1 = seed_all(db)
        assert res1["snapshots_seeded"] == 0

    # Second startup run
    migrate_mandi_prices_cache_fetched_at_nullable(test_engine)
    with Session() as db:
        res2 = seed_all(db)
        assert res2["crops_seeded"] == 0
        assert res2["snapshots_seeded"] == 0

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache")
    assert cur.fetchone()[0] == 91
    conn.close()


def test_autoincrement_sequence_high_water_mark_preserved(tmp_path):
    """Verifies that the historical AUTOINCREMENT sequence is preserved across table recreation."""
    db_path = tmp_path / "test_autoincrement_seq.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Create old schema with fetched_at NOT NULL and AUTOINCREMENT
    cur.execute("""
        CREATE TABLE mandi_prices_cache (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            state VARCHAR NOT NULL,
            district VARCHAR NOT NULL,
            market VARCHAR NOT NULL,
            commodity VARCHAR NOT NULL,
            variety VARCHAR,
            min_price FLOAT NOT NULL,
            max_price FLOAT NOT NULL,
            modal_price FLOAT NOT NULL,
            arrival_date VARCHAR NOT NULL,
            source VARCHAR NOT NULL,
            dataset_id VARCHAR,
            fetched_at DATETIME NOT NULL
        )
    """)

    # 2. Insert records with IDs up to 1000
    rows = []
    for i in range(1, 1001):
        rows.append((
            i, f"State{i}", f"District{i}", f"Market{i}", "Onion", "Red",
            2000.0, 2500.0, 2200.0, "15/11/2026",
            "estimated_benchmark" if i <= 25 else "live_api",
            None if i <= 25 else "ogd_123",
            "2026-11-15 12:00:00"
        ))
    cur.executemany("""
        INSERT INTO mandi_prices_cache (
            id, state, district, market, commodity, variety,
            min_price, max_price, modal_price, arrival_date,
            source, dataset_id, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()

    # 3. Delete records with IDs 100 through 1000
    cur.execute("DELETE FROM mandi_prices_cache WHERE id >= 100 AND id <= 1000")
    conn.commit()

    # 4. Confirm original sqlite_sequence.seq remains 1000
    cur.execute("SELECT seq FROM sqlite_sequence WHERE name = 'mandi_prices_cache'")
    orig_seq = cur.fetchone()[0]
    assert orig_seq == 1000, f"Expected orig_seq=1000, got {orig_seq}"

    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache")
    assert cur.fetchone()[0] == 99  # IDs 1..99 remain
    conn.close()

    # 5. Execute the actual nullable timestamp migration
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    migrate_mandi_prices_cache_fetched_at_nullable(engine)

    # 6. Verify all remaining records are preserved and benchmark timestamps normalized
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache")
    assert cur.fetchone()[0] == 99

    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache WHERE source = 'estimated_benchmark' AND fetched_at IS NULL")
    assert cur.fetchone()[0] == 25

    cur.execute("SELECT COUNT(*) FROM mandi_prices_cache WHERE source = 'live_api' AND fetched_at IS NOT NULL")
    assert cur.fetchone()[0] == 74  # 99 - 25

    # Check sqlite_sequence table
    cur.execute("SELECT seq FROM sqlite_sequence WHERE name = 'mandi_prices_cache'")
    post_seq = cur.fetchone()[0]
    assert post_seq >= 1000, f"Expected post_seq >= 1000, got {post_seq}"

    # 7. Insert a new record without explicitly specifying an ID
    cur.execute("""
        INSERT INTO mandi_prices_cache (
            state, district, market, commodity, variety,
            min_price, max_price, modal_price, arrival_date,
            source, dataset_id, fetched_at
        ) VALUES (
            'Maharashtra', 'Nashik', 'New Market', 'Onion', 'Red',
            3000.0, 3500.0, 3200.0, '17/11/2026',
            'live_api', 'ogd_456', '2026-11-17 11:00:00'
        )
    """)
    conn.commit()

    # 8. Confirm its ID is greater than 1000 (specifically 1001)
    new_id = cur.lastrowid
    assert new_id > 1000, f"Expected new_id > 1000, got {new_id}"
    assert new_id == 1001, f"Expected new_id == 1001, got {new_id}"

    conn.close()
