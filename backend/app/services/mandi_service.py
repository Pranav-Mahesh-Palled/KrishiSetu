"""AGMARKNET Mandi Price Fetching & Arbitrage Integration Service for KrishiSetu.

Provides:
- Proximity-based APMC Mandi candidate selection (150 km radius or closest 5)
- Live AGMARKNET API fetching via OGD India (data.gov.in) with 3-hour SQLite caching
- Seamless automatic fallback to verified_snapshot records
- Execution of deterministic transport and spoilage arbitrage engine
"""

import asyncio
import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import httpx
from sqlalchemy.orm import Session

from backend.app.config import DATA_GOV_API_KEY
from backend.app.models import CropProfile, MandiPricesCache
from backend.app.seed import MANDI_COORDINATES, MANDI_SNAPSHOT_DATA
from backend.app.services.arbitrage_engine import (
    MandiArbitrageResult,
    MandiCandidate,
    calculate_mandi_arbitrage,
    calculate_road_distance_km,
)

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 3
COOLDOWN_SECONDS = 60
AGMARKNET_RESOURCE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
AGMARKNET_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"

# In-memory concurrency locks and rate-limiting trackers per commodity/candidate scope
_mandi_scope_locks: Dict[str, asyncio.Lock] = {}
_mandi_last_attempt: Dict[str, float] = {}


class AgmarknetFetchResult(list):
    """Subclass of list carrying upstream fetch metadata for status distinction."""
    def __init__(
        self,
        records: Optional[List[Dict[str, Any]]] = None,
        status: str = "ok",
        http_status: Optional[int] = 200,
    ):
        super().__init__(records or [])
        self.status = status
        self.http_status = http_status


def _get_mandi_scope_lock(scope_key: str) -> asyncio.Lock:
    """Retrieves or creates an asyncio.Lock for a specific commodity & candidate scope."""
    if scope_key not in _mandi_scope_locks:
        _mandi_scope_locks[scope_key] = asyncio.Lock()
    return _mandi_scope_locks[scope_key]


def clear_mandi_cooldown_trackers() -> None:
    """Utility for test suites to reset in-memory attempt timestamps and locks."""
    _mandi_last_attempt.clear()
    _mandi_scope_locks.clear()


def get_latest_mandi_fetched_at(
    mandis: List[Dict[str, Any]],
    commodity: str,
    db: Session,
) -> Optional[datetime]:
    """Finds the most recent fetched_at timestamp across candidate mandis for a commodity."""
    market_names = [m["market"] for m in mandis]
    records = (
        db.query(MandiPricesCache.fetched_at)
        .filter(
            MandiPricesCache.market.in_(market_names),
            MandiPricesCache.commodity == commodity,
            MandiPricesCache.source == "live_api",
        )
        .all()
    )
    timestamps = [normalize_utc_datetime(r[0]) for r in records if r[0] is not None]
    valid_ts = [t for t in timestamps if t is not None]
    return max(valid_ts) if valid_ts else None

# Explicit HTTP headers for OGD India gateway compliance
OGD_REQUEST_HEADERS = {
    "User-Agent": "KrishiSetu/1.0",
    "Accept": "application/json",
}

