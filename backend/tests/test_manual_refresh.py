"""Comprehensive deterministic tests for Safe Manual Refresh Mechanism (Phase B).

Validates:
Mandi Refresh:
1. force_refresh=False uses existing cache.
2. force_refresh=True bypasses a valid cache.
3. Successful refresh updates the cache correctly.
4. Original arrival_date is preserved.
5. Cooldown prevents repeated upstream requests.
6. Concurrent duplicate requests are coalesced or safely serialized.
7. Upstream timeout preserves existing cache.
8. HTTP 503 preserves existing cache.
9. HTTP 200 with no matching records preserves older valid records.
10. Invalid upstream response preserves existing records.
11. Estimated benchmarks remain unverified.

Weather Refresh:
12. Normal cache behavior remains unchanged.
13. Forced refresh bypasses the cache.
14. Successful refresh updates weather cache.
15. Cooldown prevents duplicate requests.
16. Timeout preserves the previous weather cache.
17. Invalid response uses safe fallback.
18. Stale cached data remains correctly identified.
19. Synthetic fallback has no invented fetched_at timestamp.

API Integration:
20. Existing /api/analyze requests without force_refresh remain backward compatible.
21. force_refresh=True reaches both services correctly.
22. Mandi success and weather failure are reported independently.
23. Mandi failure and weather success are reported independently.
24. Both providers failing does not break existing analysis response.
25. Refresh metadata accurately reflects each outcome and adheres to contract schema.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import time
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models import CropProfile, MandiPricesCache, WeatherCache
from backend.app.seed import seed_all
from backend.app.services.mandi_service import (
    AgmarknetFetchResult,
    clear_mandi_cooldown_trackers,
    fetch_live_agmarknet_records,
    get_mandi_candidates_with_prices,
    get_mandi_arbitrage_analysis,
)
from backend.app.services.weather_service import (
    clear_weather_cooldown_trackers,
    get_weather_forecast,
    normalize_utc_datetime,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_cooldown_trackers():
    """Ensures each test starts with empty in-memory cooldown trackers and pristine DB cache."""
    clear_mandi_cooldown_trackers()
    clear_weather_cooldown_trackers()
    with SessionLocal() as db:
        db.query(WeatherCache).delete()
        db.query(MandiPricesCache).delete()
        seed_all(db)
        db.commit()
    yield
    clear_mandi_cooldown_trackers()
    clear_weather_cooldown_trackers()
    with SessionLocal() as db:
        db.query(WeatherCache).delete()
        db.query(MandiPricesCache).delete()
        seed_all(db)
        db.commit()


# ==============================================================================
# Part 1: Mandi Refresh Unit Tests
# ==============================================================================

@pytest.mark.anyio
async def test_mandi_refresh_not_requested_uses_existing_cache():
    """1. force_refresh=False uses existing cache without calling upstream."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        now = datetime.now(timezone.utc)

        # Seed fresh cache in DB (< 3h old)
        entry = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market="Belagavi APMC",
            commodity="Onion",
            variety="Nasik Red",
            min_price=1800.0,
            max_price=2200.0,
            modal_price=2000.0,
            arrival_date="16/11/2026",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=now - timedelta(minutes=15),
        )
        db.add(entry)
        db.commit()

        call_count = 0
        async def mock_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return []

        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", side_effect=mock_fetch):
            candidates, meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=False, return_meta=True
            )

        assert meta["refresh_status"] == "not_requested"
        assert meta["cooldown_remaining_seconds"] == 0
        belagavi = next(c for c in candidates if c.market == "Belagavi APMC")
        assert belagavi.retrieval_status == "cache_hit"
        assert belagavi.modal_price == 2000.0
    finally:
        db.close()


