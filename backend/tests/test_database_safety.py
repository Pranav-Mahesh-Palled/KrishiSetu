"""Focused unit tests for the production database protection failsafe guard."""

from pathlib import Path
import pytest

from backend.tests.conftest import is_production_database, enforce_database_safety


def test_detects_default_relative_sqlite_url():
    """Detects the default relative URL 'sqlite:///./krishisetu.db'."""
    assert is_production_database("sqlite:///./krishisetu.db") is True


def test_detects_bare_relative_sqlite_url():
    """Detects bare relative URL 'sqlite:///krishisetu.db'."""
    assert is_production_database("sqlite:///krishisetu.db") is True


def test_detects_absolute_windows_path():
    """Detects canonical absolute Windows production database path."""
    prod_path = (Path(__file__).resolve().parent.parent.parent / "krishisetu.db").resolve()
    url = f"sqlite:///{prod_path.as_posix()}"
    assert is_production_database(url) is True


def test_detects_parent_traversal_relative_path():
    """Detects relative paths with directory traversal resolving to production DB."""
    assert is_production_database("sqlite:///backend/../krishisetu.db") is True


def test_detects_case_insensitive_path():
    """Detects Windows filesystem case variations (e.g. KRISHISETU.DB)."""
    assert is_production_database("sqlite:///./KRISHISETU.DB") is True


def test_allows_temporary_test_database():
    """Confirms temporary SQLite databases are recognized as safe."""
    temp_url = "sqlite:///C:/Users/Pranav/AppData/Local/Temp/krishisetu_test_xyz/test_krishisetu.db"
    assert is_production_database(temp_url) is False


def test_allows_in_memory_sqlite():
    """Confirms SQLite in-memory databases are recognized as safe."""
    assert is_production_database("sqlite:///:memory:") is False


def test_enforce_database_safety_raises_runtime_error_on_production():
    """Verifies that enforce_database_safety raises RuntimeError immediately for production references."""
    with pytest.raises(RuntimeError) as exc_info:
        enforce_database_safety("sqlite:///./krishisetu.db")
    assert "FATAL SAFETY VIOLATION" in str(exc_info.value)
    assert "strictly prohibited" in str(exc_info.value)


def test_enforce_database_safety_passes_on_temporary_database():
    """Verifies that enforce_database_safety succeeds without error on temporary test databases."""
    temp_url = "sqlite:///C:/Users/Pranav/AppData/Local/Temp/krishisetu_test_abc/test_krishisetu.db"
    # Should not raise
    enforce_database_safety(temp_url)