# Curated reference directory of Karnataka, Maharashtra & neighboring APMC Mandis
REFERENCE_MANDIS: List[Dict[str, Any]] = [
    # Belagavi Cluster
    {"market": "Belagavi APMC", "district": "Belagavi", "state": "Karnataka", "latitude": 15.8500, "longitude": 74.5000},
    {"market": "Bailhongal APMC", "district": "Belagavi", "state": "Karnataka", "latitude": 15.8167, "longitude": 74.8667},
    {"market": "Dharwad APMC", "district": "Dharwad", "state": "Karnataka", "latitude": 15.4589, "longitude": 75.0078},
    {"market": "Hubli APMC", "district": "Dharwad", "state": "Karnataka", "latitude": 15.3647, "longitude": 75.1240},
    {"market": "Kolhapur APMC", "district": "Kolhapur", "state": "Maharashtra", "latitude": 16.7050, "longitude": 74.2433},

    # Kolar Cluster
    {"market": "Kolar APMC", "district": "Kolar", "state": "Karnataka", "latitude": 13.1367, "longitude": 78.1291},
    {"market": "Malur APMC", "district": "Kolar", "state": "Karnataka", "latitude": 13.0039, "longitude": 77.9400},
    {"market": "Chintamani APMC", "district": "Chikkaballapura", "state": "Karnataka", "latitude": 13.4000, "longitude": 78.0500},
    {"market": "Bengaluru (Yeshwanthpur) APMC", "district": "Bangalore", "state": "Karnataka", "latitude": 13.0280, "longitude": 77.5400},
    {"market": "Madanapalle APMC", "district": "Annamayya", "state": "Andhra Pradesh", "latitude": 13.5500, "longitude": 78.5000},

    # Nashik Cluster
    {"market": "Nashik APMC", "district": "Nashik", "state": "Maharashtra", "latitude": 19.9975, "longitude": 73.7898},
    {"market": "Pimpalgaon APMC", "district": "Nashik", "state": "Maharashtra", "latitude": 20.1700, "longitude": 73.9800},
    {"market": "Lasalgaon APMC", "district": "Nashik", "state": "Maharashtra", "latitude": 20.1472, "longitude": 74.2267},
    {"market": "Yeola APMC", "district": "Nashik", "state": "Maharashtra", "latitude": 20.0400, "longitude": 74.4800},
    {"market": "Kalwan APMC", "district": "Nashik", "state": "Maharashtra", "latitude": 20.4900, "longitude": 74.0200},

    # Haveri Cluster
    {"market": "Haveri APMC", "district": "Haveri", "state": "Karnataka", "latitude": 14.7952, "longitude": 75.3992},
    {"market": "Byadgi APMC", "district": "Haveri", "state": "Karnataka", "latitude": 14.6800, "longitude": 75.4800},
    {"market": "Ranebennur APMC", "district": "Haveri", "state": "Karnataka", "latitude": 14.6200, "longitude": 75.6200},
    {"market": "Davanagere APMC", "district": "Davanagere", "state": "Karnataka", "latitude": 14.4644, "longitude": 75.9218},

    # Pune Cluster
    {"market": "Pune APMC (Gultekdi)", "district": "Pune", "state": "Maharashtra", "latitude": 18.5204, "longitude": 73.8567},
    {"market": "Khed (Chakan) APMC", "district": "Pune", "state": "Maharashtra", "latitude": 18.7600, "longitude": 73.8500},
    {"market": "Shirur APMC", "district": "Pune", "state": "Maharashtra", "latitude": 18.8260, "longitude": 74.3780},
    {"market": "Manchar APMC", "district": "Pune", "state": "Maharashtra", "latitude": 19.0000, "longitude": 73.9400},
    {"market": "Junnar APMC", "district": "Pune", "state": "Maharashtra", "latitude": 19.2000, "longitude": 73.8800},
]

# Mapping of APMC reference names to known AGMARKNET market and town aliases
MANDI_ALIASES: Dict[str, List[str]] = {
    "Belagavi APMC": ["belagavi", "belgaum"],
    "Bailhongal APMC": ["bailhongal", "bailhongla"],
    "Dharwad APMC": ["dharwad", "dharwar"],
    "Hubli APMC": ["hubli", "hubballi", "amargol"],
    "Kolhapur APMC": ["kolhapur", "shahu market yard"],
    "Kolar APMC": ["kolar"],
    "Malur APMC": ["malur"],
    "Chintamani APMC": ["chintamani"],
    "Bengaluru (Yeshwanthpur) APMC": ["bengaluru", "bangalore", "yeshwanthpur", "yeswantpur"],
    "Madanapalle APMC": ["madanapalle", "madanapalli"],
    "Nashik APMC": ["nashik", "nasik"],
    "Pimpalgaon APMC": ["pimpalgaon", "pimpalgaon baswant"],
    "Lasalgaon APMC": ["lasalgaon"],
    "Yeola APMC": ["yeola", "yevla"],
    "Kalwan APMC": ["kalwan"],
    "Haveri APMC": ["haveri"],
    "Byadgi APMC": ["byadgi", "byadagi"],
    "Ranebennur APMC": ["ranebennur", "ranibennur"],
    "Davanagere APMC": ["davanagere", "davangere"],
    "Pune APMC (Gultekdi)": ["pune", "gultekdi"],
    "Khed (Chakan) APMC": ["khed", "chakan"],
    "Shirur APMC": ["shirur"],
    "Manchar APMC": ["manchar"],
    "Junnar APMC": ["junnar", "narayangaon", "alephata"],
}