@pytest.mark.anyio
async def test_mandi_refresh_force_refresh_bypasses_cache():
    """2. force_refresh=True bypasses a valid cache and calls upstream."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        old_time = datetime.now(timezone.utc) - timedelta(minutes=70)  # Outside 60s cooldown, but inside 3h TTL

        entry = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market="Belagavi APMC",
            commodity="Onion",
            variety="Nasik Red",
            min_price=1800.0,
            max_price=2200.0,
            modal_price=2000.0,
            arrival_date="15/11/2026",
            source="live_api",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=old_time,
        )
        db.add(entry)
        db.commit()

        call_count = 0
        async def mock_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return [
                {
                    "state": "Karnataka",
                    "district": "Belagavi",
                    "market": "Belagavi APMC",
                    "commodity": "Onion",
                    "variety": "Nasik Red",
                    "min_price": "2100",
                    "max_price": "2500",
                    "modal_price": "2350",
                    "arrival_date": "17/11/2026",
                }
            ]

        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", side_effect=mock_fetch):
            candidates, meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )

        assert call_count > 0
        assert meta["refresh_status"] == "refreshed"
        assert meta["cooldown_remaining_seconds"] > 0
        assert meta["cooldown_remaining_seconds"] <= 60
        belagavi = next(c for c in candidates if c.market == "Belagavi APMC")
        assert belagavi.modal_price == 2350.0
        assert belagavi.retrieval_status == "live_response"
        assert belagavi.freshness_status == "fresh"
    finally:
        db.close()


@pytest.mark.anyio
async def test_mandi_refresh_success_updates_cache():
    """3. Successful refresh updates the cache correctly in SQLite."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "tomato").first()
        mock_payload = [
            {
                "state": "Karnataka",
                "district": "Kolar",
                "market": "Kolar APMC",
                "commodity": "Tomato",
                "variety": "Hybrid",
                "min_price": "1400",
                "max_price": "1800",
                "modal_price": "1650",
                "arrival_date": "17/11/2026",
            }
        ]

        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", AsyncMock(return_value=mock_payload)):
            candidates, meta = await get_mandi_candidates_with_prices(
                13.1367, 78.1291, crop, db, force_refresh=True, return_meta=True
            )

        assert meta["refresh_status"] == "refreshed"
        # Verify SQLite row was added
        kolar_entry = (
            db.query(MandiPricesCache)
            .filter(
                MandiPricesCache.market == "Kolar APMC",
                MandiPricesCache.commodity == "Tomato",
                MandiPricesCache.source == "live_api",
                MandiPricesCache.modal_price == 1650.0,
            )
            .first()
        )
        assert kolar_entry is not None
        assert kolar_entry.arrival_date == "17/11/2026"
    finally:
        db.close()


@pytest.mark.anyio
async def test_mandi_refresh_preserves_original_arrival_date():
    """4. Original arrival_date is preserved across attempts."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        historical_date = "12/11/2026"
        entry = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market="Belagavi APMC",
            commodity="Onion",
            variety="Nasik Red",
            min_price=1700.0,
            max_price=2100.0,
            modal_price=1900.0,
            arrival_date=historical_date,
            source="verified_snapshot",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        db.add(entry)
        db.commit()

        # Simulate upstream failure
        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", side_effect=httpx.ReadTimeout("Timed out")):
            candidates, meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )

        assert meta["refresh_status"] == "upstream_unavailable"
        db.refresh(entry)
        assert entry.arrival_date == historical_date
        belagavi = next(c for c in candidates if c.market == "Belagavi APMC")
        assert belagavi.arrival_date == historical_date
    finally:
        db.close()


@pytest.mark.anyio
async def test_mandi_refresh_cooldown_prevents_repeated_calls():
    """5. Cooldown prevents repeated upstream requests within 60s."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        mock_payload = [
            {
                "state": "Karnataka",
                "district": "Belagavi",
                "market": "Belagavi APMC",
                "commodity": "Onion",
                "variety": "Nasik Red",
                "min_price": "2000",
                "max_price": "2400",
                "modal_price": "2200",
                "arrival_date": "17/11/2026",
            }
        ]

        upstream_calls = 0
        async def mock_fetch(*args, **kwargs):
            nonlocal upstream_calls
            upstream_calls += 1
            return mock_payload

        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", side_effect=mock_fetch):
            # First call succeeds
            _, meta1 = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )
            assert meta1["refresh_status"] == "refreshed"
            assert upstream_calls > 0

            initial_calls = upstream_calls

            # Second call immediately after must be throttled by 60s cooldown
            _, meta2 = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )
            assert meta2["refresh_status"] == "cooldown"
            assert meta2["cooldown_remaining_seconds"] > 0
            assert meta2["cooldown_remaining_seconds"] <= 60
            assert upstream_calls == initial_calls  # Upstream was not called again!
    finally:
        db.close()


@pytest.mark.anyio
async def test_mandi_refresh_concurrent_duplicate_coalescing():
    """6. Concurrent duplicate requests are coalesced or safely serialized."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        call_count = 0

        async def slow_mock_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)  # Simulate network latency
            return [
                {
                    "state": "Karnataka",
                    "district": "Belagavi",
                    "market": "Belagavi APMC",
                    "commodity": "Onion",
                    "variety": "Nasik Red",
                    "min_price": "2000",
                    "max_price": "2400",
                    "modal_price": "2200",
                    "arrival_date": "17/11/2026",
                }
            ]

        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", side_effect=slow_mock_fetch):
            res1, res2 = await asyncio.gather(
                get_mandi_candidates_with_prices(15.85, 74.50, crop, db, force_refresh=True, return_meta=True),
                get_mandi_candidates_with_prices(15.85, 74.50, crop, db, force_refresh=True, return_meta=True),
            )

        # Both should report refreshed (or one refreshed and one coalesced)
        assert res1[1]["refresh_status"] in ("refreshed", "cooldown")
        assert res2[1]["refresh_status"] in ("refreshed", "cooldown")
        # Critical: Only one upstream query round was executed across target states (2 queries across Karnataka & Maharashtra).
        # Without concurrency coalescing, duplicate concurrent requests would issue 4 queries.
        assert call_count == 2
    finally:
        db.close()


@pytest.mark.anyio
async def test_mandi_refresh_upstream_timeout_preserves_cache():
    """7. Upstream timeout preserves existing cache."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        entry = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market="Belagavi APMC",
            commodity="Onion",
            variety="Nasik Red",
            min_price=1900.0,
            max_price=2300.0,
            modal_price=2100.0,
            arrival_date="15/11/2026",
            source="verified_snapshot",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add(entry)
        db.commit()

        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", side_effect=httpx.TimeoutException("Read timed out")):
            candidates, meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )

        assert meta["refresh_status"] == "upstream_unavailable"
        assert meta["cooldown_remaining_seconds"] > 0
        assert meta["cooldown_remaining_seconds"] <= 60
        belagavi = next(c for c in candidates if c.market == "Belagavi APMC")
        assert belagavi.modal_price == 2100.0
        assert belagavi.source == "verified_snapshot"
    finally:
        db.close()


