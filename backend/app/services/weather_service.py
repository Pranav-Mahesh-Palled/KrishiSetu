"""Open-Meteo Weather and Geocoding Service for KrishiSetu.

Provides:
- Async Geocoding via Open-Meteo Geocoding API
- Async 7-Day Weather & Topsoil Moisture Forecast with 3-Hour SQLite Caching
- Seamless offline/timeout resilience with fallback data
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
import httpx
from sqlalchemy.orm import Session

from backend.app.models import WeatherCache
from backend.app.services.weather_risk import classify_weather_risk

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 3
COOLDOWN_SECONDS = 60
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# In-memory concurrency locks and rate-limiting trackers per location scope
_weather_location_locks: Dict[str, asyncio.Lock] = {}
_weather_last_attempt: Dict[str, float] = {}


def _get_weather_lock(location_key: str) -> asyncio.Lock:
    """Retrieves or creates an asyncio.Lock for a specific geographic coordinate key."""
    if location_key not in _weather_location_locks:
        _weather_location_locks[location_key] = asyncio.Lock()
    return _weather_location_locks[location_key]


def clear_weather_cooldown_trackers() -> None:
    """Utility for test suites to reset in-memory attempt timestamps and locks."""
    _weather_last_attempt.clear()
    _weather_location_locks.clear()


def normalize_utc_datetime(dt: Optional[Union[datetime, str]]) -> Optional[datetime]:
    """Ensures datetime is timezone-aware UTC without accidental double conversion."""
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            clean_str = dt.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def geocode_location(location_query: str) -> Dict[str, Any]:
    """Resolves village, town, or district name to exact latitude and longitude."""
    clean_query = location_query.strip()
    # Strip country or state suffix for broader geocoder matching if needed
    primary_name = clean_query.split(",")[0].strip()

    params = {
        "name": primary_name,
        "count": 5,
        "language": "en",
        "format": "json",
        "country_code": "IN",
    }

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(GEOCODING_URL, params=params)
            if response.status_code == 200:
                data = response.json()
                results = data.get("results")
                if results and len(results) > 0:
                    top = results[0]
                    return {
                        "name": top.get("name", primary_name),
                        "state": top.get("admin1", "India"),
                        "lat": float(top["latitude"]),
                        "lon": float(top["longitude"]),
                    }

            # Retry without country_code restriction if not found
            params.pop("country_code", None)
            retry_resp = await client.get(GEOCODING_URL, params=params)
            if retry_resp.status_code == 200:
                data = retry_resp.json()
                results = data.get("results")
                if results and len(results) > 0:
                    top = results[0]
                    return {
                        "name": top.get("name", primary_name),
                        "state": top.get("admin1", "India"),
                        "lat": float(top["latitude"]),
                        "lon": float(top["longitude"]),
                    }
    except Exception as exc:
        logger.warning(f"Geocoding API network issue for query '{location_query}': {exc}")

    # Fallback to coordinate approximation based on recognized demo hubs
    lower_query = clean_query.lower()
    if "belagavi" in lower_query or "belgaum" in lower_query:
        return {"name": "Belagavi", "state": "Karnataka", "lat": 15.8497, "lon": 74.4977}
    elif "kolar" in lower_query:
        return {"name": "Kolar", "state": "Karnataka", "lat": 13.1367, "lon": 78.1291}
    elif "nashik" in lower_query or "nasik" in lower_query:
        return {"name": "Nashik", "state": "Maharashtra", "lat": 19.9975, "lon": 73.7898}
    elif "haveri" in lower_query:
        return {"name": "Haveri", "state": "Karnataka", "lat": 14.7952, "lon": 75.3992}
    elif "pune" in lower_query:
        return {"name": "Pune", "state": "Maharashtra", "lat": 18.5204, "lon": 73.8567}

    # If location cannot be geocoded or recognized, raise explicit error rather than silently defaulting to Hubli
    raise ValueError(
        f"Location '{location_query}' could not be resolved to geographical coordinates. "
        "Please provide a recognized village, town, or district."
    )


def _build_synthetic_forecast() -> Dict[str, Any]:
    """Generates realistic baseline weather data when upstream is unreachable."""
    today = datetime.now(timezone.utc)
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    return {
        "daily": {
            "time": dates,
            "temperature_2m_max": [31.5, 32.0, 30.8, 31.2, 32.5, 33.0, 31.0],
            "temperature_2m_min": [19.2, 19.8, 20.1, 19.5, 20.0, 20.5, 19.0],
            "precipitation_sum": [0.0, 1.2, 0.4, 0.0, 0.0, 2.5, 0.0],
            "precipitation_probability_max": [10.0, 25.0, 15.0, 5.0, 5.0, 35.0, 10.0],
            "weather_code": [0, 1, 2, 0, 0, 3, 1],
        },
        "hourly": {
            "precipitation": [0.0] * 72,
            "soil_moisture_0_to_7cm": [0.26] * 72,
            "relative_humidity_2m": [58.0] * 72,
        },
    }


async def get_weather_forecast(
    latitude: float,
    longitude: float,
    perishability_tier: str,
    db: Session,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Fetches 7-day forecast & soil moisture, applying SQLite 3h caching, 60s manual refresh cooldown, & risk classification."""
    location_key = f"{round(latitude, 2):.2f}_{round(longitude, 2):.2f}"
    now = datetime.now(timezone.utc)

    # 1. Inspect existing local SQLite cache record
    cached_record = db.query(WeatherCache).filter(WeatherCache.location_key == location_key).first()
    raw_data: Optional[Dict[str, Any]] = None
    weather_source: str = "open_meteo"
    retrieval_status: str = "cache_hit"
    freshness_status: str = "cached"
    fetched_at_utc: Optional[datetime] = None

    refresh_status: str = "not_requested"
    cooldown_remaining_seconds: int = 0

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code",
        "hourly": "precipitation,soil_moisture_0_to_7cm,relative_humidity_2m",
        "timezone": "auto",
    }

    if not force_refresh:
        # Standard workflow: check 3-hour cache TTL
        refresh_status = "not_requested"
        cooldown_remaining_seconds = 0

        if cached_record:
            fetched_at = normalize_utc_datetime(cached_record.fetched_at)
            if fetched_at and (now - fetched_at).total_seconds() < CACHE_TTL_HOURS * 3600:
                try:
                    raw_data = json.loads(cached_record.payload_json)
                    fetched_at_utc = fetched_at
                    weather_source = "open_meteo"
                    retrieval_status = "cache_hit"
                    freshness_status = "cached"
                except Exception as e:
                    logger.error(f"Failed to parse cached weather JSON for {location_key}: {e}")

        # If cache miss or stale, fetch live
        if not raw_data:
            try:
                async with httpx.AsyncClient(timeout=6.0) as client:
                    resp = await client.get(FORECAST_URL, params=params)
                    if resp.status_code == 200:
                        raw_data = resp.json()
                        fetched_at_utc = now
                        weather_source = "open_meteo"
                        retrieval_status = "live_response"
                        freshness_status = "fresh"

                        if cached_record:
                            cached_record.payload_json = json.dumps(raw_data)
                            cached_record.fetched_at = now
                        else:
                            new_cache = WeatherCache(
                                location_key=location_key,
                                payload_json=json.dumps(raw_data),
                                fetched_at=now,
                            )
                            db.add(new_cache)
                        db.commit()
                    else:
                        logger.warning(f"Open-Meteo API returned status {resp.status_code}")
            except Exception as exc:
                logger.warning(f"Open-Meteo forecast fetch failed for ({latitude}, {longitude}): {exc}")

    else:
        # Manual refresh requested: evaluate 60s cooldown per location_key
        mono_now = time.monotonic()
        mono_attempt = _weather_last_attempt.get(location_key)
        mono_rem = (
            max(1, int(COOLDOWN_SECONDS - (mono_now - mono_attempt)))
            if mono_attempt is not None and (mono_now - mono_attempt) < COOLDOWN_SECONDS
            else 0
        )

        db_rem = 0
        if cached_record and cached_record.fetched_at:
            norm_f = normalize_utc_datetime(cached_record.fetched_at)
            if norm_f:
                db_elapsed = (now - norm_f).total_seconds()
                if 0 <= db_elapsed < COOLDOWN_SECONDS:
                    db_rem = max(1, int(COOLDOWN_SECONDS - db_elapsed))

        cooldown_remaining_seconds = max(mono_rem, db_rem)

        if cooldown_remaining_seconds > 0:
            # Under cooldown: reject repeated upstream request, retain existing cache
            refresh_status = "cooldown"
        else:
            # Outside cooldown: acquire concurrency lock to prevent duplicate simultaneous upstream calls
            lock = _get_weather_lock(location_key)
            async with lock:
                mono_now = time.monotonic()
                mono_attempt = _weather_last_attempt.get(location_key)
                mono_rem = (
                    max(1, int(COOLDOWN_SECONDS - (mono_now - mono_attempt)))
                    if mono_attempt is not None and (mono_now - mono_attempt) < COOLDOWN_SECONDS
                    else 0
                )

                now_locked = datetime.now(timezone.utc)
                # Re-query cache and re-check inside lock for request coalescing
                cached_record = db.query(WeatherCache).filter(WeatherCache.location_key == location_key).first()
                db_rem = 0
                norm_f_locked = None
                if cached_record and cached_record.fetched_at:
                    norm_f_locked = normalize_utc_datetime(cached_record.fetched_at)
                    if norm_f_locked:
                        db_elapsed = (now_locked - norm_f_locked).total_seconds()
                        if 0 <= db_elapsed < COOLDOWN_SECONDS:
                            db_rem = max(1, int(COOLDOWN_SECONDS - db_elapsed))

                cooldown_rem_locked = max(mono_rem, db_rem)

                mono_elapsed = (mono_now - mono_attempt) if mono_attempt is not None else 999.0
                db_elapsed_val = (now_locked - norm_f_locked).total_seconds() if norm_f_locked else 999.0

                if (mono_elapsed < 5.0 or db_elapsed_val < 5.0) and cached_record:
                    # Concurrently coalesced request: use just-refreshed cache
                    elapsed_post = max(0.0, time.monotonic() - mono_attempt) if mono_attempt is not None else 0.0
                    cooldown_remaining_seconds = max(1, int(COOLDOWN_SECONDS - elapsed_post)) if elapsed_post < COOLDOWN_SECONDS else 0
                    try:
                        raw_data = json.loads(cached_record.payload_json)
                        fetched_at_utc = normalize_utc_datetime(cached_record.fetched_at)
                        weather_source = "open_meteo"
                        retrieval_status = "live_response"
                        freshness_status = "fresh"
                        refresh_status = "refreshed"
                    except Exception:
                        pass
                elif cooldown_rem_locked > 0:
                    refresh_status = "cooldown"
                    cooldown_remaining_seconds = cooldown_rem_locked
                else:
                    # Execute upstream request
                    _weather_last_attempt[location_key] = time.monotonic()
                    try:
                        async with httpx.AsyncClient(timeout=6.0) as client:
                            resp = await client.get(FORECAST_URL, params=params)
                            elapsed_post = max(0.0, time.monotonic() - _weather_last_attempt[location_key])
                            rem_cooldown = max(1, int(COOLDOWN_SECONDS - elapsed_post)) if elapsed_post < COOLDOWN_SECONDS else 0

                            if resp.status_code == 200:
                                parsed = resp.json()
                                if not isinstance(parsed, dict) or ("daily" not in parsed and "hourly" not in parsed):
                                    refresh_status = "invalid_response"
                                    cooldown_remaining_seconds = rem_cooldown
                                else:
                                    raw_data = parsed
                                    fetched_at_utc = now_locked
                                    weather_source = "open_meteo"
                                    retrieval_status = "live_response"
                                    freshness_status = "fresh"
                                    refresh_status = "refreshed"
                                    cooldown_remaining_seconds = rem_cooldown

                                    if cached_record:
                                        cached_record.payload_json = json.dumps(raw_data)
                                        cached_record.fetched_at = now_locked
                                    else:
                                        new_cache = WeatherCache(
                                            location_key=location_key,
                                            payload_json=json.dumps(raw_data),
                                            fetched_at=now_locked,
                                        )
                                        db.add(new_cache)
                                    db.commit()
                            elif resp.status_code in (500, 502, 503, 504):
                                refresh_status = "upstream_unavailable"
                                cooldown_remaining_seconds = rem_cooldown
                            else:
                                refresh_status = "invalid_response"
                                cooldown_remaining_seconds = rem_cooldown
                    except (httpx.TimeoutException, httpx.NetworkError):
                        elapsed_post = max(0.0, time.monotonic() - _weather_last_attempt[location_key])
                        refresh_status = "upstream_unavailable"
                        cooldown_remaining_seconds = max(1, int(COOLDOWN_SECONDS - elapsed_post)) if elapsed_post < COOLDOWN_SECONDS else 0
                    except json.JSONDecodeError:
                        elapsed_post = max(0.0, time.monotonic() - _weather_last_attempt[location_key])
                        refresh_status = "invalid_response"
                        cooldown_remaining_seconds = max(1, int(COOLDOWN_SECONDS - elapsed_post)) if elapsed_post < COOLDOWN_SECONDS else 0
                    except Exception as exc:
                        elapsed_post = max(0.0, time.monotonic() - _weather_last_attempt[location_key])
                        refresh_status = "upstream_unavailable"
                        cooldown_remaining_seconds = max(1, int(COOLDOWN_SECONDS - elapsed_post)) if elapsed_post < COOLDOWN_SECONDS else 0

    # 3. Fallback resolution if live data was not obtained
    if not raw_data:
        if cached_record:
            try:
                raw_data = json.loads(cached_record.payload_json)
                fetched_at = normalize_utc_datetime(cached_record.fetched_at)
                fetched_at_utc = fetched_at
                weather_source = "open_meteo"
                age = (now - fetched_at).total_seconds() if fetched_at else 0.0
                if age < CACHE_TTL_HOURS * 3600:
                    retrieval_status = "cache_hit"
                    freshness_status = "cached"
                else:
                    retrieval_status = "stale_cache_fallback"
                    freshness_status = "stale"
            except Exception:
                raw_data = _build_synthetic_forecast()
                fetched_at_utc = None
                weather_source = "synthetic_baseline"
                retrieval_status = "synthetic_fallback"
                freshness_status = "estimated"
        else:
            raw_data = _build_synthetic_forecast()
            fetched_at_utc = None
            weather_source = "synthetic_baseline"
            retrieval_status = "synthetic_fallback"
            freshness_status = "estimated"

    age_seconds = (
        max(0.0, round((now - fetched_at_utc).total_seconds(), 1))
        if fetched_at_utc is not None
        else None
    )

    # 4. Extract 72-hour metrics
    daily = raw_data.get("daily", {})
    hourly = raw_data.get("hourly", {})
    precipitation_sums = daily.get("precipitation_sum", [])

    # Hourly rolling 72-hour rainfall calculation (with null filtering)
    hourly_precip = hourly.get("precipitation", [])
    valid_precip = [float(p) for p in hourly_precip[:72] if p is not None and isinstance(p, (int, float))]
    if valid_precip:
        rain_72h_mm = round(sum(valid_precip), 2)
    else:
        # Fallback to daily precipitation sum if hourly is unavailable
        valid_daily = [float(p) for p in precipitation_sums[:3] if p is not None and isinstance(p, (int, float))]
        rain_72h_mm = round(sum(valid_daily), 2) if valid_daily else 0.0

    rain_probs = daily.get("precipitation_probability_max", [])
    valid_probs = [float(p) for p in rain_probs[:3] if p is not None and isinstance(p, (int, float))]
    max_rain_prob_pct = float(max(valid_probs)) if valid_probs else 0.0

    # Hourly soil moisture with null filtering — returns None when unmeasured (no artificial defaults)
    soil_moistures = hourly.get("soil_moisture_0_to_7cm", [])
    valid_sm = [float(v) for v in soil_moistures[:72] if v is not None and isinstance(v, (int, float))]
    if valid_sm:
        soil_moisture_avg: Optional[float] = round(sum(valid_sm) / len(valid_sm), 3)
    else:
        soil_moisture_avg = None

    # Hourly relative humidity with null filtering and safe fallback
    humidities = hourly.get("relative_humidity_2m", [])
    valid_rh = [float(h) for h in humidities[:72] if h is not None and isinstance(h, (int, float))]
    max_humidity = round(float(max(valid_rh)), 1) if valid_rh else 60.0

    # 5. Deterministic risk assessment
    assessment = classify_weather_risk(
        rain_72h_mm=rain_72h_mm,
        max_rain_prob_pct=max_rain_prob_pct,
        soil_moisture=soil_moisture_avg,
        perishability_tier=perishability_tier,
        max_humidity_pct=max_humidity,
    )

    # 6. Format 7-day daily forecast strip
    dates = daily.get("time", [])
    temp_maxs = daily.get("temperature_2m_max", [])
    temp_mins = daily.get("temperature_2m_min", [])
    daily_forecast = []
    for i in range(min(7, len(dates))):
        daily_forecast.append({
            "date": dates[i],
            "temp_max": temp_maxs[i] if i < len(temp_maxs) else 30.0,
            "temp_min": temp_mins[i] if i < len(temp_mins) else 20.0,
            "precipitation_mm": precipitation_sums[i] if i < len(precipitation_sums) else 0.0,
            "rain_prob_pct": rain_probs[i] if i < len(rain_probs) else 0.0,
            "weather_code": daily.get("weather_code", [0] * 7)[i] if i < len(daily.get("weather_code", [])) else 0,
        })

    return {
        "risk_level": assessment.risk_level,
        "rain_72h_mm": assessment.rain_72h_mm,
        "max_rain_prob_pct": assessment.max_rain_prob_pct,
        "soil_moisture_avg": assessment.soil_moisture,
        "soil_moisture_available": assessment.soil_moisture is not None,
        "headline": assessment.headline,
        "description": assessment.description,
        "recommended_action": assessment.recommended_action,
        "daily_forecast": daily_forecast,
        "fetched_at": fetched_at_utc.isoformat() if fetched_at_utc is not None else None,
        "data_source": weather_source,
        "freshness_status": freshness_status,
        "retrieval_status": retrieval_status,
        "data_age_seconds": age_seconds,
        "refresh_status": refresh_status,
        "cooldown_remaining_seconds": cooldown_remaining_seconds,
    }