def match_mandi_name(rec_market: str, ref_market: str) -> bool:
    """Robust bidirectional matching of AGMARKNET market names against reference APMC mandis."""
    if not rec_market or not ref_market:
        return False
    rec_clean = rec_market.lower().replace("apmc", "").replace("market", "").strip(" ()-")
    ref_clean = ref_market.lower().replace("apmc", "").replace("market", "").strip(" ()-")

    if rec_clean in ref_clean or ref_clean in rec_clean:
        return True

    aliases = MANDI_ALIASES.get(ref_market, [])
    for alias in aliases:
        if alias in rec_clean or rec_clean in alias:
            return True
    return False


def select_candidate_mandis(origin_lat: float, origin_lon: float, max_count: int = 5) -> List[Dict[str, Any]]:
    """Selects the nearest APMC mandis strictly within 150 km road distance.

    Returns an empty list if no registered APMC mandis exist within 150 km,
    preventing spurious comparisons across hundreds of kilometers.
    """
    mandis_with_dist = []
    for m in REFERENCE_MANDIS:
        dist_km = calculate_road_distance_km(origin_lat, origin_lon, m["latitude"], m["longitude"])
        mandis_with_dist.append({**m, "road_dist_km": dist_km})

    mandis_with_dist.sort(key=lambda x: x["road_dist_km"])

    # Strictly enforce 150 km radius limit
    within_radius = [m for m in mandis_with_dist if m["road_dist_km"] <= 150.0]
    return within_radius[:max_count]


async def fetch_live_agmarknet_records(
    commodity_name: str,
    state: Optional[str] = None,
    district: Optional[str] = None,
    max_records: int = 500,
    page_size: int = 100,
) -> AgmarknetFetchResult:
    """Queries live data.gov.in AGMARKNET API for commodity daily prices with pagination.

    Supports OGD India pagination via 'limit' and 'offset', gracefully handling upstream timeouts,
    empty pages, and partial record batches without failing the pipeline.
    """
    all_records: List[Dict[str, Any]] = []
    current_offset = 0
    fetch_status: str = "ok"
    last_http_status: Optional[int] = 200

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=OGD_REQUEST_HEADERS) as client:
            while len(all_records) < max_records:
                params: Dict[str, Any] = {
                    "api-key": DATA_GOV_API_KEY,
                    "format": "json",
                    "limit": page_size,
                    "offset": current_offset,
                    "filters[commodity]": commodity_name,
                }
                if state:
                    params["filters[state]"] = state
                if district:
                    params["filters[district]"] = district

                resp = await client.get(AGMARKNET_RESOURCE_URL, params=params)
                last_http_status = resp.status_code
                if resp.status_code != 200:
                    logger.warning(
                        f"Live AGMARKNET API returned status {resp.status_code} at offset {current_offset}"
                    )
                    if resp.status_code in (500, 502, 503, 504):
                        fetch_status = "upstream_unavailable"
                    else:
                        fetch_status = "invalid_response"
                    break

                try:
                    data = resp.json()
                except Exception:
                    fetch_status = "invalid_response"
                    break

                page_records = data.get("records", [])
                if not page_records:
                    # Reached end of records
                    break

                all_records.extend(page_records)

                # Check total available from OGD metadata
                total_val = data.get("total")
                total_count = None
                if total_val is not None:
                    try:
                        total_count = int(total_val)
                    except (ValueError, TypeError):
                        pass

                # If received fewer records than page_size or reached total count, stop paginating
                if len(page_records) < page_size:
                    break
                if total_count is not None and len(all_records) >= total_count:
                    break

                current_offset += len(page_records)

    except Exception as exc:
        logger.info(
            f"Live AGMARKNET API fetch interrupted or timed out at offset {current_offset}: {type(exc).__name__}. "
            f"Retaining {len(all_records)} records successfully retrieved."
        )
        if isinstance(exc, json.JSONDecodeError):
            fetch_status = "invalid_response"
        else:
            fetch_status = "upstream_unavailable"

    final_status = "ok" if all_records else fetch_status
    return AgmarknetFetchResult(all_records, status=final_status, http_status=last_http_status)