@pytest.mark.anyio
async def test_mandi_refresh_http_503_preserves_cache():
    """8. HTTP 503 preserves existing cache."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        entry = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market="Belagavi APMC",
            commodity="Onion",
            variety="Nasik Red",
            min_price=1900.0,
            max_price=2300.0,
            modal_price=2100.0,
            arrival_date="15/11/2026",
            source="verified_snapshot",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add(entry)
        db.commit()

        err_result = AgmarknetFetchResult([], status="upstream_unavailable", http_status=503)
        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", AsyncMock(return_value=err_result)):
            candidates, meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )

        assert meta["refresh_status"] == "upstream_unavailable"
        belagavi = next(c for c in candidates if c.market == "Belagavi APMC")
        assert belagavi.modal_price == 2100.0
    finally:
        db.close()


@pytest.mark.anyio
async def test_mandi_refresh_http_200_empty_matching_preserves_cache():
    """9. HTTP 200 with no matching records preserves older valid records."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        entry = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market="Belagavi APMC",
            commodity="Onion",
            variety="Nasik Red",
            min_price=1900.0,
            max_price=2300.0,
            modal_price=2100.0,
            arrival_date="15/11/2026",
            source="verified_snapshot",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add(entry)
        db.commit()

        # Upstream returns 200 OK with records for an unrelated market
        unrelated_records = [
            {
                "state": "Karnataka",
                "district": "Shimoga",
                "market": "Shimoga APMC",
                "commodity": "Onion",
                "variety": "Nasik Red",
                "modal_price": "2400",
                "arrival_date": "17/11/2026",
            }
        ]
        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", AsyncMock(return_value=unrelated_records)):
            candidates, meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )

        assert meta["refresh_status"] == "no_matching_records"
        assert meta["cooldown_remaining_seconds"] > 0
        assert meta["cooldown_remaining_seconds"] <= 60
        belagavi = next(c for c in candidates if c.market == "Belagavi APMC")
        assert belagavi.modal_price == 2100.0
        assert belagavi.source == "verified_snapshot"
    finally:
        db.close()


@pytest.mark.anyio
async def test_mandi_refresh_invalid_upstream_response_preserves_cache():
    """10. Invalid upstream response preserves existing records."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        entry = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market="Belagavi APMC",
            commodity="Onion",
            variety="Nasik Red",
            min_price=1900.0,
            max_price=2300.0,
            modal_price=2100.0,
            arrival_date="15/11/2026",
            source="verified_snapshot",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add(entry)
        db.commit()

        inv_result = AgmarknetFetchResult([], status="invalid_response", http_status=200)
        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", AsyncMock(return_value=inv_result)):
            candidates, meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )

        assert meta["refresh_status"] == "invalid_response"
        belagavi = next(c for c in candidates if c.market == "Belagavi APMC")
        assert belagavi.modal_price == 2100.0
    finally:
        db.close()


@pytest.mark.anyio
async def test_mandi_refresh_estimated_benchmarks_remain_unverified():
    """11. Estimated benchmarks remain unverified (is_benchmark=True)."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "maize").first()
        bench_entry = MandiPricesCache(
            state="Karnataka",
            district="Haveri",
            market="Haveri APMC",
            commodity="Maize",
            variety="Estimated Benchmark",
            min_price=1800.0,
            max_price=2200.0,
            modal_price=2000.0,
            arrival_date="17/11/2026",
            source="estimated_benchmark",
            dataset_id=None,
            fetched_at=None,
        )
        db.add(bench_entry)
        db.commit()

        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", side_effect=httpx.ReadTimeout("Timeout")):
            candidates, meta = await get_mandi_candidates_with_prices(
                14.7952, 75.3992, crop, db, force_refresh=True, return_meta=True
            )

        haveri = next(c for c in candidates if c.market == "Haveri APMC")
        assert haveri.is_benchmark is True
        assert haveri.source == "estimated_benchmark"
        assert haveri.freshness_status == "estimated"
        assert haveri.retrieval_status == "benchmark"
    finally:
        db.close()


# ==============================================================================
# Part 2: Weather Refresh Unit Tests
# ==============================================================================

