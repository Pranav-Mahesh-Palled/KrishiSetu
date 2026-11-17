"""Focused tests for Data Freshness Metadata, Response Contracts, and Chronological Ordering (Phase A).

Validates:
1. DD/MM/YYYY versus YYYY-MM-DD chronological ordering.
2. Cross-month and cross-year ordering in DD/MM/YYYY format.
3. Same trading date with different fetched_at timestamps (tie-breaker).
4. Missing arrival_date handling.
5. Invalid arrival_date handling.
6. Latest quotation selection across mixed formats.
7. Stale and fresh quotations in one analysis response.
8. Aggregate freshness never overstating the freshness of relevant quotations.
9. Estimated benchmark provenance, null timestamps, and zero-gain rules.
10. Cached weather freshness metadata.
11. Stale weather fallback metadata.
12. Synthetic weather fallback metadata.
13. Missing timestamps and nullable field safety.
14. Aggregate metadata consistency in /api/analyze.
15. Backward compatibility of all existing API contracts.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock
import pytest
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models import CropProfile, MandiPricesCache, WeatherCache
from backend.app.services.mandi_service import (
    get_fallback_snapshot_price,
    get_cached_or_benchmark_price,
    get_mandi_candidates_with_prices,
    parse_arrival_date,
    select_latest_mandi_record,
)
from backend.app.services.weather_service import get_weather_forecast


client = TestClient(app)


# ==============================================================================
# 1. Date Parsing & Chronological Ordering Unit Tests
# ==============================================================================

def test_parse_arrival_date_various_formats():
    """Verifies that DD/MM/YYYY, YYYY-MM-DD, and variants parse correctly to date objects."""
    assert parse_arrival_date("16/11/2026") == date(2026, 11, 16)
    assert parse_arrival_date("2026-11-15") == date(2026, 11, 15)
    assert parse_arrival_date("01/03/2026") == date(2026, 3, 1)
    assert parse_arrival_date("28/02/2026") == date(2026, 2, 28)
    assert parse_arrival_date("05-12-2026") == date(2026, 12, 5)
    assert parse_arrival_date("2026/10/20") == date(2026, 10, 20)
    assert parse_arrival_date(None) is None
    assert parse_arrival_date("") is None
    assert parse_arrival_date("   ") is None
    assert parse_arrival_date("invalid_date_string") is None


def test_dd_mm_yyyy_vs_yyyy_mm_dd_chronological_ordering():
    """Confirms 16/11/2026 beats 2026-11-15 chronologically, defying string sort order ('2' > '1')."""
    with SessionLocal() as db:
        test_market = "APMC Chrono Test 1"
        test_commodity = "ChronoCrop1"

        # Record A: 2026-11-15 (starts with '2', older date)
        rec_a = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market=test_market,
            commodity=test_commodity,
            variety="Standard",
            min_price=1000.0,
            max_price=1200.0,
            modal_price=1100.0,
            arrival_date="2026-11-15",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        # Record B: 16/11/2026 (starts with '1', newer date: Nov 16 > Nov 15)
        rec_b = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market=test_market,
            commodity=test_commodity,
            variety="Standard",
            min_price=2000.0,
            max_price=2400.0,
            modal_price=2200.0,
            arrival_date="16/11/2026",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        db.add(rec_a)
        db.add(rec_b)
        db.commit()

        selected = get_fallback_snapshot_price(test_market, test_commodity, db)
        assert selected is not None
        # Must select rec_b (16/11/2026) because Nov 16 is after Nov 15
        assert selected.arrival_date == "16/11/2026"
        assert selected.modal_price == 2200.0


def test_cross_month_and_cross_year_ordering_in_dd_mm_yyyy():
    """Confirms chronological ordering across month and year boundaries in DD/MM/YYYY format."""
    with SessionLocal() as db:
        test_market = "APMC Cross Date Test"
        test_commodity = "CrossDateCrop"

        # Case A: Cross-month: 28/02/2026 vs 01/03/2026 (string '28' > '01')
        rec_feb = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market=test_market,
            commodity=test_commodity,
            variety="Standard",
            min_price=1000.0,
            max_price=1200.0,
            modal_price=1100.0,
            arrival_date="28/02/2026",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        rec_mar = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market=test_market,
            commodity=test_commodity,
            variety="Standard",
            min_price=2000.0,
            max_price=2400.0,
            modal_price=2200.0,
            arrival_date="01/03/2026",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=6),
        )
        db.add(rec_feb)
        db.add(rec_mar)
        db.commit()

        selected = get_fallback_snapshot_price(test_market, test_commodity, db)
        assert selected is not None
        assert selected.arrival_date == "01/03/2026"
        assert selected.modal_price == 2200.0

        # Case B: Cross-year: 31/12/2026 vs 02/01/2027 (string '31' > '02')
        rec_2026 = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market=test_market,
            commodity=test_commodity,
            variety="Standard",
            min_price=3000.0,
            max_price=3400.0,
            modal_price=3200.0,
            arrival_date="31/12/2026",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        rec_2027 = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market=test_market,
            commodity=test_commodity,
            variety="Standard",
            min_price=4000.0,
            max_price=4400.0,
            modal_price=4200.0,
            arrival_date="02/01/2027",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        db.add(rec_2026)
        db.add(rec_2027)
        db.commit()

        selected_yr = get_fallback_snapshot_price(test_market, test_commodity, db)
        assert selected_yr is not None
        assert selected_yr.arrival_date == "02/01/2027"
        assert selected_yr.modal_price == 4200.0


def test_selection_same_arrival_date_different_fetched_at():
    """Prioritizes latest fetched_at timestamp when multiple records share the same trading date."""
    with SessionLocal() as db:
        test_market = "APMC Tiebreaker Test"
        test_commodity = "TiebreakerCrop"
        now = datetime.now(timezone.utc)

        # Record 1: Fetched 6 hours ago
        rec1 = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market=test_market,
            commodity=test_commodity,
            variety="Standard",
            min_price=1500.0,
            max_price=1700.0,
            modal_price=1600.0,
            arrival_date="16/11/2026",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=now - timedelta(hours=6),
        )
        # Record 2: Fetched 30 minutes ago (more recent revision for same trading day)
        rec2 = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market=test_market,
            commodity=test_commodity,
            variety="Standard",
            min_price=1700.0,
            max_price=1900.0,
            modal_price=1800.0,
            arrival_date="16/11/2026",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=now - timedelta(minutes=30),
        )
        db.add(rec1)
        db.add(rec2)
        db.commit()

        selected = get_fallback_snapshot_price(test_market, test_commodity, db)
        assert selected is not None
        assert selected.arrival_date == "16/11/2026"
        assert selected.modal_price == 1800.0


def test_timezone_safe_sorting_none_and_aware():
    """Verifies select_latest_mandi_record sorts safely when one record has fetched_at=None."""
    now = datetime.now(timezone.utc)
    r1 = MandiPricesCache(
        id=1, market="M", commodity="C", state="S", district="D",
        min_price=1, max_price=2, modal_price=1.5,
        arrival_date="2026-11-16", source="live_api", fetched_at=None,
    )
    r2 = MandiPricesCache(
        id=2, market="M", commodity="C", state="S", district="D",
        min_price=1, max_price=2, modal_price=2.0,
        arrival_date="2026-11-16", source="live_api", fetched_at=now,
    )
    selected = select_latest_mandi_record([r1, r2])
    assert selected is not None
    assert selected.id == 2
    assert selected.modal_price == 2.0


def test_timezone_safe_sorting_both_none():
    """Verifies select_latest_mandi_record sorts safely when both records have fetched_at=None."""
    r1 = MandiPricesCache(
        id=10, market="M", commodity="C", state="S", district="D",
        min_price=1, max_price=2, modal_price=1.5,
        arrival_date="2026-11-16", source="live_api", fetched_at=None,
    )
    r2 = MandiPricesCache(
        id=20, market="M", commodity="C", state="S", district="D",
        min_price=1, max_price=2, modal_price=2.5,
        arrival_date="2026-11-16", source="live_api", fetched_at=None,
    )
    selected = select_latest_mandi_record([r1, r2])
    assert selected is not None
    assert selected.id == 20
    assert selected.modal_price == 2.5


def test_timezone_safe_sorting_both_timezone_aware():
    """Verifies select_latest_mandi_record handles two timezone-aware timestamps without TypeError."""
    t1 = datetime(2026, 11, 16, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
    r1 = MandiPricesCache(
        id=1, market="M", commodity="C", state="S", district="D",
        min_price=1, max_price=2, modal_price=1.5,
        arrival_date="2026-11-16", source="live_api", fetched_at=t1,
    )
    r2 = MandiPricesCache(
        id=2, market="M", commodity="C", state="S", district="D",
        min_price=1, max_price=2, modal_price=2.5,
        arrival_date="2026-11-16", source="live_api", fetched_at=t2,
    )
    selected = select_latest_mandi_record([r1, r2])
    assert selected is not None
    assert selected.id == 2
    assert selected.modal_price == 2.5


def test_timezone_safe_sorting_naive_and_aware():
    """Verifies select_latest_mandi_record handles one naive SQLite timestamp and one timezone-aware timestamp without TypeError."""
    t_naive = datetime(2026, 11, 16, 10, 0, 0)  # naive
    t_aware = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)  # aware
    r_naive = MandiPricesCache(
        id=1, market="M", commodity="C", state="S", district="D",
        min_price=1, max_price=2, modal_price=1.5,
        arrival_date="2026-11-16", source="live_api", fetched_at=t_naive,
    )
    r_aware = MandiPricesCache(
        id=2, market="M", commodity="C", state="S", district="D",
        min_price=1, max_price=2, modal_price=2.5,
        arrival_date="2026-11-16", source="live_api", fetched_at=t_aware,
    )
    selected = select_latest_mandi_record([r_naive, r_aware])
    assert selected is not None
    assert selected.id == 2
    assert selected.modal_price == 2.5


def test_invalid_arrival_date_records_excluded_from_verified_snapshot():
    """Confirms that records with corrupt/invalid arrival dates are strictly excluded from verified snapshot pricing,
    preventing corrupt data from entering verified comparisons or arbitrage calculations."""
    with SessionLocal() as db:
        test_market = "APMC Invalid Only Test"
        test_commodity = "InvalidOnlyCrop"
        now = datetime.now(timezone.utc)

        # Insert only invalid arrival date records with source="live_api"
        db.add(
            MandiPricesCache(
                state="Karnataka",
                district="Belagavi",
                market=test_market,
                commodity=test_commodity,
                variety="Standard",
                min_price=1000.0,
                max_price=1200.0,
                modal_price=1100.0,
                arrival_date="unparseable_date_xyz",
                source="live_api",
                dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
                fetched_at=now,
            )
        )
        # Also add an estimated benchmark with a valid date
        db.add(
            MandiPricesCache(
                state="Karnataka",
                district="Belagavi",
                market=test_market,
                commodity=test_commodity,
                variety="Estimated Benchmark",
                min_price=1800.0,
                max_price=2200.0,
                modal_price=2000.0,
                arrival_date="2026-11-15",
                source="estimated_benchmark",
                dataset_id=None,
                fetched_at=now,
            )
        )
        db.commit()

        # Verified snapshot lookup must return None because the live_api record has corrupt arrival_date
        verified = get_fallback_snapshot_price(test_market, test_commodity, db)
        assert verified is None

        # Cached or benchmark must safely fall back to the estimated benchmark
        result = get_cached_or_benchmark_price(test_market, test_commodity, db)
        assert result is not None
        assert result.source == "estimated_benchmark"
        assert result.modal_price == 2000.0


def test_provenance_priority_newer_benchmark_never_replaces_older_verified():
    """Verifies that an estimated benchmark with a futuristic or newer date never replaces
    an eligible genuine verified quotation."""
    with SessionLocal() as db:
        test_market = "APMC Provenance Test"
        test_commodity = "ProvenanceCrop"
        now = datetime.now(timezone.utc)

        # Genuine verified quotation from 2026-11-15
        db.add(
            MandiPricesCache(
                state="Karnataka",
                district="Belagavi",
                market=test_market,
                commodity=test_commodity,
                variety="Standard",
                min_price=2500.0,
                max_price=2900.0,
                modal_price=2700.0,
                arrival_date="2026-11-15",
                source="live_api",
                dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
                fetched_at=now - timedelta(days=1),
            )
        )
        # Benchmark record with newer arrival date (2026-11-20) and newer fetched_at
        db.add(
            MandiPricesCache(
                state="Karnataka",
                district="Belagavi",
                market=test_market,
                commodity=test_commodity,
                variety="Estimated Benchmark",
                min_price=1800.0,
                max_price=2200.0,
                modal_price=2000.0,
                arrival_date="2026-11-20",
                source="estimated_benchmark",
                dataset_id=None,
                fetched_at=now,
            )
        )
        db.commit()

        # get_cached_or_benchmark_price must return the verified live_api quote, NOT the newer benchmark!
        selected = get_cached_or_benchmark_price(test_market, test_commodity, db)
        assert selected is not None
        assert selected.source == "live_api"
        assert selected.modal_price == 2700.0
        assert selected.arrival_date == "2026-11-15"


def test_missing_and_invalid_arrival_date_handling():
    """Confirms records with valid arrival dates always outrank missing or corrupt arrival dates."""
    with SessionLocal() as db:
        test_market = "APMC Corrupt Date Test"
        test_commodity = "CorruptDateCrop"
        now = datetime.now(timezone.utc)

        # Record with invalid arrival date
        rec_bad = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market=test_market,
            commodity=test_commodity,
            variety="Standard",
            min_price=900.0,
            max_price=1000.0,
            modal_price=950.0,
            arrival_date="not_a_real_date",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=now,
        )
        # Record with valid arrival date
        rec_good = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market=test_market,
            commodity=test_commodity,
            variety="Standard",
            min_price=1500.0,
            max_price=1700.0,
            modal_price=1600.0,
            arrival_date="10/11/2026",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=now - timedelta(hours=10),
        )
        db.add(rec_bad)
        db.add(rec_good)
        db.commit()

        selected = get_fallback_snapshot_price(test_market, test_commodity, db)
        assert selected is not None
        assert selected.arrival_date == "10/11/2026"
        assert selected.modal_price == 1600.0


def test_mixed_formats_latest_selection():
    """Selects the latest date across a set of mixed formats (DD-MM-YYYY, YYYY/MM/DD, DD/MM/YYYY, YYYY-MM-DD)."""
    with SessionLocal() as db:
        test_market = "APMC Mixed Format Test"
        test_commodity = "MixedFormatCrop"
        now = datetime.now(timezone.utc)

        records = [
            MandiPricesCache(
                state="Karnataka", district="Belagavi", market=test_market, commodity=test_commodity,
                min_price=100, max_price=200, modal_price=150,
                arrival_date="10-11-2026", source="live_api", fetched_at=now,
            ),
            MandiPricesCache(
                state="Karnataka", district="Belagavi", market=test_market, commodity=test_commodity,
                min_price=200, max_price=300, modal_price=250,
                arrival_date="2026/11/12", source="live_api", fetched_at=now,
            ),
            MandiPricesCache(
                state="Karnataka", district="Belagavi", market=test_market, commodity=test_commodity,
                min_price=300, max_price=400, modal_price=350,
                arrival_date="15/11/2026", source="live_api", fetched_at=now,
            ),
            MandiPricesCache(
                state="Karnataka", district="Belagavi", market=test_market, commodity=test_commodity,
                min_price=500, max_price=600, modal_price=550,
                arrival_date="2026-11-18", source="live_api", fetched_at=now,
            ),
            MandiPricesCache(
                state="Karnataka", district="Belagavi", market=test_market, commodity=test_commodity,
                min_price=400, max_price=500, modal_price=450,
                arrival_date="17/11/2026", source="live_api", fetched_at=now,
            ),
        ]
        for r in records:
            db.add(r)
        db.commit()

        selected = get_fallback_snapshot_price(test_market, test_commodity, db)
        assert selected is not None
        assert selected.arrival_date == "2026-11-18"
        assert selected.modal_price == 550.0


# ==============================================================================
# 2. Freshness Classification & Conservative Aggregation Tests
# ==============================================================================

def test_stale_and_fresh_quotations_in_one_response_and_conservative_aggregate():
    """Verifies that if a response includes both fresh and stale relevant quotations,
    the aggregate status conservatively reports 'stale' rather than 'fresh', while
    individual per-mandi freshness fields remain authoritative."""
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        assert crop is not None

        # Clean prior live records for Belagavi and Kolhapur
        db.query(MandiPricesCache).filter(
            MandiPricesCache.market.in_(["Belagavi APMC", "Kolhapur APMC"]),
            MandiPricesCache.commodity == crop.agmarknet_commodity,
            MandiPricesCache.source == "live_api",
        ).delete()

        # Insert fresh live record for Belagavi (10 minutes ago)
        fresh_belagavi = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market="Belagavi APMC",
            commodity=crop.agmarknet_commodity,
            variety="Red",
            min_price=4000.0,
            max_price=4500.0,
            modal_price=4300.0,
            arrival_date="16/11/2026",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=now - timedelta(minutes=10),
        )
        # Insert stale live record for Kolhapur (5 hours ago, beyond 3h TTL)
        stale_kolhapur = MandiPricesCache(
            state="Maharashtra",
            district="Kolhapur",
            market="Kolhapur APMC",
            commodity=crop.agmarknet_commodity,
            variety="Red",
            min_price=3000.0,
            max_price=3500.0,
            modal_price=3200.0,
            arrival_date="15/11/2026",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=now - timedelta(hours=5),
        )
        db.add(fresh_belagavi)
        db.add(stale_kolhapur)
        db.commit()

    # Query /api/analyze with upstream AGMARKNET returning empty so Kolhapur falls back to stale cache
    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", AsyncMock(return_value=[])):
        res = client.post(
            "/api/analyze",
            json={
                "location_query": "Belagavi, Karnataka",
                "latitude": 15.8497,
                "longitude": 74.4977,
                "crop_id": "onion",
                "quantity_quintals": 30.0,
                "language": "en",
            },
        )
        assert res.status_code == 200
        data = res.json()

        mandis = data["mandi_comparison"]
        belagavi = next((m for m in mandis if m["market"] == "Belagavi APMC"), None)
        kolhapur = next((m for m in mandis if m["market"] == "Kolhapur APMC"), None)

        assert belagavi is not None
        assert belagavi["freshness_status"] in ["fresh", "cached"]
        assert belagavi["data_age_seconds"] < 3600

        assert kolhapur is not None
        assert kolhapur["freshness_status"] == "stale"
        assert kolhapur["retrieval_status"] == "stale_cache_fallback"
        assert kolhapur["data_age_seconds"] >= 14400

        # CONSERVATIVE AGGREGATE CHECK:
        # Since at least one relevant mandi is stale, aggregate MUST NOT claim all data is fresh!
        meta = data["freshness_metadata"]["mandi"]
        assert meta["freshness_status"] == "stale"
        assert meta["retrieval_status"] == "stale_cache_fallback"
        assert meta["stale_quotes_count"] >= 1
        assert meta["last_fetched_at"] is not None
        assert meta["oldest_fetched_at"] is not None
        # Verify last_fetched_at is newer than oldest_fetched_at
        assert meta["last_fetched_at"] > meta["oldest_fetched_at"]


def test_estimated_benchmark_provenance_and_zero_gain():
    """Confirms estimated benchmarks have freshness_status='estimated', fetched_at is null,
    and net_gain_vs_local_total is strictly 0.0."""
    res = client.post(
        "/api/analyze",
        json={
            "location_query": "Haveri, Karnataka",
            "latitude": 14.7952,
            "longitude": 75.3992,
            "crop_id": "maize",
            "quantity_quintals": 50.0,
            "language": "en",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["price_comparison_status"] == "no_verified_price_data"

    benchmarks = [m for m in data["mandi_comparison"] if m["is_benchmark"]]
    assert len(benchmarks) > 0
    for b in benchmarks:
        assert b["data_source"] == "estimated_benchmark"
        assert b["freshness_status"] == "estimated"
        assert b["retrieval_status"] in ["benchmark", "synthetic_fallback"]
        assert b["fetched_at"] is None
        assert b["data_age_seconds"] is None
        assert b["dataset_id"] is None
        assert b["net_gain_vs_local_total"] == 0.0

    meta = data["freshness_metadata"]["mandi"]
    assert meta["freshness_status"] == "estimated"
    assert meta["retrieval_status"] == "benchmark"
    assert meta["last_fetched_at"] is None
    assert meta["oldest_fetched_at"] is None


# ==============================================================================
# 3. Weather Freshness & Fallback Tests
# ==============================================================================

def test_cached_weather_freshness_metadata():
    """Verifies weather metadata when served from cache."""
    res = client.post(
        "/api/analyze",
        json={
            "location_query": "Belagavi, Karnataka",
            "latitude": 15.8497,
            "longitude": 74.4977,
            "crop_id": "onion",
            "quantity_quintals": 30.0,
            "language": "en",
        },
    )
    assert res.status_code == 200
    data = res.json()
    w = data["weather"]
    assert "fetched_at" in w
    assert "data_source" in w
    assert "freshness_status" in w
    assert "retrieval_status" in w
    assert "data_age_seconds" in w
    assert w["data_source"] == "open_meteo"
    assert w["freshness_status"] in ["fresh", "cached"]
    assert w["retrieval_status"] in ["live_response", "cache_hit"]


def test_stale_weather_fallback_metadata():
    """Verifies stale weather fallback metadata when cache is expired and upstream fails."""
    now = datetime.now(timezone.utc)
    stale_time = now - timedelta(hours=6)
    loc_key = "19.99_73.79"

    with SessionLocal() as db:
        # Set weather cache to 6 hours ago
        db.query(WeatherCache).filter(WeatherCache.location_key == loc_key).delete()
        db.add(
            WeatherCache(
                location_key=loc_key,
                payload_json='{"daily": {"time": ["2026-11-17"], "temperature_2m_max": [30.0], "temperature_2m_min": [20.0], "precipitation_sum": [0.0], "precipitation_probability_max": [0.0], "weather_code": [0]}, "hourly": {"precipitation": [0.0], "soil_moisture_0_to_7cm": [0.25], "relative_humidity_2m": [50.0]}}',
                fetched_at=stale_time,
            )
        )
        db.commit()

        # Force upstream fetch failure
        with patch("backend.app.services.weather_service.httpx.AsyncClient.get", side_effect=Exception("Timeout")):
            import anyio
            w = anyio.run(get_weather_forecast, 19.99, 73.79, "medium", db)

        assert w["data_source"] == "open_meteo"
        assert w["freshness_status"] == "stale"
        assert w["retrieval_status"] == "stale_cache_fallback"
        assert w["fetched_at"] is not None
        assert w["data_age_seconds"] is not None
        assert w["data_age_seconds"] >= 20000  # ~6 hours


def test_synthetic_weather_fallback_metadata():
    """Verifies synthetic weather fallback when no cache exists and upstream fails."""
    loc_key = "12.34_56.78"
    with SessionLocal() as db:
        db.query(WeatherCache).filter(WeatherCache.location_key == loc_key).delete()
        db.commit()

        with patch("backend.app.services.weather_service.httpx.AsyncClient.get", side_effect=Exception("Network error")):
            import anyio
            w = anyio.run(get_weather_forecast, 12.34, 56.78, "medium", db)

        assert w["data_source"] == "synthetic_baseline"
        assert w["freshness_status"] == "estimated"
        assert w["retrieval_status"] == "synthetic_fallback"
        assert w["fetched_at"] is None
        assert w["data_age_seconds"] is None


def test_missing_timestamps_nullable_handling():
    """Verifies JSON serialization is completely robust when timestamps are None."""
    res = client.post(
        "/api/analyze",
        json={
            "location_query": "Haveri, Karnataka",
            "latitude": 14.7952,
            "longitude": 75.3992,
            "crop_id": "maize",
            "quantity_quintals": 50.0,
            "language": "en",
        },
    )
    assert res.status_code == 200
    data = res.json()
    freshness = data["freshness_metadata"]
    assert freshness["mandi"]["freshness_status"] == "estimated"
    assert freshness["mandi"]["last_fetched_at"] is None
    assert freshness["mandi"]["oldest_fetched_at"] is None


def test_aggregate_metadata_consistency():
    """Verifies top-level freshness_metadata contains both mandi and weather summaries."""
    res = client.post(
        "/api/analyze",
        json={
            "location_query": "Belagavi, Karnataka",
            "latitude": 15.8497,
            "longitude": 74.4977,
            "crop_id": "onion",
            "quantity_quintals": 30.0,
            "language": "en",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "freshness_metadata" in data
    meta = data["freshness_metadata"]
    assert "mandi" in meta
    assert "weather" in meta

    mandi_meta = meta["mandi"]
    assert "freshness_status" in mandi_meta
    assert "retrieval_status" in mandi_meta
    assert "live_quotes_count" in mandi_meta
    assert "cached_quotes_count" in mandi_meta
    assert "benchmark_quotes_count" in mandi_meta
    assert "total_mandis" in mandi_meta
    assert mandi_meta["total_mandis"] == len(data["mandi_comparison"])

    weather_meta = meta["weather"]
    assert weather_meta["data_source"] == data["weather"]["data_source"]
    assert weather_meta["freshness_status"] == data["weather"]["freshness_status"]
    assert weather_meta["retrieval_status"] == data["weather"]["retrieval_status"]


def test_aggregate_freshness_matrix_out_of_coverage():
    """Verifies aggregate behavior when location is out of coverage."""
    res = client.post(
        "/api/analyze",
        json={
            "location_query": "Delhi, India",
            "latitude": 28.6139,
            "longitude": 77.2090,
            "crop_id": "onion",
            "quantity_quintals": 30.0,
            "language": "en",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["coverage_status"] == "out_of_coverage"
    meta = data["freshness_metadata"]["mandi"]
    assert meta["freshness_status"] == "unavailable"
    assert meta["retrieval_status"] == "out_of_coverage"
    assert meta["total_mandis"] == 0
    assert meta["last_fetched_at"] is None
    assert meta["oldest_fetched_at"] is None


def test_aggregate_freshness_mixed_live_and_cached():
    """Verifies aggregate behavior when all quotes are fresh/cached (<3h) but mixed live and cache hits."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        assert crop is not None

        # Clean prior live records for Belagavi and Kolhapur
        db.query(MandiPricesCache).filter(
            MandiPricesCache.market.in_(["Belagavi APMC", "Kolhapur APMC"]),
            MandiPricesCache.commodity == crop.agmarknet_commodity,
            MandiPricesCache.source == "live_api",
        ).delete()

        # Insert fresh cached record (<3h) for Kolhapur
        db.add(
            MandiPricesCache(
                state="Maharashtra", district="Kolhapur", market="Kolhapur APMC",
                commodity=crop.agmarknet_commodity, variety="Red",
                min_price=3000.0, max_price=3500.0, modal_price=3200.0,
                arrival_date="16/11/2026", source="live_api",
                dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
                fetched_at=now - timedelta(minutes=45),
            )
        )
        db.commit()

    # When querying with mock AGMARKNET returning live record for Belagavi only:
    canned_live = [{
        "state": "Karnataka", "district": "Belagavi", "market": "Belagavi APMC",
        "commodity": "Onion", "variety": "Red", "min_price": "4000",
        "max_price": "4500", "modal_price": "4200", "arrival_date": "16/11/2026",
    }]
    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", AsyncMock(return_value=canned_live)):
        res = client.post(
            "/api/analyze",
            json={
                "location_query": "Belagavi, Karnataka",
                "latitude": 15.8497,
                "longitude": 74.4977,
                "crop_id": "onion",
                "quantity_quintals": 30.0,
                "language": "en",
            },
        )
        assert res.status_code == 200
        data = res.json()
        meta = data["freshness_metadata"]["mandi"]
        # Belagavi is live, Kolhapur is cached (<3h). None is stale!
        assert meta["freshness_status"] == "cached"
        assert meta["retrieval_status"] == "live_response"
        assert meta["live_quotes_count"] >= 1
        assert meta["cached_quotes_count"] >= 1
        assert meta["stale_quotes_count"] == 0


