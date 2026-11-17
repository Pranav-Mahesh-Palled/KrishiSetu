"""Pytest configuration and session fixtures for KrishiSetu test suite.

Provides:
- Complete database isolation: creates a dedicated temporary SQLite database for testing,
  guaranteeing zero reads, writes, migrations, or schema operations on production krishisetu.db.
- Hardened failsafe guard preventing tests from connecting to the production database
  across all SQLite URL representations (relative, absolute, symlinks, normalized).
- Automatic database initialization and seeding for the test database.
- Automatic cleanup of temporary database directory upon test completion.
- Deterministic canned fixtures for AGMARKNET, Open-Meteo, Gemini, and TTS.
- Global offline-safe mocks ensuring zero real outbound network calls occur during tests.
"""

import os
import shutil
import tempfile
import atexit
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy.engine import make_url

# ==============================================================================
# Step 1: Create isolated temporary directory and SQLite database path BEFORE importing backend
# ==============================================================================
_TEST_TEMP_DIR = tempfile.mkdtemp(prefix="krishisetu_test_")
_TEST_DB_PATH = Path(_TEST_TEMP_DIR) / "test_krishisetu.db"
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH.as_posix()}"

# Set DATABASE_URL so backend.app.config and backend.app.database load the test DB
os.environ["DATABASE_URL"] = _TEST_DB_URL

# Register emergency process exit cleanup
def _cleanup_test_dir():
    try:
        shutil.rmtree(_TEST_TEMP_DIR, ignore_errors=True)
    except Exception:
        pass

atexit.register(_cleanup_test_dir)

# ==============================================================================
# Step 2: Hardened Production Database Detection & Safety Guard
# ==============================================================================
_PROD_DB_PATH = (Path(__file__).resolve().parent.parent.parent / "krishisetu.db").resolve()


def is_production_database(db_url_or_str: str, prod_db_path: Optional[Path] = None) -> bool:
    """Evaluates whether a database URL or connection string resolves to the production krishisetu.db.

    Uses SQLAlchemy make_url parsing and canonical filesystem path resolution (Path.resolve())
    to detect absolute, relative, symlinked, or variant SQLite representations.
    """
    if prod_db_path is None:
        target_prod = _PROD_DB_PATH
    else:
        target_prod = Path(prod_db_path).resolve()

    raw_str = str(db_url_or_str).strip()
    if not raw_str:
        return False

    try:
        url_obj = make_url(raw_str)
    except Exception:
        # If not parseable as a SQLAlchemy URL, fallback to raw path inspection
        if "krishisetu.db" in raw_str.lower():
            return True
        return False

    if not url_obj.drivername.startswith("sqlite"):
        return False

    db_file_str = url_obj.database
    if not db_file_str or db_file_str == ":memory:":
        return False

    # Check canonical resolved filesystem path
    try:
        resolved_path = Path(db_file_str).resolve()
        if resolved_path == target_prod:
            return True
        if resolved_path.as_posix().lower() == target_prod.as_posix().lower():
            return True
    except Exception:
        pass

    # Detect any relative or bare references named krishisetu.db
    clean_name = Path(db_file_str).name.lower()
    if clean_name == "krishisetu.db":
        return True

    return False


def enforce_database_safety(db_url_or_engine, prod_db_path: Optional[Path] = None):
    """Raises RuntimeError immediately if the provided engine or URL points to production."""
    url_str = str(db_url_or_engine.url if hasattr(db_url_or_engine, "url") else db_url_or_engine)
    if is_production_database(url_str, prod_db_path):
        target = prod_db_path or _PROD_DB_PATH
        raise RuntimeError(
            f"FATAL SAFETY VIOLATION: Test database engine resolved to production database '{target}'! "
            f"Active engine URL is '{url_str}'. Automated tests are strictly prohibited from accessing production data."
        )


# Import database modules now that DATABASE_URL is set to temporary database
from backend.app.database import engine, init_db, SessionLocal
from backend.app.seed import seed_all

# Enforce safety check on the active engine
enforce_database_safety(engine)