@pytest.mark.anyio
async def test_weather_refresh_normal_cache_behavior_unchanged(canned_weather_forecast):
    """12. Normal cache behavior remains unchanged (force_refresh=False)."""
    db = SessionLocal()
    try:
        lat, lon = 15.85, 74.50
        loc_key = f"{round(lat, 2):.2f}_{round(lon, 2):.2f}"
        now = datetime.now(timezone.utc)

        weather_cache = WeatherCache(
            location_key=loc_key,
            payload_json=json.dumps(canned_weather_forecast),
            fetched_at=now - timedelta(minutes=30),
        )
        db.add(weather_cache)
        db.commit()

        call_count = 0
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return AsyncMock(status_code=200, json=lambda: canned_weather_forecast)

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            data = await get_weather_forecast(lat, lon, "medium", db, force_refresh=False)

        assert data["refresh_status"] == "not_requested"
        assert data["cooldown_remaining_seconds"] == 0
        assert data["retrieval_status"] == "cache_hit"
        assert data["freshness_status"] == "cached"
        assert call_count == 0  # Did not call upstream!
    finally:
        db.close()


@pytest.mark.anyio
async def test_weather_refresh_force_refresh_bypasses_cache(canned_weather_forecast):
    """13. Forced refresh bypasses the cache when outside cooldown."""
    db = SessionLocal()
    try:
        lat, lon = 15.85, 74.50
        loc_key = f"{round(lat, 2):.2f}_{round(lon, 2):.2f}"
        old_time = datetime.now(timezone.utc) - timedelta(minutes=70)  # >60s cooldown

        weather_cache = WeatherCache(
            location_key=loc_key,
            payload_json=json.dumps(canned_weather_forecast),
            fetched_at=old_time,
        )
        db.add(weather_cache)
        db.commit()

        call_count = 0
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = AsyncMock()
            resp.status_code = 200
            resp.json = lambda: canned_weather_forecast
            return resp

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            data = await get_weather_forecast(lat, lon, "medium", db, force_refresh=True)

        assert call_count > 0
        assert data["refresh_status"] == "refreshed"
        assert data["cooldown_remaining_seconds"] > 0
        assert data["cooldown_remaining_seconds"] <= 60
        assert data["retrieval_status"] == "live_response"
        assert data["freshness_status"] == "fresh"
    finally:
        db.close()


@pytest.mark.anyio
async def test_weather_refresh_success_updates_weather_cache(canned_weather_forecast):
    """14. Successful refresh updates weather cache in SQLite."""
    db = SessionLocal()
    try:
        lat, lon = 18.52, 73.86
        loc_key = f"{round(lat, 2):.2f}_{round(lon, 2):.2f}"

        # Modify forecast payload to verify it is stored in DB
        custom_payload = dict(canned_weather_forecast)
        custom_payload["daily"]["temperature_2m_max"][0] = 38.5

        resp = AsyncMock()
        resp.status_code = 200
        resp.json = lambda: custom_payload

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=resp)):
            data = await get_weather_forecast(lat, lon, "medium", db, force_refresh=True)

        assert data["refresh_status"] == "refreshed"
        db_cache = db.query(WeatherCache).filter(WeatherCache.location_key == loc_key).first()
        assert db_cache is not None
        stored_payload = json.loads(db_cache.payload_json)
        assert stored_payload["daily"]["temperature_2m_max"][0] == 38.5
    finally:
        db.close()


@pytest.mark.anyio
async def test_weather_refresh_cooldown_prevents_duplicate_requests(canned_weather_forecast):
    """15. Cooldown prevents duplicate requests within 60s."""
    db = SessionLocal()
    try:
        lat, lon = 15.85, 74.50
        resp = AsyncMock()
        resp.status_code = 200
        resp.json = lambda: canned_weather_forecast

        calls = 0
        async def counting_get(*args, **kwargs):
            nonlocal calls
            calls += 1
            return resp

        with patch("httpx.AsyncClient.get", side_effect=counting_get):
            # First request refreshes
            data1 = await get_weather_forecast(lat, lon, "medium", db, force_refresh=True)
            assert data1["refresh_status"] == "refreshed"
            assert calls == 1

            # Second request within 60s is throttled
            data2 = await get_weather_forecast(lat, lon, "medium", db, force_refresh=True)
            assert data2["refresh_status"] == "cooldown"
            assert data2["cooldown_remaining_seconds"] > 0
            assert calls == 1  # No second upstream call!
    finally:
        db.close()