def normalize_utc_datetime(dt: Optional[Union[datetime, str]]) -> Optional[datetime]:
    """Ensures datetime is timezone-aware UTC without accidental double conversion.

    Safely handles ISO strings, naive datetimes, and aware datetimes.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_arrival_date(arrival_date_str: Optional[str]) -> Optional[date]:
    """Safely parses arrival_date strings in DD/MM/YYYY or YYYY-MM-DD or other formats into a date object.

    Returns None if arrival_date_str is None, empty, or unparseable.
    """
    if not arrival_date_str:
        return None
    clean = arrival_date_str.strip()
    if not clean:
        return None

    for fmt in (
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y.%m.%d",
    ):
        try:
            return datetime.strptime(clean, fmt).date()
        except ValueError:
            continue

    return None


def select_latest_mandi_record(records: List[MandiPricesCache]) -> Optional[MandiPricesCache]:
    """Chronologically selects the latest MandiPricesCache record.

    Prioritizes:
    1. Latest parsed trading date (supporting mixed DD/MM/YYYY and YYYY-MM-DD formats).
    2. Latest fetched_at timestamp for identical trading dates (using POSIX numeric seconds
       for 100% type-safe comparisons between naive, aware, and None timestamps).
    3. Highest primary key id as deterministic final tie-breaker.
    Records with missing or unparseable dates are sorted after valid dates.
    """
    if not records:
        return None

    def sort_key(rec: MandiPricesCache):
        parsed_d = parse_arrival_date(rec.arrival_date) or date.min
        norm_fetch = normalize_utc_datetime(rec.fetched_at)
        fetch_ts = norm_fetch.timestamp() if norm_fetch is not None else float("-inf")
        rec_id = rec.id or 0
        return (parsed_d, fetch_ts, rec_id)

    return max(records, key=sort_key)


def get_fallback_snapshot_price(
    market: str,
    commodity: str,
    db: Session,
) -> Optional[MandiPricesCache]:
    """Retrieves the latest verified snapshot or live_api record from SQLite for an exact market and commodity.

    Prioritizes:
    1. Latest parsed AGMARKNET arrival_date (chronological, supporting DD/MM/YYYY and YYYY-MM-DD).
    2. Latest fetched_at timestamp for records representing the same trading date.
    Never falls back to unrelated markets to prevent misrepresenting prices as verified.

    Conservative Data Integrity Guard:
    Records with missing or unparseable arrival dates are strictly excluded from verified quotations
    to prevent corrupt or undated data from entering verified arbitrage calculations.
    """
    records = (
        db.query(MandiPricesCache)
        .filter(
            MandiPricesCache.market == market,
            MandiPricesCache.commodity.ilike(f"%{commodity}%"),
            MandiPricesCache.source.in_(["verified_snapshot", "live_api"]),
        )
        .all()
    )
    # Strictly require a valid parseable arrival date for verified quotations
    valid_records = [r for r in records if parse_arrival_date(r.arrival_date) is not None]
    return select_latest_mandi_record(valid_records)


def get_cached_or_benchmark_price(
    market: str,
    commodity: str,
    db: Session,
) -> Optional[MandiPricesCache]:
    """Retrieves verified price if available; otherwise retrieves estimated benchmark for the market.

    Prioritizes:
    1. Latest verified price (chronologically, strictly requiring a valid arrival date).
    2. Latest estimated benchmark (chronologically).
    """
    verified = get_fallback_snapshot_price(market, commodity, db)
    if verified:
        return verified

    benchmark_records = (
        db.query(MandiPricesCache)
        .filter(
            MandiPricesCache.market == market,
            MandiPricesCache.commodity.ilike(f"%{commodity}%"),
            MandiPricesCache.source == "estimated_benchmark",
        )
        .all()
    )
    return select_latest_mandi_record(benchmark_records)


async def get_mandi_candidates_with_prices(
    origin_lat: float,
    origin_lon: float,
    crop: CropProfile,
    db: Session,
    force_refresh: bool = False,
    return_meta: bool = False,
) -> Union[List[MandiCandidate], Tuple[List[MandiCandidate], Dict[str, Any]]]:
    """Retrieves candidates, fetches live or cached prices, and falls back to snapshot data."""
    selected_mandis = select_candidate_mandis(origin_lat, origin_lon, max_count=5)
    now = datetime.now(timezone.utc)
    commodity = crop.agmarknet_commodity

    if not selected_mandis:
        refresh_status = "no_matching_records" if force_refresh else "not_requested"
        cooldown_remaining_seconds = 0
        meta = {
            "refresh_status": refresh_status,
            "cooldown_remaining_seconds": cooldown_remaining_seconds,
        }
        return ([], meta) if return_meta else []

    scope_key = f"{commodity.lower()}:{','.join(sorted(m['market'] for m in selected_mandis))}"
    cached_live: Dict[str, MandiPricesCache] = {}
    cached_live_status: Dict[str, str] = {}  # 'cache_hit' vs 'live_response'

    refresh_status: str = "not_requested"
    cooldown_remaining_seconds: int = 0

    if not force_refresh:
        # Standard workflow: check 3h cache TTL
        refresh_status = "not_requested"
        cooldown_remaining_seconds = 0

        for m in selected_mandis:
            live_records = (
                db.query(MandiPricesCache)
                .filter(
                    MandiPricesCache.market == m["market"],
                    MandiPricesCache.commodity == commodity,
                    MandiPricesCache.source == "live_api",
                )
                .all()
            )
            valid_live = [r for r in live_records if parse_arrival_date(r.arrival_date) is not None]
            latest_live = select_latest_mandi_record(valid_live)
            if latest_live:
                fetched_at = normalize_utc_datetime(latest_live.fetched_at)
                if fetched_at and (now - fetched_at).total_seconds() < CACHE_TTL_HOURS * 3600:
                    cached_live[m["market"]] = latest_live
                    cached_live_status[m["market"]] = "cache_hit"

        # If some mandis lack fresh live cache, attempt live fetch from data.gov.in
        if len(cached_live) < len(selected_mandis):
            target_states = list(dict.fromkeys(m["state"] for m in selected_mandis if m.get("state")))
            live_records_fetched: List[Dict[str, Any]] = []

            for st in target_states:
                st_records = await fetch_live_agmarknet_records(commodity, state=st)
                if st_records:
                    live_records_fetched.extend(st_records)

            if not live_records_fetched:
                live_records_fetched = await fetch_live_agmarknet_records(commodity)

            for rec in live_records_fetched:
                rec_market = rec.get("market") or rec.get("market_name", "")
                for m in selected_mandis:
                    if rec_market and match_mandi_name(rec_market, m["market"]):
                        try:
                            min_p = float(rec.get("min_price", 0))
                            max_p = float(rec.get("max_price", 0))
                            modal_p = float(rec.get("modal_price", 0))
                            arr_date = rec.get("arrival_date") or now.strftime("%Y-%m-%d")

                            entry = MandiPricesCache(
                                state=rec.get("state", m["state"]),
                                district=rec.get("district", m["district"]),
                                market=m["market"],
                                commodity=commodity,
                                variety=rec.get("variety", "Standard"),
                                min_price=min_p,
                                max_price=max_p,
                                modal_price=modal_p,
                                arrival_date=arr_date,
                                source="live_api",
                                dataset_id=AGMARKNET_RESOURCE_ID,
                                fetched_at=now,
                            )
                            db.add(entry)
                            db.commit()
                            cached_live[m["market"]] = entry
                            cached_live_status[m["market"]] = "live_response"
                        except Exception as e:
                            logger.warning(f"Error parsing live AGMARKNET record: {e}")

    else:
        # Manual refresh requested: evaluate 60s cooldown per commodity & candidate geography
        mono_now = time.monotonic()
        mono_attempt = _mandi_last_attempt.get(scope_key)
        mono_rem = (
            max(1, int(COOLDOWN_SECONDS - (mono_now - mono_attempt)))
            if mono_attempt is not None and (mono_now - mono_attempt) < COOLDOWN_SECONDS
            else 0
        )

        last_fetched = get_latest_mandi_fetched_at(selected_mandis, commodity, db)
        db_rem = 0
        if last_fetched:
            norm_f = normalize_utc_datetime(last_fetched)
            if norm_f:
                db_elapsed = (now - norm_f).total_seconds()
                if 0 <= db_elapsed < COOLDOWN_SECONDS:
                    db_rem = max(1, int(COOLDOWN_SECONDS - db_elapsed))

        cooldown_remaining_seconds = max(mono_rem, db_rem)

        if cooldown_remaining_seconds > 0:
            # Under cooldown: reject repeated upstream request, retain existing cache
            refresh_status = "cooldown"
            # Populate cached_live from SQLite if available
            for m in selected_mandis:
                live_records = (
                    db.query(MandiPricesCache)
                    .filter(
                        MandiPricesCache.market == m["market"],
                        MandiPricesCache.commodity == commodity,
                        MandiPricesCache.source == "live_api",
                    )
                    .all()
                )
                valid_live = [r for r in live_records if parse_arrival_date(r.arrival_date) is not None]
                latest_live = select_latest_mandi_record(valid_live)
                if latest_live:
                    cached_live[m["market"]] = latest_live
                    cached_live_status[m["market"]] = "cache_hit"
        else:
            # Outside cooldown: acquire lock for this scope to prevent concurrent duplicate upstream calls
            lock = _get_mandi_scope_lock(scope_key)
            async with lock:
                mono_now = time.monotonic()
                mono_attempt = _mandi_last_attempt.get(scope_key)
                mono_rem = (
                    max(1, int(COOLDOWN_SECONDS - (mono_now - mono_attempt)))
                    if mono_attempt is not None and (mono_now - mono_attempt) < COOLDOWN_SECONDS
                    else 0
                )

                now_locked = datetime.now(timezone.utc)
                last_fetched = get_latest_mandi_fetched_at(selected_mandis, commodity, db)
                db_rem = 0
                norm_last_fetched = None
                if last_fetched:
                    norm_last_fetched = normalize_utc_datetime(last_fetched)
                    if norm_last_fetched:
                        db_elapsed = (now_locked - norm_last_fetched).total_seconds()
                        if 0 <= db_elapsed < COOLDOWN_SECONDS:
                            db_rem = max(1, int(COOLDOWN_SECONDS - db_elapsed))

                cooldown_rem_locked = max(mono_rem, db_rem)

                mono_elapsed = (mono_now - mono_attempt) if mono_attempt is not None else 999.0
                db_elapsed_val = (now_locked - norm_last_fetched).total_seconds() if norm_last_fetched else 999.0

                if (mono_elapsed < 5.0 or db_elapsed_val < 5.0) and last_fetched is not None:
                    # Concurrently coalesced request: use freshly updated cache
                    refresh_status = "refreshed"
                    cooldown_remaining_seconds = cooldown_rem_locked
                    for m in selected_mandis:
                        live_records = (
                            db.query(MandiPricesCache)
                            .filter(
                                MandiPricesCache.market == m["market"],
                                MandiPricesCache.commodity == commodity,
                                MandiPricesCache.source == "live_api",
                            )
                            .all()
                        )
                        valid_live = [r for r in live_records if parse_arrival_date(r.arrival_date) is not None]
                        latest_live = select_latest_mandi_record(valid_live)
                        if latest_live:
                            cached_live[m["market"]] = latest_live
                            cached_live_status[m["market"]] = "live_response"
                elif cooldown_rem_locked > 0:
                    refresh_status = "cooldown"
                    cooldown_remaining_seconds = cooldown_rem_locked
                    for m in selected_mandis:
                        live_records = (
                            db.query(MandiPricesCache)
                            .filter(
                                MandiPricesCache.market == m["market"],
                                MandiPricesCache.commodity == commodity,
                                MandiPricesCache.source == "live_api",
                            )
                            .all()
                        )
                        valid_live = [r for r in live_records if parse_arrival_date(r.arrival_date) is not None]
                        latest_live = select_latest_mandi_record(valid_live)
                        if latest_live:
                            cached_live[m["market"]] = latest_live
                            cached_live_status[m["market"]] = "cache_hit"
                else:
                    # Execute upstream query
                    _mandi_last_attempt[scope_key] = time.monotonic()
                    target_states = list(dict.fromkeys(m["state"] for m in selected_mandis if m.get("state")))
                    live_records_fetched = []
                    last_error_status = None

                    try:
                        for st in target_states:
                            st_records = await fetch_live_agmarknet_records(commodity, state=st)
                            st_status = getattr(st_records, "status", None)
                            if st_status in ("upstream_unavailable", "invalid_response"):
                                last_error_status = st_status
                            elif st_records:
                                live_records_fetched.extend(st_records)

                        if not live_records_fetched and not last_error_status:
                            unscoped = await fetch_live_agmarknet_records(commodity)
                            u_status = getattr(unscoped, "status", None)
                            if u_status in ("upstream_unavailable", "invalid_response"):
                                last_error_status = u_status
                            elif unscoped:
                                live_records_fetched.extend(unscoped)
                    except (httpx.TimeoutException, httpx.NetworkError):
                        last_error_status = "upstream_unavailable"
                    except json.JSONDecodeError:
                        last_error_status = "invalid_response"
                    except Exception as exc:
                        exc_name = type(exc).__name__
                        if "503" in str(exc) or "timeout" in str(exc).lower() or "Timeout" in exc_name:
                            last_error_status = "upstream_unavailable"
                        else:
                            last_error_status = "upstream_unavailable"

                    matched_count = 0
                    if live_records_fetched:
                        for rec in live_records_fetched:
                            rec_market = rec.get("market") or rec.get("market_name", "")
                            for m in selected_mandis:
                                if rec_market and match_mandi_name(rec_market, m["market"]):
                                    try:
                                        min_p = float(rec.get("min_price", 0))
                                        max_p = float(rec.get("max_price", 0))
                                        modal_p = float(rec.get("modal_price", 0))
                                        arr_date = rec.get("arrival_date") or now_locked.strftime("%Y-%m-%d")

                                        entry = MandiPricesCache(
                                            state=rec.get("state", m["state"]),
                                            district=rec.get("district", m["district"]),
                                            market=m["market"],
                                            commodity=commodity,
                                            variety=rec.get("variety", "Standard"),
                                            min_price=min_p,
                                            max_price=max_p,
                                            modal_price=modal_p,
                                            arrival_date=arr_date,
                                            source="live_api",
                                            dataset_id=AGMARKNET_RESOURCE_ID,
                                            fetched_at=now_locked,
                                        )
                                        db.add(entry)
                                        cached_live[m["market"]] = entry
                                        cached_live_status[m["market"]] = "live_response"
                                        matched_count += 1
                                    except Exception as e:
                                        logger.warning(f"Error parsing live AGMARKNET record: {e}")

                        if matched_count > 0:
                            db.commit()

                    elapsed_post = max(0.0, time.monotonic() - _mandi_last_attempt[scope_key])
                    rem_cooldown = max(1, int(COOLDOWN_SECONDS - elapsed_post)) if elapsed_post < COOLDOWN_SECONDS else 0

                    if matched_count > 0:
                        refresh_status = "refreshed"
                        cooldown_remaining_seconds = rem_cooldown
                    elif last_error_status:
                        refresh_status = last_error_status
                        cooldown_remaining_seconds = rem_cooldown
                    else:
                        refresh_status = "no_matching_records"
                        cooldown_remaining_seconds = rem_cooldown

    # 3. Assemble candidates using either live_api or verified_snapshot fallback
    candidates: List[MandiCandidate] = []
    for m in selected_mandis:
        market_name = m["market"]
        if market_name in cached_live:
            item = cached_live[market_name]
            retrieval_status = cached_live_status.get(market_name, "cache_hit")
            fetched_at_utc = normalize_utc_datetime(item.fetched_at)
            age_seconds = (
                max(0.0, round((now - fetched_at_utc).total_seconds(), 1))
                if fetched_at_utc
                else None
            )
            freshness_status = "fresh" if retrieval_status == "live_response" else "cached"

            candidates.append(
                MandiCandidate(
                    market=market_name,
                    district=m["district"],
                    state=m["state"],
                    latitude=m["latitude"],
                    longitude=m["longitude"],
                    modal_price=item.modal_price,
                    min_price=item.min_price,
                    max_price=item.max_price,
                    arrival_date=item.arrival_date,
                    source="live_api",
                    variety=item.variety or "Standard",
                    is_benchmark=False,
                    dataset_id=item.dataset_id or AGMARKNET_RESOURCE_ID,
                    fetched_at=fetched_at_utc,
                    freshness_status=freshness_status,
                    retrieval_status=retrieval_status,
                    data_age_seconds=age_seconds,
                )
            )
        else:
            # Fall back to verified price if available, or illustrative estimated benchmark
            cached_item = get_cached_or_benchmark_price(market_name, commodity, db)
            if cached_item:
                is_bench = (cached_item.source == "estimated_benchmark")
                fetched_at_utc = normalize_utc_datetime(cached_item.fetched_at)

                if is_bench:
                    freshness_status = "estimated"
                    retrieval_status = "benchmark"
                    cand_fetched_at = None
                    age_seconds = None
                elif cached_item.source == "live_api":
                    freshness_status = "stale"
                    retrieval_status = "stale_cache_fallback"
                    cand_fetched_at = fetched_at_utc
                    age_seconds = (
                        max(0.0, round((now - fetched_at_utc).total_seconds(), 1))
                        if fetched_at_utc
                        else None
                    )
                elif cached_item.source == "verified_snapshot":
                    cand_fetched_at = fetched_at_utc
                    age_seconds = (
                        max(0.0, round((now - fetched_at_utc).total_seconds(), 1))
                        if fetched_at_utc
                        else None
                    )
                    freshness_status = "cached" if (age_seconds is not None and age_seconds < CACHE_TTL_HOURS * 3600) else "stale"
                    retrieval_status = "snapshot_fallback"
                else:
                    cand_fetched_at = fetched_at_utc
                    age_seconds = (
                        max(0.0, round((now - fetched_at_utc).total_seconds(), 1))
                        if fetched_at_utc
                        else None
                    )
                    freshness_status = "stale"
                    retrieval_status = "cache_hit"

                candidates.append(
                    MandiCandidate(
                        market=market_name,
                        district=m["district"],
                        state=m["state"],
                        latitude=m["latitude"],
                        longitude=m["longitude"],
                        modal_price=cached_item.modal_price,
                        min_price=cached_item.min_price,
                        max_price=cached_item.max_price,
                        arrival_date=cached_item.arrival_date,
                        source=cached_item.source,
                        variety=cached_item.variety or ("Estimated Benchmark" if is_bench else "Standard"),
                        is_benchmark=is_bench,
                        dataset_id=None if is_bench else (cached_item.dataset_id or AGMARKNET_RESOURCE_ID),
                        fetched_at=cand_fetched_at,
                        freshness_status=freshness_status,
                        retrieval_status=retrieval_status,
                        data_age_seconds=age_seconds,
                    )
                )
            else:
                # Default estimated benchmark for crops/markets without cached records
                base_modal = 2000.0
                candidates.append(
                    MandiCandidate(
                        market=market_name,
                        district=m["district"],
                        state=m["state"],
                        latitude=m["latitude"],
                        longitude=m["longitude"],
                        modal_price=base_modal,
                        min_price=base_modal - 200.0,
                        max_price=base_modal + 200.0,
                        arrival_date=now.strftime("%Y-%m-%d"),
                        source="estimated_benchmark",
                        variety="Estimated Benchmark",
                        is_benchmark=True,
                        dataset_id=None,
                        fetched_at=None,
                        freshness_status="estimated",
                        retrieval_status="synthetic_fallback",
                        data_age_seconds=None,
                    )
                )

    refresh_meta = {
        "refresh_status": refresh_status,
        "cooldown_remaining_seconds": cooldown_remaining_seconds,
    }
    if return_meta:
        return candidates, refresh_meta
    return candidates


async def get_mandi_arbitrage_analysis(
    origin_lat: float,
    origin_lon: float,
    crop: CropProfile,
    quantity_quintals: float,
    db: Session,
    force_refresh: bool = False,
    return_meta: bool = False,
) -> Union[List[MandiArbitrageResult], Tuple[List[MandiArbitrageResult], Dict[str, Any]]]:
    """Finds target mandis, retrieves prices, and executes the deterministic arbitrage engine."""
    candidates, refresh_meta = await get_mandi_candidates_with_prices(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        crop=crop,
        db=db,
        force_refresh=force_refresh,
        return_meta=True,
    )
    results = calculate_mandi_arbitrage(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        quantity_quintals=quantity_quintals,
        mandis=candidates,
        perishability_tier=crop.perishability_tier,
        base_transport_per_km_qtl=crop.base_transport_per_km_qtl,
    )
    if return_meta:
        return results, refresh_meta
    return results