@pytest.fixture(scope="session", autouse=True)
def isolated_test_database():
    """Session-scoped fixture ensuring the test database is initialized and seeded,
    and cleanly removed after the test session finishes."""
    enforce_database_safety(engine)
    init_db()
    with SessionLocal() as db:
        seed_all(db)

    yield

    # Teardown: close engine connections and delete temporary test directory
    engine.dispose()
    _cleanup_test_dir()


# ==============================================================================
# Deterministic Canned Fixtures: AGMARKNET Government API
# ==============================================================================

@pytest.fixture
def canned_belagavi_onion_records():
    """Canned AGMARKNET records for Belagavi Onion preset (both local and alternative verified)."""
    return [
        {
            "state": "Karnataka",
            "district": "Belagavi",
            "market": "Belagavi APMC",
            "commodity": "Onion",
            "variety": "Red",
            "min_price": "4200",
            "max_price": "4800",
            "modal_price": "4500",
            "arrival_date": "16/11/2026",
        },
        {
            "state": "Maharashtra",
            "district": "Kolhapur",
            "market": "Kolhapur APMC",
            "commodity": "Onion",
            "variety": "Red",
            "min_price": "3300",
            "max_price": "3700",
            "modal_price": "3500",
            "arrival_date": "16/11/2026",
        },
    ]


@pytest.fixture
def canned_nashik_onion_records():
    """Canned AGMARKNET records for Nashik Onion preset:
    Alternative mandis (Pimpalgaon, Lasalgaon) verified; local Nashik APMC missing."""
    return [
        {
            "state": "Maharashtra",
            "district": "Nashik",
            "market": "Pimpalgaon APMC",
            "commodity": "Onion",
            "variety": "Red",
            "min_price": "2400",
            "max_price": "2800",
            "modal_price": "2600",
            "arrival_date": "16/11/2026",
        },
        {
            "state": "Maharashtra",
            "district": "Nashik",
            "market": "Lasalgaon APMC",
            "commodity": "Onion",
            "variety": "Red",
            "min_price": "2300",
            "max_price": "2700",
            "modal_price": "2500",
            "arrival_date": "16/11/2026",
        },
    ]


@pytest.fixture
def canned_haveri_maize_records():
    """Canned AGMARKNET records for Haveri Maize preset: empty list (no verified quotes)."""
    return []


@pytest.fixture
def canned_pune_potato_records():
    """Canned AGMARKNET records for Pune Potato preset:
    Local Pune APMC verified; alternatives are benchmarks."""
    return [
        {
            "state": "Maharashtra",
            "district": "Pune",
            "market": "Pune APMC (Gultekdi)",
            "commodity": "Potato",
            "variety": "Jyoti",
            "min_price": "2100",
            "max_price": "2400",
            "modal_price": "2250",
            "arrival_date": "16/11/2026",
        }
    ]


@pytest.fixture
def canned_kolar_tomato_records():
    """Canned AGMARKNET records for Kolar Tomato preset: local and alternative verified."""
    return [
        {
            "state": "Karnataka",
            "district": "Kolar",
            "market": "Kolar APMC",
            "commodity": "Tomato",
            "variety": "Hybrid",
            "min_price": "1200",
            "max_price": "1500",
            "modal_price": "1350",
            "arrival_date": "16/11/2026",
        },
        {
            "state": "Karnataka",
            "district": "Kolar",
            "market": "Malur APMC",
            "commodity": "Tomato",
            "variety": "Hybrid",
            "min_price": "1300",
            "max_price": "1600",
            "modal_price": "1450",
            "arrival_date": "16/11/2026",
        },
    ]


# ==============================================================================
# Deterministic Canned Fixtures: Open-Meteo Weather & Geocoding
# ==============================================================================

@pytest.fixture
def canned_weather_forecast():
    """Successful dry 7-day weather forecast and hourly soil moisture payload."""
    today = "2026-11-17"
    return {
        "daily": {
            "time": [today] * 7,
            "temperature_2m_max": [31.5, 32.0, 30.8, 31.2, 32.5, 33.0, 31.0],
            "temperature_2m_min": [19.2, 19.8, 20.1, 19.5, 20.0, 20.5, 19.0],
            "precipitation_sum": [0.0] * 7,
            "precipitation_probability_max": [5.0] * 7,
            "weather_code": [0] * 7,
        },
        "hourly": {
            "precipitation": [0.0] * 72,
            "soil_moisture_0_to_7cm": [0.25] * 72,
            "relative_humidity_2m": [55.0] * 72,
        },
    }