@pytest.mark.anyio
async def test_weather_refresh_timeout_preserves_previous_cache(canned_weather_forecast):
    """16. Timeout preserves previous weather cache."""
    db = SessionLocal()
    try:
        lat, lon = 15.85, 74.50
        loc_key = f"{round(lat, 2):.2f}_{round(lon, 2):.2f}"
        now = datetime.now(timezone.utc)
        initial_fetched_at = now - timedelta(minutes=45)

        weather_cache = WeatherCache(
            location_key=loc_key,
            payload_json=json.dumps(canned_weather_forecast),
            fetched_at=initial_fetched_at,
        )
        db.add(weather_cache)
        db.commit()

        with patch("httpx.AsyncClient.get", side_effect=httpx.ReadTimeout("Timeout")):
            data = await get_weather_forecast(lat, lon, "medium", db, force_refresh=True)

        assert data["refresh_status"] == "upstream_unavailable"
        assert data["retrieval_status"] == "cache_hit"
        assert data["freshness_status"] == "cached"
        db.refresh(weather_cache)
        assert normalize_utc_datetime(weather_cache.fetched_at) == initial_fetched_at  # Unchanged!
    finally:
        db.close()


@pytest.mark.anyio
async def test_weather_refresh_invalid_response_uses_safe_fallback(canned_weather_forecast):
    """17. Invalid response uses safe fallback."""
    db = SessionLocal()
    try:
        lat, lon = 15.85, 74.50
        loc_key = f"{round(lat, 2):.2f}_{round(lon, 2):.2f}"

        # Existing valid cache
        weather_cache = WeatherCache(
            location_key=loc_key,
            payload_json=json.dumps(canned_weather_forecast),
            fetched_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        db.add(weather_cache)
        db.commit()

        resp = AsyncMock()
        resp.status_code = 200
        resp.json = lambda: "not_a_valid_weather_dictionary"

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=resp)):
            data = await get_weather_forecast(lat, lon, "medium", db, force_refresh=True)

        assert data["refresh_status"] == "invalid_response"
        assert data["retrieval_status"] == "cache_hit"
    finally:
        db.close()


@pytest.mark.anyio
async def test_weather_refresh_stale_cached_data_remains_stale(canned_weather_forecast):
    """18. Stale cached data (>3h old) remains correctly identified when refresh fails."""
    db = SessionLocal()
    try:
        lat, lon = 15.85, 74.50
        loc_key = f"{round(lat, 2):.2f}_{round(lon, 2):.2f}"
        stale_time = datetime.now(timezone.utc) - timedelta(hours=4)

        weather_cache = WeatherCache(
            location_key=loc_key,
            payload_json=json.dumps(canned_weather_forecast),
            fetched_at=stale_time,
        )
        db.add(weather_cache)
        db.commit()

        with patch("httpx.AsyncClient.get", side_effect=httpx.ReadTimeout("Timeout")):
            data = await get_weather_forecast(lat, lon, "medium", db, force_refresh=True)

        assert data["refresh_status"] == "upstream_unavailable"
        assert data["retrieval_status"] == "stale_cache_fallback"
        assert data["freshness_status"] == "stale"
    finally:
        db.close()


@pytest.mark.anyio
async def test_weather_refresh_synthetic_fallback_no_invented_timestamp():
    """19. Synthetic fallback has no invented fetched_at timestamp."""
    db = SessionLocal()
    try:
        lat, lon = 25.00, 85.00  # No cache exists for this location

        with patch("httpx.AsyncClient.get", side_effect=httpx.NetworkError("Network down")):
            data = await get_weather_forecast(lat, lon, "medium", db, force_refresh=True)

        assert data["refresh_status"] == "upstream_unavailable"
        assert data["retrieval_status"] == "synthetic_fallback"
        assert data["freshness_status"] == "estimated"
        assert data["fetched_at"] is None
        assert data["data_age_seconds"] is None
    finally:
        db.close()


# ==============================================================================
# Part 3: API Integration Tests (/api/analyze)
# ==============================================================================

