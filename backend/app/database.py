import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.config import DATABASE_URL

logger = logging.getLogger(__name__)

# For SQLite, check_same_thread=False is needed for multi-threaded FastAPI workers
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency for managing database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_mandi_prices_cache_fetched_at_nullable(db_engine):
    """Safely upgrades mandi_prices_cache table in SQLite so fetched_at is NULLABLE if an older NOT NULL schema exists.

    Uses transactional SQLite table-recreation migration per official SQLite documentation:
    - Verifies foreign_keys are disabled before beginning the transaction
    - Recreates table with fetched_at DATETIME (nullable)
    - Preserves all rows, autoincrement primary keys, column data, and constraints
    - Normalizes estimated_benchmark records (fetched_at = NULL, dataset_id = NULL)
    - Preserves live_api records with their original fetched_at, dataset_id, and price values
    - Preserves and restores saved custom indexes and triggers
    - Verifies PRAGMA foreign_key_check and PRAGMA integrity_check before commit
    - Re-enables foreign_keys outside the transaction
    - Does not swallow exceptions, raising an actionable RuntimeError on failure
    """
    if not str(db_engine.url).startswith("sqlite"):
        return

    raw_conn = db_engine.raw_connection()
    try:
        cursor = raw_conn.cursor()

        # Step 1: Check if mandi_prices_cache table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mandi_prices_cache'")
        if not cursor.fetchone():
            return

        # Step 2: Inspect columns
        cursor.execute("PRAGMA table_info(mandi_prices_cache)")
        cols = cursor.fetchall()
        # Col: (cid, name, type, notnull, dflt_value, pk)
        fetched_at_col = next((c for c in cols if c[1] == "fetched_at"), None)

        # Check if any estimated_benchmark has non-null fetched_at
        cursor.execute(
            "SELECT COUNT(*) FROM mandi_prices_cache WHERE source = 'estimated_benchmark' AND fetched_at IS NOT NULL"
        )
        non_null_benchmarks = cursor.fetchone()[0]

        # If fetched_at is already nullable and all benchmarks have NULL fetched_at, no migration needed
        if fetched_at_col and fetched_at_col[3] == 0 and non_null_benchmarks == 0:
            return

        logger.info(
            "Migrating mandi_prices_cache: making fetched_at nullable and normalizing estimated_benchmark records."
        )

        # Step 3: Capture existing custom indexes, triggers, dependent views, and AUTOINCREMENT sequence
        cursor.execute("""
            SELECT type, name, sql FROM sqlite_master 
            WHERE tbl_name = 'mandi_prices_cache' 
              AND type IN ('index', 'trigger') 
              AND sql IS NOT NULL
        """)
        saved_objects = cursor.fetchall()

        # Capture dependent views that reference mandi_prices_cache
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type = 'view' AND sql IS NOT NULL")
        all_views = cursor.fetchall()
        dependent_views = [v for v in all_views if "mandi_prices_cache" in v[1]]

        # Capture original AUTOINCREMENT sequence counter from sqlite_sequence
        orig_seq = None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
        if cursor.fetchone():
            cursor.execute("SELECT seq FROM sqlite_sequence WHERE name = 'mandi_prices_cache'")
            seq_row = cursor.fetchone()
            if seq_row:
                orig_seq = seq_row[0]

        # Step 4: Disable foreign keys outside transaction
        cursor.execute("PRAGMA foreign_keys = OFF")

        # Step 5: Begin explicit immediate transaction
        cursor.execute("BEGIN IMMEDIATE TRANSACTION")
        try:
            # Create replacement table with nullable fetched_at
            cursor.execute("""
                CREATE TABLE mandi_prices_cache_new (
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
                    fetched_at DATETIME
                )
            """)

            # Copy data: normalize estimated_benchmark records, preserve live_api and verified_snapshot
            cursor.execute("""
                INSERT INTO mandi_prices_cache_new (
                    id, state, district, market, commodity, variety,
                    min_price, max_price, modal_price, arrival_date,
                    source, dataset_id, fetched_at
                )
                SELECT
                    id, state, district, market, commodity, variety,
                    min_price, max_price, modal_price, arrival_date,
                    source,
                    CASE WHEN source = 'estimated_benchmark' THEN NULL ELSE dataset_id END,
                    CASE WHEN source = 'estimated_benchmark' THEN NULL ELSE fetched_at END
                FROM mandi_prices_cache
            """)

            # Drop dependent views before dropping old table
            for view_name, _ in dependent_views:
                cursor.execute(f"DROP VIEW IF EXISTS {view_name}")

            # Drop old table
            cursor.execute("DROP TABLE mandi_prices_cache")

            # Rename new table to original name
            cursor.execute("ALTER TABLE mandi_prices_cache_new RENAME TO mandi_prices_cache")

            # Restore original AUTOINCREMENT high-water mark in sqlite_sequence
            if orig_seq is not None:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
                if cursor.fetchone():
                    cursor.execute("SELECT seq FROM sqlite_sequence WHERE name = 'mandi_prices_cache'")
                    if cursor.fetchone():
                        cursor.execute(
                            "UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'mandi_prices_cache'",
                            (orig_seq,),
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO sqlite_sequence (name, seq) VALUES ('mandi_prices_cache', ?)",
                            (orig_seq,),
                        )

            # Recreate saved custom indexes and triggers
            for obj_type, obj_name, obj_sql in saved_objects:
                cursor.execute(obj_sql)

            # Recreate dependent views
            for _, view_sql in dependent_views:
                cursor.execute(view_sql)

            # Check foreign key consistency
            cursor.execute("PRAGMA foreign_key_check")
            fk_violations = cursor.fetchall()
            if fk_violations:
                raise RuntimeError(f"Foreign key violations detected during migration: {fk_violations}")

            # Check table integrity
            cursor.execute("PRAGMA integrity_check")
            ic = cursor.fetchall()
            if ic != [("ok",)]:
                raise RuntimeError(f"Integrity check failed: {ic}")

            # Commit the transaction
            raw_conn.commit()
            logger.info("Successfully migrated mandi_prices_cache to nullable fetched_at.")
        except Exception as e:
            raw_conn.rollback()
            raise RuntimeError(f"Migration of mandi_prices_cache failed and was rolled back: {e}") from e
        finally:
            cursor.execute("PRAGMA foreign_keys = ON")
    finally:
        raw_conn.close()


def init_db():
    """Initializes all database tables declared in models and applies idempotent SQLite migrations."""
    from backend.app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # SQLite lightweight column migration for dataset_id
    if DATABASE_URL.startswith("sqlite"):
        from sqlalchemy import text
        with engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE mandi_prices_cache ADD COLUMN dataset_id VARCHAR"))
                conn.commit()
            except Exception:
                pass  # Column already exists

            # Idempotently reclassify unverified legacy snapshot records to estimated_benchmark and clear dataset_id
            try:
                conn.execute(text(
                    "UPDATE mandi_prices_cache "
                    "SET source = 'estimated_benchmark', dataset_id = NULL "
                    "WHERE source = 'verified_snapshot'"
                ))
                conn.commit()
            except Exception:
                pass

        # Idempotently migrate mandi_prices_cache so fetched_at is nullable
        migrate_mandi_prices_cache_fetched_at_nullable(engine)
