"""Unit and Integration Tests for KrishiSetu Phase 1.

Covers:
- Deterministic Arbitrage Engine (0 km baseline, negative gain, perishability math, ranking)
- Weather Risk Classification Engine (HIGH_SPOILAGE_ALERT, HARVEST_WITHIN_48H, SAFE_WINDOW)
- Database Seeding Idempotency
- FastAPI Endpoints (/api/health and /api/presets)
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.database import Base, SessionLocal, engine, init_db
from backend.app.main import app
from backend.app.models import CropProfile, MandiPricesCache
from backend.app.seed import (
    CROP_PROFILES_DATA,
    DEMO_PRESETS,
    MANDI_SNAPSHOT_DATA,
    seed_all,
)
from backend.app.services.arbitrage_engine import (
    MandiCandidate,
    calculate_mandi_arbitrage,
    calculate_road_distance_km,
    get_spoilage_rate_per_km,
    haversine_distance_km,
)
from backend.app.services.weather_risk import classify_weather_risk


# ==============================================================================
# Arbitrage Engine Tests
# ==============================================================================

def test_haversine_and_road_adjustment():
    """Verifies Haversine calculation and 1.25 road winding multiplier."""
    # Belagavi to Hubli (~86.4 km straight line)
    belagavi = (15.8497, 74.4977)
    hubli = (15.3647, 75.1240)

    straight_dist = haversine_distance_km(belagavi[0], belagavi[1], hubli[0], hubli[1])
    assert 80.0 < straight_dist < 92.0

    road_dist = calculate_road_distance_km(belagavi[0], belagavi[1], hubli[0], hubli[1])
    expected_road = round(straight_dist * 1.25, 2)
    assert abs(road_dist - expected_road) < 0.01

    # Exact zero distance for identical coordinates
    assert haversine_distance_km(15.85, 74.50, 15.85, 74.50) == 0.0
    assert calculate_road_distance_km(15.85, 74.50, 15.85, 74.50) == 0.0


def test_arbitrage_local_zero_km_baseline():
    """At 0 km distance, transport and spoilage costs are 0 and net gain is 0."""
    origin_lat, origin_lon = 15.8500, 74.5000
    quantity = 30.0

    cand = MandiCandidate(
        market="Belagavi APMC",
        district="Belagavi",
        state="Karnataka",
        latitude=15.8500,
        longitude=74.5000,
        modal_price=2050.0,
    )

    results = calculate_mandi_arbitrage(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        quantity_quintals=quantity,
        mandis=[cand],
        perishability_tier="medium",
        base_transport_per_km_qtl=2.50,
    )

    assert len(results) == 1
    res = results[0]
    assert res.market == "Belagavi APMC"
    assert res.distance_km == 0.0
    assert res.transport_cost_per_qtl == 0.0
    assert res.spoilage_deduction_per_qtl == 0.0
    assert res.net_price_per_qtl == 2050.0
    assert res.net_gain_vs_local_total == 0.0
    assert res.is_local is True


def test_arbitrage_negative_net_gain_when_costs_exceed_spread():
    """Verifies that when transport + spoilage exceeds modal price spread, net gain is negative."""
    origin_lat, origin_lon = 15.0000, 75.0000
    quantity = 40.0

    # Local mandi: 2000 ₹/qtl at 0 km
    local_mandi = MandiCandidate(
        market="Local Mandi",
        district="LocalDist",
        state="Karnataka",
        latitude=15.0000,
        longitude=75.0000,
        modal_price=2000.0,
    )

    # Distant mandi: 2150 ₹/qtl (+150 sticker price spread), but ~100 km away (road ~125 km)
    # Approx 1 degree latitude is ~111 km -> road dist ~138 km
    distant_mandi = MandiCandidate(
        market="Far Mandi",
        district="FarDist",
        state="Karnataka",
        latitude=16.0000,
        longitude=75.0000,
        modal_price=2150.0,
    )

    results = calculate_mandi_arbitrage(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        quantity_quintals=quantity,
        mandis=[local_mandi, distant_mandi],
        perishability_tier="high",  # 0.0005 per km
        base_transport_per_km_qtl=2.50,
    )

    # Distant mandi transport cost: ~138.89 km * 2.50 = ~347.22 ₹/qtl
    # Spoilage deduction: 2150 * (0.0005 * 138.89) = ~149.31 ₹/qtl
    # Total deduction: ~496.53 ₹/qtl
    # Net price: 2150 - 496.53 = ~1653.47 ₹/qtl (much lower than local 2000)
    far_res = next(r for r in results if r.market == "Far Mandi")
    local_res = next(r for r in results if r.market == "Local Mandi")

    assert far_res.net_price_per_qtl < local_res.net_price_per_qtl
    assert far_res.net_gain_vs_local_total < 0.0

    # Results must be sorted descending by net_price_per_qtl (Local should be ranked #1)
    assert results[0].market == "Local Mandi"
    assert results[1].market == "Far Mandi"


def test_arbitrage_perishability_tier_spoilage_math():
    """Compares high (0.0005), medium (0.0002), and low (0.00005) perishability deductions."""
    origin_lat, origin_lon = 15.0, 75.0
    distant_lat, distant_lon = 15.8, 75.0  # ~88.9 km straight, ~111.19 km road
    modal_price = 3000.0

    mandi = MandiCandidate(
        market="Test APMC",
        district="TestDist",
        state="Karnataka",
        latitude=distant_lat,
        longitude=distant_lon,
        modal_price=modal_price,
    )

    high_res = calculate_mandi_arbitrage(
        origin_lat, origin_lon, 10.0, [mandi], perishability_tier="high"
    )[0]
    med_res = calculate_mandi_arbitrage(
        origin_lat, origin_lon, 10.0, [mandi], perishability_tier="medium"
    )[0]
    low_res = calculate_mandi_arbitrage(
        origin_lat, origin_lon, 10.0, [mandi], perishability_tier="low"
    )[0]

    # Spoilage rate high (0.0005) is exactly 10x low (0.00005)
    assert high_res.spoilage_deduction_per_qtl > med_res.spoilage_deduction_per_qtl > low_res.spoilage_deduction_per_qtl
    ratio = high_res.spoilage_deduction_per_qtl / low_res.spoilage_deduction_per_qtl
    assert round(ratio) == 10

    # Net realizable price ordering
    assert low_res.net_price_per_qtl > med_res.net_price_per_qtl > high_res.net_price_per_qtl


# ==============================================================================
# Weather Risk Classification Tests
# ==============================================================================

def test_weather_risk_high_spoilage_alert_on_rainfall():
    """Rainfall >= 15 mm triggers HIGH_SPOILAGE_ALERT regardless of crop."""
    # Exactly 15.0 mm threshold
    assessment = classify_weather_risk(
        rain_72h_mm=15.0,
        max_rain_prob_pct=30.0,
        soil_moisture=0.20,
        perishability_tier="low",
    )
    assert assessment.risk_level == "HIGH_SPOILAGE_ALERT"
    assert "15.0 mm" in assessment.description

    # Heavy deluge 35.0 mm
    assessment2 = classify_weather_risk(
        rain_72h_mm=35.0,
        max_rain_prob_pct=90.0,
        soil_moisture=0.40,
        perishability_tier="high",
    )
    assert assessment2.risk_level == "HIGH_SPOILAGE_ALERT"


def test_weather_risk_high_spoilage_alert_on_probability_and_perishability():
    """Max rain prob >= 70% for high/medium perishability triggers HIGH_SPOILAGE_ALERT."""
    # High perishability with 75% prob but little rain yet (e.g. tomatoes)
    assessment_high = classify_weather_risk(
        rain_72h_mm=3.0,
        max_rain_prob_pct=75.0,
        soil_moisture=0.25,
        perishability_tier="high",
    )
    assert assessment_high.risk_level == "HIGH_SPOILAGE_ALERT"

    # Medium perishability with 70% prob (e.g. onions)
    assessment_med = classify_weather_risk(
        rain_72h_mm=2.5,
        max_rain_prob_pct=70.0,
        soil_moisture=0.25,
        perishability_tier="medium",
    )
    assert assessment_med.risk_level == "HIGH_SPOILAGE_ALERT"

    # Low perishability with 75% prob (e.g. maize) does NOT trigger high alert if rain < 5 mm
    assessment_low = classify_weather_risk(
        rain_72h_mm=3.0,
        max_rain_prob_pct=75.0,
        soil_moisture=0.25,
        perishability_tier="low",
    )
    assert assessment_low.risk_level == "SAFE_WINDOW"


def test_weather_risk_harvest_within_48h():
    """Moderate rain (5–15 mm) OR saturated soil (>0.35) triggers HARVEST_WITHIN_48H."""
    # Lower boundary 5.0 mm
    res1 = classify_weather_risk(
        rain_72h_mm=5.0,
        max_rain_prob_pct=50.0,
        soil_moisture=0.20,
        perishability_tier="medium",
    )
    assert res1.risk_level == "HARVEST_WITHIN_48H"

    # Upper boundary 14.9 mm
    res2 = classify_weather_risk(
        rain_72h_mm=14.9,
        max_rain_prob_pct=60.0,
        soil_moisture=0.30,
        perishability_tier="medium",
    )
    assert res2.risk_level == "HARVEST_WITHIN_48H"

    # Saturated soil (> 0.35) even with low rain
    res3 = classify_weather_risk(
        rain_72h_mm=2.0,
        max_rain_prob_pct=40.0,
        soil_moisture=0.38,
        perishability_tier="high",
    )
    assert res3.risk_level == "HARVEST_WITHIN_48H"


def test_weather_risk_safe_window():
    """Dry weather (< 5 mm rain, prob < 70%, soil <= 0.35) yields SAFE_WINDOW."""
    res = classify_weather_risk(
        rain_72h_mm=1.2,
        max_rain_prob_pct=25.0,
        soil_moisture=0.22,
        perishability_tier="medium",
    )
    assert res.risk_level == "SAFE_WINDOW"
    assert "Favorable Weather" in res.headline


# ==============================================================================
# Database Seeding & Idempotency Tests
# ==============================================================================

def test_database_seeding_idempotency():
    """Verifies that seed_all can be called multiple times without duplicate records."""
    init_db()
    with SessionLocal() as db:
        # First seeding run
        seed_all(db)
        crop_count_1 = db.query(CropProfile).count()
        snapshot_count_1 = db.query(MandiPricesCache).count()

        assert crop_count_1 == 10
        assert snapshot_count_1 >= len(MANDI_SNAPSHOT_DATA)

        # Second seeding run (idempotency check)
        second_run = seed_all(db)
        crop_count_2 = db.query(CropProfile).count()
        snapshot_count_2 = db.query(MandiPricesCache).count()

        assert crop_count_2 == crop_count_1
        assert snapshot_count_2 == snapshot_count_1
        assert second_run["crops_seeded"] == 0
        assert second_run["snapshots_seeded"] == 0


# ==============================================================================
# API Endpoints Integration Tests (TestClient)
# ==============================================================================

@pytest.fixture(scope="module")
def client():
    """Initializes FastAPI test client and ensures database is seeded."""
    init_db()
    with SessionLocal() as db:
        seed_all(db)
    with TestClient(app) as test_client:
        yield test_client


def test_api_health_endpoint(client: TestClient):
    """GET /api/health must return HTTP 200 with ok status and db connected."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"
    assert "timestamp" in data


def test_api_presets_endpoint(client: TestClient):
    """GET /api/presets must return HTTP 200 with presets, crops, and languages."""
    response = client.get("/api/presets")
    assert response.status_code == 200
    data = response.json()

    # Presets validation
    assert "presets" in data
    assert len(data["presets"]) == 5
    preset_ids = [p["id"] for p in data["presets"]]
    assert "belagavi-onion" in preset_ids
    assert "kolar-tomato" in preset_ids
    assert "nashik-onion" in preset_ids
    assert "haveri-maize" in preset_ids
    assert "pune-potato" in preset_ids

    # Crops validation
    assert "crops" in data
    assert len(data["crops"]) == 10
    crop_ids = [c["crop_id"] for c in data["crops"]]
    for expected_crop in ["onion", "tomato", "potato", "green_chilli", "soybean", "maize", "turmeric", "cotton", "paddy", "banana"]:
        assert expected_crop in crop_ids

    # Languages validation
    assert "languages" in data
    assert len(data["languages"]) == 4
    lang_codes = [l["code"] for l in data["languages"]]
    assert set(lang_codes) == {"en", "kn", "hi", "mr"}