def test_api_analyze_backward_compatible_without_force_refresh():
    """20. Existing /api/analyze requests without force_refresh remain backward compatible."""
    payload = {
        "location_query": "Belagavi, Karnataka",
        "latitude": 15.8497,
        "longitude": 74.4977,
        "crop_id": "onion",
        "quantity_quintals": 30.0,
        "language": "en",
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "freshness_metadata" in data
    mandi_f = data["freshness_metadata"]["mandi"]
    weather_f = data["freshness_metadata"]["weather"]
    assert mandi_f["refresh_status"] == "not_requested"
    assert mandi_f["cooldown_remaining_seconds"] == 0
    assert weather_f["refresh_status"] == "not_requested"
    assert weather_f["cooldown_remaining_seconds"] == 0


def test_api_analyze_force_refresh_true_reaches_both_services(canned_weather_forecast):
    """21. force_refresh=True reaches both services correctly."""
    live_records = [
        {
            "state": "Karnataka",
            "district": "Belagavi",
            "market": "Belagavi APMC",
            "commodity": "Onion",
            "variety": "Nasik Red",
            "min_price": "2200",
            "max_price": "2600",
            "modal_price": "2400",
            "arrival_date": "17/11/2026",
        }
    ]

    weather_resp = AsyncMock()
    weather_resp.status_code = 200
    weather_resp.json = lambda: canned_weather_forecast

    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", AsyncMock(return_value=live_records)):
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=weather_resp)):
            resp = client.post(
                "/api/analyze",
                json={
                    "location_query": "Belagavi, Karnataka",
                    "latitude": 15.8497,
                    "longitude": 74.4977,
                    "crop_id": "onion",
                    "quantity_quintals": 30.0,
                    "language": "en",
                    "force_refresh": True,
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    mandi_f = data["freshness_metadata"]["mandi"]
    weather_f = data["freshness_metadata"]["weather"]
    assert mandi_f["refresh_status"] == "refreshed"
    assert mandi_f["cooldown_remaining_seconds"] > 0
    assert mandi_f["cooldown_remaining_seconds"] <= 60
    assert weather_f["refresh_status"] == "refreshed"
    assert weather_f["cooldown_remaining_seconds"] > 0
    assert weather_f["cooldown_remaining_seconds"] <= 60


def test_api_analyze_mandi_success_weather_failure_independent():
    """22. Mandi success and weather failure are reported independently."""
    live_records = [
        {
            "state": "Karnataka",
            "district": "Belagavi",
            "market": "Belagavi APMC",
            "commodity": "Onion",
            "variety": "Nasik Red",
            "min_price": "2200",
            "max_price": "2600",
            "modal_price": "2400",
            "arrival_date": "17/11/2026",
        }
    ]

    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", AsyncMock(return_value=live_records)):
        with patch("backend.app.services.weather_service.httpx.AsyncClient.get", side_effect=httpx.ReadTimeout("Weather timeout")):
            resp = client.post(
                "/api/analyze",
                json={
                    "location_query": "Belagavi, Karnataka",
                    "latitude": 15.8497,
                    "longitude": 74.4977,
                    "crop_id": "onion",
                    "quantity_quintals": 30.0,
                    "language": "en",
                    "force_refresh": True,
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    mandi_f = data["freshness_metadata"]["mandi"]
    weather_f = data["freshness_metadata"]["weather"]
    assert mandi_f["refresh_status"] == "refreshed"
    assert weather_f["refresh_status"] == "upstream_unavailable"


def test_api_analyze_mandi_failure_weather_success_independent(canned_weather_forecast):
    """23. Mandi failure and weather success are reported independently."""
    weather_resp = AsyncMock()
    weather_resp.status_code = 200
    weather_resp.json = lambda: canned_weather_forecast

    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", side_effect=httpx.ReadTimeout("AGMARKNET timeout")):
        with patch("backend.app.services.weather_service.httpx.AsyncClient.get", AsyncMock(return_value=weather_resp)):
            resp = client.post(
                "/api/analyze",
                json={
                    "location_query": "Belagavi, Karnataka",
                    "latitude": 15.8497,
                    "longitude": 74.4977,
                    "crop_id": "onion",
                    "quantity_quintals": 30.0,
                    "language": "en",
                    "force_refresh": True,
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    mandi_f = data["freshness_metadata"]["mandi"]
    weather_f = data["freshness_metadata"]["weather"]
    assert mandi_f["refresh_status"] == "upstream_unavailable"
    assert weather_f["refresh_status"] == "refreshed"


def test_api_analyze_both_providers_failing_does_not_break_response():
    """24. Both providers failing does not break existing analysis response."""
    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", side_effect=httpx.ReadTimeout("AGMARKNET timeout")):
        with patch("backend.app.services.weather_service.httpx.AsyncClient.get", side_effect=httpx.ReadTimeout("Weather timeout")):
            resp = client.post(
                "/api/analyze",
                json={
                    "location_query": "Belagavi, Karnataka",
                    "latitude": 15.8497,
                    "longitude": 74.4977,
                    "crop_id": "onion",
                    "quantity_quintals": 30.0,
                    "language": "en",
                    "force_refresh": True,
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    mandi_f = data["freshness_metadata"]["mandi"]
    weather_f = data["freshness_metadata"]["weather"]
    assert mandi_f["refresh_status"] == "upstream_unavailable"
    assert weather_f["refresh_status"] == "upstream_unavailable"
    assert "ai_advisory" in data
    assert "mandi_comparison" in data
    assert "weather" in data


def test_api_analyze_refresh_metadata_contract_structure():
    """25. Contract verification: freshness_metadata accurately reflects all fields."""
    resp = client.post(
        "/api/analyze",
        json={
            "location_query": "Belagavi, Karnataka",
            "crop_id": "onion",
            "force_refresh": False,
        },
    )
    assert resp.status_code == 200
    meta = resp.json()["freshness_metadata"]

    # Verify mandi contract
    mandi_keys = {
        "freshness_status",
        "retrieval_status",
        "refresh_status",
        "cooldown_remaining_seconds",
        "last_fetched_at",
        "oldest_fetched_at",
        "live_quotes_count",
        "cached_quotes_count",
        "stale_quotes_count",
        "benchmark_quotes_count",
        "total_mandis",
    }
    assert mandi_keys.issubset(set(meta["mandi"].keys()))

    # Verify weather contract
    weather_keys = {
        "freshness_status",
        "retrieval_status",
        "refresh_status",
        "cooldown_remaining_seconds",
        "data_source",
        "fetched_at",
        "data_age_seconds",
    }
    assert weather_keys.issubset(set(meta["weather"].keys()))


# ==============================================================================
# Phase D Focused Cooldown Lifecycle & Metadata Tests
# ==============================================================================

@pytest.mark.anyio
async def test_cooldown_reported_immediately_on_successful_refresh(canned_weather_forecast):
    """26. Successful refresh immediately reports server-side remaining cooldown (>0 and <=60)."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        clear_mandi_cooldown_trackers()
        clear_weather_cooldown_trackers()

        live_records = [{
            "state": "Karnataka",
            "district": "Belagavi",
            "market": "Belagavi APMC",
            "commodity": "Onion",
            "variety": "Nasik Red",
            "min_price": "2200",
            "max_price": "2600",
            "modal_price": "2400",
            "arrival_date": "17/11/2026",
        }]

        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", AsyncMock(return_value=live_records)):
            _, mandi_meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )

        assert mandi_meta["refresh_status"] == "refreshed"
        assert 50 <= mandi_meta["cooldown_remaining_seconds"] <= 60

        weather_resp = AsyncMock()
        weather_resp.status_code = 200
        weather_resp.json = lambda: canned_weather_forecast

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=weather_resp)):
            weather_data = await get_weather_forecast(15.85, 74.50, "medium", db, force_refresh=True)

        assert weather_data["refresh_status"] == "refreshed"
        assert 50 <= weather_data["cooldown_remaining_seconds"] <= 60
    finally:
        db.close()


@pytest.mark.anyio
async def test_cooldown_reported_immediately_on_failed_refresh():
    """27. Failed upstream refresh reports remaining cooldown when failure cooldown is activated."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        clear_mandi_cooldown_trackers()
        clear_weather_cooldown_trackers()

        # Mandi upstream failure
        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", side_effect=httpx.TimeoutException("Upstream timed out")):
            _, mandi_meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )

        assert mandi_meta["refresh_status"] == "upstream_unavailable"
        assert 50 <= mandi_meta["cooldown_remaining_seconds"] <= 60

        # Weather upstream failure
        with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")):
            weather_data = await get_weather_forecast(15.85, 74.50, "medium", db, force_refresh=True)

        assert weather_data["refresh_status"] == "upstream_unavailable"
        assert 50 <= weather_data["cooldown_remaining_seconds"] <= 60
    finally:
        db.close()


@pytest.mark.anyio
async def test_cooldown_reported_on_no_matching_records():
    """28. No matching records response reports cooldown correctly."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        clear_mandi_cooldown_trackers()

        # Upstream responds with empty / unrelated records
        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", AsyncMock(return_value=[])):
            _, mandi_meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )

        assert mandi_meta["refresh_status"] == "no_matching_records"
        assert 50 <= mandi_meta["cooldown_remaining_seconds"] <= 60
    finally:
        db.close()


@pytest.mark.anyio
async def test_independent_mandi_and_weather_cooldowns(canned_weather_forecast):
    """29. Mandi and weather cooldowns operate completely independently."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        clear_mandi_cooldown_trackers()
        clear_weather_cooldown_trackers()

        # Simulate mandi refreshed 40 seconds ago (cooldown ~20s remaining)
        from backend.app.services.mandi_service import _mandi_last_attempt, select_candidate_mandis
        from backend.app.services.weather_service import _weather_last_attempt

        mandis = select_candidate_mandis(15.85, 74.50, max_count=5)
        scope_key = f"{crop.agmarknet_commodity.lower()}:{','.join(sorted(m['market'] for m in mandis))}"
        _mandi_last_attempt[scope_key] = time.monotonic() - 40.0

        # Weather refreshed just 5 seconds ago (cooldown ~55s remaining)
        loc_key = f"{round(15.85, 2):.2f}_{round(74.50, 2):.2f}"
        _weather_last_attempt[loc_key] = time.monotonic() - 5.0

        # Request forced refresh for both
        _, mandi_meta = await get_mandi_candidates_with_prices(
            15.85, 74.50, crop, db, force_refresh=True, return_meta=True
        )
        weather_data = await get_weather_forecast(15.85, 74.50, "medium", db, force_refresh=True)

        assert mandi_meta["refresh_status"] == "cooldown"
        assert 15 <= mandi_meta["cooldown_remaining_seconds"] <= 25

        assert weather_data["refresh_status"] == "cooldown"
        assert 50 <= weather_data["cooldown_remaining_seconds"] <= 60

        # Discrepancy proves independent tracking
        assert weather_data["cooldown_remaining_seconds"] > mandi_meta["cooldown_remaining_seconds"]
    finally:
        db.close()


@pytest.mark.anyio
async def test_cooldown_countdown_expiration_resets_cooldown():
    """30. Cooldown expires after COOLDOWN_SECONDS, re-enabling fresh upstream calls."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        clear_mandi_cooldown_trackers()

        from backend.app.services.mandi_service import _mandi_last_attempt, select_candidate_mandis
        mandis = select_candidate_mandis(15.85, 74.50, max_count=5)
        scope_key = f"{crop.agmarknet_commodity.lower()}:{','.join(sorted(m['market'] for m in mandis))}"

        # Set last attempt to 65 seconds ago (exceeded 60s cooldown)
        _mandi_last_attempt[scope_key] = time.monotonic() - 65.0

        call_count = 0
        async def mock_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return []

        with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", side_effect=mock_fetch):
            _, mandi_meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )

        # Call succeeded because cooldown expired
        assert call_count > 0
        assert mandi_meta["refresh_status"] == "no_matching_records"
        # New cooldown has now begun
        assert 50 <= mandi_meta["cooldown_remaining_seconds"] <= 60
    finally:
        db.close()


@pytest.mark.anyio
async def test_normal_analysis_does_not_start_cooldown(canned_weather_forecast):
    """31. Normal analysis (force_refresh=False) does not start an unnecessary cooldown."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        clear_mandi_cooldown_trackers()
        clear_weather_cooldown_trackers()

        # Seed verified snapshot in DB
        entry = MandiPricesCache(
            state="Karnataka",
            district="Belagavi",
            market="Belagavi APMC",
            commodity="Onion",
            variety="Nasik Red",
            min_price=2000.0,
            max_price=2400.0,
            modal_price=2200.0,
            arrival_date="17/11/2026",
            source="verified_snapshot",
            dataset_id="9ef84268-d588-465a-a308-a864a43d0070",
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(entry)
        db.commit()

        # Normal analysis: force_refresh=False
        _, mandi_meta = await get_mandi_candidates_with_prices(
            15.85, 74.50, crop, db, force_refresh=False, return_meta=True
        )
        weather_data = await get_weather_forecast(15.85, 74.50, "medium", db, force_refresh=False)

        assert mandi_meta["refresh_status"] == "not_requested"
        assert mandi_meta["cooldown_remaining_seconds"] == 0

        assert weather_data["refresh_status"] == "not_requested"
        assert weather_data["cooldown_remaining_seconds"] == 0

        # Last attempt trackers must remain empty!
        from backend.app.services.mandi_service import _mandi_last_attempt, select_candidate_mandis
        from backend.app.services.weather_service import _weather_last_attempt

        mandis = select_candidate_mandis(15.85, 74.50, max_count=5)
        scope_key = f"{crop.agmarknet_commodity.lower()}:{','.join(sorted(m['market'] for m in mandis))}"
        assert scope_key not in _mandi_last_attempt
        loc_key = f"{round(15.85, 2):.2f}_{round(74.50, 2):.2f}"
        assert loc_key not in _weather_last_attempt
    finally:
        db.close()


@pytest.mark.anyio
async def test_cooldown_clock_consistency_under_system_clock_jump(canned_weather_forecast):
    """32. Process-local attempt cooldowns are immune to system clock jumps (monotonic clock separation)."""
    db = SessionLocal()
    try:
        crop = db.query(CropProfile).filter(CropProfile.crop_id == "onion").first()
        clear_mandi_cooldown_trackers()
        clear_weather_cooldown_trackers()

        from backend.app.services.mandi_service import _mandi_last_attempt, select_candidate_mandis
        from backend.app.services.weather_service import _weather_last_attempt

        mandis = select_candidate_mandis(15.85, 74.50, max_count=5)
        scope_key = f"{crop.agmarknet_commodity.lower()}:{','.join(sorted(m['market'] for m in mandis))}"
        loc_key = f"{round(15.85, 2):.2f}_{round(74.50, 2):.2f}"

        # Record attempt 30 seconds ago in monotonic time
        _mandi_last_attempt[scope_key] = time.monotonic() - 30.0
        _weather_last_attempt[loc_key] = time.monotonic() - 30.0

        # Simulate system wall clock jumping forward 2 hours (e.g. NTP or VM resume)
        jumped_wall_time = datetime.now(timezone.utc) + timedelta(hours=2)

        class JumpedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return jumped_wall_time
                return jumped_wall_time.astimezone(tz)

        with patch("backend.app.services.mandi_service.datetime", JumpedDatetime), \
             patch("backend.app.services.weather_service.datetime", JumpedDatetime):
            # Query under cooldown with jumped wall clock
            _, mandi_meta = await get_mandi_candidates_with_prices(
                15.85, 74.50, crop, db, force_refresh=True, return_meta=True
            )
            weather_data = await get_weather_forecast(15.85, 74.50, "medium", db, force_refresh=True)

        # Monotonic duration ensures cooldown remains accurate (~30s remaining) rather than jumping to 0s or erroring!
        assert mandi_meta["refresh_status"] == "cooldown"
        assert 25 <= mandi_meta["cooldown_remaining_seconds"] <= 35
        assert weather_data["refresh_status"] == "cooldown"
        assert 25 <= weather_data["cooldown_remaining_seconds"] <= 35
    finally:
        db.close()