def test_existing_api_contracts_backward_compatibility():
    """Verifies that all pre-existing response fields in /api/analyze remain fully backward-compatible."""
    res = client.post(
        "/api/analyze",
        json={
            "location_query": "Belagavi, Karnataka",
            "latitude": 15.8497,
            "longitude": 74.4977,
            "crop_id": "onion",
            "quantity_quintals": 30.0,
            "language": "en",
        },
    )
    assert res.status_code == 200
    data = res.json()

    # Required top-level keys
    required_top = [
        "location",
        "weather",
        "mandi_comparison",
        "ai_advisory",
        "coverage_status",
        "price_comparison_status",
        "price_comparison_notice",
        "freshness_metadata",
    ]
    for key in required_top:
        assert key in data, f"Missing key {key}"

    # Required mandi keys
    required_mandi_keys = [
        "market",
        "district",
        "state",
        "distance_km",
        "modal_price",
        "transport_cost_per_qtl",
        "spoilage_deduction_per_qtl",
        "net_price_per_qtl",
        "net_gain_vs_local_total",
        "is_local",
        "arrival_date",
        "data_source",
        "variety",
        "is_benchmark",
        "dataset_id",
        # New additive keys
        "fetched_at",
        "freshness_status",
        "retrieval_status",
        "data_age_seconds",
    ]
    for m in data["mandi_comparison"]:
        for k in required_mandi_keys:
            assert k in m, f"Missing mandi item key {k}"