@pytest.fixture
def canned_geocoding_success():
    """Successful Open-Meteo geocoding search result for Belagavi."""
    return {
        "results": [
            {
                "name": "Belagavi",
                "admin1": "Karnataka",
                "latitude": 15.8497,
                "longitude": 74.4977,
                "country": "India",
            }
        ]
    }


@pytest.fixture
def canned_geocoding_unknown():
    """Empty geocoding result for unknown / unresolvable query."""
    return {"results": []}


@pytest.fixture
def canned_weather_error():
    """HTTP 500 error response structure from weather provider."""
    return {"error": True, "reason": "Internal Server Error"}


@pytest.fixture
def canned_weather_timeout():
    """Timeout exception representation for upstream weather service."""
    return httpx.ReadTimeout("Open-Meteo read timed out after 6.0s")


@pytest.fixture
def canned_weather_missing_data():
    """Weather response with empty/null arrays simulating unmeasured sensor data."""
    today = "2026-11-17"
    return {
        "daily": {
            "time": [today] * 7,
            "temperature_2m_max": [30.0] * 7,
            "temperature_2m_min": [20.0] * 7,
            "precipitation_sum": [0.0] * 7,
            "precipitation_probability_max": [5.0] * 7,
            "weather_code": [0] * 7,
        },
        "hourly": {
            "precipitation": [],
            "soil_moisture_0_to_7cm": [None] * 72,
            "relative_humidity_2m": [],
        },
    }


# ==============================================================================
# Deterministic Canned Fixtures: Gemini AI Advisory & Multilingual Q&A
# ==============================================================================

@pytest.fixture
def canned_gemini_advisory_json():
    """Deterministic structured AIAdvisory JSON string."""
    return json.dumps({
        "headline": "Sell Produce at Belagavi APMC for Best Realized Return",
        "harvest_action": "Favorable dry window forecast. Complete scheduled harvest.",
        "recommended_mandi": "Belagavi APMC",
        "price_justification": "Verified local quotations yield top realized financial return after logistics.",
        "protection_tips": [
            "Store produce in ventilated jute gunny bags.",
            "Cover cargo bed securely with waterproof tarpaulin."
        ],
        "language": "en"
    })


@pytest.fixture
def canned_kannada_chat_response():
    """Deterministic regional Kannada assistant answer."""
    return "ಹುಬ್ಬಳ್ಳಿ ಎಪಿಎಂಸಿ ಮಾರುಕಟ್ಟೆ ಉತ್ತಮವಾಗಿದೆ, ಅಲ್ಲಿ ನಿವ್ವಳ ಲಾಭ ದೊರೆಯುತ್ತದೆ."


@pytest.fixture
def canned_hindi_chat_response():
    """Deterministic regional Hindi assistant answer."""
    return "हुबली मंडी में बेचना सबसे अच्छा विकल्प है, जहां आपको अधिकतम लाभ मिलेगा।"


# ==============================================================================
# Deterministic Canned Fixtures: Google TTS Audio Stream
# ==============================================================================

_DETERMINISTIC_AUDIO_BYTES = b"\xff\xfb\x90\x44" + b"\x00" * 1200


@pytest.fixture
def canned_tts_mp3_bytes():
    """Deterministic local audio/mpeg bytes fixture (>1000 bytes) for TTS tests."""
    return _DETERMINISTIC_AUDIO_BYTES


# ==============================================================================
# Global Autouse Network Protection & Service Mocking
# ==============================================================================

