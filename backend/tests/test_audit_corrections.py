"""Pre-Deployment Audit Correction Pass Regression Tests for KrishiSetu.

Covers verification for Tasks 1-6:
- Task 1: Estimated benchmark price generation and labelling (no unverified snapshot labels)
- Task 2: Strict geocoding resolution (no silent Hubli fallback, structured 400 on unknown)
- Task 3: Mandi radius enforcement (strict 150 km road boundary; empty/warning outside)
- Task 4: AGMARKNET market alias matching (Belgaum/Belagavi, Hubballi/Hubli, etc.)
- Task 5: Spoilage rate cap at 35% under extreme transit distances
- Task 6: Weather hourly null filtering (soil moisture, rainfall) and rolling 72-hour sum
"""

import pytest
import httpx
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal, init_db
from backend.app.main import app
from backend.app.models import CropProfile
from backend.app.seed import seed_all
from backend.app.services.arbitrage_engine import (
    MandiCandidate,
    calculate_mandi_arbitrage,
    calculate_road_distance_km,
    MAX_TRANSIT_SPOILAGE_RATE,
)
from backend.app.services.mandi_service import (
    match_mandi_name,
    select_candidate_mandis,
    get_mandi_candidates_with_prices,
)
from backend.app.services.weather_service import (
    geocode_location,
    get_weather_forecast,
)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Ensures database is seeded before running tests."""
    init_db()
    with SessionLocal() as db:
        seed_all(db)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# Task 1: Data Integrity & Benchmark Labelling
# ==============================================================================

@pytest.mark.anyio
async def test_task1_benchmark_labelling_when_no_snapshot():
    """Verifies that missing crop/market records receive estimated_benchmark, not verified_snapshot."""
    with SessionLocal() as db:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "banana").first()
        assert crop is not None

        # Fetch candidates for Belagavi where snapshot data exists for onion/potato, but not banana
        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", return_value=[]):
            candidates = await get_mandi_candidates_with_prices(15.85, 74.50, crop, db)
        assert len(candidates) > 0

        for c in candidates:
            # If there was no snapshot for banana in this mandi, it MUST be estimated_benchmark
            if c.source != "live_api" and c.source != "verified_snapshot":
                assert c.source == "estimated_benchmark"
                assert c.is_benchmark is True
                assert c.variety == "Estimated Benchmark"
                assert c.modal_price == 2000.0


def test_task1_benchmark_excluded_from_verified_net_gain():
    """Verifies that arbitrage engine zeroes out net_gain_vs_local_total for benchmark records."""
    candidates = [
        MandiCandidate(
            market="Local APMC",
            district="Local",
            state="Karnataka",
            latitude=15.85,
            longitude=74.50,
            modal_price=2000.0,
            source="verified_snapshot",
            is_benchmark=False,
        ),
        MandiCandidate(
            market="Benchmark APMC",
            district="Neighbor",
            state="Karnataka",
            latitude=15.95,
            longitude=74.60,
            modal_price=3500.0,
            source="estimated_benchmark",
            is_benchmark=True,
        ),
    ]

    results = calculate_mandi_arbitrage(15.85, 74.50, 30.0, candidates, "medium")
    benchmark_result = next(r for r in results if r.market == "Benchmark APMC")
    assert benchmark_result.is_benchmark is True
    # Benchmark gain must be 0 to prevent claiming unverified profit
    assert benchmark_result.net_gain_vs_local_total == 0.0


# ==============================================================================
# Task 2: Geographical Resolution
# ==============================================================================

@pytest.mark.anyio
async def test_task2_geocoding_unknown_location_raises_error():
    """Verifies that an unknown location raises ValueError rather than defaulting to Hubli."""
    with pytest.raises(ValueError) as exc_info:
        await geocode_location("XyZ123FakeTownNonExistent")
    assert "could not be resolved" in str(exc_info.value).lower()


def test_task2_api_analyze_returns_400_on_unresolvable_location(client: TestClient):
    """Verifies that /api/analyze returns HTTP 400 when geocoding fails."""
    payload = {
        "location_query": "NonExistentUnknownVillage123456",
        "crop_id": "onion",
        "quantity_quintals": 30.0,
        "language": "en",
    }
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 400
    assert "unable to resolve" in response.json()["detail"].lower()


@pytest.mark.anyio
async def test_task2_geocoding_offline_demo_hubs():
    """Verifies recognized demo hubs resolve correctly offline or online."""
    # Test with network failure simulation to explicitly test demo hubs fallback
    with patch("httpx.AsyncClient.get", side_effect=Exception("Network down")):
        res_belgaum = await geocode_location("Belgaum")
        assert res_belgaum["name"] == "Belagavi"
        assert abs(res_belgaum["lat"] - 15.8497) < 0.01

        res_pune = await geocode_location("Pune")
        assert res_pune["name"] == "Pune"
        assert abs(res_pune["lat"] - 18.5204) < 0.01


@pytest.mark.anyio
async def test_task6_weather_null_filtering_and_rolling_sum():
    """Verifies that Open-Meteo nulls in hourly soil moisture and precipitation are safely handled."""
    # Synthetic payload with interspersed nulls in hourly data
    mock_payload = {
        "daily": {
            "time": ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22"],
            "temperature_2m_max": [30.0] * 7,
            "temperature_2m_min": [20.0] * 7,
            "precipitation_sum": [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "precipitation_probability_max": [40.0] * 7,
            "weather_code": [0] * 7,
        },
        "hourly": {
            # 72 hours of hourly precipitation with nulls: 1.0mm for first 10 hours, then None
            "precipitation": [1.0] * 10 + [None] * 62,
            # 72 hours of soil moisture with nulls: alternating 0.30 and None
            "soil_moisture_0_to_7cm": [0.30 if i % 2 == 0 else None for i in range(72)],
            "relative_humidity_2m": [65.0] * 72,
        },
    }

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: mock_payload

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with SessionLocal() as db:
            # Query an uncached coordinate to trigger Open-Meteo parser
            res = await get_weather_forecast(11.11, 77.77, "high", db)

            # Rolling 72h precipitation should be 10 * 1.0 = 10.0 mm
            assert res["rain_72h_mm"] == 10.0

            # Soil moisture average should be 0.30 (nulls properly excluded)
            assert res["soil_moisture_avg"] == 0.30


# ==============================================================================
# Task 3: Mandi Geographic Boundaries (150 km Radius)
# ==============================================================================

def test_task3_within_150km_returns_nearby_mandis():
    """Origin in Belagavi should return only mandis <= 150 km away."""
    mandis = select_candidate_mandis(15.85, 74.50, max_count=5)
    assert len(mandis) >= 1
    for m in mandis:
        dist = calculate_road_distance_km(15.85, 74.50, m["latitude"], m["longitude"])
        assert dist <= 150.0


def test_task3_outside_150km_returns_empty_list():
    """Origin in New Delhi (28.6139, 77.2090) is >1000 km away and must return 0 mandis."""
    mandis = select_candidate_mandis(28.6139, 77.2090, max_count=5)
    assert len(mandis) == 0


def test_task3_api_analyze_out_of_coverage_warning(client: TestClient):
    """Verifies that /api/analyze handles distant locations with coverage_status='out_of_coverage'."""
    payload = {
        "location_query": "New Delhi, Delhi",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "crop_id": "onion",
        "quantity_quintals": 30.0,
        "language": "en",
    }
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["coverage_status"] == "out_of_coverage"
    assert len(data["mandi_comparison"]) == 0
    assert "No APMC mandis found within 150 km" in data["coverage_warning"]
    assert "outside" in data["ai_advisory"]["price_justification"].lower()


# ==============================================================================
# Task 4: AGMARKNET Name Matching & Aliases
# ==============================================================================

def test_task4_mandi_alias_matching():
    """Verifies bidirectional alias matching for AGMARKNET variations."""
    assert match_mandi_name("Belgaum", "Belagavi APMC") is True
    assert match_mandi_name("Belagavi", "Belagavi APMC") is True
    assert match_mandi_name("Hubballi", "Hubli APMC") is True
    assert match_mandi_name("Amargol", "Hubli APMC") is True
    assert match_mandi_name("Pune", "Pune APMC (Gultekdi)") is True
    assert match_mandi_name("Gultekdi", "Pune APMC (Gultekdi)") is True
    assert match_mandi_name("Pimpalgaon Baswant", "Pimpalgaon APMC") is True
    assert match_mandi_name("Chakan", "Khed (Chakan) APMC") is True
    assert match_mandi_name("Bangalore", "Bengaluru (Yeshwanthpur) APMC") is True
    assert match_mandi_name("Yeshwanthpur", "Bengaluru (Yeshwanthpur) APMC") is True

    # Negative check
    assert match_mandi_name("Azadpur", "Belagavi APMC") is False


# ==============================================================================
# Task 5: Financial Spoilage Rate Cap
# ==============================================================================

def test_task5_spoilage_rate_cap_on_extreme_distance():
    """Verifies that transit spoilage rate is strictly capped at 35% (0.35)."""
    # 2500 km distance with high perishability (0.0005/km) -> uncapped would be 1.25 (125%)
    origin_lat, origin_lon = 10.0, 75.0
    distant_lat, distant_lon = 30.0, 75.0  # ~2500 km road distance

    road_km = calculate_road_distance_km(origin_lat, origin_lon, distant_lat, distant_lon)
    assert road_km > 2000.0

    candidate = MandiCandidate(
        market="Far APMC",
        district="Far",
        state="India",
        latitude=distant_lat,
        longitude=distant_lon,
        modal_price=3000.0,
        source="verified_snapshot",
    )

    results = calculate_mandi_arbitrage(
        origin_lat, origin_lon, 10.0, [candidate], perishability_tier="high"
    )
    res = results[0]

    # Spoilage deduction must not exceed 35% of modal price (0.35 * 3000 = 1050.0)
    expected_max_spoilage = round(3000.0 * MAX_TRANSIT_SPOILAGE_RATE, 2)
    assert res.spoilage_deduction_per_qtl == expected_max_spoilage
    assert res.spoilage_deduction_per_qtl <= 3000.0 * 0.35


# ==============================================================================
# Additional Tests: Task 1 (Soil Moisture Missing-Data & Risk Handling)
# ==============================================================================

@pytest.mark.anyio
async def test_task1_weather_all_null_soil_moisture():
    """All-null soil moisture must return None and soil_moisture_available=False (no 0.25 default)."""
    mock_payload = {
        "daily": {
            "time": ["2026-11-16"] * 7,
            "temperature_2m_max": [30.0] * 7,
            "temperature_2m_min": [20.0] * 7,
            "precipitation_sum": [0.0] * 7,
            "precipitation_probability_max": [10.0] * 7,
            "weather_code": [0] * 7,
        },
        "hourly": {
            "precipitation": [0.0] * 72,
            "soil_moisture_0_to_7cm": [None] * 72,
            "relative_humidity_2m": [50.0] * 72,
        },
    }

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: mock_payload

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with SessionLocal() as db:
            res = await get_weather_forecast(12.34, 76.54, "medium", db)
            assert res["soil_moisture_avg"] is None
            assert res["soil_moisture_available"] is False
            assert res["risk_level"] == "SAFE_WINDOW"
            assert "unavailable" in res["description"].lower()


@pytest.mark.anyio
async def test_task1_weather_empty_hourly_arrays():
    """Empty hourly arrays must handle safely without exceptions and return soil_moisture_avg=None."""
    mock_payload = {
        "daily": {
            "time": ["2026-11-16"] * 7,
            "temperature_2m_max": [30.0] * 7,
            "temperature_2m_min": [20.0] * 7,
            "precipitation_sum": [2.0] * 7,
            "precipitation_probability_max": [20.0] * 7,
            "weather_code": [0] * 7,
        },
        "hourly": {
            "precipitation": [],
            "soil_moisture_0_to_7cm": [],
            "relative_humidity_2m": [],
        },
    }

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: mock_payload

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with SessionLocal() as db:
            res = await get_weather_forecast(13.45, 75.67, "medium", db)
            assert res["soil_moisture_avg"] is None
            assert res["soil_moisture_available"] is False
            assert res["rain_72h_mm"] >= 0.0


def test_task1_weather_risk_calculation_with_unavailable_soil_moisture():
    """Validates weather-risk engine behavior when soil_moisture is None."""
    from backend.app.services.weather_risk import classify_weather_risk

    # Heavy rain (>15mm) triggers HIGH_SPOILAGE_ALERT even if soil moisture is None
    risk_heavy = classify_weather_risk(rain_72h_mm=25.0, max_rain_prob_pct=80.0, soil_moisture=None)
    assert risk_heavy.risk_level == "HIGH_SPOILAGE_ALERT"
    assert risk_heavy.soil_moisture is None

    # Moderate rain (8mm) triggers HARVEST_WITHIN_48H even if soil moisture is None
    risk_mod = classify_weather_risk(rain_72h_mm=8.0, max_rain_prob_pct=40.0, soil_moisture=None)
    assert risk_mod.risk_level == "HARVEST_WITHIN_48H"
    assert risk_mod.soil_moisture is None

    # Dry weather triggers SAFE_WINDOW without claiming soil moisture is within optimal threshold
    risk_dry = classify_weather_risk(rain_72h_mm=1.0, max_rain_prob_pct=15.0, soil_moisture=None)
    assert risk_dry.risk_level == "SAFE_WINDOW"
    assert risk_dry.soil_moisture is None
    assert "unavailable" in risk_dry.description.lower()


# ==============================================================================
# Additional Tests: Task 2 (AGMARKNET Pagination & Upstream Resilience)
# ==============================================================================

@pytest.mark.anyio
async def test_task2_agmarknet_pagination_multiple_pages():
    """Verifies that fetch_live_agmarknet_records paginates through multiple batches."""
    from backend.app.services.mandi_service import fetch_live_agmarknet_records

    # Simulate 2 pages of records (100 on page 1, 45 on page 2)
    def mock_get_side_effect(url, params):
        offset = params.get("offset", 0)
        mock = AsyncMock()
        mock.status_code = 200
        if offset == 0:
            mock.json = lambda: {
                "total": 145,
                "count": 100,
                "records": [{"market": f"Market_{i}", "modal_price": 2000 + i} for i in range(100)],
            }
        elif offset == 100:
            mock.json = lambda: {
                "total": 145,
                "count": 45,
                "records": [{"market": f"Market_{100 + i}", "modal_price": 2100 + i} for i in range(45)],
            }
        else:
            mock.json = lambda: {"total": 145, "count": 0, "records": []}
        return mock

    with patch("httpx.AsyncClient.get", side_effect=mock_get_side_effect):
        records = await fetch_live_agmarknet_records("Onion", state="Karnataka", page_size=100)
        assert len(records) == 145
        assert records[0]["market"] == "Market_0"
        assert records[144]["market"] == "Market_144"


@pytest.mark.anyio
async def test_task2_agmarknet_pagination_empty_page():
    """Empty first page must return empty list without error."""
    from backend.app.services.mandi_service import fetch_live_agmarknet_records

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"total": 0, "count": 0, "records": []}

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        records = await fetch_live_agmarknet_records("NonExistentCommodity")
        assert records == []


@pytest.mark.anyio
async def test_task2_agmarknet_pagination_upstream_failure_graceful():
    """If page 2 fails with timeout, all records fetched on page 1 must be preserved."""
    from backend.app.services.mandi_service import fetch_live_agmarknet_records

    call_count = 0

    def mock_get_flaky(url, params):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            mock = AsyncMock()
            mock.status_code = 200
            mock.json = lambda: {
                "total": 200,
                "count": 100,
                "records": [{"market": f"Market_{i}", "modal_price": 2000} for i in range(100)],
            }
            return mock
        raise httpx.ReadTimeout("Read timed out on page 2")

    with patch("httpx.AsyncClient.get", side_effect=mock_get_flaky):
        records = await fetch_live_agmarknet_records("Tomato", state="Karnataka", page_size=100)
        # Should gracefully retain the 100 records from page 1
        assert len(records) == 100


# ==============================================================================
# Tasks 1-5 Regression Tests: Live OGD, User-Agent, Reclassification, Migrations
# ==============================================================================

def test_task2_seeded_records_reclassified_to_estimated_benchmark():
    """Verifies that all 25 seeded records are reclassified to estimated_benchmark with dataset_id NULL and fetched_at NULL."""
    from backend.app.models import MandiPricesCache

    with SessionLocal() as db:
        benchmarks = db.query(MandiPricesCache).filter(MandiPricesCache.source == "estimated_benchmark").all()
        assert len(benchmarks) == 25

        for b in benchmarks:
            assert b.dataset_id is None
            assert b.source == "estimated_benchmark"
            assert b.fetched_at is None
            assert b.market
            assert b.commodity
            assert b.district
            assert b.state
            assert b.modal_price > 0


def test_seed_all_repeated_execution_preserves_null_fetched_at_for_benchmarks():
    """Verifies that calling seed_all repeatedly never assigns fetched_at to estimated benchmarks."""
    from backend.app.models import MandiPricesCache
    from backend.app.seed import seed_all

    with SessionLocal() as db:
        # Run seeder multiple times to verify idempotency and non-assignment of fetched_at
        res1 = seed_all(db)
        res2 = seed_all(db)

        benchmarks = db.query(MandiPricesCache).filter(MandiPricesCache.source == "estimated_benchmark").all()
        assert len(benchmarks) == 25
        for b in benchmarks:
            assert b.source == "estimated_benchmark"
            assert b.dataset_id is None
            assert b.fetched_at is None, f"Benchmark {b.market} - {b.commodity} has non-null fetched_at: {b.fetched_at}"


def test_sqlite_idempotent_migration_reclassifies_legacy_records():
    """Verifies that init_db() migration converts any legacy verified_snapshot records to estimated_benchmark."""
    from sqlalchemy import text
    from backend.app.database import engine, init_db
    from backend.app.models import MandiPricesCache

    # Insert a dummy legacy verified_snapshot record
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO mandi_prices_cache (state, district, market, commodity, min_price, max_price, modal_price, arrival_date, source, dataset_id, fetched_at) "
            "VALUES ('TestState', 'TestDistrict', 'TestLegacy APMC', 'TestCrop', 1000, 1200, 1100, '2026-11-15', 'verified_snapshot', 'legacy_id', CURRENT_TIMESTAMP)"
        ))
        conn.commit()

    # Run init_db() migration
    init_db()

    with SessionLocal() as db:
        legacy_rec = db.query(MandiPricesCache).filter(MandiPricesCache.market == "TestLegacy APMC").first()
        assert legacy_rec is not None
        assert legacy_rec.source == "estimated_benchmark"
        assert legacy_rec.dataset_id is None

        # Clean up test record
        db.delete(legacy_rec)
        db.commit()


@pytest.mark.anyio
async def test_explicit_user_agent_and_accept_headers():
    """Verifies that fetch_live_agmarknet_records sends explicit User-Agent and Accept headers."""
    from backend.app.services.mandi_service import OGD_REQUEST_HEADERS, fetch_live_agmarknet_records

    assert OGD_REQUEST_HEADERS.get("User-Agent") == "KrishiSetu/1.0"
    assert OGD_REQUEST_HEADERS.get("Accept") == "application/json"

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {"total": 0, "records": []}
        mock_get.return_value = mock_resp

        with patch("httpx.AsyncClient.__init__", return_value=None) as mock_init:
            await fetch_live_agmarknet_records("Onion", state="Karnataka")
            # Verify headers were passed to AsyncClient initialization
            mock_init.assert_called_once()
            _, kwargs = mock_init.call_args
            assert kwargs.get("headers") == OGD_REQUEST_HEADERS
            assert kwargs.get("timeout") == 10.0


@pytest.mark.anyio
async def test_live_api_caching_and_fallback_resilience():
    """Verifies that live API records are ingested with source='live_api' and cached across subsequent calls."""
    from backend.app.services.mandi_service import get_mandi_candidates_with_prices
    from backend.app.models import MandiPricesCache

    with SessionLocal() as db:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "tomato").first()

        # Mock fetch_live_agmarknet_records returning a mock live quote for Kolar APMC
        mock_live_record = {
            "state": "Karnataka",
            "district": "Kolar",
            "market": "Kolar APMC",
            "commodity": "Tomato",
            "variety": "Hybrid",
            "min_price": "2800",
            "max_price": "3200",
            "modal_price": "3000",
            "arrival_date": "16/11/2026",
        }

        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", return_value=[mock_live_record]):
            candidates = await get_mandi_candidates_with_prices(13.1367, 78.1291, crop, db)

            kolar = next((c for c in candidates if c.market == "Kolar APMC"), None)
            assert kolar is not None
            assert kolar.source == "live_api"
            assert kolar.is_benchmark is False
            assert kolar.modal_price == 3000.0
            assert kolar.arrival_date == "16/11/2026"
            assert kolar.dataset_id == "9ef84268-d588-465a-a308-a864a43d0070"

            # Check DB has live_api cached entry
            db_kolar = db.query(MandiPricesCache).filter(
                MandiPricesCache.market == "Kolar APMC",
                MandiPricesCache.commodity == "Tomato",
                MandiPricesCache.source == "live_api",
            ).first()
            assert db_kolar is not None

            # Clean up live test record to maintain test isolation
            db.delete(db_kolar)
            db.commit()


def test_task4_benchmark_only_insufficient_data_status(client: TestClient):
    """When an unseeded crop (e.g. banana) has no verified quotes, system must return covered for geography and no_verified_price_data for price comparison."""
    payload = {
        "location_query": "Belagavi, Karnataka",
        "latitude": 15.8497,
        "longitude": 74.4977,
        "crop_id": "banana",
        "quantity_quintals": 30.0,
        "language": "en",
    }
    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", return_value=[]):
        response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Geographical coverage must be 'covered', price data sufficiency must be 'no_verified_price_data'
    assert data["coverage_status"] == "covered"
    assert data["price_comparison_status"] == "no_verified_price_data"
    assert "No authentic government AGMARKNET quotations" in data["price_comparison_notice"]

    # All candidate records must be flagged as benchmarks without dataset_id
    for m in data["mandi_comparison"]:
        assert m["is_benchmark"] is True
        assert m["data_source"] == "estimated_benchmark"
        assert m["dataset_id"] is None
        # Net gain must be 0 (no unverified gains claimed)
        assert m["net_gain_vs_local_total"] == 0.0

    # Advisory must not declare a benchmark mandi as a profit winner
    advisory = data["ai_advisory"]
    assert "insufficient verified price data" in advisory["headline"].lower()
    assert "verified data insufficient" in advisory["recommended_mandi"].lower()
    assert "cannot be used" in advisory["price_justification"].lower()


# ==============================================================================
# Verified Mandi Recommendation Refinement Tests
# ==============================================================================

from backend.app.services.arbitrage_engine import MandiArbitrageResult, determine_price_comparison_status


def test_determine_price_comparison_status_logic():
    """Unit tests for determine_price_comparison_status() across all 4 scenarios."""
    # 1. verified_comparison_available
    r1 = [
        MandiArbitrageResult(
            market="Local APMC", district="DistA", state="Karnataka", distance_km=0.0,
            modal_price=2000.0, transport_cost_per_qtl=0.0, spoilage_deduction_per_qtl=0.0,
            net_price_per_qtl=2000.0, net_gain_vs_local_total=0.0, is_local=True,
            arrival_date="16/11/2026", source="live_api", variety="Common", is_benchmark=False, dataset_id="uuid-1",
        ),
        MandiArbitrageResult(
            market="Distant APMC", district="DistB", state="Karnataka", distance_km=50.0,
            modal_price=2400.0, transport_cost_per_qtl=125.0, spoilage_deduction_per_qtl=40.0,
            net_price_per_qtl=2235.0, net_gain_vs_local_total=11750.0, is_local=False,
            arrival_date="16/11/2026", source="verified_snapshot", variety="Common", is_benchmark=False, dataset_id="uuid-2",
        ),
    ]
    assert determine_price_comparison_status(r1) == "verified_comparison_available"

    # 2. local_baseline_missing (alternative verified, local is benchmark)
    r2 = [
        MandiArbitrageResult(
            market="Local APMC", district="DistA", state="Karnataka", distance_km=0.0,
            modal_price=2000.0, transport_cost_per_qtl=0.0, spoilage_deduction_per_qtl=0.0,
            net_price_per_qtl=2000.0, net_gain_vs_local_total=0.0, is_local=True,
            arrival_date="2026-11-15", source="estimated_benchmark", variety="Common", is_benchmark=True, dataset_id=None,
        ),
        MandiArbitrageResult(
            market="Distant APMC", district="DistB", state="Karnataka", distance_km=50.0,
            modal_price=2400.0, transport_cost_per_qtl=125.0, spoilage_deduction_per_qtl=40.0,
            net_price_per_qtl=2235.0, net_gain_vs_local_total=0.0, is_local=False,
            arrival_date="16/11/2026", source="live_api", variety="Common", is_benchmark=False, dataset_id="uuid-2",
        ),
    ]
    assert determine_price_comparison_status(r2) == "local_baseline_missing"

    # 3. insufficient_alternative_quotes (local verified, alternative is benchmark)
    r3 = [
        MandiArbitrageResult(
            market="Local APMC", district="DistA", state="Maharashtra", distance_km=0.0,
            modal_price=2250.0, transport_cost_per_qtl=0.0, spoilage_deduction_per_qtl=0.0,
            net_price_per_qtl=2250.0, net_gain_vs_local_total=0.0, is_local=True,
            arrival_date="16/11/2026", source="verified_snapshot", variety="Common", is_benchmark=False, dataset_id="uuid-3",
        ),
        MandiArbitrageResult(
            market="Distant APMC", district="DistB", state="Maharashtra", distance_km=45.0,
            modal_price=2600.0, transport_cost_per_qtl=112.5, spoilage_deduction_per_qtl=20.0,
            net_price_per_qtl=2467.5, net_gain_vs_local_total=0.0, is_local=False,
            arrival_date="2026-11-15", source="estimated_benchmark", variety="Common", is_benchmark=True, dataset_id=None,
        ),
    ]
    assert determine_price_comparison_status(r3) == "insufficient_alternative_quotes"

    # 4. no_verified_price_data (both benchmark)
    r4 = [
        MandiArbitrageResult(
            market="Local APMC", district="DistA", state="Karnataka", distance_km=0.0,
            modal_price=1800.0, transport_cost_per_qtl=0.0, spoilage_deduction_per_qtl=0.0,
            net_price_per_qtl=1800.0, net_gain_vs_local_total=0.0, is_local=True,
            arrival_date="2026-11-15", source="estimated_benchmark", variety="Common", is_benchmark=True, dataset_id=None,
        ),
        MandiArbitrageResult(
            market="Distant APMC", district="DistB", state="Karnataka", distance_km=30.0,
            modal_price=1850.0, transport_cost_per_qtl=75.0, spoilage_deduction_per_qtl=10.0,
            net_price_per_qtl=1765.0, net_gain_vs_local_total=0.0, is_local=False,
            arrival_date="2026-11-15", source="estimated_benchmark", variety="Common", is_benchmark=True, dataset_id=None,
        ),
    ]
    assert determine_price_comparison_status(r4) == "no_verified_price_data"


def test_preset_belagavi_onion_verified_comparison(client: TestClient, canned_belagavi_onion_records):
    """Belagavi Onion: verified local APMC vs Kolhapur -> verified_comparison_available, local best."""
    payload = {
        "location_query": "Belagavi, Karnataka",
        "latitude": 15.8497,
        "longitude": 74.4977,
        "crop_id": "onion",
        "quantity_quintals": 50.0,
        "language": "en",
    }
    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", return_value=canned_belagavi_onion_records):
        response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["coverage_status"] == "covered"
    assert data["price_comparison_status"] == "verified_comparison_available"
    # Local market is top recommendation because ₹4500 local beats ₹3500 Kolhapur
    top_mandi = data["mandi_comparison"][0]
    assert top_mandi["market"] == "Belagavi APMC"
    assert top_mandi["is_local"] is True
    assert top_mandi["net_gain_vs_local_total"] == 0.0
    assert "Belagavi APMC" in data["ai_advisory"]["recommended_mandi"]


def test_preset_nashik_onion_local_baseline_missing(client: TestClient, canned_nashik_onion_records):
    """Nashik Onion: local Nashik APMC is unverified benchmark, while alternative
    mandis (Pimpalgaon / Lasalgaon) have verified quotes -> local_baseline_missing."""
    payload = {
        "location_query": "Nashik, Maharashtra",
        "latitude": 19.9975,
        "longitude": 73.7898,
        "crop_id": "onion",
        "quantity_quintals": 60.0,
        "language": "en",
    }
    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", return_value=canned_nashik_onion_records):
        response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["coverage_status"] == "covered"
    assert data["price_comparison_status"] == "local_baseline_missing"

    # Pimpalgaon or Lasalgaon are verified but must NOT claim additional gain over local
    for m in data["mandi_comparison"]:
        assert m["net_gain_vs_local_total"] == 0.0

    # Advisory must direct farmer to check local spot rate before travelling
    advisory = data["ai_advisory"]
    assert "local baseline price missing" in advisory["headline"].lower()
    assert "verify local spot" in advisory["recommended_mandi"].lower()
    assert "spot auction rate" in advisory["price_justification"].lower()


def test_preset_haveri_maize_no_verified_price_data(client: TestClient, canned_haveri_maize_records):
    """Haveri Maize: all nearby candidates are estimated benchmarks -> no_verified_price_data."""
    payload = {
        "location_query": "Haveri, Karnataka",
        "latitude": 14.7954,
        "longitude": 75.3992,
        "crop_id": "maize",
        "quantity_quintals": 80.0,
        "language": "en",
    }
    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", return_value=canned_haveri_maize_records):
        response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["coverage_status"] == "covered"
    assert data["price_comparison_status"] == "no_verified_price_data"
    for m in data["mandi_comparison"]:
        assert m["is_benchmark"] is True
        assert m["net_gain_vs_local_total"] == 0.0

    advisory = data["ai_advisory"]
    assert "insufficient verified price data" in advisory["headline"].lower()
    assert "verified data insufficient" in advisory["recommended_mandi"].lower()
    assert "cannot be used" in advisory["price_justification"].lower()


def test_preset_pune_potato_insufficient_alternative_quotes(client: TestClient, canned_pune_potato_records):
    """Pune Potato: Pune APMC has verified quotation (₹2,250) but alternative candidates are benchmarks.
    Must classify as insufficient_alternative_quotes and recommend local sale."""
    payload = {
        "location_query": "Pune, Maharashtra",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "crop_id": "potato",
        "quantity_quintals": 45.0,
        "language": "en",
    }
    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", return_value=canned_pune_potato_records):
        response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["coverage_status"] == "covered"
    assert data["price_comparison_status"] == "insufficient_alternative_quotes"

    top_mandi = data["mandi_comparison"][0]
    assert top_mandi["market"] == "Pune APMC (Gultekdi)"
    assert top_mandi["is_local"] is True
    assert top_mandi["is_benchmark"] is False
    assert top_mandi["net_gain_vs_local_total"] == 0.0

    advisory = data["ai_advisory"]
    assert "verified local quotation available" in advisory["headline"].lower()
    assert "local sale recommended" in advisory["recommended_mandi"].lower()
    assert "transporting produce to distant markets based on unverified estimates" in advisory["price_justification"].lower()


def test_preset_kolar_tomato_eligibility(client: TestClient, canned_kolar_tomato_records):
    """Kolar Tomato: Evaluates recommendation eligibility based on live vs benchmark availability.
    When live API returns verified local and alternative quotes, verified_comparison_available."""
    payload = {
        "location_query": "Kolar, Karnataka",
        "latitude": 13.1367,
        "longitude": 78.1292,
        "crop_id": "tomato",
        "quantity_quintals": 40.0,
        "language": "en",
    }
    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", return_value=canned_kolar_tomato_records):
        response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["coverage_status"] == "covered"
    assert data["price_comparison_status"] == "verified_comparison_available"
    assert len(data["mandi_comparison"]) >= 2
    for m in data["mandi_comparison"]:
        if m["market"] in ["Kolar APMC", "Malur APMC"]:
            assert m["is_benchmark"] is False


# ==============================================================================
# Gemini Model Connectivity & Fallback Regression Tests
# ==============================================================================

import json
from unittest.mock import MagicMock, patch
from backend.app.services.ai_service import (
    AIAdvisory,
    GEMINI_PRIMARY_MODEL,
    build_template_advisory,
    generate_ai_advisory,
    generate_chat_reply,
)


@pytest.mark.anyio
async def test_gemini_model_selection_and_successful_structured_response():
    """Verifies that gemini-3.5-flash-lite is selected (never gemini-2.5-flash) and produces a valid AIAdvisory."""
    assert GEMINI_PRIMARY_MODEL == "gemini-3.5-flash-lite"
    assert GEMINI_PRIMARY_MODEL != "gemini-2.5-flash"

    crop_info = {"display_name_en": "Onion", "display_name_kn": "ಈರುಳ್ಳಿ"}
    weather_info = {"risk_level": "SAFE_WINDOW", "rain_72h_mm": 0.0, "max_rain_prob_pct": 5.0}
    mandi_comp = [{
        "market": "Belagavi APMC", "is_local": True, "modal_price": 4500.0,
        "net_price_per_qtl": 4500.0, "net_gain_vs_local_total": 0.0, "is_benchmark": False
    }]

    mock_gemini_json = json.dumps({
        "headline": "Sell Onion locally at Belagavi APMC for top realized return",
        "harvest_action": "Dry conditions forecast over 72h. Complete harvest immediately.",
        "recommended_mandi": "Belagavi APMC",
        "price_justification": "Local market provides highest net realization of ₹4,500/qtl.",
        "protection_tips": ["Store in ventilated jute gunny bags.", "Protect cargo bed with tarpaulin."],
        "language": "en"
    })

    mock_response = MagicMock()
    mock_response.text = mock_gemini_json

    with patch("backend.app.services.ai_service._is_valid_api_key", return_value=True):
        with patch("google.genai.Client") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.models.generate_content.return_value = mock_response

            advisory = await generate_ai_advisory(
                crop_info=crop_info,
                weather_info=weather_info,
                mandi_comparison=mandi_comp,
                quantity=50.0,
                language="en",
                price_comparison_status="verified_comparison_available",
            )

            # 1. Verify model selection is strictly gemini-3.5-flash-lite
            mock_instance.models.generate_content.assert_called_once()
            call_kwargs = mock_instance.models.generate_content.call_args[1]
            assert call_kwargs["model"] == "gemini-3.5-flash-lite"
            assert call_kwargs["model"] != "gemini-2.5-flash"

            # 2. Verify structured response validation and contract
            assert isinstance(advisory, AIAdvisory)
            assert advisory.headline == "Sell Onion locally at Belagavi APMC for top realized return"
            assert advisory.recommended_mandi == "Belagavi APMC"
            assert len(advisory.protection_tips) == 2
            assert advisory.language == "en"

            # 3. Verify grounding rules present in system instruction
            sys_inst = call_kwargs["config"].system_instruction
            assert "GROUNDING RULES" in sys_inst
            assert "NEVER invent, modify, or hallucinate financial numbers" in sys_inst


@pytest.mark.anyio
async def test_gemini_auth_failure_triggers_deterministic_fallback():
    """Verifies that 401 UNAUTHENTICATED triggers deterministic template fallback safely."""
    crop_info = {"display_name_en": "Tomato", "display_name_kn": "ಟೊಮೆಟೊ"}
    weather_info = {"risk_level": "HIGH_SPOILAGE_ALERT", "rain_72h_mm": 25.0, "max_rain_prob_pct": 80.0}
    mandi_comp = [{
        "market": "Kolar APMC", "is_local": True, "modal_price": 3000.0,
        "net_price_per_qtl": 3000.0, "net_gain_vs_local_total": 0.0, "is_benchmark": False
    }]

    with patch("backend.app.services.ai_service._is_valid_api_key", return_value=True):
        with patch("google.genai.Client") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.models.generate_content.side_effect = Exception("401 UNAUTHENTICATED: ACCESS_TOKEN_TYPE_UNSUPPORTED")

            advisory = await generate_ai_advisory(
                crop_info=crop_info,
                weather_info=weather_info,
                mandi_comparison=mandi_comp,
                quantity=40.0,
                language="kn",
                price_comparison_status="verified_comparison_available",
            )

            assert isinstance(advisory, AIAdvisory)
            assert advisory.language == "kn"
            assert "Kolar APMC" in advisory.recommended_mandi
            assert len(advisory.protection_tips) >= 2


@pytest.mark.anyio
async def test_gemini_timeout_triggers_deterministic_fallback():
    """Verifies that network timeout triggers deterministic template fallback safely."""
    crop_info = {"display_name_en": "Potato", "display_name_hi": "आलू"}
    weather_info = {"risk_level": "SAFE_WINDOW", "rain_72h_mm": 0.0, "max_rain_prob_pct": 0.0}
    mandi_comp = [{
        "market": "Pune APMC", "is_local": True, "modal_price": 2250.0,
        "net_price_per_qtl": 2250.0, "net_gain_vs_local_total": 0.0, "is_benchmark": False
    }]

    with patch("backend.app.services.ai_service._is_valid_api_key", return_value=True):
        with patch("google.genai.Client") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.models.generate_content.side_effect = TimeoutError("Deadline exceeded connecting to Gemini API")

            advisory = await generate_ai_advisory(
                crop_info=crop_info,
                weather_info=weather_info,
                mandi_comparison=mandi_comp,
                quantity=30.0,
                language="hi",
                price_comparison_status="insufficient_alternative_quotes",
            )

            assert isinstance(advisory, AIAdvisory)
            assert advisory.language == "hi"
            assert "Pune APMC" in advisory.recommended_mandi


@pytest.mark.anyio
async def test_gemini_503_and_504_trigger_deterministic_fallback():
    """Verifies that 503 UNAVAILABLE and 504 DEADLINE_EXCEEDED gracefully trigger template fallback."""
    crop_info = {"display_name_en": "Tomato", "display_name_en": "Tomato"}
    weather_info = {"risk_level": "SAFE_WINDOW", "rain_72h_mm": 0.0, "max_rain_prob_pct": 0.0}
    mandi_comp = [{
        "market": "Kolar Mandi", "is_local": True, "modal_price": 2500.0,
        "net_price_per_qtl": 2500.0, "net_gain_vs_local_total": 0.0, "is_benchmark": False
    }]

    with patch("backend.app.services.ai_service._is_valid_api_key", return_value=True):
        with patch("google.genai.Client") as MockClient:
            mock_instance = MockClient.return_value

            # Test 503
            mock_instance.models.generate_content.side_effect = Exception("503 UNAVAILABLE: Model experiencing high demand")
            adv_503 = await generate_ai_advisory(
                crop_info=crop_info,
                weather_info=weather_info,
                mandi_comparison=mandi_comp,
                quantity=10.0,
                language="en",
                price_comparison_status="verified_comparison_available",
            )
            assert isinstance(adv_503, AIAdvisory)
            assert "Kolar Mandi" in adv_503.recommended_mandi

            # Test 504
            mock_instance.models.generate_content.side_effect = Exception("504 DEADLINE_EXCEEDED: Deadline expired")
            adv_504 = await generate_ai_advisory(
                crop_info=crop_info,
                weather_info=weather_info,
                mandi_comparison=mandi_comp,
                quantity=10.0,
                language="en",
                price_comparison_status="verified_comparison_available",
            )
            assert isinstance(adv_504, AIAdvisory)
            assert "Kolar Mandi" in adv_504.recommended_mandi


@pytest.mark.anyio
async def test_gemini_malformed_json_triggers_deterministic_fallback():
    """Verifies that invalid or non-schema JSON output triggers deterministic template fallback."""
    crop_info = {"display_name_en": "Tomato"}
    weather_info = {"risk_level": "SAFE_WINDOW", "rain_72h_mm": 0.0, "max_rain_prob_pct": 0.0}
    mandi_comp = [{
        "market": "Kolar Mandi", "is_local": True, "modal_price": 2500.0,
        "net_price_per_qtl": 2500.0, "net_gain_vs_local_total": 0.0, "is_benchmark": False
    }]

    mock_resp = MagicMock()
    mock_resp.text = "This is not JSON at all! Just raw plain text."

    with patch("backend.app.services.ai_service._is_valid_api_key", return_value=True):
        with patch("google.genai.Client") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.models.generate_content.return_value = mock_resp

            adv = await generate_ai_advisory(
                crop_info=crop_info,
                weather_info=weather_info,
                mandi_comparison=mandi_comp,
                quantity=10.0,
                language="en",
                price_comparison_status="verified_comparison_available",
            )
            assert isinstance(adv, AIAdvisory)
            assert "Kolar Mandi" in adv.recommended_mandi


@pytest.mark.anyio
async def test_chat_reply_uses_gemini_35_flash_lite_and_falls_back():
    """Verifies that generate_chat_reply uses gemini-3.5-flash-lite and falls back on error."""
    context = {
        "mandi_comparison": [{"market": "Kolar APMC", "net_price_per_qtl": 2600.0, "net_gain_vs_local_total": 2500.0}],
        "weather": {"risk_level": "SAFE_WINDOW", "rain_72h_mm": 0.0},
    }

    # 1. Success path
    mock_resp = MagicMock()
    mock_resp.text = "Sell at Kolar APMC for ₹2,500 additional profit."

    with patch("backend.app.services.ai_service._is_valid_api_key", return_value=True):
        with patch("google.genai.Client") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.models.generate_content.return_value = mock_resp

            reply = await generate_chat_reply(context, "Which market should I choose?", "en")
            assert reply == "Sell at Kolar APMC for ₹2,500 additional profit."
            call_kwargs = mock_instance.models.generate_content.call_args[1]
            assert call_kwargs["model"] == "gemini-3.5-flash-lite"
            assert call_kwargs["model"] != "gemini-2.5-flash"

            # 2. Failure path -> template fallback
            mock_instance.models.generate_content.side_effect = Exception("503 Server Error")
            fallback_reply = await generate_chat_reply(context, "What is the price?", "en")
            assert "₹2,600/qtl" in fallback_reply
            assert "Kolar APMC" in fallback_reply


@pytest.mark.anyio
async def test_gemini_rate_limit_429_triggers_deterministic_fallback():
    """Verifies that 429 RESOURCE_EXHAUSTED triggers deterministic template fallback."""
    crop_info = {"display_name_en": "Onion", "display_name_mr": "कांदा"}
    weather_info = {"risk_level": "HARVEST_WITHIN_48H", "rain_72h_mm": 8.0, "max_rain_prob_pct": 50.0}
    mandi_comp = [{
        "market": "Nashik APMC", "is_local": True, "modal_price": 2300.0,
        "net_price_per_qtl": 2300.0, "net_gain_vs_local_total": 0.0, "is_benchmark": True
    }]

    with patch("backend.app.services.ai_service._is_valid_api_key", return_value=True):
        with patch("google.genai.Client") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Rate limit reached")

            advisory = await generate_ai_advisory(
                crop_info=crop_info,
                weather_info=weather_info,
                mandi_comparison=mandi_comp,
                quantity=60.0,
                language="mr",
                price_comparison_status="local_baseline_missing",
            )

            assert isinstance(advisory, AIAdvisory)
            assert advisory.language == "mr"
            assert "Nashik APMC" in advisory.recommended_mandi


def test_deterministic_template_multilingual_structure():
    """Verifies all required fields and structural validity across EN, KN, HI, MR in deterministic engine."""
    crop_info = {
        "display_name_en": "Onion",
        "display_name_kn": "ಈರುಳ್ಳಿ",
        "display_name_hi": "प्याज",
        "display_name_mr": "कांदा",
    }
    weather_info = {"risk_level": "SAFE_WINDOW", "rain_72h_mm": 1.0, "max_rain_prob_pct": 10.0}
    mandi_comp = [{
        "market": "Belagavi APMC", "is_local": True, "modal_price": 4500.0,
        "net_price_per_qtl": 4500.0, "net_gain_vs_local_total": 0.0, "is_benchmark": False
    }]

    for lang in ["en", "kn", "hi", "mr"]:
        advisory = build_template_advisory(
            crop_info=crop_info,
            weather_info=weather_info,
            mandi_comparison=mandi_comp,
            quantity=50.0,
            language=lang,
            price_comparison_status="verified_comparison_available",
        )
        assert isinstance(advisory, AIAdvisory)
        assert advisory.language == lang
        assert len(advisory.headline) > 5
        assert len(advisory.harvest_action) > 5
        assert len(advisory.recommended_mandi) > 3
        assert len(advisory.price_justification) > 10
        assert len(advisory.protection_tips) >= 2