@pytest.fixture(autouse=True)
def autouse_mock_external_services(
    canned_weather_forecast,
    canned_kannada_chat_response,
    canned_hindi_chat_response,
    canned_gemini_advisory_json,
    canned_tts_mp3_bytes,
):
    """Global autouse fixture providing deterministic fallbacks for external HTTP services.

    Protects:
    1. Open-Meteo Geocoding & Forecast APIs (httpx.AsyncClient.get)
    2. Google Gemini Generative AI SDK (google.genai.Client)
    3. Google Translate TTS (gTTS.write_to_fp)

    Individual tests can override these mocks via standard `with patch(...)` blocks.
    """
    # 1. Mock httpx.AsyncClient.get for Open-Meteo & AGMARKNET
    async def mock_async_get(self, url, *args, **kwargs):
        params = kwargs.get("params", {})
        url_str = str(url)

        resp = AsyncMock()
        resp.status_code = 200

        if "geocoding-api.open-meteo.com" in url_str:
            name = str(params.get("name", "")).lower()
            if any(bad in name for bad in ["nonexistent", "faketown", "unknown", "xyz123"]):
                resp.json = lambda: {"results": []}
            elif "kolar" in name:
                resp.json = lambda: {
                    "results": [{"name": "Kolar", "admin1": "Karnataka", "latitude": 13.1367, "longitude": 78.1291, "country": "India"}]
                }
            elif "nashik" in name or "nasik" in name:
                resp.json = lambda: {
                    "results": [{"name": "Nashik", "admin1": "Maharashtra", "latitude": 19.9975, "longitude": 73.7898, "country": "India"}]
                }
            elif "haveri" in name:
                resp.json = lambda: {
                    "results": [{"name": "Haveri", "admin1": "Karnataka", "latitude": 14.7952, "longitude": 75.3992, "country": "India"}]
                }
            elif "pune" in name:
                resp.json = lambda: {
                    "results": [{"name": "Pune", "admin1": "Maharashtra", "latitude": 18.5204, "longitude": 73.8567, "country": "India"}]
                }
            else:
                resp.json = lambda: {
                    "results": [{"name": "Belagavi", "admin1": "Karnataka", "latitude": 15.8497, "longitude": 74.4977, "country": "India"}]
                }
            return resp

        if "api.open-meteo.com" in url_str:
            resp.json = lambda: canned_weather_forecast
            return resp

        if "api.data.gov.in" in url_str:
            resp.json = lambda: {"total": 0, "count": 0, "records": []}
            return resp

        # Default fallback response
        resp.json = lambda: {}
        return resp

    # 2. Mock google.genai.Client for Gemini
    mock_genai_client = MagicMock()
    mock_models = MagicMock()
    mock_genai_client.models = mock_models

    def mock_generate_content(*args, **kwargs):
        resp = MagicMock()
        contents = str(kwargs.get("contents", ""))
        config = kwargs.get("config")
        sys_inst = str(getattr(config, "system_instruction", ""))

        try:
            parsed_contents = json.loads(contents)
        except Exception:
            parsed_contents = {}

        target_lang = parsed_contents.get("target_language")
        if not target_lang:
            for candidate in ["kn", "hi", "mr", "en"]:
                if f"farmers in '{candidate}'" in sys_inst or f"requested language: '{candidate}'" in sys_inst:
                    target_lang = candidate
                    break
        if not target_lang:
            target_lang = "en"

        if "farmer_question" in contents or "farmer_question" in parsed_contents:
            if target_lang == "kn" or "ಈರುಳ್ಳಿ" in contents:
                resp.text = canned_kannada_chat_response
            elif target_lang == "hi" or "बारिश" in contents:
                resp.text = canned_hindi_chat_response
            else:
                resp.text = "Hubli APMC offers the highest verified net profit."
        else:
            resp.text = json.dumps({
                "headline": f"Recommended Mandi Selected for Best Realized Return ({target_lang})",
                "harvest_action": "Favorable dry window forecast. Complete scheduled harvest.",
                "recommended_mandi": "Belagavi APMC",
                "price_justification": "Verified local quotations yield top realized financial return after logistics.",
                "protection_tips": [
                    "Store produce in ventilated jute gunny bags.",
                    "Cover cargo bed securely with waterproof tarpaulin."
                ],
                "language": target_lang
            })

        return resp

    mock_models.generate_content.side_effect = mock_generate_content

    # 3. Mock gTTS.write_to_fp for Google TTS
    def mock_tts_write(self, fp):
        fp.write(canned_tts_mp3_bytes)

    with patch("httpx.AsyncClient.get", new=mock_async_get), \
         patch("google.genai.Client", return_value=mock_genai_client), \
         patch("gtts.gTTS.write_to_fp", new=mock_tts_write):
        yield
